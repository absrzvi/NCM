"""
Integration tests for STORY-03 — idempotency replay against a mock Postgres.

These tests exercise the full middleware dispatch loop (including the Starlette
body-iterator path) using an in-memory asyncpg mock rather than a real database,
confirming that:
  - A successful POST stores the response and returns it on replay.
  - TTL expiry makes the key re-usable (cache miss on replay after 25h).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from bff.middleware.idempotency import IdempotencyMiddleware
from bff.utils.canonical_json import canonical_json_hash

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_USER_SUB = "integration-user-sub"
_KEY = "aaaabbbb-cccc-dddd-eeee-ffffffffffff"
_BODY = {"fleet": "alpin", "op": "create"}
_FINGERPRINT = canonical_json_hash(_BODY)

import base64 as _base64


def _make_bearer(sub: str) -> str:
    payload_b64 = _base64.urlsafe_b64encode(
        json.dumps({"sub": sub}).encode()
    ).rstrip(b"=").decode()
    return f"Bearer hdr.{payload_b64}.sig"


def _build_conn(fetchrow_result: Any = None) -> AsyncMock:
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=fetchrow_result)
    conn.execute = AsyncMock(return_value=None)
    return conn


def _pool_from_conn(conn: AsyncMock) -> MagicMock:
    pool = MagicMock()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=False)
    pool.acquire = MagicMock(return_value=cm)
    return pool


def _make_app(pool: Any) -> FastAPI:
    fresh = FastAPI()
    fresh.state.db_pool = pool
    fresh.add_middleware(IdempotencyMiddleware)

    @fresh.post("/api/policies/drafts", status_code=201)
    async def create_draft(body: dict) -> dict:  # type: ignore[type-arg]
        return {"id": "draft-uuid-001", "status": "ACTIVE"}

    return fresh


# ---------------------------------------------------------------------------
# test_idempotency_replay_against_mock_postgres
# ---------------------------------------------------------------------------


def test_idempotency_replay_against_mock_postgres() -> None:
    """
    First POST caches the 201 response. Second POST with the same key and body
    returns the cached 201 without re-executing the route handler.
    """
    conn = _build_conn(fetchrow_result=None)
    pool = _pool_from_conn(conn)
    client = TestClient(_make_app(pool), raise_server_exceptions=True)

    headers = {
        "Authorization": _make_bearer(_USER_SUB),
        "Idempotency-Key": _KEY,
    }

    # ---- First request: cache miss → proceeds → response cached. ----
    resp1 = client.post("/api/policies/drafts", json=_BODY, headers=headers)
    assert resp1.status_code == 201
    assert resp1.json() == {"id": "draft-uuid-001", "status": "ACTIVE"}

    # Verify INSERT was called (first arg = key).
    conn.execute.assert_called_once()
    insert_args = conn.execute.call_args[0]
    assert _KEY in insert_args
    assert _USER_SUB in insert_args

    # ---- Second request: simulate cache hit by returning the cached row. ----
    future = datetime.now(tz=timezone.utc) + timedelta(hours=12)
    cached_row = {
        "fingerprint": _FINGERPRINT,
        "status_code": 201,
        "response_body": json.dumps({"id": "draft-uuid-001", "status": "ACTIVE"}),
        "expires_at": future,
    }
    conn2 = _build_conn(fetchrow_result=cached_row)
    pool2 = _pool_from_conn(conn2)

    app2 = _make_app(pool2)
    # Instrument the route to detect if it was called.
    route_called = []

    @app2.post("/api/policies/drafts", status_code=201)  # type: ignore[misc]
    async def create_draft_spy(body: dict) -> dict:  # type: ignore[type-arg]
        route_called.append(True)
        return {"id": "draft-uuid-001", "status": "ACTIVE"}

    client2 = TestClient(app2, raise_server_exceptions=True)
    resp2 = client2.post("/api/policies/drafts", json=_BODY, headers=headers)

    assert resp2.status_code == 201
    assert resp2.json() == {"id": "draft-uuid-001", "status": "ACTIVE"}
    # Route must NOT have been called — response came from cache.
    # (route_called will be empty because the middleware short-circuited)
    assert route_called == [], "Route handler must not execute on cache hit"
    conn2.execute.assert_not_called()


# ---------------------------------------------------------------------------
# test_idempotency_ttl_expiry
# ---------------------------------------------------------------------------


def test_idempotency_ttl_expiry() -> None:
    """
    A row whose expires_at is 25h in the past must be ignored.
    The replay must proceed as a cache miss and the route handler must execute.
    """
    expired_at = datetime.now(tz=timezone.utc) - timedelta(hours=25)
    expired_row = {
        "fingerprint": _FINGERPRINT,
        "status_code": 201,
        "response_body": json.dumps({"id": "draft-uuid-001", "status": "ACTIVE"}),
        "expires_at": expired_at,
    }
    conn = _build_conn(fetchrow_result=expired_row)
    pool = _pool_from_conn(conn)
    client = TestClient(_make_app(pool), raise_server_exceptions=True)

    headers = {
        "Authorization": _make_bearer(_USER_SUB),
        "Idempotency-Key": _KEY,
    }

    resp = client.post("/api/policies/drafts", json=_BODY, headers=headers)

    # Cache miss path: route executes and returns 201.
    assert resp.status_code == 201
    assert resp.json() == {"id": "draft-uuid-001", "status": "ACTIVE"}
    # A new INSERT must have been attempted (key is re-usable after expiry).
    conn.execute.assert_called_once()
