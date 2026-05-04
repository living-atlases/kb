"""Tests for POST /api/chat SSE endpoint and chat.py helpers."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_chroma():
    col = MagicMock()
    col.query.return_value = {
        "documents": [["Collectory is configured via application.yml.", "See ala-install roles for details."]],
        "metadatas": [[
            {"repo": "collectory", "file": "docs/config.md", "chunk": 0},
            {"repo": "ala-install", "file": "ansible/roles/collectory/tasks/main.yml", "chunk": 0},
        ]],
        "distances": [[0.2, 0.4]],
    }
    return col


@pytest.fixture
def mock_chroma_client(mock_chroma):
    client = MagicMock()
    client.get_collection.return_value = mock_chroma
    return client


@pytest.fixture
def app_client(mock_chroma_client):
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))
    import server.api as api_module
    api_module.chroma_client = mock_chroma_client
    from fastapi.testclient import TestClient
    return TestClient(api_module.app)


# ── chat.py unit tests ───────────────────────────────────────────────────────

class TestBuildPrompt:
    def test_includes_question(self):
        from server.chat import build_prompt
        prompt = build_prompt(["context chunk"], "How to deploy collectory?")
        assert "How to deploy collectory?" in prompt

    def test_includes_context(self):
        from server.chat import build_prompt
        prompt = build_prompt(["important context"], "some question")
        assert "important context" in prompt

    def test_empty_context(self):
        from server.chat import build_prompt
        prompt = build_prompt([], "some question")
        assert "some question" in prompt
        assert "[INST]" in prompt

    def test_multiple_chunks_joined(self):
        from server.chat import build_prompt
        prompt = build_prompt(["chunk1", "chunk2"], "q")
        assert "chunk1" in prompt
        assert "chunk2" in prompt


class TestStreamOllama:
    @pytest.mark.asyncio
    async def test_yields_tokens(self):
        from server.chat import stream_ollama

        fake_lines = [
            json.dumps({"response": "Hello", "done": False}),
            json.dumps({"response": " world", "done": False}),
            json.dumps({"response": "", "done": True}),
        ]

        class FakeStreamResponse:
            async def aiter_lines(self):
                for line in fake_lines:
                    yield line

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                pass

            def raise_for_status(self):
                pass

        class FakeClient:
            def stream(self, *args, **kwargs):
                return FakeStreamResponse()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                pass

        with patch("server.chat.httpx.AsyncClient", return_value=FakeClient()):
            tokens = [t async for t in stream_ollama("test prompt")]

        assert tokens == ["Hello", " world"]

    @pytest.mark.asyncio
    async def test_skips_empty_tokens(self):
        from server.chat import stream_ollama

        fake_lines = [
            json.dumps({"response": "", "done": False}),
            json.dumps({"response": "text", "done": True}),
        ]

        class FakeStreamResponse:
            async def aiter_lines(self):
                for line in fake_lines:
                    yield line

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                pass

            def raise_for_status(self):
                pass

        class FakeClient:
            def stream(self, *args, **kwargs):
                return FakeStreamResponse()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                pass

        with patch("server.chat.httpx.AsyncClient", return_value=FakeClient()):
            tokens = [t async for t in stream_ollama("test prompt")]

        # "text" token arrives with done=True — still yielded before break
        assert tokens == ["text"]


# ── /api/chat integration tests ─────────────────────────────────────────────

class TestChatEndpoint:
    def _make_sse_response(self, tokens: list[str]) -> str:
        """Build fake SSE body from token list."""
        lines = [f'data: {{"token": "{t}"}}\n\n' for t in tokens]
        lines.append("data: [DONE]\n\n")
        return "".join(lines)

    def _mock_stream_ollama(self, tokens):
        async def _gen(_prompt):
            for t in tokens:
                yield t
        return _gen

    def test_chat_returns_sse_stream(self, app_client, mock_chroma_client):
        import server.api as api_module

        tokens = ["The ", "answer ", "is ", "42."]
        with patch("server.api.stream_ollama", self._mock_stream_ollama(tokens)):
            response = app_client.post(
                "/api/chat",
                json={"question": "What is collectory?"},
            )

        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        body = response.text
        assert "data:" in body
        assert "[DONE]" in body

    def test_chat_collection_not_found(self, app_client, mock_chroma_client):
        mock_chroma_client.get_collection.side_effect = Exception("not found")

        response = app_client.post(
            "/api/chat",
            json={"question": "test", "collection": "nonexistent"},
        )

        assert response.status_code == 200  # SSE always 200; error in body
        assert "error" in response.text

    def test_chat_ollama_unavailable(self, app_client, mock_chroma_client):
        import httpx

        async def _failing(_prompt):
            raise httpx.ConnectError("connection refused")
            yield  # make it an async generator

        with patch("server.api.stream_ollama", _failing):
            response = app_client.post(
                "/api/chat",
                json={"question": "test"},
            )

        assert response.status_code == 200
        assert "error" in response.text
        assert "Ollama" in response.text

    def test_chat_validates_n_results_range(self, app_client):
        response = app_client.post(
            "/api/chat",
            json={"question": "test", "n_results": 0},
        )
        assert response.status_code == 422

        response = app_client.post(
            "/api/chat",
            json={"question": "test", "n_results": 11},
        )
        assert response.status_code == 422

    def test_chat_default_collection(self, app_client, mock_chroma_client):
        tokens = ["ok"]
        with patch("server.api.stream_ollama", self._mock_stream_ollama(tokens)):
            response = app_client.post(
                "/api/chat",
                json={"question": "test"},
            )

        assert response.status_code == 200
        mock_chroma_client.get_collection.assert_called_with("la_toolkit_kb")
