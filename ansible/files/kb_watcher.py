#!/usr/bin/env python3
"""
kb_watcher.py — Living Atlas KB commit watcher

Polls the latest commit SHA of every repo in config/repos.yml via
`git ls-remote` (default branch / HEAD unless a branch override is set).
Re-indexes a repo only when new commits are detected since the last run.

State stored in: {KB_HOME}/data/watcher_state.json
  { "ORG/NAME": "<last_commit_sha>", ... }

Cron: 0 * * * * (every hour)
"""

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

import yaml

# ── Config ────────────────────────────────────────────────────────────────────

KB_HOME = Path(os.environ.get("KB_HOME", Path(__file__).parent.parent))
CONFIG_FILE = KB_HOME / "config" / "repos.yml"
STATE_FILE = KB_HOME / "data" / "watcher_state.json"
INDEXER = KB_HOME / "scripts" / "kb_indexer.py"
VENV_PYTHON = KB_HOME / "venv" / "bin" / "python3"

REQUEST_TIMEOUT = 20  # seconds

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
            else:
                name = entry["name"]
                branch = entry.get("branch", default_branch)
                has_wiki = bool(entry.get("wiki", False))
            repos.append(
                {
                    "org": org,
                    "name": name,
                    "branch": branch,
                    "is_wiki": False,
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
                        "url": f"{base_url}/{name}.wiki.git",
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


# ── Indexer invocation ────────────────────────────────────────────────────────

def reindex_repo(org: str, name: str) -> bool:
    """Call kb_indexer.py --repo ORG/NAME. Returns True on success."""
    python = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable
    cmd = [python, str(INDEXER), "--repo", f"{org}/{name}"]
    log.info("Re-indexing %s/%s ...", org, name)
    try:
        result = subprocess.run(
            cmd,
            cwd=str(KB_HOME),
            capture_output=True,
            text=True,
            timeout=1800,
        )
        if result.returncode != 0:
            log.error("%s/%s: indexer failed:\n%s", org, name, result.stderr[-2000:])
            return False
        log.info("%s/%s: re-indexed successfully", org, name)
        return True
    except subprocess.TimeoutExpired:
        log.error("%s/%s: indexer timed out", org, name)
        return False
    except Exception as e:
        log.error("%s/%s: indexer error — %s", org, name, e)
        return False


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    if not CONFIG_FILE.exists():
        log.error("Config not found: %s", CONFIG_FILE)
        sys.exit(1)

    with open(CONFIG_FILE) as f:
        manifest = yaml.safe_load(f)

    repos = expand_repos(manifest)
    state = load_state()
    updated = 0
    errors = 0

    for repo in repos:
        org, name, branch = repo["org"], repo["name"], repo["branch"]
        key = f"{org}/{name}"

        sha = fetch_latest_sha(org, name, repo["url"], branch)
        if sha is None:
            errors += 1
            continue

        if state.get(key) == sha:
            log.debug("%s: no new commits (sha=%s)", key, sha[:12])
            continue

        log.info("%s: new commits detected (old=%s new=%s)", key, state.get(key, "none")[:12], sha[:12])
        if reindex_repo(org, name):
            state[key] = sha
            save_state(state)
            updated += 1
        else:
            errors += 1

    log.info(
        "Watch cycle complete. Updated: %d, Errors: %d, Unchanged: %d",
        updated,
        errors,
        len(repos) - updated - errors,
    )


if __name__ == "__main__":
    main()
