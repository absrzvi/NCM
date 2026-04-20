# BFF API Contracts

> Maintained by architect and bff-dev agents.
> Frontend-dev reads this as the source of truth for all response types.
> Any change here must be communicated to frontend-dev immediately.

---

## GET /healthz
Auth: None (unauthenticated — infrastructure probe)
Role: None
Idempotency-Key required: No
SLO: none (reason: infra liveness probe, not user-facing)
Request: none
Response (200): `{"status": "ok"}`
Downstream: none
Error codes:
- 429: `{"detail": "Rate limit exceeded"}` (> 10 req/s per IP)

## GET /readyz
Auth: None (unauthenticated — infrastructure probe)
Role: None
Idempotency-Key required: No
SLO: none (reason: infra readiness probe, not user-facing)
Request: none
Response (200): `{"status": "ready", "checks": {"postgres": "ok", "keycloak_jwks": "ok", "gitlab_api": "ok"}}`
Response (503): `{"status": "not_ready", "checks": {"postgres": "<ok|error: ...>", "keycloak_jwks": "<ok|timeout|error: ...>", "gitlab_api": "<ok|timeout|error: ...>"}}`
Downstream: Postgres (`SELECT 1`), Keycloak JWKS (`GET <KEYCLOAK_JWKS_URI>`), GitLab API (`GET <GITLAB_API_BASE_URL>/api/v4/version`). All with 5s timeout. PuppetDB is NOT checked (soft dependency).
Error codes:
- 429: `{"detail": "Rate limit exceeded"}` (> 10 req/s per IP)
- 503: one or more downstream checks failed (see `checks` body for details)

---

## Idempotency Requirements (D4 — applies to ALL write endpoints)

Every `POST`, `PUT`, `PATCH`, and `DELETE` endpoint in the `/api/*` namespace
**requires** an `Idempotency-Key` header.  Frontend must generate a UUID v4 per
write attempt and reuse the same value on retries.

| Scenario | Response |
|----------|----------|
| `Idempotency-Key` header absent | `400 {"detail": "Idempotency-Key header required"}` |
| Key not seen before (or expired) | Request proceeds normally; successful response cached for 24h |
| Key seen, same request body | Cached response returned (same status code) — no duplicate processing |
| Key seen, different request body | `409 {"detail": "Idempotency-Key fingerprint mismatch"}` |

Fingerprint algorithm: SHA-256 of RFC 8785 JCS canonical JSON of the request body.
Keys are user-scoped: `(Idempotency-Key, user_sub)` is the composite lookup key.
TTL: 24 hours.  Expired keys may be reused.

Read endpoints (`GET`, `HEAD`, `OPTIONS`) are exempt.

---

## Contract Template

### [METHOD] /api/[module]/[resource]
Auth: Keycloak JWT required via `get_current_user`
Role: viewer | editor | admin
Idempotency-Key required: yes (write) | no (read)
SLO: write-path | read-path | none (reason)
Request: [Pydantic model or "none"]
Response: [Pydantic model]
Downstream: [GitLab | PuppetDB | Puppet Server | Keycloak] at [endpoint]
D14 gates triggered (if hieradata write): [list]
Error codes:
- 401: JWT invalid or expired
- 403: Insufficient role
- 400: Idempotency-Key header required (write endpoints only)
- 409: Idempotency-Key fingerprint mismatch (write endpoints only)
- 422: D14 gate failure (hieradata writes) or validation error
- 502: downstream service unavailable
