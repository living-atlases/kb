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

# Used when the context blocks are numbered ([1], [2], ...) so the model can
# attribute its statements to specific sources.
SYSTEM_PROMPT_CITED = (
    "You are a helpful assistant specialized in Living Atlas and ALA "
    "(Atlas of Living Australia) ecosystem services. "
    "Answer based ONLY on the provided context. Each context block is numbered "
    "like [1], [2]. Cite the blocks you rely on inline as [n]. "
    "If the context does not contain enough information, say so clearly and do "
    "not invent details. Be concise and technical. /no_think"
)


MAX_HISTORY_MESSAGES = 12
ALLOWED_ROLES = {"user", "assistant"}


def _sanitize_history(history: list[dict] | None) -> list[dict]:
    """Drop malformed entries and cap to the last MAX_HISTORY_MESSAGES."""
    if not history:
        return []
    clean: list[dict] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role not in ALLOWED_ROLES or not isinstance(content, str) or not content.strip():
            continue
        clean.append({"role": role, "content": content})
    if len(clean) > MAX_HISTORY_MESSAGES:
        clean = clean[-MAX_HISTORY_MESSAGES:]
    return clean


def build_messages(
    context_chunks: list[str],
    question: str,
    history: list[dict] | None = None,
    sources: list[dict] | None = None,
) -> list[dict]:
    """Build Ollama chat messages list from context, history and question.

    Uses the chat completions format so Ollama applies the correct model
    template without conflicting with manually-crafted [INST] tokens.
    The /no_think suffix disables chain-of-thought for qwen3 models.

    RAG context is injected only into the latest user turn — the conversation
    history is passed through verbatim so the model can resolve references
    like "translate the previous answer".

    When `sources` is given (one dict per chunk, with a "label" such as
    "repo/file"), context blocks are numbered `[n] label` and the system prompt
    asks the model to cite `[n]`. Without `sources`, behaviour is unchanged
    (plain concatenation) so the streaming /api/chat path is unaffected.
    """
    if sources:
        blocks = []
        for i, (chunk, src) in enumerate(zip(context_chunks, sources), 1):
            label = src.get("label") or src.get("repo") or "source"
            blocks.append(f"[{i}] {label}\n{chunk}")
        context = "\n\n---\n\n".join(blocks) if blocks else "(no context)"
        system_prompt = SYSTEM_PROMPT_CITED
    else:
        context = "\n\n---\n\n".join(context_chunks) if context_chunks else "(no context)"
        system_prompt = SYSTEM_PROMPT
    user_content = (
        f"Context from Living Atlas documentation:\n\n{context}\n\nQuestion: {question}"
    )
    return [
        {"role": "system", "content": system_prompt},
        *_sanitize_history(history),
        {"role": "user", "content": user_content},
    ]


async def generate_ollama(messages: list[dict]) -> str:
    """Non-streaming counterpart of stream_ollama — returns the full answer text.

    Used by /api/answer, which needs the complete synthesised answer (plus a
    structured source list) rather than an SSE token stream.
    """
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": 0.2,
            "num_predict": 1024,
        },
    }
    async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
        resp = await client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
        resp.raise_for_status()
        data = resp.json()
    return data.get("message", {}).get("content", "")


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
