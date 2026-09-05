"""
app/providers/ollama_provider.py
────────────────────────────────
Concrete LLM driver for local Ollama instances.
"""

from __future__ import annotations

import json
import logging
from typing import AsyncGenerator, Sequence

import httpx

from app.config import get_settings
from app.providers.base import (
    BaseLLMProvider,
    ProviderTimeoutError,
    ProviderUnavailableError,
)

logger = logging.getLogger(__name__)
settings = get_settings()


class OllamaProvider(BaseLLMProvider):
    """Local LLM driver connecting to Ollama REST API."""

    def __init__(
        self,
        base_url: str | None = None,
        model_name: str | None = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        self._base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self._model_name = model_name or settings.ollama_model
        self._timeout = timeout_seconds

    @property
    def provider_name(self) -> str:
        return "ollama"

    @property
    def model_name(self) -> str:
        return self._model_name

    def _prepare_messages(
        self,
        messages: Sequence[dict[str, str]],
        system_prompt: str | None,
    ) -> list[dict[str, str]]:
        formatted: list[dict[str, str]] = []
        if system_prompt:
            formatted.append({"role": "system", "content": system_prompt})
        for msg in messages:
            formatted.append({"role": msg["role"], "content": msg["content"]})
        return formatted

    async def stream_chat(
        self,
        messages: Sequence[dict[str, str]],
        system_prompt: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> AsyncGenerator[str, None]:
        url = f"{self._base_url}/api/chat"
        payload = {
            "model": self._model_name,
            "messages": self._prepare_messages(messages, system_prompt),
            "stream": True,
            "options": {
                "temperature": temperature,
            },
        }
        if max_tokens is not None:
            payload["options"]["num_predict"] = max_tokens

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                async with client.stream("POST", url, json=payload) as response:
                    if response.status_code == 404:
                        raise ProviderUnavailableError(
                            f"Model '{self._model_name}' not found on Ollama instance at {self._base_url}. "
                            f"Run 'ollama pull {self._model_name}'."
                        )
                    if response.status_code != 200:
                        err_text = await response.aread()
                        raise ProviderUnavailableError(
                            f"Ollama returned HTTP {response.status_code}: {err_text.decode('utf-8', errors='ignore')}"
                        )

                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            chunk = json.loads(line)
                            content = chunk.get("message", {}).get("content", "")
                            if content:
                                yield content
                            if chunk.get("done", False):
                                break
                        except json.JSONDecodeError:
                            continue

        except httpx.ConnectError as exc:
            logger.error("Ollama connection failed: %s", type(exc).__name__)
            raise ProviderUnavailableError(
                f"Ollama is not reachable at {self._base_url}. "
                "Ensure Ollama is running ('ollama serve') or switch to a cloud provider."
            ) from exc
        except httpx.TimeoutException as exc:
            logger.error("Ollama request timed out: %s", type(exc).__name__)
            raise ProviderTimeoutError(
                f"Ollama request timed out after {self._timeout}s."
            ) from exc

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
        url = f"{self._base_url}/api/tags"
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(url)
                return resp.status_code == 200
        except Exception:
            return False
