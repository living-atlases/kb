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
from server.mcp_http import handle_query, handle_list_collections  # noqa: E402


async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="query_ala_kb",
            description="Query the ALA (Atlas of Living Australia) Knowledge Base. Contains documentation, code, and configuration from ALA/GBIF repositories.",
            inputSchema={
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "The question or search query about ALA/Living Atlas"},
                    "collection": {"type": "string", "default": "la_toolkit_kb", "description": "Which KB collection to query"},
                    "n_results": {"type": "integer", "default": 5, "minimum": 1, "maximum": 10, "description": "Number of results to return"},
                },
                "required": ["question"],
            },
        ),
        Tool(
            name="list_ala_kb_collections",
            description="List available collections in the ALA Knowledge Base with document counts.",
            inputSchema={"type": "object", "properties": {}},
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
        else:
            text = f"Unknown tool: {name}"
    return [TextContent(type="text", text=text)]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
