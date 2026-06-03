"""Agent Marketplace — standalone FastAPI service.

Owns the ``agent_templates`` catalog and serves it over HTTP to the Bench
platform's backend. See README.md for the integration contract.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .builtin_templates import _PREAMBLE
from .config import get_cors_origins
from .routers import templates

app = FastAPI(title="Agent Marketplace", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(templates.router)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/preamble", tags=["meta"])
def preamble() -> dict[str, str]:
    """The shared agent system-prompt preamble. The catalog is the single
    authoritative source; Bench fetches this at seed time (with a local
    fallback) so the two repos can't silently drift (see DECISIONS D-0004)."""
    return {"preamble": _PREAMBLE}
