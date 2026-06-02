"""Caller authentication.

Two accepted credentials:

1. ``X-Marketplace-Key: <key>`` — the shared service key. This is the
   primary path: Bench's backend has already authenticated the end user,
   so the marketplace only needs to trust that the caller is Bench.

2. ``Authorization: Bearer <jwt>`` — a better-auth EdDSA JWT, validated
   against Bench's published JWKS. Only honoured when ``BETTER_AUTH_JWKS_URL``
   is configured. This exists so a future browser-direct integration works
   without changing the service.

Read endpoints accept EITHER credential (``verify_caller``). Write endpoints
(create / update / delete templates) require the service key
(``require_service_key``) — catalog curation is an operator action, not an
end-user one.
"""
from __future__ import annotations

import hmac
import threading
from typing import Optional

import jwt
from fastapi import Depends, Header, HTTPException, status
from jwt import PyJWKClient

from .config import settings


def _service_key_ok(provided: Optional[str]) -> bool:
    if not provided:
        return False
    # Constant-time compare to avoid leaking the key via timing.
    return hmac.compare_digest(provided, settings.marketplace_api_key)


# --- better-auth JWKS client (lazy, shared, key-cached) ---------------------
_jwks_client: Optional[PyJWKClient] = None
_jwks_lock = threading.Lock()


def _get_jwks_client() -> Optional[PyJWKClient]:
    global _jwks_client
    if not settings.better_auth_jwks_url:
        return None
    if _jwks_client is None:
        with _jwks_lock:
            if _jwks_client is None:
                _jwks_client = PyJWKClient(settings.better_auth_jwks_url)
    return _jwks_client


def _jwt_ok(authorization: Optional[str]) -> bool:
    if not authorization:
        return False
    client = _get_jwks_client()
    if client is None:
        return False
    parts = authorization.split(maxsplit=1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return False
    token = parts[1].strip()
    try:
        signing_key = client.get_signing_key_from_jwt(token)
        # better-auth signs with EdDSA; iss/aud both default to BETTER_AUTH_URL.
        options = {"verify_aud": bool(settings.better_auth_url)}
        jwt.decode(
            token,
            signing_key.key,
            algorithms=["EdDSA"],
            audience=settings.better_auth_url or None,
            issuer=settings.better_auth_url or None,
            options=options,
        )
        return True
    except Exception:
        return False


def verify_caller(
    x_marketplace_key: Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
) -> None:
    """Allow the request if it carries a valid service key OR a valid JWT."""
    if _service_key_ok(x_marketplace_key) or _jwt_ok(authorization):
        return
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing or invalid marketplace credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_service_key(
    x_marketplace_key: Optional[str] = Header(default=None),
) -> None:
    """Require the shared service key. Used for catalog mutations."""
    if _service_key_ok(x_marketplace_key):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="This endpoint requires the marketplace service key.",
    )
