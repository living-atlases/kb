#!/usr/bin/env python3
"""
kb_releases.py — Living Atlas KB GitHub Releases indexer

ALA/GBIF repos rarely keep CHANGELOG.md; they document changes via GitHub
Releases (tag + markdown body). This module fetches releases via the GitHub
REST API and produces two complementary outputs:

  1. Semantic  — release bodies chunked + embedded into the SAME ChromaDB
                 collection as source code, tagged metadata content_type="release".
                 Answers "what changed in X?" and surfaces cross-component
                 dependency notes (Java version, compatible services, …).
  2. Structured — data/versions.json mapping repo -> {latest_tag, latest_stable_tag,
                 published_at, prerelease, url}. A direct lookup for keeping
                 la-toolkit-backend/assets/dependencies.yaml up to date.

Auth: set GH_TOKEN (or GITHUB_TOKEN) for 5000 req/h; without it GitHub allows
only ~60 req/h (enough for a handful of repos, not the whole manifest).

Usage:
  python3 scripts/kb_releases.py --all              # index releases of all repos + write versions.json
  python3 scripts/kb_releases.py --repo ORG/NAME    # index one repo + update its versions.json entry
  python3 scripts/kb_releases.py --write-versions   # only (re)write versions.json, no embedding
"""

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

import httpx

# Reuse manifest parsing, chunking and the ChromaDB collection from the indexer.
# Both scripts are deployed side-by-side ({kb_home}/scripts), so a flat import works.
from kb_indexer import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    KB_HOME,
    UPSERT_BATCH,
    build_collection,
    chunk_text,
    expand_repos,
    load_manifest,
)

# ── Config ────────────────────────────────────────────────────────────────────

VERSIONS_FILE = Path(
    os.environ.get("KB_VERSIONS_FILE", KB_HOME / "data" / "versions.json")
)

GITHUB_API = "https://api.github.com"
PER_PAGE = 100
MAX_PAGES = 10          # 1000 releases/repo ceiling; ALA repos have far fewer
HTTP_TIMEOUT = 30       # seconds per request
CONTENT_TYPE = "release"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("kb_releases")


# ── GitHub auth ───────────────────────────────────────────────────────────────

def load_github_headers() -> dict:
    """Return request headers, including a bearer token if GH_TOKEN/GITHUB_TOKEN is set."""
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "living-atlas-kb-releases",
    }
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    else:
        log.warning(
            "No GH_TOKEN/GITHUB_TOKEN set — GitHub API limited to ~60 req/h; "
            "indexing many repos will hit the rate limit."
        )
    return headers


# ── GitHub Releases API ───────────────────────────────────────────────────────

def fetch_releases(org: str, name: str, headers: dict, client: httpx.Client) -> list[dict]:
    """Return published releases (newest first) for a repo, or [] if none/unavailable.

    Drafts are skipped (noise, and require auth). On a rate-limit response the
    caller is signalled by raising RateLimited so the run can stop cleanly.
    """
    releases: list[dict] = []
    for page in range(1, MAX_PAGES + 1):
        url = f"{GITHUB_API}/repos/{org}/{name}/releases"
        try:
            resp = client.get(
                url,
                headers=headers,
                params={"per_page": PER_PAGE, "page": page},
                timeout=HTTP_TIMEOUT,
            )
        except httpx.RequestError as e:
            log.warning("%s/%s: request error — %s", org, name, e)
            return releases

        if resp.status_code == 404:
            log.debug("%s/%s: no releases (404)", org, name)
            return []
        if resp.status_code == 403 and resp.headers.get("X-RateLimit-Remaining") == "0":
            reset = resp.headers.get("X-RateLimit-Reset", "?")
            raise RateLimited(f"GitHub rate limit hit (resets at epoch {reset})")
        if resp.status_code != 200:
            log.warning("%s/%s: releases HTTP %s", org, name, resp.status_code)
            return releases

        page_items = resp.json()
        if not page_items:
            break
        releases.extend(r for r in page_items if not r.get("draft"))
        if len(page_items) < PER_PAGE:
            break

    return releases


class RateLimited(Exception):
    """Raised when the GitHub API rate limit is exhausted."""


# ── Version metadata (structured output) ──────────────────────────────────────

def version_info(releases: list[dict]) -> dict | None:
    """Condense a repo's releases into latest / latest-stable version metadata.

    GitHub returns releases newest-first. `latest_tag` is the newest release
    (may be a prerelease); `latest_stable_tag` is the newest non-prerelease.
    """
    if not releases:
        return None
    latest = releases[0]
    stable = next((r for r in releases if not r.get("prerelease")), None)
    return {
        "latest_tag": latest.get("tag_name"),
        "latest_stable_tag": stable.get("tag_name") if stable else None,
        "published_at": latest.get("published_at"),
        "prerelease": bool(latest.get("prerelease")),
        "url": latest.get("html_url"),
    }


def load_versions() -> dict:
    if VERSIONS_FILE.exists():
        try:
            return json.loads(VERSIONS_FILE.read_text())
        except Exception:
            log.warning("versions.json unreadable — starting fresh")
    return {}


def write_versions(versions: dict) -> None:
    VERSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    VERSIONS_FILE.write_text(json.dumps(versions, indent=2, sort_keys=True) + "\n")
    log.info("Wrote %d component versions to %s", len(versions), VERSIONS_FILE)


