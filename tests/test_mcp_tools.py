import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
import httpx


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
