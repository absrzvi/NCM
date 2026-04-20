# Story: [STORY-03] Idempotency Middleware
Status: READY
D-decisions touched: D4 (Idempotency-Key header on writes, 24h TTL)

## Why (from PRD)
FR3 and D4 require every write endpoint (POST/PUT/PATCH/DELETE) to enforce an `Idempotency-Key` header. Same key + same fingerprint → return cached response. Same key + different fingerprint → 409. Missing header → 400. 24h TTL. This prevents duplicate MR creation, duplicate force-runs, and stale draft conflicts when clients retry on network errors.

## Assumptions (inherited from PRD + ARCHITECTURE)
- Idempotency keys are stored in the `idempotency_keys` Postgres table (schema defined in ARCHITECTURE.md §3).
- Fingerprint is computed as RFC 8785 JCS (canonical JSON) hash of the request body.
- Keys are user-scoped: `(key, user_sub)` is the PK.
- 24h TTL: rows where `expires_at < NOW()` are eligible for deletion by a periodic sweep job.
- Middleware applies only to write methods (POST/PUT/PATCH/DELETE); GET/HEAD/OPTIONS are exempt.
- Cached response includes original status code and body (stored as JSONB).
- Read endpoints (GET) do NOT require or check idempotency keys.

## What to Build
1. `bff/middleware/idempotency.py` — FastAPI middleware:
   - Check HTTP method; if GET/HEAD/OPTIONS → skip (pass through)
   - If POST/PUT/PATCH/DELETE:
     - Extract `Idempotency-Key` header; if missing → 400
     - Compute fingerprint as RFC 8785 JCS hash of request body
     - Query `idempotency_keys` for `(key, user_sub)`:
       - Not found → proceed with request, cache response before returning
       - Found, same fingerprint → return cached response (status + body)
       - Found, different fingerprint → 409 `{"detail": "Idempotency-Key fingerprint mismatch"}`
   - Store successful response (2xx/3xx) in `idempotency_keys` with `expires_at = now() + 24h`
2. `bff/utils/canonical_json.py` — RFC 8785 JCS helper:
   - `def canonical_json_hash(data: dict) -> str` — returns SHA-256 hex of JCS-serialised data
3. Mount middleware globally in `bff/main.py`

## Affected Files
- bff/middleware/idempotency.py → create (new middleware)
- bff/utils/canonical_json.py → create (JCS helper)
- bff/main.py → mount idempotency middleware
- tests/test_idempotency.py → create (unit tests)
- tests/integration/test_idempotency_replay.py → create (integration tests)

## BFF Endpoint Spec
Not an endpoint — this is middleware applied to all write methods.

All write endpoints (POST/PUT/PATCH/DELETE) enforce:
Idempotency-Key required: yes
Error cases (applied to every write endpoint):
- 400: `{"detail": "Idempotency-Key header required"}` (missing header)
- 409: `{"detail": "Idempotency-Key fingerprint mismatch"}` (same key, different body)

## Cross-Cutting Concerns

| Concern | Owner | Coordinates With | Detail |
|---------|-------|-----------------|--------|
| Idempotency-Key generation | frontend-dev | bff-dev | Frontend generates UUID v4 per write attempt; reuses same key on retry |
| Fingerprint algorithm | bff-dev | security-sentinel | RFC 8785 JCS (canonical JSON serialisation) + SHA-256 |
| TTL sweep job | bff-dev | devops | Periodic job (cron or BFF startup sweep) deletes rows where `expires_at < NOW()` |
| Key scope | bff-dev | bff-dev (auth) | Keys are user-scoped: `(key, user_sub)` PK ensures one user cannot replay another's key |

## Validation Commands

BFF agent:
```bash
cd bff && python -m mypy . && python -m pytest tests/test_idempotency.py tests/integration/test_idempotency_replay.py -v --cov --cov-fail-under=90
```

