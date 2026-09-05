"""
app/providers/base.py
─────────────────────
Base abstract interface and exceptions for all LLM providers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncGenerator, Sequence


class LLMProviderError(Exception):
    """Base exception for LLM provider failures."""
    pass


class ProviderUnavailableError(LLMProviderError):
    """Raised when an LLM provider service is unreachable or not running."""
    pass


class ProviderAuthError(LLMProviderError):
    """Raised when API credentials are missing, invalid, or unauthorized."""
    pass


class ProviderTimeoutError(LLMProviderError):
    """Raised when an LLM provider request times out."""
    pass


def user_facing_provider_error(provider_name: str, error: Exception) -> str:
    """Return a safe provider failure message without exposing SDK details or secrets."""
    provider = provider_name.capitalize()
    if isinstance(error, ProviderAuthError):
        return f"{provider} is not configured or rejected the request. Check its API credentials."
    if isinstance(error, ProviderTimeoutError):
        return f"{provider} took too long to respond. Please try again."
    if isinstance(error, ProviderUnavailableError):
        return f"{provider} is currently unavailable. Check that it is running and try again."
    return f"{provider} could not generate a response. Please try again."


class BaseLLMProvider(ABC):
    """Abstract interface that all LLM backend drivers must implement."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the provider (e.g. 'ollama', 'anthropic', 'openai')."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Model identifier currently in use."""
        pass

    @abstractmethod
    async def stream_chat(
        self,
        messages: Sequence[dict[str, str]],
        system_prompt: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> AsyncGenerator[str, None]:
        """
        Stream response tokens from the LLM.

        Args:
            messages: List of dicts with keys 'role' ('user'|'assistant'|'system') and 'content'.
            system_prompt: Optional top-level system instruction.
            temperature: Sampling temperature (default 0.2 for grounded RAG).
            max_tokens: Optional token generation limit.

        Yields:
            Response token strings as they arrive.
        """
        pass

    @abstractmethod
    async def complete_chat(
        self,
        messages: Sequence[dict[str, str]],
        system_prompt: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> str:
        """
        Non-streaming chat completion.

        Returns full text response string.
        """
        pass

    @abstractmethod
    async def check_availability(self) -> bool:
        """Return True if provider backend is reachable and configured."""
        pass
