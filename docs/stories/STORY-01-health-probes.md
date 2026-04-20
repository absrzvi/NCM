# Story: [STORY-01] Health Probes
Status: READY
D-decisions touched: None (infrastructure probes only)

## Why (from PRD)
FR8 requires liveness and readiness probes for Docker Compose health checks and nginx upstream pool marking. `/healthz` confirms the BFF process is up; `/readyz` confirms downstream connectivity to Postgres, Keycloak JWKS, and GitLab API base (but not PuppetDB, which is a soft dependency). These endpoints are unauthenticated and rate-limited to prevent abuse.

## Assumptions (inherited from PRD + ARCHITECTURE)
- Health probes are infrastructure-facing, not user-facing — no auth required.
- `/healthz` makes zero downstream calls (liveness only).
- `/readyz` checks Postgres (`SELECT 1`), Keycloak JWKS reachability (`GET <jwks_uri>` with 5s timeout), and GitLab API base reachability (`GET /api/v4/version` with 5s timeout).
- `/readyz` does NOT check PuppetDB — it's a soft dependency with 5-minute staleness tolerance.
- Both endpoints are rate-limited to 10 req/s per IP to prevent probe flooding.
- Docker Compose `healthcheck:` hits `/healthz` every 10s (3 retries, 5s timeout).
- nginx upstream pool checks `/readyz` before marking the BFF healthy; Compose `depends_on: { bff: { condition: service_healthy } }` gates nginx startup.

## What to Build
Two unauthenticated GET endpoints in `bff/routers/health_router.py`:
- `GET /healthz` — returns 200 `{"status": "ok"}` if the process is up; makes no downstream calls.
- `GET /readyz` — returns 200 `{"status": "ready", "checks": {"postgres": "ok", "keycloak_jwks": "ok", "gitlab_api": "ok"}}` if all checks pass. Returns 503 `{"status": "not_ready", "checks": {...}}` with per-check details if any fail.

Both endpoints apply rate limiting via `bff/middleware/rate_limit.py` (10 req/s per IP).

## Affected Files
- bff/routers/health_router.py → create (new router)
- bff/middleware/rate_limit.py → create (new middleware)
- bff/main.py → mount health_router at root (no `/api/` prefix)
- tests/test_health.py → create (unit tests)
- tests/integration/test_health_readyz.py → create (integration tests)

## BFF Endpoint Spec

### GET /healthz
Method: GET
Path: /healthz
Auth: None (unauthenticated)
Role: None
Idempotency-Key required: No
SLO: none (infra probe)
Request body: none
Response (200 OK): `{"status": "ok"}`
Downstream: none
D14 gates triggered: n/a
Error cases:
- 429: `{"detail": "Rate limit exceeded"}` (if > 10 req/s from same IP)

### GET /readyz
Method: GET
Path: /readyz
Auth: None (unauthenticated)
Role: None
Idempotency-Key required: No
SLO: none (infra probe)
Request body: none
Response (200 OK): `{"status": "ready", "checks": {"postgres": "ok", "keycloak_jwks": "ok", "gitlab_api": "ok"}}`
Response (503 Service Unavailable): `{"status": "not_ready", "checks": {"postgres": "error: connection refused", "keycloak_jwks": "ok", "gitlab_api": "timeout"}}`
Downstream: Postgres (`SELECT 1`), Keycloak JWKS (`GET <jwks_uri>`), GitLab API (`GET /api/v4/version`)
D14 gates triggered: n/a
Error cases:
- 429: `{"detail": "Rate limit exceeded"}` (if > 10 req/s from same IP)
- 503: (as above — per-check failure details in response body)

## Cross-Cutting Concerns

| Concern | Owner | Coordinates With | Detail |
|---------|-------|-----------------|--------|
| Rate limiting strategy | bff-dev | devops | 10 req/s per IP; sliding window; memory-backed (no Redis in MVP) |
| Downstream timeout values | bff-dev | bff-dev (clients) | All `/readyz` downstream checks: 5s timeout |
| Docker healthcheck config | devops | bff-dev | Compose `healthcheck:` hits `/healthz` every 10s, 3 retries, 5s timeout |
| nginx upstream health check | devops | bff-dev | nginx `check` directive calls `/readyz` every 10s to mark BFF pool healthy |

## Validation Commands

BFF agent:
```bash
cd bff && python -m mypy . && python -m pytest tests/test_health.py tests/integration/test_health_readyz.py -v --cov --cov-fail-under=90
# Smoke test (no real downstreams — mocked):
curl http://localhost:8000/healthz  # should return {"status": "ok"}
curl http://localhost:8000/readyz   # should return 200 or 503 depending on mock setup
```

## Tests Required

Unit (`tests/test_health.py`):
- `test_healthz_returns_200_no_downstream_calls` — assert no httpx calls made
- `test_healthz_rate_limited` — send 11 requests in 1s, assert 11th returns 429
- `test_readyz_all_checks_pass` — mock all downstreams healthy, assert 200
- `test_readyz_postgres_down` — mock Postgres connection failure, assert 503 with `"postgres": "error: ..."`
- `test_readyz_keycloak_jwks_timeout` — mock JWKS 5s timeout, assert 503 with `"keycloak_jwks": "timeout"`
- `test_readyz_gitlab_api_unreachable` — mock GitLab 5s timeout, assert 503 with `"gitlab_api": "timeout"`
- `test_readyz_rate_limited` — send 11 requests in 1s, assert 11th returns 429

Integration (`tests/integration/test_health_readyz.py`):
- `test_readyz_against_mock_postgres` — fixture provides mock Postgres, assert `/readyz` returns 200
- `test_readyz_postgres_connection_refused` — fixture injects Postgres connection error, assert 503

Coverage targets:
- BFF new business logic: ≥90% line coverage (`pytest --cov --cov-fail-under=90`)

## Acceptance Criteria
- [ ] Given the BFF process is running, when `GET /healthz` is called, then the response is 200 with body `{"status": "ok"}` and no downstream calls are made
- [ ] Given 11 requests to `/healthz` are sent from the same IP in 1 second, when the 11th request arrives, then the response is 429 `{"detail": "Rate limit exceeded"}`
- [ ] Given Postgres, Keycloak JWKS, and GitLab API are all reachable, when `GET /readyz` is called, then the response is 200 with `"checks": {"postgres": "ok", "keycloak_jwks": "ok", "gitlab_api": "ok"}`
- [ ] Given Postgres is unreachable, when `GET /readyz` is called, then the response is 503 with `"checks": {"postgres": "error: connection refused", ...}`
- [ ] Given Keycloak JWKS times out after 5 seconds, when `GET /readyz` is called, then the response is 503 with `"checks": {"keycloak_jwks": "timeout", ...}`
- [ ] Given GitLab API is unreachable, when `GET /readyz` is called, then the response is 503 with `"checks": {"gitlab_api": "timeout", ...}`

## Definition of Done
- [ ] All acceptance criteria pass
- [ ] Python mypy passes with zero errors
- [ ] All unit tests green (`tests/test_health.py`)
- [ ] All integration tests green (`tests/integration/test_health_readyz.py`)
- [ ] BFF coverage ≥90% (`pytest --cov --cov-fail-under=90`)
- [ ] Rate limiting tested (11th request returns 429)
- [ ] Code Reviewer agent approved
- [ ] Security Sentinel agent approved
- [ ] docs/API_CONTRACTS.md updated with `/healthz` and `/readyz` contracts