## Security Tests (mandatory)
- [ ] Write endpoint called without `Idempotency-Key` header returns 400
- [ ] Write endpoint called with `Idempotency-Key` and body `{"a": 1}`, then replayed with same key and same body, returns cached response without re-executing
- [ ] Write endpoint called with `Idempotency-Key` and body `{"a": 1}`, then replayed with same key and body `{"a": 2}`, returns 409
- [ ] Two different users use the same `Idempotency-Key` UUID with different bodies → each succeeds independently (keys are user-scoped)
- [ ] Cached response with status 201 is returned as 201 on replay (not 200)
- [ ] Cached response expires after 24h (fixture advances time, assert cache miss)

## Tests Required

Unit (`tests/test_idempotency.py`):
- `test_idempotency_key_missing` — POST without header, assert 400
- `test_idempotency_key_cache_miss` — POST with key, no existing row, assert request proceeds and response is cached
- `test_idempotency_key_cache_hit_same_fingerprint` — POST with key, existing row with same fingerprint, assert cached response returned
- `test_idempotency_key_fingerprint_mismatch` — POST with key, existing row with different fingerprint, assert 409
- `test_idempotency_key_scoped_to_user` — two users with same key, assert each has independent cache
- `test_canonical_json_hash_deterministic` — assert `canonical_json_hash({"b": 2, "a": 1})` == `canonical_json_hash({"a": 1, "b": 2})`
- `test_get_request_bypasses_idempotency` — GET request, no `Idempotency-Key` header, assert passes through

Integration (`tests/integration/test_idempotency_replay.py`):
- `test_idempotency_replay_against_mock_postgres` — fixture provides mock Postgres, POST twice with same key and body, assert second returns cached 201
- `test_idempotency_ttl_expiry` — fixture advances time by 25h, assert cache miss on replay

Coverage targets:
- BFF new business logic: ≥90% line coverage (`pytest --cov --cov-fail-under=90`)

## Acceptance Criteria
- [ ] Given a write endpoint is called without an `Idempotency-Key` header, when the request arrives, then the response is 400 `{"detail": "Idempotency-Key header required"}`
- [ ] Given a write endpoint is called with `Idempotency-Key: <uuid>` and body `{"a": 1}`, when the request succeeds with 201, then the response is cached in `idempotency_keys` with `expires_at = now() + 24h`
- [ ] Given a write endpoint is called with `Idempotency-Key: <uuid>` and body `{"a": 1}`, and the same request is replayed, when the second request arrives, then the cached 201 response is returned without re-executing the endpoint logic
- [ ] Given a write endpoint is called with `Idempotency-Key: <uuid>` and body `{"a": 1}`, and a second request arrives with the same key but body `{"a": 2}`, when the second request arrives, then the response is 409 `{"detail": "Idempotency-Key fingerprint mismatch"}`
- [ ] Given two users call the same write endpoint with the same `Idempotency-Key` UUID but different bodies, when both requests arrive, then each succeeds independently (keys are user-scoped)
- [ ] Given a cached response has `expires_at` in the past, when the same `Idempotency-Key` is replayed, then the cache is treated as expired and the request re-executes

## Definition of Done
- [ ] All acceptance criteria pass
- [ ] Python mypy passes with zero errors
- [ ] All security tests pass (missing key, replay same body, replay different body, user scoping, TTL expiry)
- [ ] All unit tests green (`tests/test_idempotency.py`)
- [ ] All integration tests green (`tests/integration/test_idempotency_replay.py`)
- [ ] BFF coverage ≥90% (`pytest --cov --cov-fail-under=90`)
- [ ] RFC 8785 JCS fingerprinting tested (key order independence)
- [ ] GET requests bypass idempotency check
- [ ] Code Reviewer agent approved
- [ ] Security Sentinel agent approved
- [ ] docs/API_CONTRACTS.md updated with idempotency requirement on all write endpoints
