"""Puppet Server client — write-capable, httpx-based (D9, D11, D13).

IMPORTANT: callers MUST use this module only through the D13 safety envelope
(bff.envelopes.safety_envelope). Never construct the /run-force request inline.
"""
import logging

import httpx
from fastapi import HTTPException

from bff.config import settings

logger = logging.getLogger(__name__)

_TIMEOUT = 10.0
_POOL_LIMITS = httpx.Limits(max_connections=10, max_keepalive_connections=10)

_client: httpx.AsyncClient | None = None


def get_puppet_server_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            base_url=settings.puppet_server_url,
            headers={"X-Authentication": settings.puppet_server_token},
            timeout=_TIMEOUT,
            limits=_POOL_LIMITS,
        )
    return _client


async def close_puppet_server_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def _sanitise(exc: Exception) -> HTTPException:
    if isinstance(exc, httpx.TimeoutException):
        logger.error("Puppet Server request timed out")
        return HTTPException(status_code=502, detail="Downstream error: Puppet Server timeout")
    if isinstance(exc, httpx.ConnectError):
        logger.error("Puppet Server connection error")
        return HTTPException(status_code=502, detail="Downstream error: Puppet Server unavailable")
    logger.error("Puppet Server error: %s", type(exc).__name__)
    return HTTPException(status_code=502, detail="Downstream error: Puppet Server unavailable")


async def trigger_puppet_run(certname: str, environment: str) -> dict:
    """Call /run-force on Puppet Server and return the run UUID.

    Must only be called via the D13 safety envelope.
    """
    client = get_puppet_server_client()
    try:
        resp = await client.post(
            "/run-force",
            json={"certname": certname, "environment": environment},
        )
        resp.raise_for_status()
        return resp.json()
    except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPError) as exc:
        raise _sanitise(exc) from None
