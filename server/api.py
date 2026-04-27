"""FastAPI REST service for Living Atlas Knowledge Base."""

import os
from contextlib import asynccontextmanager
from typing import Optional

import chromadb
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

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
