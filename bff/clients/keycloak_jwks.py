"""JWKS fetcher with 1-hour in-memory cache and httpx connection pool (D2, D9)."""
import logging
import time

import httpx
from fastapi import HTTPException

from bff.config import settings

logger = logging.getLogger(__name__)

_CACHE_TTL = 3600  # 1 hour
_TIMEOUT = 10.0
_READYZ_TIMEOUT = 5.0
_POOL_LIMITS = httpx.Limits(max_connections=10, max_keepalive_connections=10)

_jwks_cache: dict | None = None
_jwks_fetched_at: float = 0.0

_client: httpx.AsyncClient | None = None


def get_keycloak_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            timeout=_TIMEOUT,
            limits=_POOL_LIMITS,
        )
    return _client


async def close_keycloak_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def _sanitise(exc: Exception) -> HTTPException:
    if isinstance(exc, httpx.TimeoutException):
        logger.error("Keycloak JWKS request timed out")
        return HTTPException(status_code=502, detail="Downstream error: Keycloak timeout")
    if isinstance(exc, httpx.ConnectError):
        logger.error("Keycloak JWKS connection error")
        return HTTPException(status_code=502, detail="Downstream error: Keycloak unavailable")
    logger.error("Keycloak JWKS error: %s", type(exc).__name__)
    return HTTPException(status_code=502, detail="Downstream error: Keycloak unavailable")


async def fetch_jwks(timeout: float = _TIMEOUT) -> dict:
    """Return JWKS from Keycloak, cached for up to 1 hour.

    Pass timeout=5.0 when called from /readyz.
    """
    global _jwks_cache, _jwks_fetched_at

    now = time.monotonic()
    if _jwks_cache is not None and (now - _jwks_fetched_at) < _CACHE_TTL:
        return _jwks_cache

    client = get_keycloak_client()
    try:
        resp = await client.get(settings.keycloak_jwks_uri, timeout=timeout)
        resp.raise_for_status()
        _jwks_cache = resp.json()
        _jwks_fetched_at = now
        return _jwks_cache
    except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPError) as exc:
        raise _sanitise(exc) from None


def invalidate_jwks_cache() -> None:
    """Force cache expiry so the next call re-fetches from Keycloak."""
    global _jwks_cache, _jwks_fetched_at
    _jwks_cache = None
    _jwks_fetched_at = 0.0


# Backwards-compatible alias used by auth middleware from STORY-02
async def get_jwks() -> dict:
    return await fetch_jwks()
