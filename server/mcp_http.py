"""MCP HTTP server using FastMCP with streamable-HTTP transport."""

import httpx
from mcp.server.fastmcp import FastMCP

REST_API_URL = "http://localhost:8080"

mcp = FastMCP("living-atlas-kb")


async def handle_query(arguments: dict, http_client=None) -> str:
    """Query the KB via REST API and return formatted markdown."""
    if http_client is None:
        http_client = httpx.AsyncClient()

    question = arguments["question"]
    collection = arguments.get("collection", "la_toolkit_kb")
    n_results = min(arguments.get("n_results", 5), 10)

    response = await http_client.post(
        f"{REST_API_URL}/api/query",
        json={"question": question, "collection": collection, "n_results": n_results},
        timeout=30,
    )

    if response.status_code != 200:
        return f"Error querying KB: {response.status_code} — {response.json().get('detail', 'unknown error')}"

    results = response.json()["results"]
    if not results:
        return "No results found."

    lines = [f"# ALA KB Results for: {question}\n"]
    for i, r in enumerate(results, 1):
        meta = r["metadata"]
        repo = meta.get("repo", "unknown")
        file_path = meta.get("file", "")
        relevance = r["relevance"]
        lines.append(f"## Result {i} — `{repo}/{file_path}` (relevance: {relevance})")
        lines.append(f"```\n{r['content']}\n```\n")

    return "\n".join(lines)


async def handle_list_collections(arguments: dict, http_client=None) -> str:
    """List KB collections via REST API."""
    if http_client is None:
        http_client = httpx.AsyncClient()

    response = await http_client.get(f"{REST_API_URL}/api/collections", timeout=10)

    if response.status_code != 200:
        return f"Error: {response.status_code}"

    cols = response.json()["collections"]
    lines = ["# Living Atlas KB Collections\n"]
    for c in cols:
        lines.append(f"- **{c['name']}**: {c['count']} documents")
    return "\n".join(lines)


@mcp.tool()
async def query_ala_kb(question: str, collection: str = "la_toolkit_kb", n_results: int = 5) -> str:
    """Query the ALA (Atlas of Living Australia) Knowledge Base."""
    return await handle_query({"question": question, "collection": collection, "n_results": n_results})


@mcp.tool()
async def list_ala_kb_collections() -> str:
    """List available collections in the ALA Knowledge Base."""
    return await handle_list_collections({})


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=3000)
