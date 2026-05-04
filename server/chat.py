"""RAG chat endpoint: POST /api/chat — streams Ollama response with ChromaDB context."""

import json
import os
from typing import AsyncGenerator

import httpx

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:14b-instruct-q4_K_M")
OLLAMA_TIMEOUT = float(os.environ.get("OLLAMA_TIMEOUT", "120"))

SYSTEM_PROMPT = """You are a helpful assistant specialized in Living Atlas and ALA (Atlas of Living Australia) \
ecosystem services. Answer based on the provided context. If the context does not contain enough information, \
say so clearly. Be concise and technical."""


def build_prompt(context_chunks: list[str], question: str) -> str:
    context = "\n\n---\n\n".join(context_chunks)
    return (
        f"[INST] <<SYS>>\n{SYSTEM_PROMPT}\n<</SYS>>\n\n"
        f"Context from Living Atlas documentation:\n\n{context}\n\n"
        f"Question: {question} [/INST]"
    )


async def stream_ollama(prompt: str) -> AsyncGenerator[str, None]:
    """Yield text chunks from Ollama generate API as SSE data lines."""
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": True,
        "options": {
            "temperature": 0.2,
            "num_predict": 1024,
        },
    }
    async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
        async with client.stream(
            "POST",
            f"{OLLAMA_BASE_URL}/api/generate",
            json=payload,
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                token = chunk.get("response", "")
                if token:
                    yield token
                if chunk.get("done"):
                    break
