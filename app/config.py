"""Runtime configuration for the Agent Marketplace service.

The marketplace is a standalone service: it owns its own Postgres database
(the ``agent_templates`` catalog) and is consumed over HTTP by the Bench
platform's backend. It never reaches into Bench's database.

Two auth modes are supported (see ``app.auth``):

* ``MARKETPLACE_API_KEY`` — a shared secret presented by trusted callers
  (Bench's backend) in the ``X-Marketplace-Key`` header. This is the
  primary integration path: Bench has already authenticated the end user,
  so the service hop only needs to prove it's Bench.
* ``BETTER_AUTH_JWKS_URL`` — optional. When set, the service can also accept
  Bench's better-auth EdDSA JWTs directly (validated against the published
  JWKS), so a future browser-direct integration works without a rewrite.
"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Marketplace's OWN database — not Bench's.
    database_url: str = (
        "postgresql+psycopg://postgres:postgres@localhost:5432/agent_marketplace"
    )

    # Shared secret for trusted server-to-server calls from Bench. Required
    # in production; the dev default is intentionally weak. Write endpoints
    # (create/update/delete templates) ALWAYS require this key.
    marketplace_api_key: str = "DEV-INSECURE-MARKETPLACE-KEY"

    # Optional: validate Bench's better-auth JWTs directly. Point at the same
    # JWKS Bench's backend uses, e.g. https://bench.nova4.ai/api/auth/jwks.
    # Leave blank to disable JWT acceptance (API-key-only mode).
    better_auth_jwks_url: str = ""
    # Expected issuer/audience on the JWT, matching better-auth's config.
    # better-auth sets both to BETTER_AUTH_URL by default.
    better_auth_url: str = ""

    # Comma-separated CORS origins for any future browser-direct calls.
    cors_origins: str = "http://localhost:3000"


settings = Settings()


def get_cors_origins() -> list[str]:
    return [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
