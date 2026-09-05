"""
app/config.py
─────────────
Central configuration loaded from environment variables.
All tuneable parameters live here — nothing is hardcoded elsewhere.

Uses pydantic-settings so every field is type-checked, documented,
and validated at startup.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ───────────────────────────────────────────────────────────
    app_env: Literal["development", "production"] = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    log_format: Literal["json", "text"] = "json"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # ── Database ──────────────────────────────────────────────────────────────
    postgres_user: str = "lenny"
    postgres_password: str = "lenny_secret"
    postgres_db: str = "lenny_db"
    postgres_host: str = "db"
    postgres_port: int = 5432

    # Optional override — if set, takes precedence over individual fields
    database_url: str | None = None

    @property
    def async_database_url(self) -> str:
        if self.database_url:
            # Ensure async driver
            url = self.database_url
            if url.startswith("postgresql://"):
                url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
            return url
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def sync_database_url(self) -> str:
        """Sync URL for Alembic and one-off scripts."""
        return self.async_database_url.replace("+asyncpg", "+psycopg2")

    # ── LLM Provider ──────────────────────────────────────────────────────────
    default_llm_provider: Literal["ollama", "anthropic", "openai"] = "ollama"

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:3b"

    # Anthropic
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-3-5-sonnet-20241022"

    # OpenAI
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o"

    # ── Embeddings ────────────────────────────────────────────────────────────
    embedding_provider: Literal["local", "ollama"] = "local"
    embedding_model: str = "all-MiniLM-L6-v2"

    # ── RAG / Retrieval ───────────────────────────────────────────────────────
    rag_top_k: int = Field(default=5, ge=1, le=20)
    rag_similarity_threshold: float = Field(default=0.30, ge=0.0, le=1.0)
    chunk_size: int = Field(default=600, ge=100, le=2000)
    chunk_overlap: int = Field(default=100, ge=0, le=500)

    # ── CORS ──────────────────────────────────────────────────────────────────
    frontend_origin: str = "http://localhost:3000"

    @field_validator("chunk_overlap")
    @classmethod
    def overlap_less_than_size(cls, v: int, info: "FieldValidationInfo") -> int:  # type: ignore[name-defined]
        chunk_size = info.data.get("chunk_size", 600)
        if v >= chunk_size:
            raise ValueError("chunk_overlap must be less than chunk_size")
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached singleton Settings instance."""
    return Settings()
