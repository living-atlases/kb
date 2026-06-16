"""Tests for kb_releases.py — GitHub Releases ingestion (no network)."""

import json
from unittest.mock import MagicMock

import pytest

import kb_releases as kr


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
    headers = kr.load_github_headers()
    assert headers["Authorization"] == "Bearer abc123"


def test_headers_without_token(monkeypatch):
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    headers = kr.load_github_headers()
    assert "Authorization" not in headers


# ── fetch_releases ────────────────────────────────────────────────────────────

def test_fetch_releases_paginates_until_short_page():
    page1 = [{"tag_name": f"v{i}", "draft": False} for i in range(kr.PER_PAGE)]
    page2 = [{"tag_name": "v100", "draft": False}]
    client = _client([_resp(200, page1), _resp(200, page2)])
    releases = kr.fetch_releases("org", "repo", {}, client)
    assert len(releases) == kr.PER_PAGE + 1
    assert client.get.call_count == 2


def test_fetch_releases_skips_drafts():
    payload = [
        {"tag_name": "v1", "draft": False},
        {"tag_name": "v2-draft", "draft": True},
    ]
    client = _client([_resp(200, payload)])
    releases = kr.fetch_releases("org", "repo", {}, client)
    assert [r["tag_name"] for r in releases] == ["v1"]


def test_fetch_releases_404_returns_empty():
    client = _client([_resp(404)])
    assert kr.fetch_releases("org", "repo", {}, client) == []


def test_fetch_releases_rate_limited_raises():
    client = _client([_resp(403, headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "999"})])
    with pytest.raises(kr.RateLimited):
        kr.fetch_releases("org", "repo", {}, client)


# ── version_info ──────────────────────────────────────────────────────────────

def test_version_info_picks_latest_and_latest_stable():
    releases = [
        {"tag_name": "v2.0.0-rc1", "prerelease": True, "published_at": "2024-06-10T00:00:00Z", "html_url": "u1"},
        {"tag_name": "v1.9.0", "prerelease": False, "published_at": "2024-05-01T00:00:00Z", "html_url": "u2"},
    ]
    info = kr.version_info(releases)
    assert info["latest_tag"] == "v2.0.0-rc1"
    assert info["latest_stable_tag"] == "v1.9.0"
    assert info["prerelease"] is True


def test_version_info_none_when_empty():
    assert kr.version_info([]) is None


# ── release_document ──────────────────────────────────────────────────────────

def test_release_document_includes_tag_and_body():
    doc = kr.release_document({"tag_name": "v1.2.3", "name": "Spring", "published_at": "2024-01-01T00:00:00Z", "body": "Requires Java 17"})
    assert "v1.2.3" in doc
    assert "Requires Java 17" in doc


# ── versions.json roundtrip ───────────────────────────────────────────────────

def test_write_and_load_versions(tmp_path, monkeypatch):
    target = tmp_path / "versions.json"
    monkeypatch.setattr(kr, "VERSIONS_FILE", target)
    data = {"org/repo": {"latest_tag": "v1", "latest_stable_tag": "v1", "prerelease": False}}
    kr.write_versions(data)
    assert json.loads(target.read_text()) == data
    assert kr.load_versions() == data


# ── index_releases (ChromaDB collection mocked) ───────────────────────────────

def test_index_releases_upserts_with_release_metadata():
    payload = [{"tag_name": "v1.0.0", "draft": False, "prerelease": False,
                "published_at": "2024-01-01T00:00:00Z", "html_url": "https://x/r",
                "body": "Initial release. Requires biocache-service 2.x."}]
    client = _client([_resp(200, payload)])
    collection = MagicMock()
    repo_meta = {"org": "AtlasOfLivingAustralia", "name": "collectory"}

    count, info = kr.index_releases(repo_meta, collection, {}, client)

    assert count >= 1
    assert info["latest_tag"] == "v1.0.0"
    # cleared old release chunks before upsert
    collection.delete.assert_called_once()
    # upserted with content_type=release metadata + namespaced ids
    args, kwargs = collection.upsert.call_args
    assert all(m["content_type"] == "release" for m in kwargs["metadatas"])
    assert kwargs["ids"][0].startswith("AtlasOfLivingAustralia/collectory:release:v1.0.0:")
