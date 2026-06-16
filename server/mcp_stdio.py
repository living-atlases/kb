"""MCP stdio server — local use via SSH. Calls REST API on localhost."""

import os
import asyncio
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
import httpx

# When running locally on the server, REST API is on localhost
REST_API_URL = os.environ.get("KB_API_URL", "http://localhost:8080")

# Re-use handler functions from mcp_http
from server.mcp_http import (  # noqa: E402
    handle_list_collections,
    handle_query,
    handle_versions,
)


async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="query_ala_kb",
            description="Query the ALA (Atlas of Living Australia) Knowledge Base. Contains documentation, code, configuration, and GitHub release notes from ALA/GBIF repositories.",
            inputSchema={
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "The question or search query about ALA/Living Atlas"},
                    "collection": {"type": "string", "default": "la_toolkit_kb", "description": "Which KB collection to query"},
                    "n_results": {"type": "integer", "default": 5, "minimum": 1, "maximum": 10, "description": "Number of results to return"},
                    "content_type": {"type": "string", "enum": ["release", "source"], "description": "Optionally restrict to 'release' (release notes/changelogs) or 'source' (repo files)"},
                },
                "required": ["question"],
            },
        ),
        Tool(
            name="list_ala_kb_collections",
            description="List available collections in the ALA Knowledge Base with document counts.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="get_ala_component_versions",
            description="Latest release/version of ALA components (from GitHub Releases). Useful for keeping deployment dependency lists up to date.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "Component as 'ORG/NAME' (e.g. 'AtlasOfLivingAustralia/collectory'); omit for all"},
                },
            },
        ),
    ]


app = Server("living-atlas-kb-local")
app.list_tools()(list_tools)


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    async with httpx.AsyncClient() as client:
        if name == "query_ala_kb":
            text = await handle_query(arguments, http_client=client)
        elif name == "list_ala_kb_collections":
            text = await handle_list_collections(arguments, http_client=client)
        elif name == "get_ala_component_versions":
            text = await handle_versions(arguments, http_client=client)
        else:
            text = f"Unknown tool: {name}"
    return [TextContent(type="text", text=text)]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
