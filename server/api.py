"""FastAPI REST service for Living Atlas Knowledge Base."""

import os
from contextlib import asynccontextmanager
from typing import Optional

import chromadb
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

try:
    from chat import build_prompt, stream_ollama
except ImportError:
    from server.chat import build_prompt, stream_ollama

CHROMA_PATH = os.environ.get("CHROMA_PATH", "/opt/la-toolkit-kb/data/chromadb/")

chroma_client: Optional[chromadb.PersistentClient] = None  # set on startup


@asynccontextmanager
async def lifespan(app: FastAPI):
    global chroma_client
    chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
    yield


app = FastAPI(title="Living Atlas KB API", lifespan=lifespan)


class QueryRequest(BaseModel):
    question: str
    collection: str = "la_toolkit_kb"
    n_results: int = Field(default=5, ge=1, le=10)


class QueryResult(BaseModel):
    content: str
    metadata: dict
    relevance: float


class QueryResponse(BaseModel):
    results: list[QueryResult]


class CollectionInfo(BaseModel):
    name: str
    count: int


class CollectionsResponse(BaseModel):
    collections: list[CollectionInfo]


class ChatRequest(BaseModel):
    question: str
    collection: str = "la_toolkit_kb"
    n_results: int = Field(default=5, ge=1, le=10)


@app.get("/", response_class=HTMLResponse)
def home():
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Living Atlas Knowledge Base</title>
  <style>
    body { font-family: sans-serif; max-width: 860px; margin: 60px auto; padding: 0 20px; color: #333; line-height: 1.6; }
    h1 { color: #2c7a4b; }
    h2 { color: #2c7a4b; border-bottom: 1px solid #ddd; padding-bottom: 4px; margin-top: 40px; }
    code { background: #f4f4f4; padding: 2px 6px; border-radius: 3px; font-size: 0.9em; }
    pre { background: #f4f4f4; padding: 16px; border-radius: 6px; overflow-x: auto; font-size: 0.88em; }
    a { color: #2c7a4b; }
    .endpoint { margin: 10px 0; }
    .badge { display: inline-block; background: #2c7a4b; color: white; border-radius: 3px; padding: 1px 7px; font-size: 0.8em; font-weight: bold; margin-right: 6px; }
    .badge.post { background: #1565c0; }
    .badge.get { background: #2c7a4b; }
    ul { padding-left: 20px; }
  </style>
</head>
<body>
  <h1>Living Atlas Knowledge Base</h1>
  <p>
    The <strong>Living Atlas Knowledge Base</strong> is an AI-powered semantic search system over the
    documentation, configuration, and source code of the
    <a href="https://living-atlas.org" target="_blank">Living Atlas</a> and
    <a href="https://www.gbif.org" target="_blank">GBIF</a> ecosystem.
    It is built to help portal administrators, developers, and data managers quickly find answers
    about deploying and configuring ALA/Living Atlas services such as
    <em>biocache, collectory, spatial-hub, ala-bie, image-service, species-lists</em>, and many more.
  </p>
  <p>
    The knowledge base indexes content from multiple repositories (ala-install, la-toolkit,
    gbif-pipelines, collectory, biocache-service, biocache-hubs, ala-bie-hub, spatial-hub,
    image-service, species-lists, etc.) and uses
    <a href="https://www.trychroma.com/" target="_blank">ChromaDB</a> with
    sentence-transformers embeddings for semantic retrieval.
  </p>

  <h2>REST API</h2>
  <p>Query the knowledge base programmatically from any HTTP client.</p>
  <div class="endpoint"><span class="badge get">GET</span> <code>/health</code> — Health check</div>
  <div class="endpoint"><span class="badge get">GET</span> <code>/api/collections</code> — List available collections and document counts</div>
  <div class="endpoint"><span class="badge post">POST</span> <code>/api/query</code> — Semantic search query</div>

  <h3>Example query</h3>
  <pre>curl -X POST https://kb.l-a.site/api/query \\
  -H 'Content-Type: application/json' \\
  -d '{
    "question": "How to configure biocache-service?",
    "collection": "la_toolkit_kb",
    "n_results": 5
  }'</pre>

  <h2>MCP Server (AI assistant integration)</h2>
  <p>
    The knowledge base also exposes an
    <a href="https://modelcontextprotocol.io/" target="_blank">MCP (Model Context Protocol)</a> server,
    allowing AI assistants such as <strong>Claude</strong>, <strong>Cursor</strong>, or any MCP-compatible
    client to query it directly as a tool during a conversation.
  </p>
  <p>
    The MCP server is available at <code>https://kb.l-a.site/mcp</code> using the
    <strong>Streamable HTTP</strong> transport.
  </p>
  <h3>Configure in Claude Desktop / OpenCode</h3>
  <pre>{
  "mcpServers": {
    "ala-kb": {
      "type": "http",
      "url": "https://kb.l-a.site/mcp"
    }
  }
}</pre>
  <h3>Available MCP tools</h3>
  <ul>
    <li><code>query_ala_kb</code> — Semantic search over the Living Atlas knowledge base</li>
    <li><code>list_ala_kb_collections</code> — List available document collections</li>
  </ul>

  <h2>Interactive API docs</h2>
  <p><a href="/docs">Swagger UI</a> · <a href="/redoc">ReDoc</a></p>
</body>
</html>"""


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/query", response_model=QueryResponse)
def query(req: QueryRequest):
    try:
        col = chroma_client.get_collection(req.collection)
    except Exception:
        raise HTTPException(status_code=404, detail=f"Collection '{req.collection}' not found")

    results = col.query(
        query_texts=[req.question],
        n_results=req.n_results,
        include=["documents", "metadatas", "distances"],
    )

    items = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        items.append(QueryResult(
            content=doc[:3000],
            metadata=meta,
            relevance=round(1 - dist, 3),
        ))

    return QueryResponse(results=items)


@app.get("/api/collections", response_model=CollectionsResponse)
def list_collections():
    cols = chroma_client.list_collections()
    return CollectionsResponse(collections=[
        CollectionInfo(name=c.name, count=c.count()) for c in cols
    ])


async def _chat_sse_generator(req: ChatRequest):
    """Fetch context from ChromaDB, stream Ollama response as SSE."""
    try:
        col = chroma_client.get_collection(req.collection)
    except Exception:
        yield f"data: {{\"error\": \"Collection '{req.collection}' not found\"}}\n\n"
        return

    results = col.query(
        query_texts=[req.question],
        n_results=req.n_results,
        include=["documents"],
    )
    context_chunks = results["documents"][0] if results["documents"] else []
    prompt = build_prompt(context_chunks, req.question)

    try:
        async for token in stream_ollama(prompt):
            # Escape newlines inside JSON string value
            escaped = token.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
            yield f'data: {{"token": "{escaped}"}}\n\n'
    except httpx.ConnectError:
        yield 'data: {"error": "Ollama not available. Is it running on localhost:11434?"}\n\n'
    except httpx.HTTPStatusError as exc:
        yield f'data: {{"error": "Ollama error: {exc.response.status_code}"}}\n\n'

    yield "data: [DONE]\n\n"


@app.post("/api/chat")
async def chat(req: ChatRequest):
    """Stream RAG-augmented chat response as Server-Sent Events.

    Each SSE event is one of:
      data: {"token": "<text>"}   — one text chunk from the model
      data: [DONE]                — stream finished
      data: {"error": "<msg>"}   — error occurred
    """
    return StreamingResponse(
        _chat_sse_generator(req),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering
        },
    )
