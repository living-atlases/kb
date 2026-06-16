import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient


@pytest.fixture
def mock_chroma():
    """Mock ChromaDB collection."""
    col = MagicMock()
    col.query.return_value = {
        "documents": [["content of doc 1", "content of doc 2"]],
        "metadatas": [[
            {"repo": "collectory", "file": "grails-app/conf/application.groovy", "chunk": 0, "description": "Config"},
            {"repo": "ala-install", "file": "ansible/roles/collectory/tasks/main.yml", "chunk": 0, "description": "Tasks"},
        ]],
        "distances": [[0.3, 0.5]],
    }
    return col


@pytest.fixture
def mock_client(mock_chroma):
    """Mock ChromaDB PersistentClient."""
    client = MagicMock()
    client.get_collection.return_value = mock_chroma
    col1 = MagicMock()
    col1.name = "la_toolkit_kb"
    col1.count = lambda: 3671
    col2 = MagicMock()
    col2.name = "la-toolkit-tier1"
    col2.count = lambda: 858
    client.list_collections.return_value = [col1, col2]
    return client


@pytest.fixture
def mock_embed():
    """Mock SentenceTransformer; embed_model.encode([...]).tolist() -> vectors."""
    emb = MagicMock()
    emb.encode.return_value.tolist.return_value = [[0.1, 0.2, 0.3]]
    return emb


@pytest.fixture
def test_client(mock_client, mock_embed):
    import server.api as api_module
    original_client = api_module.chroma_client
    original_embed = api_module.embed_model
    api_module.chroma_client = mock_client
    api_module.embed_model = mock_embed
    from server.api import app
    client = TestClient(app)
    yield client
    api_module.chroma_client = original_client
    api_module.embed_model = original_embed


def test_query_returns_results(test_client, mock_chroma):
    response = test_client.post("/api/query", json={"question": "collectory database config"})
    assert response.status_code == 200
    data = response.json()
    assert len(data["results"]) == 2
    assert data["results"][0]["metadata"]["repo"] == "collectory"
    assert 0.0 <= data["results"][0]["relevance"] <= 1.0
    assert "content of doc 1" in data["results"][0]["content"]


def test_query_default_collection(test_client, mock_client):
    test_client.post("/api/query", json={"question": "test"})
    mock_client.get_collection.assert_called_with("la_toolkit_kb")


def test_query_custom_collection(test_client, mock_client):
    test_client.post("/api/query", json={"question": "test", "collection": "la-toolkit-tier1"})
    mock_client.get_collection.assert_called_with("la-toolkit-tier1")


def test_query_content_type_adds_where_filter(test_client, mock_chroma):
    test_client.post("/api/query", json={"question": "what changed", "content_type": "release"})
    _, kwargs = mock_chroma.query.call_args
    assert kwargs["where"] == {"content_type": "release"}


def test_query_without_content_type_has_no_where(test_client, mock_chroma):
    test_client.post("/api/query", json={"question": "test"})
    _, kwargs = mock_chroma.query.call_args
    assert "where" not in kwargs


def test_query_n_results_capped_at_10(test_client, mock_chroma):
    # n_results > 10 is rejected by pydantic validation (le=10 constraint)
    response = test_client.post("/api/query", json={"question": "test", "n_results": 99})
    assert response.status_code == 422


def test_query_missing_question_returns_422(test_client):
    response = test_client.post("/api/query", json={})
    assert response.status_code == 422


def test_collections_returns_list(test_client):
    response = test_client.get("/api/collections")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["collections"], list)
    assert len(data["collections"]) == 2
    names = [c["name"] for c in data["collections"]]
    assert "la_toolkit_kb" in names


def test_health_check(test_client):
    response = test_client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_versions_endpoint_reads_file(test_client, tmp_path):
    import server.api as api_module
    vfile = tmp_path / "versions.json"
    vfile.write_text('{"AtlasOfLivingAustralia/collectory": {"latest_tag": "v3.2.5"}}')
    original = api_module.VERSIONS_FILE
    api_module.VERSIONS_FILE = str(vfile)
    try:
        all_resp = test_client.get("/api/versions")
        assert all_resp.status_code == 200
        assert all_resp.json()["AtlasOfLivingAustralia/collectory"]["latest_tag"] == "v3.2.5"

        one_resp = test_client.get("/api/versions/AtlasOfLivingAustralia/collectory")
        assert one_resp.status_code == 200
        assert one_resp.json()["latest_tag"] == "v3.2.5"

        missing = test_client.get("/api/versions/foo/bar")
        assert missing.status_code == 404
    finally:
        api_module.VERSIONS_FILE = original


def test_versions_endpoint_empty_when_no_file(test_client, tmp_path):
    import server.api as api_module
    original = api_module.VERSIONS_FILE
    api_module.VERSIONS_FILE = str(tmp_path / "nonexistent.json")
    try:
        resp = test_client.get("/api/versions")
        assert resp.status_code == 200
        assert resp.json() == {}
    finally:
        api_module.VERSIONS_FILE = original
