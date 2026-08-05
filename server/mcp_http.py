"""MCP HTTP server using FastMCP with streamable-HTTP transport."""

import httpx
from mcp.server.fastmcp import FastMCP

REST_API_URL = "http://localhost:8080"

# The REST API answers in milliseconds when healthy, but a ChromaDB operation
# can stall it for far longer. 10s was tight enough that any hiccup surfaced as
# a bare timeout, so give the plain lookups real headroom.
API_TIMEOUT = 60
ANSWER_TIMEOUT = 180

mcp = FastMCP("living-atlas-kb", host="127.0.0.1", port=3000)

_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    """Return the shared HTTP client, creating it on first use.

    Handlers used to build a fresh AsyncClient per call and never close it,
    leaking a connection pool on every tool invocation.
    """
    global _client
    if _client is None:
        _client = httpx.AsyncClient()
    return _client


def api_error(exc: Exception) -> str:
    """Render a failed REST call as a message that says what actually happened.

    httpx timeout exceptions stringify to the empty string, so an unhandled one
    reached the MCP client as "Error executing tool <name>: " with nothing after
    the colon — the symptom that made a wedged API take an hour to diagnose.
    Always name the exception class.
    """
    if isinstance(exc, httpx.TimeoutException):
        return (
            f"Error: the KB REST API did not respond in time ({type(exc).__name__}). "
            "It is likely busy or wedged — check the la-toolkit-kb-api service."
        )
    return f"Error contacting the KB REST API: {type(exc).__name__}: {exc}"


async def handle_query(arguments: dict, http_client=None) -> str:
    """Query the KB via REST API and return formatted markdown."""
    if http_client is None:
        http_client = get_client()

    question = arguments["question"]
    collection = arguments.get("collection", "la_toolkit_kb")
    n_results = min(arguments.get("n_results", 5), 10)
    content_type = arguments.get("content_type")

    payload = {"question": question, "collection": collection, "n_results": n_results}
    if content_type:
        payload["content_type"] = content_type

    try:
        response = await http_client.post(
            f"{REST_API_URL}/api/query",
            json=payload,
            timeout=API_TIMEOUT,
        )
    except httpx.RequestError as e:
        return api_error(e)

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


async def handle_answer(arguments: dict, http_client=None) -> str:
    """Get a RAG-synthesised, cited answer via REST API; format as markdown."""
    if http_client is None:
        http_client = get_client()

    question = arguments["question"]
    collection = arguments.get("collection", "la_toolkit_kb")
    n_results = min(arguments.get("n_results", 8), 10)
    content_type = arguments.get("content_type")

    payload = {"question": question, "collection": collection, "n_results": n_results}
    if content_type:
        payload["content_type"] = content_type

    try:
        response = await http_client.post(
            f"{REST_API_URL}/api/answer",
            json=payload,
            timeout=ANSWER_TIMEOUT,
        )
    except httpx.RequestError as e:
        return api_error(e)

    if response.status_code != 200:
        detail = "unknown error"
        try:
            detail = response.json().get("detail", detail)
        except Exception:
            pass
        return f"Error answering from KB: {response.status_code} — {detail}"

    data = response.json()
    lines = [data.get("answer", "").strip(), "", "## Sources"]
    for s in data.get("sources", []):
        loc = f"{s['repo']}/{s['file']}" if s.get("file") else s["repo"]
        lines.append(f"- [{s['n']}] `{loc}` (relevance: {s['relevance']})")
    return "\n".join(lines)


async def handle_versions(arguments: dict, http_client=None) -> str:
    """Fetch component version metadata via REST API and format as markdown."""
    if http_client is None:
        http_client = get_client()

    repo = arguments.get("repo")
    path = f"/api/versions/{repo}" if repo else "/api/versions"
    try:
        response = await http_client.get(f"{REST_API_URL}{path}", timeout=API_TIMEOUT)
    except httpx.RequestError as e:
        return api_error(e)

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
        http_client = get_client()

    try:
        response = await http_client.get(f"{REST_API_URL}/api/collections", timeout=API_TIMEOUT)
    except httpx.RequestError as e:
        return api_error(e)

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
async def answer_ala_kb(
    question: str,
    collection: str = "la_toolkit_kb",
    n_results: int = 8,
    content_type: str | None = None,
) -> str:
    """Answer a question about the ALA / Living Atlas ecosystem.

    Unlike query_ala_kb (which returns raw chunks), this returns a synthesised
    answer composed by an LLM from the knowledge base, followed by a numbered
    list of the sources it cited. Best for non-Claude clients or when you want a
    ready-to-use answer; for your own synthesis, use query_ala_kb.

    content_type: optionally restrict retrieval to 'faq', 'wiki', 'source' or
    'release'. Omit for all.
    """
    return await handle_answer(
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
