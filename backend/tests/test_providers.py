"""
backend/tests/test_providers.py
───────────────────────────────
Phase 3 tests for LLM providers:
- BaseLLMProvider contract & provider switching factory
- OllamaProvider streaming and error handling
- AnthropicProvider & OpenAIProvider auth validation and streaming mocks
"""

import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.providers import (
    AnthropicProvider,
    BaseLLMProvider,
    OllamaProvider,
    OpenAIProvider,
    ProviderAuthError,
    ProviderUnavailableError,
    get_provider,
)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Provider Routing & Factory Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_get_provider_routing():
    ollama_p = get_provider("ollama")
    assert isinstance(ollama_p, OllamaProvider)
    assert ollama_p.provider_name == "ollama"

    anthropic_p = get_provider("anthropic")
    assert isinstance(anthropic_p, AnthropicProvider)
    assert anthropic_p.provider_name == "anthropic"

    openai_p = get_provider("openai")
    assert isinstance(openai_p, OpenAIProvider)
    assert openai_p.provider_name == "openai"


def test_get_provider_fallback_on_unknown():
    fallback_p = get_provider("unknown_provider_xyz")
    assert isinstance(fallback_p, BaseLLMProvider)


# ─────────────────────────────────────────────────────────────────────────────
# 2. OllamaProvider Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ollama_streaming_success():
    provider = OllamaProvider(base_url="http://mock-ollama:11434", model_name="llama3.2:3b")

    mock_ndjson_lines = [
        json.dumps({"message": {"content": "Product"}, "done": False}),
        json.dumps({"message": {"content": "-Led"}, "done": False}),
        json.dumps({"message": {"content": " Growth"}, "done": True}),
    ]

    mock_response = MagicMock()
    mock_response.status_code = 200

    async def aiter_lines_mock():
        for line in mock_ndjson_lines:
            yield line

    mock_response.aiter_lines = aiter_lines_mock

    @asynccontextmanager
    async def mock_stream(*args, **kwargs):
        yield mock_response

    mock_client = MagicMock()
    mock_client.stream = mock_stream
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_client):
        tokens = []
        async for token in provider.stream_chat(
            messages=[{"role": "user", "content": "Hello"}],
            system_prompt="You are an assistant.",
        ):
            tokens.append(token)

        assert "".join(tokens) == "Product-Led Growth"


@pytest.mark.asyncio
async def test_ollama_unreachable_raises_unavailable():
    provider = OllamaProvider(base_url="http://127.0.0.1:9999", model_name="llama3.2:3b")

    @asynccontextmanager
    async def mock_stream_error(*args, **kwargs):
        raise httpx.ConnectError("Connection refused")
        yield  # noqa: unreachable

    mock_client = MagicMock()
    mock_client.stream = mock_stream_error
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(ProviderUnavailableError) as exc_info:
            async for _ in provider.stream_chat(
                messages=[{"role": "user", "content": "test"}]
            ):
                pass
        assert "not reachable" in str(exc_info.value)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Cloud Provider (Anthropic) Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_anthropic_missing_key_raises_auth_error():
    provider = AnthropicProvider(api_key=None)
    with pytest.raises(ProviderAuthError) as exc_info:
        provider._get_client()
    assert "ANTHROPIC_API_KEY" in str(exc_info.value)


@pytest.mark.asyncio
async def test_anthropic_streaming_mock():
    provider = AnthropicProvider(api_key="sk-ant-test-key", model_name="claude-3-5-sonnet-20241022")

    mock_stream = AsyncMock()

    async def text_stream_mock():
        for token in ["Grounded ", "answer ", "with ", "citations."]:
            yield token

    mock_stream.text_stream = text_stream_mock()
    mock_stream.__aenter__.return_value = mock_stream

    mock_client = MagicMock()
    mock_client.messages.stream.return_value = mock_stream

    with patch.object(provider, "_get_client", return_value=mock_client):
        tokens = []
        async for tok in provider.stream_chat(
            messages=[{"role": "user", "content": "What is PLG?"}],
            system_prompt="System prompt",
        ):
            tokens.append(tok)

        assert "".join(tokens) == "Grounded answer with citations."


# ─────────────────────────────────────────────────────────────────────────────
# 4. Cloud Provider (OpenAI) Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_openai_missing_key_raises_auth_error():
    provider = OpenAIProvider(api_key=None)
    with pytest.raises(ProviderAuthError) as exc_info:
        provider._get_client()
    assert "OPENAI_API_KEY" in str(exc_info.value)


@pytest.mark.asyncio
async def test_openai_streaming_mock():
    provider = OpenAIProvider(api_key="sk-openai-test-key", model_name="gpt-4o")

    class MockChunk:
        def __init__(self, content):
            delta = MagicMock()
            delta.content = content
            choice = MagicMock()
            choice.delta = delta
            self.choices = [choice]

    async def aiter_chunks():
        for word in ["Retrieved ", "framework ", "steps."]:
            yield MockChunk(word)

    mock_client = AsyncMock()
    mock_client.chat.completions.create.return_value = aiter_chunks()

    with patch.object(provider, "_get_client", return_value=mock_client):
        tokens = []
        async for tok in provider.stream_chat(
            messages=[{"role": "user", "content": "Explain loops"}],
            system_prompt="System prompt",
        ):
            tokens.append(tok)

        assert "".join(tokens) == "Retrieved framework steps."
