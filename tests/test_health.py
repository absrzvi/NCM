"""Unit tests for health probe endpoints (STORY-01).

All downstream I/O is mocked — no real Postgres, Keycloak, or GitLab calls.
"""
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from bff.middleware.rate_limit import RateLimitMiddleware
from bff.routers.health import router as health_router


def _make_app() -> FastAPI:
    """Return a fresh FastAPI app with health routes and rate limiting."""
    fresh = FastAPI()
    fresh.add_middleware(RateLimitMiddleware, paths=["/healthz", "/readyz"])
    fresh.include_router(health_router)
    return fresh


# Shared client for non-rate-limit tests (state carries across within a module,
# but rate-limit tests get their own isolated client).
_app = _make_app()
client = TestClient(_app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# /healthz
# ---------------------------------------------------------------------------


def test_healthz_returns_200_no_downstream_calls() -> None:
    with (
        patch("bff.services.health_service.asyncpg") as mock_asyncpg,
        patch("bff.services.health_service.httpx.AsyncClient") as mock_httpx,
    ):
        resp = client.get("/healthz")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    mock_asyncpg.connect.assert_not_called()
    mock_httpx.assert_not_called()


def test_healthz_rate_limited() -> None:
    """11th request from the same IP within 1 second must return 429."""
    isolated = TestClient(_make_app(), raise_server_exceptions=True)
    responses = [isolated.get("/healthz") for _ in range(11)]

    assert all(r.status_code == 200 for r in responses[:10]), [
        r.status_code for r in responses[:10]
    ]
    assert responses[10].status_code == 429
    assert responses[10].json() == {"detail": "Rate limit exceeded"}


# ---------------------------------------------------------------------------
# /readyz — happy path
# ---------------------------------------------------------------------------


def test_readyz_all_checks_pass() -> None:
    with (
        patch(
            "bff.routers.health.check_postgres",
            new_callable=AsyncMock,
            return_value="ok",
        ),
        patch(
            "bff.routers.health.check_keycloak_jwks",
            new_callable=AsyncMock,
            return_value="ok",
        ),
        patch(
            "bff.routers.health.check_gitlab_api",
            new_callable=AsyncMock,
            return_value="ok",
        ),
    ):
        resp = client.get("/readyz")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert body["checks"] == {
        "postgres": "ok",
        "keycloak_jwks": "ok",
        "gitlab_api": "ok",
    }


# ---------------------------------------------------------------------------
# /readyz — failure cases
# ---------------------------------------------------------------------------


def test_readyz_postgres_down() -> None:
    with (
        patch(
            "bff.routers.health.check_postgres",
            new_callable=AsyncMock,
            return_value="error: connection refused",
        ),
        patch(
            "bff.routers.health.check_keycloak_jwks",
            new_callable=AsyncMock,
            return_value="ok",
        ),
        patch(
            "bff.routers.health.check_gitlab_api",
            new_callable=AsyncMock,
            return_value="ok",
        ),
    ):
        resp = client.get("/readyz")

    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["postgres"].startswith("error:")
    assert body["checks"]["keycloak_jwks"] == "ok"
    assert body["checks"]["gitlab_api"] == "ok"


def test_readyz_keycloak_jwks_timeout() -> None:
    with (
        patch(
            "bff.routers.health.check_postgres",
            new_callable=AsyncMock,
            return_value="ok",
        ),
        patch(
            "bff.routers.health.check_keycloak_jwks",
            new_callable=AsyncMock,
            return_value="timeout",
        ),
        patch(
            "bff.routers.health.check_gitlab_api",
            new_callable=AsyncMock,
            return_value="ok",
        ),
    ):
        resp = client.get("/readyz")

    assert resp.status_code == 503
    body = resp.json()
    assert body["checks"]["keycloak_jwks"] == "timeout"


def test_readyz_gitlab_api_unreachable() -> None:
    with (
        patch(
            "bff.routers.health.check_postgres",
            new_callable=AsyncMock,
            return_value="ok",
        ),
        patch(
            "bff.routers.health.check_keycloak_jwks",
            new_callable=AsyncMock,
            return_value="ok",
        ),
        patch(
            "bff.routers.health.check_gitlab_api",
            new_callable=AsyncMock,
            return_value="timeout",
        ),
    ):
        resp = client.get("/readyz")

    assert resp.status_code == 503
    body = resp.json()
    assert body["checks"]["gitlab_api"] == "timeout"


def test_readyz_rate_limited() -> None:
    """11th /readyz request from same IP within 1 second must return 429."""
    isolated = TestClient(_make_app(), raise_server_exceptions=True)
    with (
        patch(
            "bff.routers.health.check_postgres",
            new_callable=AsyncMock,
            return_value="ok",
        ),
        patch(
            "bff.routers.health.check_keycloak_jwks",
            new_callable=AsyncMock,
            return_value="ok",
        ),
        patch(
            "bff.routers.health.check_gitlab_api",
            new_callable=AsyncMock,
            return_value="ok",
        ),
    ):
        responses = [isolated.get("/readyz") for _ in range(11)]

    assert all(r.status_code == 200 for r in responses[:10])
    assert responses[10].status_code == 429
    assert responses[10].json() == {"detail": "Rate limit exceeded"}
