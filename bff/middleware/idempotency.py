"""
Idempotency middleware — D4.

Enforces Idempotency-Key header on every write request (POST/PUT/PATCH/DELETE).

Behaviour:
  - GET/HEAD/OPTIONS: pass through unconditionally.
  - Missing header on write: 400 {"detail": "Idempotency-Key header required"}.
  - Key + fingerprint not found in DB: proceed, cache successful (2xx/3xx) response.
  - Key + fingerprint found, same fingerprint: return cached response.
  - Key found but fingerprint differs: 409 {"detail": "Idempotency-Key fingerprint mismatch"}.
  - Expired row (expires_at < NOW()): treat as cache miss (key is re-usable per D4 TTL).

Fingerprint = SHA-256 of RFC 8785 JCS serialisation of the request body.
Keys are user-scoped: (key, user_sub) is the composite PK.

The Postgres connection pool is read from request.app.state.db_pool, which is
populated during the FastAPI lifespan startup hook in bff/main.py.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from bff.utils.canonical_json import canonical_json_hash

logger = logging.getLogger(__name__)

_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _extract_user_sub(request: Request) -> str:
    """
    Extract the 'sub' claim from the Authorization bearer token without
    re-validating the signature — full JWT validation is already performed by
    the auth layer that runs before this middleware.

    Returns an empty string when the token is absent or unparseable (the auth
    middleware will have already rejected unauthenticated requests with 401).
    """
    auth_header: str = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return ""
    token = auth_header[len("Bearer "):]
    try:
        payload_b64 = token.split(".")[1]
        # Re-add padding required by Python's base64 decoder.
        remainder = len(payload_b64) % 4
        if remainder:
            payload_b64 += "=" * (4 - remainder)
        payload: dict[str, Any] = json.loads(base64.urlsafe_b64decode(payload_b64))
        return str(payload.get("sub", ""))
    except Exception:  # noqa: BLE001
        return ""


def _compute_fingerprint(body_bytes: bytes) -> str:
    """Return SHA-256 hex of RFC 8785 JCS of the body, or raw-bytes hash for non-objects."""
    if not body_bytes:
        return canonical_json_hash({})
    try:
        body_data: Any = json.loads(body_bytes)
        if isinstance(body_data, dict):
            return canonical_json_hash(body_data)
    except (json.JSONDecodeError, TypeError):
        pass
    # Non-JSON or non-object bodies: fall back to raw SHA-256.
    return hashlib.sha256(body_bytes).hexdigest()


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """FastAPI/Starlette ASGI middleware that enforces D4 idempotency on write endpoints.

    Reads the asyncpg pool from ``request.app.state.db_pool`` so no constructor
    argument is needed — mount with ``app.add_middleware(IdempotencyMiddleware)``.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        if request.method not in _WRITE_METHODS:
            return await call_next(request)

        # --- 1. Require Idempotency-Key header ---
        idempotency_key: str | None = request.headers.get("Idempotency-Key")
        if not idempotency_key:
            return JSONResponse(
                status_code=400,
                content={"detail": "Idempotency-Key header required"},
            )

        # --- 2. Compute fingerprint ---
        body_bytes: bytes = await request.body()
        fingerprint = _compute_fingerprint(body_bytes)

        user_sub = _extract_user_sub(request)

        pool = request.app.state.db_pool

        # --- 3. Query idempotency_keys table ---
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT fingerprint, status_code, response_body, expires_at
                FROM idempotency_keys
                WHERE key = $1 AND user_sub = $2
                """,
                idempotency_key,
                user_sub,
            )

        if row is not None:
            expires_at: datetime = row["expires_at"]
            now = datetime.now(tz=timezone.utc)
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)

            if expires_at > now:
                if row["fingerprint"] == fingerprint:
                    # Cache hit — return cached response.
                    cached_body = row["response_body"]
                    if isinstance(cached_body, str):
                        cached_body = json.loads(cached_body)
                    return JSONResponse(
                        status_code=row["status_code"],
                        content=cached_body,
                    )
                # Same key, different fingerprint → conflict.
                return JSONResponse(
                    status_code=409,
                    content={"detail": "Idempotency-Key fingerprint mismatch"},
                )
            # Expired row: fall through to cache-miss path (key is re-usable).

        # --- 4. Cache miss: proceed with the request ---
        response: Response = await call_next(request)

        if 200 <= response.status_code < 400:
            resp_body_bytes = b""
            async for chunk in response.body_iterator:  # type: ignore[attr-defined]
                resp_body_bytes += chunk

            try:
                resp_body_data: Any = json.loads(resp_body_bytes) if resp_body_bytes else {}
            except json.JSONDecodeError:
                resp_body_data = {}

            expires_at_new = datetime.now(tz=timezone.utc) + timedelta(hours=24)

            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO idempotency_keys
                        (key, user_sub, fingerprint, endpoint, status_code,
                         response_body, created_at, expires_at)
                    VALUES ($1, $2, $3, $4, $5, $6, NOW(), $7)
                    ON CONFLICT (key, user_sub) DO UPDATE SET
                        fingerprint   = EXCLUDED.fingerprint,
                        endpoint      = EXCLUDED.endpoint,
                        status_code   = EXCLUDED.status_code,
                        response_body = EXCLUDED.response_body,
                        created_at    = NOW(),
                        expires_at    = EXCLUDED.expires_at
                    """,
                    idempotency_key,
                    user_sub,
                    fingerprint,
                    str(request.url.path),
                    response.status_code,
                    json.dumps(resp_body_data),
                    expires_at_new,
                )

            return Response(
                content=resp_body_bytes,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )

        return response
