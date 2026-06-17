#!/usr/bin/env python3
"""
kb_watcher.py — Living Atlas KB commit watcher

Polls each repo in config/repos.yml for three kinds of change and re-indexes
only what changed:
  - new commits → latest SHA via `git ls-remote` (default branch / HEAD) →
    kb_indexer.py --repo
  - new GitHub release → latest release date via the GitHub API →
    kb_releases.py --repo
  - updated issues/PRs (ALA repos by default) → newest updated_at via the
    GitHub API → kb_issues.py --repo (incremental from its own high-water mark)

Releases can be published without moving the default-branch HEAD (a tag on an
older commit), so the SHA poll alone would miss them — hence the separate polls.

State stored in: {KB_HOME}/data/watcher_state.json
  { "ORG/NAME": {"head_sha": "<sha>", "release_date": "<iso>", "issue_update": "<iso>"}, ... }
Legacy plain-string SHA values are migrated transparently.

Cron: 0 * * * * (every hour)
"""

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

import httpx
import yaml

# ── Config ────────────────────────────────────────────────────────────────────

KB_HOME = Path(os.environ.get("KB_HOME", Path(__file__).parent.parent))
CONFIG_FILE = KB_HOME / "config" / "repos.yml"
STATE_FILE = KB_HOME / "data" / "watcher_state.json"
INDEXER = KB_HOME / "scripts" / "kb_indexer.py"
RELEASER = KB_HOME / "scripts" / "kb_releases.py"
ISSUER = KB_HOME / "scripts" / "kb_issues.py"
VENV_PYTHON = KB_HOME / "venv" / "bin" / "python3"

REQUEST_TIMEOUT = 20  # seconds
GITHUB_API = "https://api.github.com"

# Orgs whose issues/PRs are indexed by default (mirrors kb_indexer.ALA_ORGS).
ALA_ORGS = {"AtlasOfLivingAustralia", "living-atlases"}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("kb_watcher")


# ── State helpers ─────────────────────────────────────────────────────────────

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def entry_for(state: dict, key: str) -> dict:
    """Return the per-repo state dict, migrating legacy plain-SHA strings."""
    val = state.get(key)
    if isinstance(val, str):  # legacy format: bare head SHA
        return {"head_sha": val}
    if isinstance(val, dict):
        return val
    return {}


# ── Manifest helpers ──────────────────────────────────────────────────────────

def expand_repos(manifest: dict) -> list[dict]:
    """Return repo entries plus virtual `{name}.wiki` entries for wiki: true repos.

    `branch` is None unless explicitly set; None means "use the remote's default
    branch (HEAD)". Each entry carries the clone `url` so the watcher can poll
    via `git ls-remote` — robust against per-repo branch-name differences.
    """
    repos = []
    for org, org_cfg in manifest.get("orgs", {}).items():
        base_url = org_cfg["base_url"].rstrip("/")
        default_branch = org_cfg.get("branch_default")  # None → auto-detect HEAD
        for entry in org_cfg.get("repos", []):
            if isinstance(entry, str):
                name = entry
                branch = default_branch
                has_wiki = False
                index_releases = True
                index_issues = org in ALA_ORGS
            else:
                name = entry["name"]
                branch = entry.get("branch", default_branch)
                has_wiki = bool(entry.get("wiki", False))
                index_releases = bool(entry.get("releases", True))
                index_issues = bool(entry.get("issues", org in ALA_ORGS))
            repos.append(
                {
                    "org": org,
                    "name": name,
                    "branch": branch,
                    "is_wiki": False,
                    "index_releases": index_releases,
                    "index_issues": index_issues,
                    "url": f"{base_url}/{name}.git",
                }
            )
            if has_wiki:
                repos.append(
                    {
                        "org": org,
                        "name": f"{name}.wiki",
                        "branch": None,
                        "is_wiki": True,
                        "index_releases": False,
                        "index_issues": False,
                        "url": f"{base_url}/{name}.wiki.git",
                    }
                )

    # Local (non-git) sources, e.g. the curated FAQ folder. Polled by content
    # fingerprint (file mtime/size) instead of git SHA.
    for src in manifest.get("local_sources", []):
        repos.append(
            {
                "org": src.get("org", "local"),
                "name": src["name"],
                "branch": None,
                "is_wiki": False,
                "index_releases": False,
                "index_issues": False,
                "url": None,
                "is_local": True,
                "local_path": src["path"],
            }
        )
    return repos


