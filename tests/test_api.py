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
