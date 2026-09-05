"""
app/main.py
────────────
FastAPI application entry point.

Responsibilities:
  - Configure structured logging (structlog + JSON formatter)
  - Register API routers under /api prefix
  - Set up CORS (restricted to configured frontend origin)
  - Run init_db on startup (create tables, enable pgvector extension)
  - Register global exception handlers (never expose raw tracebacks)
  - Expose lifespan for clean startup/shutdown
"""

import logging
import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.database import init_db
from app.models.schemas import ErrorDetail

settings = get_settings()


# ─────────────────────────────────────────────────────────────────────────────
# Structured logging setup
# ─────────────────────────────────────────────────────────────────────────────

def _configure_logging() -> None:
    """Configure structlog with JSON or text renderer based on LOG_FORMAT env var."""
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if settings.log_format == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=shared_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processor=renderer,
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(getattr(logging, settings.log_level))

    # Silence noisy third-party loggers
    for noisy in ("httpx", "httpcore", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


_configure_logging()
logger = structlog.get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Lifespan (startup / shutdown)
# ─────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info(
        "application_starting",
        env=settings.app_env,
        provider=settings.default_llm_provider,
    )
    await init_db()
    logger.info("application_ready")
    yield
    logger.info("application_shutdown")


# ─────────────────────────────────────────────────────────────────────────────
# App
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Lenny Growth Assistant API",
    version="1.0.0",
    description="RAG-powered Q&A over Lenny's Podcast transcripts",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────────────────────────
# Global exception handlers
# ─────────────────────────────────────────────────────────────────────────────

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all — logs the exception, returns a structured error, never a traceback."""
    logger.exception(
        "unhandled_exception",
        path=request.url.path,
        method=request.method,
        exc_type=type(exc).__name__,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorDetail(
            error="internal_server_error",
            message="An unexpected error occurred. Please try again.",
        ).model_dump(),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Routers
# ─────────────────────────────────────────────────────────────────────────────
from app.api import artifacts, health, sessions, chat, ingest  # noqa: E402  (after app created)

app.include_router(health.router, prefix="/api")
app.include_router(sessions.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(ingest.router, prefix="/api")
app.include_router(artifacts.router, prefix="/api")


# ─────────────────────────────────────────────────────────────────────────────
# Root redirect
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def root():
    return {"service": "Lenny Growth Assistant API", "docs": "/api/docs"}
