#!/usr/bin/env python3
"""
kb_indexer.py — Living Atlas KB indexer

Reads config/repos.yml, clones/updates repos, indexes content into ChromaDB.

Usage:
  python3 scripts/kb_indexer.py --tier1          # index tier1 repos only
  python3 scripts/kb_indexer.py --all            # index all repos
  python3 scripts/kb_indexer.py --repo ORG/NAME  # index a single repo
"""

import argparse
import fnmatch
import logging
import os
import sys
from pathlib import Path

import chromadb
import yaml
from chromadb.utils import embedding_functions
from git import InvalidGitRepositoryError, Repo

# ── Config ────────────────────────────────────────────────────────────────────

KB_HOME = Path(os.environ.get("KB_HOME", Path(__file__).parent.parent))
REPOS_DIR = KB_HOME / "repos"
# Deploy layout puts the manifest at {KB_HOME}/config/repos.yml; in the repo it
# lives at ansible/repos.yml. KB_REPOS_YML overrides for local runs (matches
# server/repos.py).
CONFIG_FILE = Path(os.environ.get("KB_REPOS_YML", KB_HOME / "config" / "repos.yml"))
CHROMA_PATH = Path(os.environ.get("CHROMA_PATH", KB_HOME / "data" / "chromadb"))
COLLECTION_NAME = os.environ.get("KB_COLLECTION", "la_toolkit_kb")

CHUNK_SIZE = 800          # characters
CHUNK_OVERLAP = 100
UPSERT_BATCH = 512        # chunks per ChromaDB upsert (batched = far faster than 1-by-1)

# Text file extensions to index (everything else skipped silently)
TEXT_EXTENSIONS = {
    ".md", ".txt", ".rst", ".adoc",
    ".java", ".groovy", ".kt",
    ".py", ".js", ".ts", ".dart",
    ".yml", ".yaml", ".json", ".toml", ".ini", ".cfg", ".conf", ".properties",
    ".xml", ".html", ".gsp", ".sh", ".bash",
    ".sql", ".gradle",
}

