"""Repository manifest loader for the KB API.

Reads `{KB_HOME}/config/repos.yml` and normalises entries to a uniform shape.
Cached in memory with mtime invalidation so the API doesn't hit disk per request.
"""

import os
from pathlib import Path
from typing import Optional

import yaml

KB_HOME = Path(os.environ.get("KB_HOME", "/opt/la-toolkit-kb"))
CONFIG_FILE = Path(os.environ.get("KB_REPOS_YML", KB_HOME / "config" / "repos.yml"))

_cache: dict = {"mtime": 0.0, "data": None}


def _normalise(manifest: dict) -> dict:
    orgs_out: dict = {}
    for org, org_cfg in manifest.get("orgs", {}).items():
        base_url = org_cfg["base_url"].rstrip("/")
        default_branch = org_cfg.get("branch_default", "master")
        repos = []
        for entry in org_cfg.get("repos", []):
            if isinstance(entry, str):
                repos.append({
                    "name": entry,
                    "branch": default_branch,
                    "description": None,
                })
            else:
                repos.append({
                    "name": entry["name"],
                    "branch": entry.get("branch", default_branch),
                    "description": entry.get("description"),
                })
        orgs_out[org] = {"base_url": base_url, "repos": repos}
    return {
        "orgs": orgs_out,
        "tier1": list(manifest.get("tier1", [])),
    }


def load_manifest(path: Optional[Path] = None) -> dict:
    """Return normalised manifest. Re-reads from disk if the file changed."""
    target = path or CONFIG_FILE
    try:
        mtime = target.stat().st_mtime
    except FileNotFoundError:
        return {"orgs": {}, "tier1": []}

    if _cache["data"] is not None and _cache["mtime"] == mtime:
        return _cache["data"]

    with open(target) as f:
        raw = yaml.safe_load(f) or {}
    data = _normalise(raw)
    _cache["mtime"] = mtime
    _cache["data"] = data
    return data
