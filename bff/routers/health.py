"""Health probe routes — liveness and readiness.

Routes only; business logic lives in bff.services.health_service.
Both endpoints are unauthenticated (FR8 / STORY-01).
Rate limiting is applied at middleware level (bff.middleware.rate_limit).
"""
import asyncio

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from bff.services.health_service import (
    check_gitlab_api,
    check_keycloak_jwks,
    check_postgres,
)

router = APIRouter(tags=["health"])


class LivenessResponse(BaseModel):
    status: str


class ReadinessChecks(BaseModel):
    postgres: str
    keycloak_jwks: str
    gitlab_api: str


class ReadinessResponse(BaseModel):
    status: str
    checks: ReadinessChecks


@router.get("/healthz", response_model=LivenessResponse)
async def healthz() -> LivenessResponse:
    """Liveness probe — returns 200 if the process is running.

    Makes no downstream calls.
    """
    return LivenessResponse(status="ok")


@router.get("/readyz")
async def readyz() -> JSONResponse:
    """Readiness probe — checks Postgres, Keycloak JWKS, and GitLab API.

    Returns 200 if all checks pass; 503 with per-check detail if any fail.
    Does NOT check PuppetDB (soft dependency — 5-minute staleness tolerance).
    """
    postgres_status, keycloak_status, gitlab_status = await asyncio.gather(
        check_postgres(),
        check_keycloak_jwks(),
        check_gitlab_api(),
    )

    checks = ReadinessChecks(
        postgres=postgres_status,
        keycloak_jwks=keycloak_status,
        gitlab_api=gitlab_status,
    )

    all_ok = all(v == "ok" for v in [postgres_status, keycloak_status, gitlab_status])

    if all_ok:
        body = ReadinessResponse(status="ready", checks=checks)
        return JSONResponse(status_code=200, content=body.model_dump())

    body = ReadinessResponse(status="not_ready", checks=checks)
    return JSONResponse(status_code=503, content=body.model_dump())