# Extensionless text files worth indexing (CI/CD & build), matched by name/stem
# so e.g. Dockerfile, Dockerfile.dev, Jenkinsfile, Makefile all qualify.
TEXT_FILENAMES = {
    "dockerfile", "containerfile", "jenkinsfile", "makefile",
    "procfile", "vagrantfile",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("kb_indexer")


# ── Manifest helpers ──────────────────────────────────────────────────────────

def load_manifest() -> dict:
    with open(CONFIG_FILE) as f:
        return yaml.safe_load(f)


def expand_repos(manifest: dict) -> list[dict]:
    """Return list of repo dicts: {org, name, url, branch, description, is_wiki}.

    `branch` is None unless explicitly set (per-repo `branch:` or org-level
    `branch_default`). None means "use the remote's default branch (HEAD)".

    Repos flagged `wiki: true` emit two entries: the code repo and a virtual
    `{name}.wiki` entry pointing at `{base_url}/{name}.wiki.git`.
    """
    repos = []
    for org, org_cfg in manifest.get("orgs", {}).items():
        base_url = org_cfg["base_url"].rstrip("/")
        default_branch = org_cfg.get("branch_default")  # None → auto-detect HEAD
        for entry in org_cfg.get("repos", []):
            if isinstance(entry, str):
                name = entry
                branch = default_branch
                description = ""
                has_wiki = False
                index_releases = True
            else:
                name = entry["name"]
                branch = entry.get("branch", default_branch)
                description = entry.get("description", "")
                has_wiki = bool(entry.get("wiki", False))
                index_releases = bool(entry.get("releases", True))
            repos.append(
                {
                    "org": org,
                    "name": name,
                    "url": f"{base_url}/{name}.git",
                    "branch": branch,
                    "description": description,
                    "is_wiki": False,
                    "index_releases": index_releases,
                }
            )
            if has_wiki:
                repos.append(
                    {
                        "org": org,
                        "name": f"{name}.wiki",
                        "url": f"{base_url}/{name}.wiki.git",
                        "branch": None,
                        "description": f"GitHub wiki for {org}/{name}",
                        "is_wiki": True,
                        "index_releases": False,
                    }
                )
    return repos


def tier1_keys(manifest: dict) -> set[str]:
    return set(manifest.get("tier1", []))


def get_blocklist(manifest: dict) -> list[str]:
    return manifest.get("blocklist", [])


# ── Git helpers ───────────────────────────────────────────────────────────────

def clone_or_pull(repo_meta: dict) -> tuple[Repo, bool]:
    """Clone repo if missing, pull if exists. Returns (Repo, changed)."""
    dest = REPOS_DIR / repo_meta["org"] / repo_meta["name"]
    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.exists():
        try:
            repo = Repo(dest)
            before = repo.head.commit.hexsha
            repo.remotes.origin.pull()
            after = repo.head.commit.hexsha
            changed = before != after
            log.info(
                "%s/%s: %s",
                repo_meta["org"],
                repo_meta["name"],
                "updated" if changed else "already up to date",
            )
            return repo, changed
        except InvalidGitRepositoryError:
            log.warning("%s: invalid git repo, re-cloning", dest)
            import shutil
            shutil.rmtree(dest)

    log.info("Cloning %s → %s", repo_meta["url"], dest)
    clone_kwargs = {"depth": 1}
    if repo_meta.get("branch"):
        clone_kwargs["branch"] = repo_meta["branch"]
    # No branch → GitPython clones the remote's default branch (HEAD).
    repo = Repo.clone_from(repo_meta["url"], dest, **clone_kwargs)
    return repo, True


# ── Indexing helpers ──────────────────────────────────────────────────────────

def is_blocked(path: Path, blocklist: list[str]) -> bool:
    parts = path.parts
    name = path.name
    for pattern in blocklist:
        if pattern.endswith("/"):
            # directory component match
            dir_name = pattern.rstrip("/")
            if dir_name in parts:
                return True
        elif fnmatch.fnmatch(name, pattern):
            return True
    return False


def read_text_safe(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + size
        chunks.append(text[start:end])
        start = end - overlap
    return chunks


def index_repo(
    repo_meta: dict,
    collection: chromadb.Collection,
    blocklist: list[str],
) -> int:
    repo_dir = REPOS_DIR / repo_meta["org"] / repo_meta["name"]
    org_name = f"{repo_meta['org']}/{repo_meta['name']}"
    count = 0

    ids: list[str] = []
    docs: list[str] = []
    metas: list[dict] = []

    def flush() -> None:
        nonlocal ids, docs, metas
        if not ids:
            return
        collection.upsert(ids=ids, documents=docs, metadatas=metas)
        ids, docs, metas = [], [], []

    for file_path in repo_dir.rglob("*"):
        if not file_path.is_file():
            continue
        if (file_path.suffix.lower() not in TEXT_EXTENSIONS
                and file_path.name.lower() not in TEXT_FILENAMES
                and file_path.stem.lower() not in TEXT_FILENAMES):
            continue
        rel = file_path.relative_to(repo_dir)
        if is_blocked(rel, blocklist):
            continue

        text = read_text_safe(file_path)
        if not text or not text.strip():
            continue

        for i, chunk in enumerate(chunk_text(text)):
            if not chunk.strip():
                continue
            ids.append(f"{org_name}:{rel}:{i}")
            docs.append(chunk)
            metas.append(
                {
                    "repo": org_name,
                    "org": repo_meta["org"],
                    "file": str(rel),
                    "chunk": i,
                    "content_type": "source",
                }
            )
            count += 1
            if len(ids) >= UPSERT_BATCH:
                flush()

    flush()
    log.info("%s: indexed %d chunks", org_name, count)
    return count


# ── Main ──────────────────────────────────────────────────────────────────────

def build_collection() -> chromadb.Collection:
    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )


def run(repos: list[dict], blocklist: list[str]) -> None:
    collection = build_collection()
    total = 0
    for repo_meta in repos:
        try:
            _, _ = clone_or_pull(repo_meta)
            total += index_repo(repo_meta, collection, blocklist)
        except Exception as exc:
            if repo_meta.get("is_wiki"):
                log.warning(
                    "%s/%s: wiki not available or empty — skipping (%s)",
                    repo_meta["org"], repo_meta["name"], exc,
                )
            else:
                log.error("%s/%s: failed — %s", repo_meta["org"], repo_meta["name"], exc)
    log.info("Done. Total chunks indexed: %d", total)


def main() -> None:
    parser = argparse.ArgumentParser(description="Living Atlas KB indexer")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--tier1", action="store_true", help="Index tier1 repos only")
    group.add_argument("--all", action="store_true", help="Index all repos")
    group.add_argument(
        "--repo", metavar="ORG/NAME", help="Index a single repo (e.g. AtlasOfLivingAustralia/collectory)"
    )
    args = parser.parse_args()

    manifest = load_manifest()
    all_repos = expand_repos(manifest)
    blocklist = get_blocklist(manifest)

    if args.tier1:
        keys = tier1_keys(manifest)
        repos = [r for r in all_repos if f"{r['org']}/{r['name']}" in keys]
        log.info("Indexing %d tier1 repos", len(repos))
    elif getattr(args, "all"):
        repos = all_repos
        log.info("Indexing all %d repos", len(repos))
    else:
        target = args.repo
        repos = [r for r in all_repos if f"{r['org']}/{r['name']}" == target]
        if not repos:
            log.error("Repo not found in manifest: %s", target)
            sys.exit(1)
        log.info("Indexing single repo: %s", target)

    run(repos, blocklist)


if __name__ == "__main__":
    main()
