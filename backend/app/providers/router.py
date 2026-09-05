"""
app/providers/router.py
───────────────────────
LLM provider registry and routing factory.

Selects active driver via:
1. Explicit per-request parameter (`provider: "ollama" | "anthropic" | "openai"`)
2. `DEFAULT_LLM_PROVIDER` environment variable
No code changes required to switch providers.
"""

from __future__ import annotations

import logging
from typing import Literal

from app.config import get_settings
from app.providers.base import BaseLLMProvider, ProviderUnavailableError
from app.providers.cloud_provider import AnthropicProvider, OpenAIProvider
from app.providers.ollama_provider import OllamaProvider

logger = logging.getLogger(__name__)
settings = get_settings()

ProviderType = Literal["ollama", "anthropic", "openai"]


def get_provider(provider_name: str | None = None) -> BaseLLMProvider:
    """
    Factory to retrieve configured LLM provider instance.

    Args:
        provider_name: 'ollama', 'anthropic', 'openai', or None (defaults to DEFAULT_LLM_PROVIDER).
    """
    name = (provider_name or settings.default_llm_provider).lower().strip()

    if name == "ollama":
        return OllamaProvider()
    elif name == "anthropic":
        return AnthropicProvider()
    elif name == "openai":
        return OpenAIProvider()
    else:
        logger.warning("Unknown provider '%s', falling back to default '%s'", name, settings.default_llm_provider)
        if settings.default_llm_provider == "anthropic":
            return AnthropicProvider()
        elif settings.default_llm_provider == "openai":
            return OpenAIProvider()
        return OllamaProvider()

