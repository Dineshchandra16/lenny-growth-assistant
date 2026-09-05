"""
app/providers/cloud_provider.py
───────────────────────────────
Concrete LLM drivers for Cloud APIs (Anthropic Claude & OpenAI GPT-4o).
"""

from __future__ import annotations

import logging
from typing import AsyncGenerator, Sequence

from app.config import get_settings
from app.providers.base import (
    BaseLLMProvider,
    ProviderAuthError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)

logger = logging.getLogger(__name__)
settings = get_settings()


# ─────────────────────────────────────────────────────────────────────────────
# Anthropic Provider
# ─────────────────────────────────────────────────────────────────────────────

class AnthropicProvider(BaseLLMProvider):
    """Cloud driver for Anthropic Claude models via official Anthropic SDK."""

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str | None = None,
    ) -> None:
        self._api_key = api_key or settings.anthropic_api_key
        self._model_name = model_name or settings.anthropic_model
        self._client = None

    @property
    def provider_name(self) -> str:
        return "anthropic"

    @property
    def model_name(self) -> str:
        return self._model_name

    def _get_client(self):
        if not self._api_key:
            raise ProviderAuthError(
                "Anthropic API key is not configured. "
                "Set ANTHROPIC_API_KEY in your .env or environment variables."
            )
        if self._client is None:
            import anthropic
            self._client = anthropic.AsyncAnthropic(api_key=self._api_key)
        return self._client

    async def stream_chat(
        self,
        messages: Sequence[dict[str, str]],
        system_prompt: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> AsyncGenerator[str, None]:
        import anthropic

        client = self._get_client()
        limit = max_tokens or 4096

        # Anthropic requires system prompt as a dedicated top-level parameter
        formatted_messages = [
            {"role": m["role"], "content": m["content"]}
            for m in messages
            if m["role"] in ("user", "assistant")
        ]

        kwargs = {
            "model": self._model_name,
            "max_tokens": limit,
            "messages": formatted_messages,
            "temperature": temperature,
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        try:
            async with client.messages.stream(**kwargs) as stream:
                async for text in stream.text_stream:
                    yield text
        except anthropic.AuthenticationError as exc:
            logger.error("Anthropic auth error: %s", type(exc).__name__)
            raise ProviderAuthError(f"Anthropic authentication failed: {exc}") from exc
        except anthropic.APITimeoutError as exc:
            logger.error("Anthropic timeout: %s", type(exc).__name__)
            raise ProviderTimeoutError(f"Anthropic API timed out: {exc}") from exc
        except anthropic.APIConnectionError as exc:
            logger.error("Anthropic connection error: %s", type(exc).__name__)
            raise ProviderUnavailableError(f"Could not connect to Anthropic API: {exc}") from exc
        except anthropic.APIError as exc:
            logger.error("Anthropic API error: %s", type(exc).__name__)
            raise ProviderUnavailableError(f"Anthropic API error: {exc}") from exc

    async def complete_chat(
        self,
        messages: Sequence[dict[str, str]],
        system_prompt: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> str:
        tokens = []
        async for tok in self.stream_chat(
            messages,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            tokens.append(tok)
        return "".join(tokens)

    async def check_availability(self) -> bool:
        return bool(self._api_key)


# ─────────────────────────────────────────────────────────────────────────────
# OpenAI Provider
# ─────────────────────────────────────────────────────────────────────────────

class OpenAIProvider(BaseLLMProvider):
    """Cloud driver for OpenAI models (GPT-4o) via official OpenAI SDK."""

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str | None = None,
    ) -> None:
        self._api_key = api_key or settings.openai_api_key
        self._model_name = model_name or settings.openai_model
        self._client = None

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def model_name(self) -> str:
        return self._model_name

    def _get_client(self):
        if not self._api_key:
            raise ProviderAuthError(
                "OpenAI API key is not configured. "
                "Set OPENAI_API_KEY in your .env or environment variables."
            )
        if self._client is None:
            import openai
            self._client = openai.AsyncOpenAI(api_key=self._api_key)
        return self._client

    async def stream_chat(
        self,
        messages: Sequence[dict[str, str]],
        system_prompt: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> AsyncGenerator[str, None]:
        import openai

        client = self._get_client()
        formatted_messages: list[dict[str, str]] = []
        if system_prompt:
            formatted_messages.append({"role": "system", "content": system_prompt})
        for m in messages:
            formatted_messages.append({"role": m["role"], "content": m["content"]})

        kwargs = {
            "model": self._model_name,
            "messages": formatted_messages,
            "temperature": temperature,
            "stream": True,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        try:
            response = await client.chat.completions.create(**kwargs)
            async for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except openai.AuthenticationError as exc:
            logger.error("OpenAI auth error: %s", type(exc).__name__)
            raise ProviderAuthError(f"OpenAI authentication failed: {exc}") from exc
        except openai.APITimeoutError as exc:
            logger.error("OpenAI timeout: %s", type(exc).__name__)
            raise ProviderTimeoutError(f"OpenAI API timed out: {exc}") from exc
        except openai.APIConnectionError as exc:
            logger.error("OpenAI connection error: %s", type(exc).__name__)
            raise ProviderUnavailableError(f"Could not connect to OpenAI API: {exc}") from exc
        except openai.APIError as exc:
            logger.error("OpenAI API error: %s", type(exc).__name__)
            raise ProviderUnavailableError(f"OpenAI API error: {exc}") from exc

    async def complete_chat(
        self,
        messages: Sequence[dict[str, str]],
        system_prompt: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> str:
        tokens = []
        async for tok in self.stream_chat(
            messages,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            tokens.append(tok)
        return "".join(tokens)

    async def check_availability(self) -> bool:
        return bool(self._api_key)
