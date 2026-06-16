"""MCP HTTP server using FastMCP with streamable-HTTP transport."""

import httpx
from mcp.server.fastmcp import FastMCP

REST_API_URL = "http://localhost:8080"

mcp = FastMCP("living-atlas-kb", host="127.0.0.1", port=3000)


async def handle_query(arguments: dict, http_client=None) -> str:
    """Query the KB via REST API and return formatted markdown."""
    if http_client is None:
        http_client = httpx.AsyncClient()

    question = arguments["question"]
    collection = arguments.get("collection", "la_toolkit_kb")
    n_results = min(arguments.get("n_results", 5), 10)
    content_type = arguments.get("content_type")

    payload = {"question": question, "collection": collection, "n_results": n_results}
    if content_type:
        payload["content_type"] = content_type

    response = await http_client.post(
        f"{REST_API_URL}/api/query",
        json=payload,
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
        relevance = r["relevance"]
        if meta.get("content_type") == "release":
            tag = meta.get("tag", "")
            loc = f"`{repo}` release {tag}"
            if meta.get("url"):
                loc += f" — {meta['url']}"
        else:
            loc = f"`{repo}/{meta.get('file', '')}`"
        lines.append(f"## Result {i} — {loc} (relevance: {relevance})")
        lines.append(f"```\n{r['content']}\n```\n")

    return "\n".join(lines)


async def handle_versions(arguments: dict, http_client=None) -> str:
    """Fetch component version metadata via REST API and format as markdown."""
    if http_client is None:
        http_client = httpx.AsyncClient()

    repo = arguments.get("repo")
    path = f"/api/versions/{repo}" if repo else "/api/versions"
    response = await http_client.get(f"{REST_API_URL}{path}", timeout=10)

    if response.status_code == 404:
        return f"No version data for '{repo}'."
    if response.status_code != 200:
        return f"Error: {response.status_code}"

    data = response.json()
    if repo:
        data = {repo: data}
    if not data:
        return "No version data available yet."

    lines = ["# Living Atlas component versions\n"]
    for key in sorted(data):
        v = data[key]
        stable = v.get("latest_stable_tag") or "—"
        latest = v.get("latest_tag") or "—"
        date = (v.get("published_at") or "")[:10]
        lines.append(f"- **{key}**: stable `{stable}`, latest `{latest}` ({date})")
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
async def query_ala_kb(
    question: str,
    collection: str = "la_toolkit_kb",
    n_results: int = 5,
    content_type: str | None = None,
) -> str:
    """Query the ALA (Atlas of Living Australia) Knowledge Base.

    content_type: optionally restrict results to 'release' (GitHub release notes /
    changelogs) or 'source' (repo files). Omit for both.
    """
    return await handle_query(
        {
            "question": question,
            "collection": collection,
            "n_results": n_results,
            "content_type": content_type,
        }
    )


@mcp.tool()
async def list_ala_kb_collections() -> str:
    """List available collections in the ALA Knowledge Base."""
    return await handle_list_collections({})


@mcp.tool()
async def get_ala_component_versions(repo: str | None = None) -> str:
    """Latest release/version of ALA components, from GitHub Releases.

    Pass repo as 'ORG/NAME' (e.g. 'AtlasOfLivingAustralia/collectory') for one
    component, or omit for all. Useful for keeping deployment dependency lists
    (e.g. la-toolkit-backend/assets/dependencies.yaml) up to date.
    """
    return await handle_versions({"repo": repo})


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
