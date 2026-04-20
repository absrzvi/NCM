"""Integration tests for /readyz (STORY-01).

These tests exercise the full request/response cycle with injected fixtures
for Postgres — no real downstream services are contacted.
"""
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from bff.middleware.rate_limit import RateLimitMiddleware
from bff.routers.health import router as health_router


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, paths=["/healthz", "/readyz"])
    app.include_router(health_router)
    return TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# Postgres fixture scenarios
# ---------------------------------------------------------------------------


def test_readyz_against_mock_postgres(client: TestClient) -> None:
    """Fixture provides mock Postgres — /readyz must return 200."""
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
    assert body["checks"]["postgres"] == "ok"


def test_readyz_postgres_connection_refused(client: TestClient) -> None:
    """Fixture injects Postgres connection error — /readyz must return 503."""
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
    assert "error" in body["checks"]["postgres"]
