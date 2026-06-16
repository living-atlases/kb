import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
import httpx


# We test the tool handler functions directly, not the MCP transport layer
# The handlers call the REST API via httpx

@pytest.fixture
def mock_httpx_client():
    client = AsyncMock(spec=httpx.AsyncClient)
    return client


@pytest.mark.asyncio
async def test_query_tool_formats_results(mock_httpx_client):
    mock_httpx_client.post.return_value = MagicMock(
        status_code=200,
        json=lambda: {
            "results": [
                {
                    "content": "grails { ... }",
                    "metadata": {"repo": "collectory", "file": "conf/app.groovy", "chunk": 0},
                    "relevance": 0.7,
                }
            ]
        }
    )

    from server.mcp_http import handle_query
    result = await handle_query(
        {"question": "collectory config", "collection": "la_toolkit_kb", "n_results": 1},
        http_client=mock_httpx_client,
    )

    assert "collectory/conf/app.groovy" in result
    assert "relevance: 0.7" in result
    assert "grails { ... }" in result


@pytest.mark.asyncio
async def test_query_tool_handles_api_error(mock_httpx_client):
    mock_httpx_client.post.return_value = MagicMock(
        status_code=404,
        json=lambda: {"detail": "Collection not found"},
    )

    from server.mcp_http import handle_query
    result = await handle_query(
        {"question": "test", "collection": "nonexistent"},
        http_client=mock_httpx_client,
    )

    assert "Error" in result


@pytest.mark.asyncio
async def test_answer_tool_formats_answer_and_sources(mock_httpx_client):
    mock_httpx_client.post.return_value = MagicMock(
        status_code=200,
        json=lambda: {
            "answer": "Set the filter pattern [1].",
            "sources": [
                {"n": 1, "repo": "AtlasOfLivingAustralia/ala-install", "file": "config.properties",
                 "content_type": "source", "relevance": 0.62},
            ],
        },
    )

    from server.mcp_http import handle_answer
    result = await handle_answer(
        {"question": "require login on downloads", "n_results": 8},
        http_client=mock_httpx_client,
    )

    assert "Set the filter pattern [1]." in result
    assert "## Sources" in result
    assert "[1] `AtlasOfLivingAustralia/ala-install/config.properties`" in result


@pytest.mark.asyncio
async def test_answer_tool_handles_api_error(mock_httpx_client):
    mock_httpx_client.post.return_value = MagicMock(
        status_code=503,
        json=lambda: {"detail": "Ollama not available"},
    )

    from server.mcp_http import handle_answer
    result = await handle_answer({"question": "test"}, http_client=mock_httpx_client)

    assert "Error" in result
    assert "Ollama not available" in result


@pytest.mark.asyncio
async def test_list_collections_tool(mock_httpx_client):
    mock_httpx_client.get.return_value = MagicMock(
        status_code=200,
        json=lambda: {
            "collections": [
                {"name": "la_toolkit_kb", "count": 3671},
                {"name": "la-toolkit-tier1", "count": 858},
            ]
        }
    )

    from server.mcp_http import handle_list_collections
    result = await handle_list_collections({}, http_client=mock_httpx_client)

    assert "la_toolkit_kb" in result
    assert "3671" in result
