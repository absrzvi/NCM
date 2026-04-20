"""
Unit tests for STORY-03 — Idempotency middleware and canonical_json helper.

All Postgres I/O is mocked — no real DB connection is made.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from bff.middleware.idempotency import IdempotencyMiddleware
from bff.utils.canonical_json import canonical_json_hash

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_USER_SUB = "user-sub-123"
_OTHER_SUB = "user-sub-456"
_IDEMPOTENCY_KEY = "550e8400-e29b-41d4-a716-446655440000"
_BODY_A = {"a": 1}
_BODY_B = {"a": 2}

# Pre-computed expected fingerprint for _BODY_A using JCS.
_FINGERPRINT_A = canonical_json_hash(_BODY_A)
_FINGERPRINT_B = canonical_json_hash(_BODY_B)

# JWT payload for _USER_SUB (not cryptographically valid — just needs decodable payload).
import base64 as _base64

def _make_bearer(sub: str) -> str:
    """Build a fake Bearer token whose payload encodes the given sub."""
    payload_json = json.dumps({"sub": sub}).encode()
    # Encode without padding then strip it (urlsafe_b64encode adds padding).
    payload_b64 = _base64.urlsafe_b64encode(payload_json).rstrip(b"=").decode()
    return f"Bearer header.{payload_b64}.sig"


def _make_app(mock_pool: Any) -> FastAPI:
    """Return a minimal FastAPI app with IdempotencyMiddleware and a test write route."""
    fresh = FastAPI()
    fresh.state.db_pool = mock_pool
    fresh.add_middleware(IdempotencyMiddleware)

    @fresh.post("/api/test-write", status_code=201)
    async def test_write(body: dict) -> dict:  # type: ignore[type-arg]
        return {"created": True}

    @fresh.get("/api/test-read")
    async def test_read() -> dict:  # type: ignore[type-arg]
        return {"ok": True}

    return fresh


def _make_pool(fetchrow_result: Any = None) -> MagicMock:
    """Return a mock asyncpg pool whose acquire() context manager returns a mock conn."""
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=fetchrow_result)
    conn.execute = AsyncMock(return_value=None)

    pool = MagicMock()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=False)
    pool.acquire = MagicMock(return_value=cm)
    return pool


# ---------------------------------------------------------------------------
# canonical_json_hash tests
# ---------------------------------------------------------------------------


def test_canonical_json_hash_deterministic() -> None:
    """Key order must not affect the digest (RFC 8785 JCS property)."""
    assert canonical_json_hash({"b": 2, "a": 1}) == canonical_json_hash({"a": 1, "b": 2})


def test_canonical_json_hash_differs_for_different_data() -> None:
    assert canonical_json_hash({"a": 1}) != canonical_json_hash({"a": 2})


# ---------------------------------------------------------------------------
# Missing Idempotency-Key → 400
# ---------------------------------------------------------------------------


def test_idempotency_key_missing() -> None:
    pool = _make_pool()
    client = TestClient(_make_app(pool), raise_server_exceptions=True)
    resp = client.post(
        "/api/test-write",
        json=_BODY_A,
        headers={"Authorization": _make_bearer(_USER_SUB)},
        # Deliberately no Idempotency-Key header.
    )
    assert resp.status_code == 400
    assert resp.json() == {"detail": "Idempotency-Key header required"}


# ---------------------------------------------------------------------------
# GET bypasses idempotency check
# ---------------------------------------------------------------------------


def test_get_request_bypasses_idempotency() -> None:
    """GET with no Idempotency-Key must pass through without 400."""
    pool = _make_pool()
    client = TestClient(_make_app(pool), raise_server_exceptions=True)
    resp = client.get("/api/test-read")
    assert resp.status_code == 200
    # Pool must not have been consulted.
    pool.acquire.assert_not_called()


# ---------------------------------------------------------------------------
# Cache miss — request proceeds and response is cached
# ---------------------------------------------------------------------------


def test_idempotency_key_cache_miss() -> None:
    """When no existing row exists, request proceeds and response is cached."""
    pool = _make_pool(fetchrow_result=None)
    client = TestClient(_make_app(pool), raise_server_exceptions=True)

    resp = client.post(
        "/api/test-write",
        json=_BODY_A,
        headers={
            "Authorization": _make_bearer(_USER_SUB),
            "Idempotency-Key": _IDEMPOTENCY_KEY,
        },
    )

    assert resp.status_code == 201
    assert resp.json() == {"created": True}

    # Verify an INSERT was attempted (conn.execute called).
    conn = pool.acquire.return_value.__aenter__.return_value
    conn.execute.assert_called_once()
    call_args = conn.execute.call_args[0]
    assert _IDEMPOTENCY_KEY in call_args
    assert _USER_SUB in call_args
    assert _FINGERPRINT_A in call_args


# ---------------------------------------------------------------------------
# Cache hit — same fingerprint returns cached response
# ---------------------------------------------------------------------------


def test_idempotency_key_cache_hit_same_fingerprint() -> None:
    """Replay with same key + same body returns cached 201 without re-executing."""
    future = datetime.now(tz=timezone.utc) + timedelta(hours=12)
    cached_row = {
        "fingerprint": _FINGERPRINT_A,
        "status_code": 201,
        "response_body": json.dumps({"created": True}),
        "expires_at": future,
    }
    pool = _make_pool(fetchrow_result=cached_row)
    client = TestClient(_make_app(pool), raise_server_exceptions=True)

    resp = client.post(
        "/api/test-write",
        json=_BODY_A,
        headers={
            "Authorization": _make_bearer(_USER_SUB),
            "Idempotency-Key": _IDEMPOTENCY_KEY,
        },
    )

    assert resp.status_code == 201
    assert resp.json() == {"created": True}

    # No INSERT/UPDATE — only the SELECT fetchrow.
    conn = pool.acquire.return_value.__aenter__.return_value
    conn.execute.assert_not_called()


# ---------------------------------------------------------------------------
# Fingerprint mismatch → 409
# ---------------------------------------------------------------------------


def test_idempotency_key_fingerprint_mismatch() -> None:
    """Same key but different body fingerprint must return 409."""
    future = datetime.now(tz=timezone.utc) + timedelta(hours=12)
    cached_row = {
        "fingerprint": _FINGERPRINT_A,
        "status_code": 201,
        "response_body": json.dumps({"created": True}),
        "expires_at": future,
    }
    pool = _make_pool(fetchrow_result=cached_row)
    client = TestClient(_make_app(pool), raise_server_exceptions=True)

    resp = client.post(
        "/api/test-write",
        json=_BODY_B,  # Different body → different fingerprint.
        headers={
            "Authorization": _make_bearer(_USER_SUB),
            "Idempotency-Key": _IDEMPOTENCY_KEY,
        },
    )

    assert resp.status_code == 409
    assert resp.json() == {"detail": "Idempotency-Key fingerprint mismatch"}


# ---------------------------------------------------------------------------
# User scoping — two users, same key, independent caches
# ---------------------------------------------------------------------------


def test_idempotency_key_scoped_to_user() -> None:
    """Different users with the same Idempotency-Key must be treated independently."""
    future = datetime.now(tz=timezone.utc) + timedelta(hours=12)
    # Pool returns None (cache miss) for user A's sub; user B would also get None.
    # The key point is that fetchrow is called with the correct user_sub each time.
    pool = _make_pool(fetchrow_result=None)
    client = TestClient(_make_app(pool), raise_server_exceptions=True)

    # User A
    resp_a = client.post(
        "/api/test-write",
        json=_BODY_A,
        headers={
            "Authorization": _make_bearer(_USER_SUB),
            "Idempotency-Key": _IDEMPOTENCY_KEY,
        },
    )
    assert resp_a.status_code == 201

    # User B — reset the mock so we can inspect calls independently.
    conn = pool.acquire.return_value.__aenter__.return_value
    conn.fetchrow.reset_mock()
    conn.execute.reset_mock()

    resp_b = client.post(
        "/api/test-write",
        json={"a": 99},
        headers={
            "Authorization": _make_bearer(_OTHER_SUB),
            "Idempotency-Key": _IDEMPOTENCY_KEY,  # Same UUID, different user.
        },
    )
    assert resp_b.status_code == 201

    # Verify that the fetchrow for user B used _OTHER_SUB.
    fetchrow_call_args = conn.fetchrow.call_args[0]
    assert _OTHER_SUB in fetchrow_call_args


# ---------------------------------------------------------------------------
# Cached status code is preserved (201 returned as 201, not 200)
# ---------------------------------------------------------------------------


def test_cached_status_code_preserved() -> None:
    """Cached 201 must be returned as 201, not normalised to 200."""
    future = datetime.now(tz=timezone.utc) + timedelta(hours=12)
    cached_row = {
        "fingerprint": _FINGERPRINT_A,
        "status_code": 201,
        "response_body": json.dumps({"id": "abc"}),
        "expires_at": future,
    }
    pool = _make_pool(fetchrow_result=cached_row)
    client = TestClient(_make_app(pool), raise_server_exceptions=True)

    resp = client.post(
        "/api/test-write",
        json=_BODY_A,
        headers={
            "Authorization": _make_bearer(_USER_SUB),
            "Idempotency-Key": _IDEMPOTENCY_KEY,
        },
    )

    assert resp.status_code == 201
    assert resp.json() == {"id": "abc"}


# ---------------------------------------------------------------------------
# Expired TTL — expired row is treated as cache miss
# ---------------------------------------------------------------------------


def test_idempotency_key_expired_ttl_treated_as_cache_miss() -> None:
    """Row with expires_at in the past must be ignored (key is re-usable)."""
    past = datetime.now(tz=timezone.utc) - timedelta(hours=1)
    expired_row = {
        "fingerprint": _FINGERPRINT_A,
        "status_code": 201,
        "response_body": json.dumps({"created": True}),
        "expires_at": past,
    }
    pool = _make_pool(fetchrow_result=expired_row)
    client = TestClient(_make_app(pool), raise_server_exceptions=True)

    # Replaying with the same key after expiry — even with a different body — must succeed.
    resp = client.post(
        "/api/test-write",
        json=_BODY_B,
        headers={
            "Authorization": _make_bearer(_USER_SUB),
            "Idempotency-Key": _IDEMPOTENCY_KEY,
        },
    )

    # Cache miss path: request proceeds normally (201 from the route).
    assert resp.status_code == 201
    # A new INSERT must have been attempted.
    conn = pool.acquire.return_value.__aenter__.return_value
    conn.execute.assert_called_once()
