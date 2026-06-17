"""Tests for kb_issues.py — GitHub issues/PRs ingestion (no network)."""

from unittest.mock import MagicMock

import pytest

import kb_issues as ki


# ── Fake HTTP plumbing ────────────────────────────────────────────────────────

def _resp(status=200, payload=None, headers=None):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = payload if payload is not None else []
    r.headers = headers or {}
    return r


def _client(responses):
    """httpx.Client stub whose .get returns the queued responses in order."""
    c = MagicMock()
    c.get.side_effect = list(responses)
    return c


# ── load_github_headers ───────────────────────────────────────────────────────

def test_headers_with_token(monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "abc123")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    assert ki.load_github_headers()["Authorization"] == "Bearer abc123"


def test_headers_without_token(monkeypatch):
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    assert "Authorization" not in ki.load_github_headers()


# ── is_bot / should_index filtering ───────────────────────────────────────────

def test_is_bot_by_type():
    assert ki.is_bot({"type": "Bot", "login": "x"}) is True


def test_is_bot_by_login_suffix():
    assert ki.is_bot({"type": "User", "login": "dependabot[bot]"}) is True


def test_is_bot_by_known_login():
    assert ki.is_bot({"type": "User", "login": "renovate"}) is True


def test_is_bot_false_for_human():
    assert ki.is_bot({"type": "User", "login": "djtfmartin"}) is False


def test_should_index_skips_bot():
    issue = {"user": {"type": "Bot", "login": "dependabot[bot]"}, "title": "Bump x", "body": "y" * 100}
    assert ki.should_index(issue) is False


def test_should_index_skips_trivial():
    issue = {"user": {"type": "User", "login": "h"}, "title": "hi", "body": ""}
    assert ki.should_index(issue) is False


def test_should_index_keeps_substantial_human_issue():
    issue = {"user": {"type": "User", "login": "h"}, "title": "Collectory upload fails",
             "body": "Steps to reproduce: configure the data resource and ..."}
    assert ki.should_index(issue) is True


# ── fetch_issues ──────────────────────────────────────────────────────────────

def test_fetch_issues_passes_since_param():
    client = _client([_resp(200, [{"number": 1, "updated_at": "2024-01-02T00:00:00Z"}])])
    ki.fetch_issues("org", "repo", {}, client, since="2024-01-01T00:00:00Z")
    _, kwargs = client.get.call_args
    assert kwargs["params"]["since"] == "2024-01-01T00:00:00Z"
    assert kwargs["params"]["state"] == "all"


def test_fetch_issues_paginates_until_short_page():
    page1 = [{"number": i} for i in range(ki.PER_PAGE)]
    page2 = [{"number": 999}]
    client = _client([_resp(200, page1), _resp(200, page2)])
    items = ki.fetch_issues("org", "repo", {}, client, since=None)
    assert len(items) == ki.PER_PAGE + 1
    assert client.get.call_count == 2


def test_fetch_issues_404_returns_empty():
    client = _client([_resp(404)])
    assert ki.fetch_issues("org", "repo", {}, client, since=None) == []


def test_fetch_issues_rate_limited_raises():
    client = _client([_resp(403, headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "9"})])
    with pytest.raises(ki.RateLimited):
        ki.fetch_issues("org", "repo", {}, client, since=None)


# ── fetch_comments ────────────────────────────────────────────────────────────

def test_fetch_comments_drops_bots_and_caps():
    payload = [{"user": {"type": "Bot", "login": "ci[bot]"}, "body": "ran CI"}]
    payload += [{"user": {"type": "User", "login": f"u{i}"}, "body": f"comment {i}"}
                for i in range(ki.MAX_COMMENTS + 5)]
    client = _client([_resp(200, payload)])
    out = ki.fetch_comments("org", "repo", 5, {}, client)
    assert len(out) == ki.MAX_COMMENTS
    assert all("ran CI" not in c["body"] for c in out)


# ── issue_document ────────────────────────────────────────────────────────────

def test_issue_document_labels_issue_vs_pr():
    issue_doc = ki.issue_document({"number": 7, "title": "Bug", "state": "open", "body": "broken"}, [])
    assert issue_doc.startswith("# Issue #7: Bug")

    pr_doc = ki.issue_document(
        {"number": 8, "title": "Fix", "state": "closed", "body": "patch", "pull_request": {}}, [])
    assert pr_doc.startswith("# Pull Request #8: Fix")


def test_issue_document_includes_comments():
    doc = ki.issue_document(
        {"number": 1, "title": "T", "state": "open", "body": "body text"},
        [{"author": "alice", "body": "try setting the flag"}],
    )
    assert "body text" in doc
    assert "Comment by alice" in doc
    assert "try setting the flag" in doc