# ── Commit SHA polling ────────────────────────────────────────────────────────

def fetch_latest_sha(org: str, name: str, url: str, branch: str | None) -> str | None:
    """Return the latest commit SHA via `git ls-remote`, or None on failure.

    `branch` None → query HEAD (the remote's default branch). Otherwise query
    `refs/heads/{branch}`. One network call per repo per cycle. An empty or
    unreachable repo/wiki returns nothing -> None.
    """
    ref = "HEAD" if not branch else f"refs/heads/{branch}"
    try:
        result = subprocess.run(
            ["git", "ls-remote", url, ref],
            capture_output=True,
            text=True,
            timeout=REQUEST_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        log.warning("%s/%s: ls-remote timed out", org, name)
        return None
    except Exception as e:
        log.warning("%s/%s: ls-remote error — %s", org, name, e)
        return None

    if result.returncode != 0 or not result.stdout.strip():
        log.debug("%s/%s: empty or unreachable (ref=%s)", org, name, ref)
        return None

    return result.stdout.split()[0].strip()


def fetch_local_fingerprint(local_path: str) -> str | None:
    """Return a fingerprint of a local source dir (file path/mtime/size), or None.

    Changes to any indexed file flip the fingerprint, triggering a re-index —
    the local-source equivalent of a new commit SHA.
    """
    import hashlib

    base = (KB_HOME / local_path).resolve()
    if not base.exists():
        log.warning("local source path missing: %s", base)
        return None
    h = hashlib.sha256()
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        st = path.stat()
        h.update(f"{path.relative_to(base)}:{int(st.st_mtime)}:{st.st_size}\n".encode())
    return h.hexdigest()


# ── Release polling ───────────────────────────────────────────────────────────

def github_headers() -> dict:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "living-atlas-kb-watcher",
    }
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def fetch_latest_release_date(org: str, name: str, headers: dict) -> str | None:
    """Return the latest published release's `published_at`, or None.

    Uses /releases/latest (newest non-draft, non-prerelease). 404 = no full
    release. Any error → None (treated as "no change" this cycle).
    """
    url = f"{GITHUB_API}/repos/{org}/{name}/releases/latest"
    try:
        resp = httpx.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
    except httpx.RequestError as e:
        log.warning("%s/%s: releases/latest error — %s", org, name, e)
        return None
    if resp.status_code != 200:
        log.debug("%s/%s: releases/latest HTTP %s", org, name, resp.status_code)
        return None
    return resp.json().get("published_at")


