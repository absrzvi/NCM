"""Business logic for readiness checks.

Each check returns a status string: "ok", "timeout", or "error: <detail>".
All downstream calls use httpx with a 5-second timeout (D9).
"""
import os

import asyncpg
import httpx


async def check_postgres() -> str:
    dsn = os.environ.get("POSTGRES_DSN", "")
    try:
        conn = await asyncpg.connect(dsn, timeout=5)
        await conn.fetchval("SELECT 1")
        await conn.close()
        return "ok"
    except asyncpg.exceptions.TooManyConnectionsError as exc:
        return f"error: {exc}"
    except OSError as exc:
        return f"error: {exc}"
    except Exception as exc:  # noqa: BLE001
        return f"error: {exc}"


async def check_keycloak_jwks() -> str:
    jwks_uri = os.environ.get("KEYCLOAK_JWKS_URI", "")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(jwks_uri)
            resp.raise_for_status()
        return "ok"
    except httpx.TimeoutException:
        return "timeout"
    except Exception as exc:  # noqa: BLE001
        return f"error: {exc}"


async def check_gitlab_api() -> str:
    base_url = os.environ.get("GITLAB_API_BASE_URL", "").rstrip("/")
    url = f"{base_url}/api/v4/version"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
        return "ok"
    except httpx.TimeoutException:
        return "timeout"
    except Exception as exc:  # noqa: BLE001
        return f"error: {exc}"