# ── index_repo_issues (ChromaDB collection mocked) ────────────────────────────

def test_index_repo_issues_upserts_with_issue_metadata():
    issues = [{
        "number": 42, "title": "Collectory upload fails", "state": "open",
        "updated_at": "2024-03-01T00:00:00Z", "html_url": "https://x/42",
        "body": "Detailed reproduction steps for the collectory upload failure.",
        "comments": 0, "user": {"type": "User", "login": "h"},
    }]
    client = _client([_resp(200, issues)])
    collection = MagicMock()
    repo_meta = {"org": "AtlasOfLivingAustralia", "name": "collectory"}

    count, hwm = ki.index_repo_issues(repo_meta, collection, {}, client, since=None)

    assert count >= 1
    assert hwm == "2024-03-01T00:00:00Z"
    collection.delete.assert_called()  # idempotent cleanup per issue
    _, kwargs = collection.upsert.call_args
    assert all(m["content_type"] == "issue" for m in kwargs["metadatas"])
    assert kwargs["ids"][0].startswith("AtlasOfLivingAustralia/collectory:issue:42:")


def test_index_repo_issues_classifies_pr_and_advances_hwm():
    issues = [{
        "number": 9, "title": "Add retry logic", "state": "closed",
        "updated_at": "2024-04-02T00:00:00Z", "html_url": "https://x/9",
        "body": "This PR adds retry logic to the indexer to handle flaky uploads.",
        "comments": 0, "user": {"type": "User", "login": "h"},
        "pull_request": {"merged_at": "2024-04-02T00:00:00Z"},
    }]
    client = _client([_resp(200, issues)])
    collection = MagicMock()
    repo_meta = {"org": "living-atlases", "name": "la-toolkit"}

    count, hwm = ki.index_repo_issues(repo_meta, collection, {}, client, since="2024-01-01T00:00:00Z")

    assert count >= 1
    assert hwm == "2024-04-02T00:00:00Z"
    _, kwargs = collection.upsert.call_args
    assert all(m["content_type"] == "pr" for m in kwargs["metadatas"])
    assert all(m["is_pr"] is True and m["merged"] is True for m in kwargs["metadatas"])


def test_index_repo_issues_skips_bot_but_cleans_chunks():
    issues = [{
        "number": 5, "title": "Bump dep", "state": "open",
        "updated_at": "2024-05-01T00:00:00Z",
        "body": "automated bump", "comments": 0,
        "user": {"type": "Bot", "login": "dependabot[bot]"},
        "pull_request": {},
    }]
    client = _client([_resp(200, issues)])
    collection = MagicMock()
    repo_meta = {"org": "AtlasOfLivingAustralia", "name": "collectory"}

    count, hwm = ki.index_repo_issues(repo_meta, collection, {}, client, since=None)

    assert count == 0                       # bot PR not indexed
    assert hwm == "2024-05-01T00:00:00Z"    # but hwm still advances
    collection.delete.assert_called()       # stale chunks (if any) cleared
    collection.upsert.assert_not_called()


# ── issue_repos scope (ALA on by default, GBIF opt-in) ────────────────────────

def test_issue_repos_defaults_ala_on_gbif_off():
    manifest = {
        "orgs": {
            "AtlasOfLivingAustralia": {
                "base_url": "https://github.com/AtlasOfLivingAustralia",
                "repos": ["collectory", {"name": "logger-service", "issues": False}],
            },
            "living-atlases": {
                "base_url": "https://github.com/living-atlases",
                "repos": ["la-toolkit"],
            },
            "gbif": {
                "base_url": "https://github.com/gbif",
                "repos": ["registry", {"name": "pipelines", "issues": True}],
            },
        }
    }
    names = {f"{r['org']}/{r['name']}" for r in ki.issue_repos(manifest)}
    assert "AtlasOfLivingAustralia/collectory" in names      # ALA default on
    assert "living-atlases/la-toolkit" in names              # ALA default on
    assert "gbif/pipelines" in names                         # GBIF opt-in
    assert "AtlasOfLivingAustralia/logger-service" not in names  # explicit opt-out
    assert "gbif/registry" not in names                      # GBIF default off


# ── state roundtrip ───────────────────────────────────────────────────────────

def test_state_roundtrip(tmp_path, monkeypatch):
    target = tmp_path / "issues_state.json"
    monkeypatch.setattr(ki, "ISSUES_STATE_FILE", target)
    data = {"org/repo": {"since": "2024-01-01T00:00:00Z"}}
    ki.save_state(data)
    assert ki.load_state() == data
