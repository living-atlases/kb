#!/usr/bin/env python3
"""
kb_issues.py — Living Atlas KB GitHub Issues & Pull Requests indexer

Issues and PRs hold a lot of "tribal knowledge" that never lands in code or
docs: real-world bugs with workarounds, design discussions, migration notes,
and "how do I …" Q&A. This module fetches them via the GitHub REST API and
embeds title + body + top-N comments into the SAME ChromaDB collection as
source code, tagged metadata content_type="issue" or "pr".

Scope: only repos opted in to issue indexing (kb_indexer.expand_repos sets
`index_issues` True for ALA orgs by default; GBIF repos are opt-in via
`issues: true`). High-signal-only by design — bot/dependabot noise is dropped
and only the first MAX_COMMENTS comments per thread are indexed, so the index
stays lean.

Incremental: a per-repo high-water mark (newest `updated_at`) is stored in
data/issues_state.json; subsequent runs pass it as the API `since` filter, so a
no-change run costs a single request. Each changed issue's old chunks are
deleted before re-upsert, so re-indexing is idempotent.

Auth: set GH_TOKEN (or GITHUB_TOKEN) for 5000 req/h; without it GitHub allows
only ~60 req/h (not enough for the whole manifest).

Usage:
  python3 scripts/kb_issues.py --all              # incrementally index all opted-in repos
  python3 scripts/kb_issues.py --repo ORG/NAME    # incrementally index a single repo
  python3 scripts/kb_issues.py --repo ORG/NAME --full   # ignore high-water mark, re-scan
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
# Deployed side-by-side ({kb_home}/scripts), so a flat import works.
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

ISSUES_STATE_FILE = Path(
    os.environ.get("KB_ISSUES_STATE_FILE", KB_HOME / "data" / "issues_state.json")
)

GITHUB_API = "https://api.github.com"
PER_PAGE = 100
MAX_PAGES = 20           # 2000 issues/run ceiling — plenty for an incremental sync
MAX_COMMENTS = 10        # top-N comments per thread (oldest first) — caps volume
MIN_TEXT_CHARS = 30      # skip near-empty issues (title+body shorter than this)
HTTP_TIMEOUT = 30        # seconds per request
COMMENT_BODY_CAP = 4000  # truncate very long single comments before chunking

# Logins treated as bots even when the API doesn't flag user.type == "Bot".
BOT_LOGINS = {
    "dependabot", "dependabot-preview", "github-actions",
    "codecov", "mergify", "renovate", "snyk-bot", "greenkeeper",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("kb_issues")


class RateLimited(Exception):
    """Raised when the GitHub API rate limit is exhausted."""


# ── GitHub auth ───────────────────────────────────────────────────────────────

def load_github_headers() -> dict:
    """Return request headers, including a bearer token if GH_TOKEN/GITHUB_TOKEN is set."""
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "living-atlas-kb-issues",
    }
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    else:
        log.warning(
            "No GH_TOKEN/GITHUB_TOKEN set — GitHub API limited to ~60 req/h; "
            "indexing issues for many repos will hit the rate limit."
        )
    return headers


# ── Filtering ─────────────────────────────────────────────────────────────────

def is_bot(user: dict | None) -> bool:
    """True for GitHub Apps / automation accounts (dependabot, CI bots, …)."""
    if not user:
        return False
    if user.get("type") == "Bot":
        return True
    login = (user.get("login") or "").lower()
    return login.endswith("[bot]") or login in BOT_LOGINS


def should_index(issue: dict) -> bool:
    """Keep human-authored issues/PRs with at least a little substance."""
    if is_bot(issue.get("user")):
        return False
    text = (issue.get("title") or "").strip() + (issue.get("body") or "").strip()
    return len(text) >= MIN_TEXT_CHARS


# ── GitHub API ────────────────────────────────────────────────────────────────

def _get(client: httpx.Client, url: str, headers: dict, params: dict) -> httpx.Response:
    resp = client.get(url, headers=headers, params=params, timeout=HTTP_TIMEOUT)
    if resp.status_code == 403 and resp.headers.get("X-RateLimit-Remaining") == "0":
        reset = resp.headers.get("X-RateLimit-Reset", "?")
        raise RateLimited(f"GitHub rate limit hit (resets at epoch {reset})")
    return resp


def fetch_issues(
    org: str, name: str, headers: dict, client: httpx.Client, since: str | None
) -> list[dict]:
    """Return issues AND pull requests updated since `since` (oldest-first).

    The /issues endpoint returns both; PRs carry a `pull_request` key. `since`
    (ISO-8601) filters by last-updated. Results are sorted updated-ascending so
    the high-water mark advances monotonically even if a run is interrupted.
    """
    items: list[dict] = []
    for page in range(1, MAX_PAGES + 1):
        url = f"{GITHUB_API}/repos/{org}/{name}/issues"
        params = {
            "state": "all",
            "sort": "updated",
            "direction": "asc",
            "per_page": PER_PAGE,
            "page": page,
        }
        if since:
            params["since"] = since
        try:
            resp = _get(client, url, headers, params)
        except httpx.RequestError as e:
            log.warning("%s/%s: request error — %s", org, name, e)
            return items
        if resp.status_code == 404:
            log.debug("%s/%s: no issues (404)", org, name)
            return []
        if resp.status_code != 200:
            log.warning("%s/%s: issues HTTP %s", org, name, resp.status_code)
            return items
        page_items = resp.json()
        if not page_items:
            break
        items.extend(page_items)
        if len(page_items) < PER_PAGE:
            break
    return items


def fetch_comments(
    org: str, name: str, number: int, headers: dict, client: httpx.Client
) -> list[dict]:
    """Return up to MAX_COMMENTS human comment bodies for an issue/PR (oldest first)."""
    url = f"{GITHUB_API}/repos/{org}/{name}/issues/{number}/comments"
    try:
        resp = _get(client, url, headers, {"per_page": PER_PAGE, "page": 1})
    except httpx.RequestError as e:
        log.debug("%s/%s#%s: comments error — %s", org, name, number, e)
        return []
    if resp.status_code != 200:
        return []
    out = []
    for c in resp.json():
        if is_bot(c.get("user")):
            continue
        body = (c.get("body") or "").strip()
        if not body:
            continue
        out.append({
            "author": (c.get("user") or {}).get("login", "unknown"),
            "body": body[:COMMENT_BODY_CAP],
        })
        if len(out) >= MAX_COMMENTS:
            break
    return out


# ── Document rendering ────────────────────────────────────────────────────────

def issue_document(issue: dict, comments: list[dict]) -> str:
    """Render an issue/PR as a self-describing markdown blob before chunking."""
    kind = "Pull Request" if "pull_request" in issue else "Issue"
    number = issue.get("number")
    title = issue.get("title") or "(no title)"
    state = issue.get("state") or "?"
    labels = ", ".join(l.get("name", "") for l in issue.get("labels", []) if isinstance(l, dict))
    header = f"# {kind} #{number}: {title}\nState: {state}"
    if labels:
        header += f"\nLabels: {labels}"
    parts = [header, "\n\n", issue.get("body") or ""]
    for c in comments:
        parts.append(f"\n\n---\nComment by {c['author']}:\n{c['body']}")
    return "".join(parts)


# ── Semantic indexing ─────────────────────────────────────────────────────────

def index_repo_issues(
    repo_meta: dict,
    collection,
    headers: dict,
    client: httpx.Client,
    since: str | None,
) -> tuple[int, str | None]:
    """Fetch + (re)index a repo's issues/PRs updated since `since`.

    Returns (chunks_indexed, new_high_water_mark). Each touched issue's old
    chunks are deleted before re-upsert so re-indexing is idempotent and
    closed/edited threads never orphan stale chunks.
    """
    org, name = repo_meta["org"], repo_meta["name"]
    org_name = f"{org}/{name}"

    issues = fetch_issues(org, name, headers, client, since)
    if not issues:
        log.info("%s: no updated issues", org_name)
        return 0, since

    ids: list[str] = []
    docs: list[str] = []
    metas: list[dict] = []
    count = 0
    hwm = since

    def flush() -> None:
        nonlocal ids, docs, metas
        if not ids:
            return
        collection.upsert(ids=ids, documents=docs, metadatas=metas)
        ids, docs, metas = [], [], []

    for issue in issues:
        number = issue.get("number")
        updated = issue.get("updated_at")
        if updated and (hwm is None or updated > hwm):
            hwm = updated

        # Idempotent: clear this issue's existing chunks (issue & pr share the
        # repo's number space) before deciding whether to re-add it.
        try:
            collection.delete(where={"$and": [{"repo": org_name}, {"number": number}]})
        except Exception as e:
            log.debug("%s#%s: chunk cleanup skipped — %s", org_name, number, e)

        if not should_index(issue):
            continue

        is_pr = "pull_request" in issue
        content_type = "pr" if is_pr else "issue"
        comments = []
        if (issue.get("comments") or 0) > 0:
            comments = fetch_comments(org, name, number, headers, client)

        text = issue_document(issue, comments)
        if not text.strip():
            continue

        merged = bool((issue.get("pull_request") or {}).get("merged_at")) if is_pr else False
        for i, chunk in enumerate(chunk_text(text, CHUNK_SIZE, CHUNK_OVERLAP)):
            if not chunk.strip():
                continue
            ids.append(f"{org_name}:{content_type}:{number}:{i}")
            docs.append(chunk)
            metas.append({
                "repo": org_name,
                "org": org,
                "content_type": content_type,
                "number": number,
                "state": issue.get("state") or "",
                "title": issue.get("title") or "",
                "url": issue.get("html_url") or "",
                "updated_at": updated or "",
                "is_pr": is_pr,
                "merged": merged,
            })
            count += 1
            if len(ids) >= UPSERT_BATCH:
                flush()
    flush()

    log.info("%s: indexed %d issue/PR chunks (%d threads scanned)", org_name, count, len(issues))
    return count, hwm


# ── State (high-water marks) ──────────────────────────────────────────────────

def load_state() -> dict:
    if ISSUES_STATE_FILE.exists():
        try:
            return json.loads(ISSUES_STATE_FILE.read_text())
        except Exception:
            log.warning("issues_state.json unreadable — starting fresh")
    return {}


def save_state(state: dict) -> None:
    ISSUES_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    ISSUES_STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


# ── Runners ───────────────────────────────────────────────────────────────────

def issue_repos(manifest: dict) -> list[dict]:
    """Repos opted in to issue indexing (skip wikis, local sources, opt-outs)."""
    return [
        r for r in expand_repos(manifest)
        if not r.get("is_wiki")
        and not r.get("is_local")
        and r.get("index_issues", False)
    ]


def run(repos: list[dict], full: bool) -> None:
    collection = build_collection()
    headers = load_github_headers()
    state = load_state()
    total = 0
    with httpx.Client() as client:
        for repo_meta in repos:
            org_name = f"{repo_meta['org']}/{repo_meta['name']}"
            since = None if full else state.get(org_name, {}).get("since")
            try:
                count, hwm = index_repo_issues(repo_meta, collection, headers, client, since)
            except RateLimited as e:
                log.error("%s: %s — stopping", org_name, e)
                break
            except Exception as e:
                log.error("%s: failed — %s", org_name, e)
                continue
            total += count
            if hwm:
                state[org_name] = {"since": hwm}
                save_state(state)
            time.sleep(0.1)  # be gentle with the API
    log.info("Done. Total issue/PR chunks indexed: %d", total)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Living Atlas KB GitHub Issues/PRs indexer")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="Index issues of all opted-in repos")
    group.add_argument("--repo", metavar="ORG/NAME", help="Index issues of a single repo")
    parser.add_argument(
        "--full", action="store_true",
        help="Ignore the stored high-water mark and re-scan from the start",
    )
    args = parser.parse_args()

    manifest = load_manifest()
    repos = issue_repos(manifest)

    if args.repo:
        repos = [r for r in repos if f"{r['org']}/{r['name']}" == args.repo]
        if not repos:
            log.error("Repo not found or issue-indexing disabled: %s", args.repo)
            sys.exit(1)
        log.info("Indexing issues for single repo: %s", args.repo)
    else:
        log.info("Indexing issues for all %d opted-in repos", len(repos))

    run(repos, full=args.full)


if __name__ == "__main__":
    main()
