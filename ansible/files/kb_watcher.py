#!/usr/bin/env python3
"""
kb_watcher.py — Living Atlas KB RSS/Atom watcher

Polls GitHub commit Atom feeds for all repos in config/repos.yml.
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
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

# ── Config ────────────────────────────────────────────────────────────────────

KB_HOME = Path(os.environ.get("KB_HOME", Path(__file__).parent.parent))
CONFIG_FILE = KB_HOME / "config" / "repos.yml"
STATE_FILE = KB_HOME / "data" / "watcher_state.json"
INDEXER = KB_HOME / "scripts" / "kb_indexer.py"
VENV_PYTHON = KB_HOME / "venv" / "bin" / "python3"

ATOM_URL = "https://github.com/{org}/{name}/commits/{branch}.atom"
REQUEST_TIMEOUT = 20  # seconds

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("kb_watcher")

# GitHub Atom NS
ATOM_NS = "http://www.w3.org/2005/Atom"


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
    repos = []
    for org, org_cfg in manifest.get("orgs", {}).items():
        default_branch = org_cfg.get("branch_default", "master")
        for entry in org_cfg.get("repos", []):
            if isinstance(entry, str):
                name = entry
                branch = default_branch
            else:
                name = entry["name"]
                branch = entry.get("branch", default_branch)
            repos.append({"org": org, "name": name, "branch": branch})
    return repos


# ── Atom feed helpers ─────────────────────────────────────────────────────────

def fetch_latest_sha(org: str, name: str, branch: str) -> str | None:
    """Fetch the Atom feed and return the SHA of the most recent commit, or None on error."""
    url = ATOM_URL.format(org=org, name=name, branch=branch)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "la-kb-watcher/1.0"})
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            body = resp.read()
    except urllib.error.HTTPError as e:
        log.warning("%s/%s: HTTP %d fetching feed", org, name, e.code)
        return None
    except Exception as e:
        log.warning("%s/%s: feed fetch error — %s", org, name, e)
        return None

    try:
        root = ET.fromstring(body)
    except ET.ParseError as e:
        log.warning("%s/%s: feed parse error — %s", org, name, e)
        return None

    # First <entry> is the most recent commit.
    # <id>tag:github.com,2008:Grit::Commit/SHA</id>
    entry = root.find(f"{{{ATOM_NS}}}entry")
    if entry is None:
        return None

    id_el = entry.find(f"{{{ATOM_NS}}}id")
    if id_el is None or not id_el.text:
        return None

    # id text ends with the full commit SHA after the last "/"
    return id_el.text.rsplit("/", 1)[-1].strip()


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

        sha = fetch_latest_sha(org, name, branch)
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
