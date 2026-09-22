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


@pytest.mark.asyncio
async def test_list_collections_reports_timeout_instead_of_empty_error(mock_httpx_client):
    """A timeout must name itself.

    httpx timeout exceptions stringify to '', so an unhandled one reached the
    client as "Error executing tool <name>: " with nothing after the colon.
    """
    mock_httpx_client.get.side_effect = httpx.ReadTimeout("")

    from server.mcp_http import handle_list_collections
    result = await handle_list_collections({}, http_client=mock_httpx_client)

    assert "ReadTimeout" in result
    assert "la-toolkit-kb-api" in result


@pytest.mark.asyncio
async def test_query_reports_connection_error(mock_httpx_client):
    mock_httpx_client.post.side_effect = httpx.ConnectError("connection refused")

    from server.mcp_http import handle_query
    result = await handle_query({"question": "test"}, http_client=mock_httpx_client)

    assert "ConnectError" in result


@pytest.mark.asyncio
async def test_testing_tool_formats_table(mock_httpx_client):
    mock_httpx_client.get.return_value = MagicMock(
        status_code=200,
        json=lambda: {
            "gbif/pipelines": {
                "status": "ok", "stack": ["maven"], "main_loc": 97035,
                "unit": {"cases": 988, "files": 218},
                "integration": {"cases": 138, "files": 36},
                "e2e": {"cases": 0, "files": 0},
                "total_cases": 1126, "cases_per_kloc": 11.6,
                "coverage_tools": ["sonar"],
            },
            "AtlasOfLivingAustralia/ala-bie": {"status": "not_cloned"},
        },
    )

    from server.mcp_http import handle_testing
    result = await handle_testing({}, http_client=mock_httpx_client)

    assert "gbif/pipelines" in result
    assert "1126" in result
    assert "sonar" in result
    # Repos that were never cloned have no counts to show.
    assert "ala-bie" not in result


@pytest.mark.asyncio
async def test_testing_tool_filters_by_org(mock_httpx_client):
    mock_httpx_client.get.return_value = MagicMock(
        status_code=200,
        json=lambda: {
            "gbif/ipt": {
                "status": "ok", "stack": ["maven"], "main_loc": 66703,
                "unit": {"cases": 398, "files": 79},
                "integration": {"cases": 15, "files": 6},
                "e2e": {"cases": 0, "files": 0},
                "total_cases": 413, "cases_per_kloc": 6.2, "coverage_tools": [],
            },
            "AtlasOfLivingAustralia/collectory": {
                "status": "ok", "stack": ["grails"], "main_loc": 58427,
                "unit": {"cases": 116, "files": 7},
                "integration": {"cases": 0, "files": 0},
                "e2e": {"cases": 0, "files": 0},
                "total_cases": 116, "cases_per_kloc": 2.0, "coverage_tools": [],
            },
        },
    )

    from server.mcp_http import handle_testing
    result = await handle_testing({"org": "gbif"}, http_client=mock_httpx_client)

    assert "gbif/ipt" in result
    assert "collectory" not in result


@pytest.mark.asyncio
async def test_testing_tool_reports_missing_repo(mock_httpx_client):
    mock_httpx_client.get.return_value = MagicMock(status_code=404)

    from server.mcp_http import handle_testing
    result = await handle_testing({"repo": "foo/bar"}, http_client=mock_httpx_client)

    assert "No test data for 'foo/bar'" in result


@pytest.mark.asyncio
async def test_testing_tool_names_the_exception_on_timeout(mock_httpx_client):
    mock_httpx_client.get.side_effect = httpx.ReadTimeout("")

    from server.mcp_http import handle_testing
    result = await handle_testing({}, http_client=mock_httpx_client)

    assert "ReadTimeout" in result
