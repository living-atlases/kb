"""RAG chat endpoint: POST /api/chat — streams Ollama response with ChromaDB context."""

import json
import os
from typing import AsyncGenerator

import httpx

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3-coder:30b")
OLLAMA_TIMEOUT = float(os.environ.get("OLLAMA_TIMEOUT", "120"))

SYSTEM_PROMPT = (
    "You are a helpful assistant specialized in Living Atlas and ALA "
    "(Atlas of Living Australia) ecosystem services. "
    "Answer based on the provided context. "
    "If the context does not contain enough information, say so clearly. "
    "Be concise and technical. /no_think"
)


def build_messages(context_chunks: list[str], question: str) -> list[dict]:
    """Build Ollama chat messages list from context and question.

    Uses the chat completions format so Ollama applies the correct model
    template without conflicting with manually-crafted [INST] tokens.
    The /no_think suffix disables chain-of-thought for qwen3 models.
    """
    context = "\n\n---\n\n".join(context_chunks) if context_chunks else "(no context)"
    user_content = (
        f"Context from Living Atlas documentation:\n\n{context}\n\nQuestion: {question}"
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


async def stream_ollama(messages: list[dict]) -> AsyncGenerator[str, None]:
    """Yield text chunks from Ollama chat API as SSE data lines.

    Uses /api/chat with messages so Ollama applies the model-specific
    chat template correctly, avoiding duplicate tokens / response loops
    that occur when manually formatting prompts with /api/generate.
    """
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": True,
        "options": {
            "temperature": 0.2,
            "num_predict": 1024,
        },
    }
    async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
        async with client.stream(
            "POST",
            f"{OLLAMA_BASE_URL}/api/chat",
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
                token = chunk.get("message", {}).get("content", "")
                if token:
                    yield token
                if chunk.get("done"):
                    break