def fetch_latest_issue_update(org: str, name: str, headers: dict) -> str | None:
    """Return the newest issue/PR `updated_at` for a repo, or None.

    A single cheap call (per_page=1, sorted updated-desc) used only to decide
    whether to spawn the full kb_issues incremental sync. Includes PRs (the
    /issues endpoint returns both). Any error → None (treated as "no change").
    """
    url = f"{GITHUB_API}/repos/{org}/{name}/issues"
    params = {"state": "all", "sort": "updated", "direction": "desc", "per_page": 1}
    try:
        resp = httpx.get(url, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
    except httpx.RequestError as e:
        log.warning("%s/%s: issues poll error — %s", org, name, e)
        return None
    if resp.status_code != 200:
        log.debug("%s/%s: issues poll HTTP %s", org, name, resp.status_code)
        return None
    items = resp.json()
    return items[0].get("updated_at") if items else None


# ── Indexer invocation ────────────────────────────────────────────────────────

def _run_indexer(script: Path, org: str, name: str, label: str) -> bool:
    """Call a KB indexer script with --repo ORG/NAME. Returns True on success."""
    python = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable
    cmd = [python, str(script), "--repo", f"{org}/{name}"]
    log.info("%s %s/%s ...", label, org, name)
    try:
        result = subprocess.run(
            cmd,
            cwd=str(KB_HOME),
            capture_output=True,
            text=True,
            timeout=1800,
        )
        if result.returncode != 0:
            log.error("%s/%s: %s failed:\n%s", org, name, label, result.stderr[-2000:])
            return False
        log.info("%s/%s: %s ok", org, name, label)
        return True
    except subprocess.TimeoutExpired:
        log.error("%s/%s: %s timed out", org, name, label)
        return False
    except Exception as e:
        log.error("%s/%s: %s error — %s", org, name, label, e)
        return False


def reindex_repo(org: str, name: str) -> bool:
    """Re-index repo file content (new commits)."""
    return _run_indexer(INDEXER, org, name, "Re-indexing")


def reindex_releases(org: str, name: str) -> bool:
    """Re-index repo GitHub releases (new release)."""
    return _run_indexer(RELEASER, org, name, "Re-indexing releases")


def reindex_issues(org: str, name: str) -> bool:
    """Incrementally re-index repo GitHub issues/PRs (kb_issues tracks its own since)."""
    return _run_indexer(ISSUER, org, name, "Re-indexing issues")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    if not CONFIG_FILE.exists():
        log.error("Config not found: %s", CONFIG_FILE)
        sys.exit(1)

    with open(CONFIG_FILE) as f:
        manifest = yaml.safe_load(f)

    repos = expand_repos(manifest)
    state = load_state()
    headers = github_headers()
    updated = 0
    errors = 0
    unchanged = 0

    for repo in repos:
        org, name, branch = repo["org"], repo["name"], repo["branch"]
        key = f"{org}/{name}"
        entry = entry_for(state, key)
        changed = False

        # ── Local (non-git) source → fingerprint poll ──
        if repo.get("is_local"):
            fp = fetch_local_fingerprint(repo["local_path"])
            if fp is None:
                errors += 1
            elif entry.get("fingerprint") == fp:
                log.debug("%s: local source unchanged", key)
                unchanged += 1
            else:
                log.info("%s: local source changed — re-indexing", key)
                if reindex_repo(org, name):
                    entry["fingerprint"] = fp
                    state[key] = entry
                    save_state(state)
                    updated += 1
                else:
                    errors += 1
            continue

        # ── Commit poll → re-index file content ──
        sha = fetch_latest_sha(org, name, repo["url"], branch)
        if sha is None:
            errors += 1
        elif entry.get("head_sha") == sha:
            log.debug("%s: no new commits (sha=%s)", key, sha[:12])
        else:
            log.info("%s: new commits (old=%s new=%s)", key, (entry.get("head_sha") or "none")[:12], sha[:12])
            if reindex_repo(org, name):
                entry["head_sha"] = sha
                changed = True
            else:
                errors += 1

        # ── Release poll → re-index release notes (only opted-in repos) ──
        if repo.get("index_releases", True):
            rel_date = fetch_latest_release_date(org, name, headers)
            if rel_date and entry.get("release_date") != rel_date:
                log.info("%s: new release (old=%s new=%s)", key, entry.get("release_date"), rel_date)
                if reindex_releases(org, name):
                    entry["release_date"] = rel_date
                    changed = True
                else:
                    errors += 1

        # ── Issue poll → re-index issues/PRs (only opted-in repos) ──
        # Cheap newest-updated probe gates the (model-loading) kb_issues run, which
        # then does the full incremental sync from its own high-water mark.
        if repo.get("index_issues", False):
            issue_update = fetch_latest_issue_update(org, name, headers)
            if issue_update and entry.get("issue_update") != issue_update:
                log.info("%s: updated issues (old=%s new=%s)", key, entry.get("issue_update"), issue_update)
                if reindex_issues(org, name):
                    entry["issue_update"] = issue_update
                    changed = True
                else:
                    errors += 1

        if changed:
            state[key] = entry
            save_state(state)
            updated += 1
        else:
            unchanged += 1

    log.info(
        "Watch cycle complete. Updated: %d, Errors: %d, Unchanged: %d",
        updated,
        errors,
        unchanged,
    )


if __name__ == "__main__":
    main()
