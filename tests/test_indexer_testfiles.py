"""Test-code indexing: kb_indexer tags test chunks and drops test fixtures."""

from unittest.mock import MagicMock

import pytest

import kb_indexer as ki
from kb_testfiles import TEST_CODE_EXTENSIONS, classify


def _write(root, rel, text):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "org" / "thing"
    _write(root, "src/main/java/Service.java", "class Service { void find() {} }")
    _write(root, "src/test/java/ServiceTest.java", "@Test\nvoid findsARecord() {}")
    _write(root, "src/test/groovy/ThingSpec.groovy", 'def "returns a thing"() {}')
    # Fixtures living in the same tree as the tests.
    _write(root, "src/test/resources/expected.json", '{"a": ' + '1,' * 400 + "1}")
    _write(root, "src/test/resources/config.xml", "<a>" + "x" * 2000 + "</a>")
    return root


def _index(monkeypatch, repo_dir, blocklist=()):
    monkeypatch.setattr(ki, "REPOS_DIR", repo_dir.parent.parent)
    collection = MagicMock()
    meta = {"org": "org", "name": "thing", "content_type": "source"}
    ki.index_repo(meta, collection, list(blocklist))
    metas = []
    for call in collection.upsert.call_args_list:
        metas.extend(call.kwargs["metadatas"])
    return metas


def test_test_code_is_indexed_and_tagged(repo, monkeypatch):
    metas = _index(monkeypatch, repo)
    by_type = {}
    for m in metas:
        by_type.setdefault(m["content_type"], set()).add(m["file"])

    assert by_type["source"] == {"src/main/java/Service.java"}
    assert by_type["test"] == {
        "src/test/java/ServiceTest.java",
        "src/test/groovy/ThingSpec.groovy",
    }


def test_test_resources_are_not_indexed(repo, monkeypatch):
    """The fixtures are 78% of the volume and answer nothing asked in prose."""
    files = {m["file"] for m in _index(monkeypatch, repo)}
    assert "src/test/resources/expected.json" not in files
    assert "src/test/resources/config.xml" not in files


def test_production_code_keeps_the_repo_content_type(repo, monkeypatch):
    metas = _index(monkeypatch, repo)
    main = [m for m in metas if m["file"] == "src/main/java/Service.java"]
    assert main and all(m["content_type"] == "source" for m in main)


def test_wiki_and_faq_repos_are_never_retagged_as_test(tmp_path, monkeypatch):
    """content_type comes from the repo for non-source trees; a page called
    `tests.md` in a wiki is documentation, not a test."""
    root = tmp_path / "org" / "thing.wiki"
    _write(root, "tests.md", "# How we test\n" + "prose " * 200)
    monkeypatch.setattr(ki, "REPOS_DIR", root.parent.parent)
    collection = MagicMock()
    ki.index_repo(
        {"org": "org", "name": "thing.wiki", "content_type": "wiki"}, collection, [],
    )
    metas = [m for c in collection.upsert.call_args_list for m in c.kwargs["metadatas"]]
    assert metas and all(m["content_type"] == "wiki" for m in metas)


def test_every_test_code_extension_classifies_as_a_test():
    """The extension allowlist and the classifier must agree, or a file is
    skipped as a fixture while still being test code."""
    for ext in TEST_CODE_EXTENSIONS:
        rel = f"src/test/x/Foo{ext}" if ext not in (".py", ".dart") else f"tests/test_foo{ext}"
        assert classify(rel, rel.split("/")[-1], "") != "main", ext
