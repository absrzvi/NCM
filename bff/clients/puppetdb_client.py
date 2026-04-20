"""PuppetDB client — read-only, httpx-based PQL interface (D9)."""
import logging

import httpx
from fastapi import HTTPException

from bff.config import settings

logger = logging.getLogger(__name__)

_TIMEOUT = 10.0
_POOL_LIMITS = httpx.Limits(max_connections=10, max_keepalive_connections=10)

# Module-level singleton; initialised on first use or via lifespan.
_client: httpx.AsyncClient | None = None


def get_puppetdb_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            base_url=settings.puppetdb_url,
            headers={"X-Authentication": settings.puppetdb_token},
            timeout=_TIMEOUT,
            limits=_POOL_LIMITS,
        )
    return _client


async def close_puppetdb_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def _sanitise(exc: Exception) -> HTTPException:
    """Convert httpx exceptions → 502 without leaking URLs or tokens."""
    if isinstance(exc, httpx.TimeoutException):
        logger.error("PuppetDB request timed out")
        return HTTPException(status_code=502, detail="Downstream error: PuppetDB timeout")
    if isinstance(exc, httpx.ConnectError):
        logger.error("PuppetDB connection error")
        return HTTPException(status_code=502, detail="Downstream error: PuppetDB unavailable")
    logger.error("PuppetDB error: %s", type(exc).__name__)
    return HTTPException(status_code=502, detail="Downstream error: PuppetDB unavailable")


async def query_puppetdb(pql: str) -> list[dict]:
    """Execute a PQL query and return the parsed JSON array."""
    client = get_puppetdb_client()
    try:
        resp = await client.get("/pdb/query/v4", params={"query": pql})
        resp.raise_for_status()
        return resp.json()
    except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPError) as exc:
        raise _sanitise(exc) from None


async def get_node_facts(certname: str) -> dict:
    """Fetch all facts for a certname."""
    client = get_puppetdb_client()
    try:
        resp = await client.get(f"/pdb/query/v4/nodes/{certname}/facts")
        resp.raise_for_status()
        facts = resp.json()
        return {f["name"]: f["value"] for f in facts}
    except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPError) as exc:
        raise _sanitise(exc) from None


async def get_node_reports(certname: str) -> list[dict]:
    """Fetch recent Puppet run reports for a certname."""
    pql = f'reports[certname,status,start_time,end_time]{{certname="{certname}"}}'
    return await query_puppetdb(pql)


async def get_drift(certname: str) -> list[dict]:
    """Fetch drift (corrective-change) events for a certname."""
    pql = (
        f'events[certname,resource_type,resource_title,status,corrective_change]'
        f'{{certname="{certname}" and corrective_change=true}}'
    )
    return await query_puppetdb(pql)