# ── Semantic indexing (ChromaDB output) ───────────────────────────────────────

def release_document(release: dict) -> str:
    """Render a release as a self-describing markdown blob before chunking."""
    tag = release.get("tag_name") or "(untagged)"
    title = release.get("name") or tag
    date = release.get("published_at") or ""
    header = f"# Release {tag}: {title}\nPublished: {date}\n\n"
    return header + (release.get("body") or "")


def index_releases(
    repo_meta: dict,
    collection,
    headers: dict,
    client: httpx.Client,
) -> tuple[int, dict | None]:
    """Fetch + (re)index a repo's releases. Returns (chunks_indexed, version_info).

    Old release chunks for this repo are deleted first so shrunk/removed releases
    never orphan stale chunks (re-index is fully idempotent).
    """
    org, name = repo_meta["org"], repo_meta["name"]
    org_name = f"{org}/{name}"

    releases = fetch_releases(org, name, headers, client)
    if not releases:
        log.info("%s: no releases", org_name)
        return 0, None

    # Idempotent: clear this repo's existing release chunks before re-upserting.
    try:
        collection.delete(where={"$and": [{"repo": org_name}, {"content_type": CONTENT_TYPE}]})
    except Exception as e:
        log.debug("%s: release-chunk cleanup skipped — %s", org_name, e)

    ids: list[str] = []
    docs: list[str] = []
    metas: list[dict] = []
    count = 0

    def flush() -> None:
        nonlocal ids, docs, metas
        if not ids:
            return
        collection.upsert(ids=ids, documents=docs, metadatas=metas)
        ids, docs, metas = [], [], []

    for release in releases:
        tag = release.get("tag_name") or release.get("id")
        text = release_document(release)
        if not text.strip():
            continue
        for i, chunk in enumerate(chunk_text(text, CHUNK_SIZE, CHUNK_OVERLAP)):
            if not chunk.strip():
                continue
            ids.append(f"{org_name}:release:{tag}:{i}")
            docs.append(chunk)
            metas.append(
                {
                    "repo": org_name,
                    "org": org,
                    "content_type": CONTENT_TYPE,
                    "tag": str(tag),
                    "published_at": release.get("published_at") or "",
                    "prerelease": bool(release.get("prerelease")),
                    "url": release.get("html_url") or "",
                }
            )
            count += 1
            if len(ids) >= UPSERT_BATCH:
                flush()
    flush()

    log.info("%s: indexed %d release chunks (%d releases)", org_name, count, len(releases))
    return count, version_info(releases)


# ── Runners ───────────────────────────────────────────────────────────────────

def release_repos(manifest: dict) -> list[dict]:
    """Repos opted in to release indexing (skip wikis and `releases: false`)."""
    return [
        r for r in expand_repos(manifest)
        if not r.get("is_wiki") and r.get("index_releases", True)
    ]


def run(repos: list[dict], write_versions_file: bool) -> None:
    collection = build_collection()
    headers = load_github_headers()
    versions = load_versions()
    total = 0
    with httpx.Client() as client:
        for repo_meta in repos:
            org_name = f"{repo_meta['org']}/{repo_meta['name']}"
            try:
                count, info = index_releases(repo_meta, collection, headers, client)
                total += count
                if info:
                    versions[org_name] = info
                elif org_name in versions:
                    del versions[org_name]
            except RateLimited as e:
                log.error("%s: %s — stopping", org_name, e)
                break
            except Exception as e:
                log.error("%s: failed — %s", org_name, e)
            time.sleep(0.1)  # be gentle with the API

    if write_versions_file:
        write_versions(versions)
    log.info("Done. Total release chunks indexed: %d", total)


def run_write_versions_only(repos: list[dict]) -> None:
    """Fetch latest release per repo and rewrite versions.json without embedding."""
    headers = load_github_headers()
    versions = load_versions()
    with httpx.Client() as client:
        for repo_meta in repos:
            org, name = repo_meta["org"], repo_meta["name"]
            org_name = f"{org}/{name}"
            try:
                info = version_info(fetch_releases(org, name, headers, client))
            except RateLimited as e:
                log.error("%s: %s — stopping", org_name, e)
                break
            except Exception as e:
                log.error("%s: failed — %s", org_name, e)
                continue
            if info:
                versions[org_name] = info
            elif org_name in versions:
                del versions[org_name]
            time.sleep(0.1)
    write_versions(versions)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Living Atlas KB GitHub Releases indexer")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="Index releases of all repos")
    group.add_argument("--repo", metavar="ORG/NAME", help="Index releases of a single repo")
    group.add_argument(
        "--write-versions", action="store_true",
        help="Only (re)write data/versions.json; no embedding",
    )
    args = parser.parse_args()

    manifest = load_manifest()
    repos = release_repos(manifest)

    if args.repo:
        repos = [r for r in repos if f"{r['org']}/{r['name']}" == args.repo]
        if not repos:
            log.error("Repo not found or release-indexing disabled: %s", args.repo)
            sys.exit(1)
        log.info("Indexing releases for single repo: %s", args.repo)
        run(repos, write_versions_file=True)
    elif args.write_versions:
        log.info("Writing versions.json for %d repos", len(repos))
        run_write_versions_only(repos)
    else:
        log.info("Indexing releases for all %d repos", len(repos))
        run(repos, write_versions_file=True)


if __name__ == "__main__":
    main()
