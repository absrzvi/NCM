# Story: [STORY-02] JWT Middleware and get_current_user
Status: READY
D-decisions touched: D2 (Keycloak JWT RS256), D3 (single-tenant get_current_user)

## Why (from PRD)
Iron Rule 2 requires Keycloak JWT validation on EVERY BFF endpoint. D2 locks RS256 validation with JWKS cached hourly. D3 mandates `get_current_user` returns `sub` + `roles` from the JWT with no `customer_id` scoping (single-tenant MVP).

## Assumptions (inherited from PRD + ARCHITECTURE)
- Keycloak realm URL and JWKS URI are provided via environment variables (`KEYCLOAK_REALM_URL`, `KEYCLOAK_JWKS_URI`).
- JWTs are RS256-signed; JWKS contains the public key for verification.
- JWKS is cached in-memory for 1 hour; refreshed on cache miss or expiry.
- Every endpoint (except `/healthz` and `/readyz`) calls `get_current_user` as a dependency.
- Missing JWT → 401 `{"detail": "Not authenticated"}`.
- Malformed or expired JWT → 401 `{"detail": "Not authenticated"}`.
- `get_current_user` extracts `sub` (user identity) and `roles` (array of role strings) from the JWT `realm_access.roles` claim.
- No `customer_id` field in the return value — single-tenant MVP (D3, Iron Rule 3).

## What to Build
1. `bff/clients/keycloak_jwks.py` — JWKS fetcher with 1-hour in-memory cache:
   - `async def get_jwks() -> dict` — fetches JWKS from Keycloak, caches for 1h
   - Uses `httpx.AsyncClient` with 10s timeout
2. `bff/middleware/auth.py` — JWT verification logic:
   - `async def verify_jwt(token: str) -> dict` — verifies RS256 signature using JWKS, checks `exp` claim
   - Returns decoded JWT payload if valid; raises `HTTPException(401)` if invalid/expired
3. `bff/dependencies.py` — FastAPI dependency:
   - `async def get_current_user(authorization: str = Header(None)) -> CurrentUser` — extracts Bearer token, calls `verify_jwt`, returns `CurrentUser(sub=..., roles=[...])`
   - `CurrentUser` Pydantic model: `sub: str`, `roles: list[str]`, no `customer_id` field
4. All routers (except health) import and use `get_current_user` as a dependency

## Affected Files
- bff/clients/keycloak_jwks.py → create (new client)
- bff/middleware/auth.py → create (JWT verification)
- bff/dependencies.py → create (get_current_user FastAPI dependency)
- bff/models/user.py → create (CurrentUser Pydantic model)
- tests/test_auth.py → create (unit tests)
- tests/integration/test_jwt_verification.py → create (integration tests with fixture JWTs)

## BFF Endpoint Spec
Not an endpoint — this is middleware applied to all routes except `/healthz` and `/readyz`.

All authenticated endpoints enforce:
Auth: Keycloak JWT required via `get_current_user`
Error cases (applied to every route):
- 401: `{"detail": "Not authenticated"}` (missing, malformed, or expired JWT)

## Cross-Cutting Concerns

| Concern | Owner | Coordinates With | Detail |
|---------|-------|-----------------|--------|
| JWT header format | bff-dev | frontend-dev | `Authorization: Bearer <token>` — standard OAuth2 format |
| JWKS cache TTL | bff-dev | devops | 1-hour in-memory cache; no Redis in MVP (D8 single-container) |
| Role claim path | bff-dev | keycloak admin | Roles extracted from `realm_access.roles` (Keycloak default structure) |
| No customer_id field | bff-dev | all downstream stories | Iron Rule 3 — single-tenant MVP; multi-tenancy deferred to phase-3 |

## Validation Commands

BFF agent:
```bash
cd bff && python -m mypy . && python -m pytest tests/test_auth.py tests/integration/test_jwt_verification.py -v --cov --cov-fail-under=90
```

## Security Tests (mandatory)
- [ ] Unauthenticated request (no Authorization header) to any protected endpoint returns 401 with no data
- [ ] Malformed JWT (`Authorization: Bearer not-a-jwt`) returns 401
- [ ] Expired JWT (fixture with `exp` in the past) returns 401
- [ ] Valid JWT with `viewer` role, calling a protected endpoint, extracts `sub` and `roles` correctly
- [ ] Valid JWT with no `realm_access.roles` claim defaults to empty roles list
- [ ] JWKS cache hit (second call within 1h) does not make a second Keycloak request
- [ ] JWKS cache miss (after 1h expiry) fetches JWKS again

## Tests Required

Unit (`tests/test_auth.py`):
- `test_verify_jwt_valid_token` — mock JWKS, assert decoded payload returned
- `test_verify_jwt_expired_token` — fixture JWT with `exp` in past, assert 401
- `test_verify_jwt_malformed_token` — assert 401 on malformed token
- `test_verify_jwt_signature_mismatch` — mock wrong JWKS key, assert 401
- `test_get_current_user_extracts_sub_and_roles` — valid JWT, assert `CurrentUser(sub="...", roles=["viewer"])`
- `test_get_current_user_missing_authorization_header` — assert 401
- `test_get_current_user_no_customer_id_field` — assert `CurrentUser` model has no `customer_id` attribute

Integration (`tests/integration/test_jwt_verification.py`):
- `test_jwt_verification_against_fixture_jwks` — fixture provides canned JWKS, valid JWT, assert verification succeeds
- `test_jwt_verification_keycloak_unreachable` — mock Keycloak timeout, assert 401 with "Not authenticated" (graceful degradation)

Coverage targets:
- BFF new business logic: ≥90% line coverage (`pytest --cov --cov-fail-under=90`)

## Acceptance Criteria
- [ ] Given a protected endpoint receives a request with no Authorization header, when `get_current_user` is called, then the response is 401 `{"detail": "Not authenticated"}`
- [ ] Given a protected endpoint receives a request with a malformed JWT, when `get_current_user` is called, then the response is 401 `{"detail": "Not authenticated"}`
- [ ] Given a protected endpoint receives a request with an expired JWT, when `get_current_user` is called, then the response is 401 `{"detail": "Not authenticated"}`
- [ ] Given a protected endpoint receives a request with a valid JWT containing `sub: "user123"` and `realm_access.roles: ["viewer"]`, when `get_current_user` is called, then it returns `CurrentUser(sub="user123", roles=["viewer"])`
- [ ] Given `get_current_user` is called twice within 1 hour with the same JWT, when JWKS is fetched, then only one Keycloak request is made (cache hit on second call)
- [ ] Given the `CurrentUser` model is inspected, when checking its fields, then no `customer_id` field exists (D3 single-tenant enforcement)

## Definition of Done
- [ ] All acceptance criteria pass
- [ ] Python mypy passes with zero errors
- [ ] All security tests pass (unauthenticated, malformed, expired JWT scenarios)
- [ ] All unit tests green (`tests/test_auth.py`)
- [ ] All integration tests green (`tests/integration/test_jwt_verification.py`)
- [ ] BFF coverage ≥90% (`pytest --cov --cov-fail-under=90`)
- [ ] `CurrentUser` model has no `customer_id` field (D3 enforced)
- [ ] JWKS cache behaviour tested (cache hit within 1h)
- [ ] Code Reviewer agent approved
- [ ] Security Sentinel agent approved
- [ ] docs/API_CONTRACTS.md updated with auth requirement template
