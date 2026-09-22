"""Tests for ansible/repos.yml — the repository manifest and index blocklist.

The manifest is data, but kb_indexer reads it directly: a typo in an org key, a
duplicated repo, or a blocklist pattern that does not match what it claims to
match all change what ends up in the index. These tests pin that contract
against the real manifest shipped in this repo.
"""

from pathlib import Path

import pytest
import yaml

import kb_indexer as ki

MANIFEST_PATH = Path(__file__).resolve().parent.parent / "ansible" / "repos.yml"


@pytest.fixture(scope="module")
def manifest() -> dict:
    with open(MANIFEST_PATH) as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def repos(manifest) -> list[dict]:
    return ki.expand_repos(manifest)


@pytest.fixture(scope="module")
def blocklist(manifest) -> list[str]:
    return ki.get_blocklist(manifest)


def _by_key(repos: list[dict]) -> dict[str, dict]:
    return {f"{r['org']}/{r['name']}": r for r in repos}


# ── Manifest shape ────────────────────────────────────────────────────────────

def test_every_org_has_a_base_url(manifest):
    for org, cfg in manifest["orgs"].items():
        assert cfg["base_url"].startswith("https://github.com/"), org


def test_no_duplicate_repo_entries(repos):
    keys = [f"{r['org']}/{r['name']}" for r in repos]
    dupes = {k for k in keys if keys.count(k) > 1}
    assert not dupes


def test_tier1_entries_all_exist_in_the_manifest(manifest, repos):
    assert ki.tier1_keys(manifest) <= set(_by_key(repos))


def test_urls_are_built_from_base_url_and_name(repos):
    entry = _by_key(repos)["AtlasOfLivingAustralia/collectory"]
    assert entry["url"] == "https://github.com/AtlasOfLivingAustralia/collectory.git"


def test_repos_default_to_auto_detected_head(repos):
    """No `branch:` override means None → clone the remote's default branch."""
    assert _by_key(repos)["AtlasOfLivingAustralia/quail"]["branch"] is None


def test_wiki_flag_emits_a_companion_wiki_entry(repos):
    wiki = _by_key(repos)["AtlasOfLivingAustralia/biocache-service.wiki"]
    assert wiki["is_wiki"] is True
    assert wiki["url"].endswith("/biocache-service.wiki.git")


def test_ala_repos_index_issues_by_default_and_gbif_does_not(repos):
    by_key = _by_key(repos)
    assert by_key["AtlasOfLivingAustralia/quail"]["index_issues"] is True
    assert by_key["gbif/occurrence"]["index_issues"] is False


def test_quail_is_indexed(repos):
    entry = _by_key(repos)["AtlasOfLivingAustralia/quail"]
    assert entry["url"] == "https://github.com/AtlasOfLivingAustralia/quail.git"
    assert entry["content_type"] == "source"
    assert entry["description"]


# ── Blocklist semantics ───────────────────────────────────────────────────────

def test_directory_patterns_match_a_component_at_any_depth(blocklist):
    assert ki.is_blocked(Path("help/build/html/index.html"), blocklist)
    assert ki.is_blocked(Path("grails-app/assets/javascripts/app.js"), blocklist)


def test_directory_patterns_do_not_match_a_file_of_the_same_name(blocklist):
    assert not ki.is_blocked(Path("quail/build.py"), blocklist)


@pytest.mark.parametrize(
    "rel",
    [
        "quail/resources.py",      # Qt rcc output: 915 KB of base64 blobs
        "web-app/js/jquery.min.js",
        "package-lock.json",
    ],
)
def test_generated_files_are_blocked(blocklist, rel):
    assert ki.is_blocked(Path(rel), blocklist)


@pytest.mark.parametrize(
    "rel",
    [
        "quail/quail.py",
        "quail/vocab.py",
        "help/source/getting_started.rst",
        "README.md",
        "grails-app/services/au/org/ala/Foo.groovy",
    ],
)
def test_real_source_survives_the_blocklist(blocklist, rel):
    assert not ki.is_blocked(Path(rel), blocklist)


# ── Superseded components ─────────────────────────────────────────────────────

def _repo_entries(manifest):
    for org, cfg in manifest["orgs"].items():
        for entry in cfg.get("repos", []):
            if isinstance(entry, dict):
                yield org, entry


def test_superseded_by_resolves_to_an_indexed_repo(manifest):
    """A successor nobody indexes is a dangling pointer in every report."""
    known = {f"{org}/{e['name'] if isinstance(e, dict) else e}"
             for org, cfg in manifest["orgs"].items()
             for e in cfg.get("repos", [])}
    marked = [(org, e) for org, e in _repo_entries(manifest) if e.get("superseded_by")]
    assert marked, "the manifest records no supersessions at all"
    for org, entry in marked:
        assert entry["superseded_by"] in known, f"{org}/{entry['name']}"


def test_superseded_entries_explain_themselves(manifest):
    """The note is what a reader sees; an unexplained 'legacy' tag is worse
    than none, because 'UI replaced (90%)' and 'fully replaced' differ."""
    for org, entry in _repo_entries(manifest):
        if entry.get("superseded_by"):
            note = entry.get("superseded_note", "")
            assert note and len(note) > 20, f"{org}/{entry['name']}"


def test_nothing_is_recorded_as_superseding_itself(manifest):
    for org, entry in _repo_entries(manifest):
        if entry.get("superseded_by"):
            assert entry["superseded_by"] != f"{org}/{entry['name']}"


def test_test_code_is_no_longer_blocked(blocklist):
    """Test *code* is indexed (tagged content_type=test); only fixtures are not."""
    assert not ki.is_blocked(Path("src/test/java/au/org/ala/FooTest.java"), blocklist)
    assert not ki.is_blocked(Path("src/integration-test/groovy/FooSpec.groovy"), blocklist)
    assert ki.is_blocked(Path("src/test/resources/datasets/x-usages.json"), blocklist)
    assert ki.is_blocked(Path("test/fixtures/sample.json"), blocklist)
