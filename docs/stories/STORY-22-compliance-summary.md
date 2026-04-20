# STORY-22: GET /api/compliance/summary

**Status:** READY

---

## Summary

Implement the `GET /api/compliance/summary` endpoint on the BFF. This endpoint returns aggregated drift counts per fleet (total nodes, drifted count, failed count, compliant count) for use in the Overview page KPI cards (`/`). To avoid hammering PuppetDB on every Overview page load, the aggregated counts are cached in Postgres with a 5-minute TTL. The cache is refreshed lazily on first request after expiry (stale-while-revalidate pattern).

The endpoint must also degrade gracefully when PuppetDB is unreachable: return the cached summary with a staleness banner rather than an error.

---

## Assumptions

1. `STORY-05` is DONE and `bff/clients/puppetdb_client.py` exposes `async def query_puppetdb(pql: str) -> list[dict]`.
2. `STORY-04` is DONE and Postgres is available; a `compliance_summary_cache` table (or equivalent) stores one row per fleet with columns: `fleet`, `total`, `drifted`, `failed`, `compliant`, `fetched_at`.
3. Cache TTL is 5 minutes, aligned to the PuppetDB staleness SLO. The TTL is configurable via `COMPLIANCE_SUMMARY_CACHE_TTL_SECONDS` env var (default 300).
4. Stale-while-revalidate: if the cache row exists but `fetched_at` is older than 5 minutes, return the cached value immediately (with `"stale": true`) and trigger a background refresh. Do not block the HTTP response on the PuppetDB query.
5. Authentication is mandatory: all roles (viewer, editor, admin) may call this endpoint.
6. The endpoint is read-only; no `Idempotency-Key` header is required.
7. If both PuppetDB is unreachable and the cache is empty, return HTTP 503 with `{ "error_code": "puppetdb_unavailable", "detail": "PuppetDB unreachable and no cached data available" }`.
8. The `fleet` query parameter is optional. If omitted, the response returns a summary object for each fleet the authenticated user has access to (all three in MVP single-tenant mode). If provided, only that fleet's summary is returned.
9. Raw PuppetDB counts are mapped to `ComplianceSummary` Pydantic v2 model before returning — never proxy raw PuppetDB JSON to the frontend.

---

## Dependencies

| Dependency | Type | Unblock Condition |
|---|---|---|
| STORY-05 (puppetdb_client) | Hard — PuppetDB queries require the client wrapper | STORY-05 Status = DONE |
| STORY-04 (Postgres schema) | Hard — 5-minute cache requires a Postgres table | STORY-04 Status = DONE |
| STORY-02 (JWT middleware) | Hard — `get_current_user` dependency injection | STORY-02 Status = DONE |

---

## Acceptance Criteria

### AC-1: Happy path — cache is fresh (within 5 minutes)

**Given** a valid Keycloak JWT with any role  
**And** the Postgres cache for the requested fleet has `fetched_at` within the last 5 minutes  
**When** `GET /api/compliance/summary?fleet=alpin` is called  
**Then** the response is HTTP 200  
**And** the cached summary is returned without querying PuppetDB  
**And** the response includes `"stale": false`  
**And** the body contains `{ "fleet": "alpin", "total": <int>, "drifted": <int>, "failed": <int>, "compliant": <int>, "stale": false, "stale_since": null }`

### AC-2: Cache expired — returns stale data and triggers background refresh

**Given** a valid Keycloak JWT  
**And** the Postgres cache for the fleet has `fetched_at` older than 5 minutes  
**When** `GET /api/compliance/summary?fleet=alpin` is called  
**Then** the response is HTTP 200 with the cached (stale) data immediately  
**And** the response includes `"stale": true` and `"stale_since": <ISO-8601 timestamp>`  
**And** a background task is triggered to refresh the cache from PuppetDB  
**And** the HTTP response is not blocked on the PuppetDB refresh

### AC-3: No fleet parameter — returns summary for all fleets

**Given** a valid Keycloak JWT  
**And** cached data exists for all fleets  
**When** `GET /api/compliance/summary` is called (no `fleet` parameter)  
**Then** the response is HTTP 200  
**And** the body contains a list of `ComplianceSummary` objects, one per fleet

### AC-4: Graceful degradation — PuppetDB unreachable, cache populated

**Given** a valid Keycloak JWT  
**And** PuppetDB is unreachable  
**And** cached data exists for the fleet (even if stale)  
**When** `GET /api/compliance/summary?fleet=alpin` is called  
**Then** the response is HTTP 200 with cached data  
**And** `"stale": true` is set

### AC-5: Graceful degradation — PuppetDB unreachable, cache empty

**Given** a valid Keycloak JWT  
**And** PuppetDB is unreachable  
**And** no cached data exists for the fleet  
**When** `GET /api/compliance/summary?fleet=alpin` is called  
**Then** the response is HTTP 503  
**And** the body is `{ "error_code": "puppetdb_unavailable", "detail": "PuppetDB unreachable and no cached data available" }`

### AC-6: Missing or invalid JWT

**Given** no `Authorization` header or an expired/malformed JWT  
**When** `GET /api/compliance/summary` is called  
**Then** the response is HTTP 401  
**And** the response body shape is identical to a 403 response

### AC-7: Invalid fleet parameter

**Given** a valid Keycloak JWT  
**And** `fleet` is provided but is not one of `alpin`, `dostoneu`, `dani`  
**When** `GET /api/compliance/summary?fleet=unknown` is called  
**Then** the response is HTTP 422

---

## Definition of Done

- [ ] `bff/routers/compliance.py` contains `GET /api/compliance/summary` route (alongside STORY-21 drift route)
- [ ] `ComplianceSummary` Pydantic v2 model: `fleet: str`, `total: int`, `drifted: int`, `failed: int`, `compliant: int`, `stale: bool`, `stale_since: datetime | None`
- [ ] Postgres `compliance_summary_cache` table used for 5-minute TTL caching
- [ ] `COMPLIANCE_SUMMARY_CACHE_TTL_SECONDS` env var respected (default 300)
- [ ] Stale-while-revalidate: stale cache returns immediately; background refresh triggered asynchronously
- [ ] `fleet` query parameter is optional; when omitted, all fleets returned
- [ ] `get_current_user` injected; unauthenticated → 401
- [ ] All PuppetDB calls use `puppetdb_client.query_puppetdb` — no inline httpx calls
- [ ] BFF unit tests: cache hit (fresh), cache hit (stale + background refresh), no fleet param, PuppetDB unreachable + cache hit, PuppetDB unreachable + cache miss, invalid fleet, unauthenticated
- [ ] Background refresh task is tested independently (mock the cache write)
- [ ] Integration tests use PuppetDB fixtures (no real PuppetDB calls)
- [ ] Security tests: unauthenticated → 401, malformed JWT → 401
- [ ] `pytest --cov --cov-fail-under=90` passes on new modules
- [ ] `mypy` passes with zero errors on new modules
- [ ] `docs/API_CONTRACTS.md` updated with this endpoint's request/response shape
- [ ] Story Status set to DONE

---

## D-Decisions Touched

| Decision | Relevance |
|---|---|
| **D1** | Browser never calls PuppetDB directly; this BFF endpoint is the only path |
| **D9** | All PuppetDB queries use `puppetdb_client.py` which uses `httpx.AsyncClient` exclusively |

---

## SLO Assignment

**Read-path p95 <500ms** AND **PuppetDB staleness <5min**

Rationale: the 5-minute Postgres cache ensures this endpoint does not depend on PuppetDB response time for the common case. The stale-while-revalidate pattern means the HTTP response is never blocked on a live PuppetDB query, keeping p95 <500ms even when PuppetDB is slow.

---

## File Locations

- Router: `bff/routers/compliance.py`
- Models: `bff/models/compliance.py`
- Cache table: defined in STORY-04 migration (add `compliance_summary_cache` table if not already present)
- Unit tests: `tests/unit/routers/test_compliance_summary.py`
- Integration tests: `tests/integration/routers/test_compliance_summary_integration.py`

---

## Notes for Implementer

- The background refresh task must use FastAPI's `BackgroundTasks` mechanism. Do not spin up a thread or a separate asyncio task that outlives the request lifecycle without explicit cleanup.
- The aggregation PQL query counts nodes by status bucket across all certnames in the fleet's Puppet environment. Verify the exact PQL syntax against the DC PuppetDB version.
- `compliance_summary_cache` and the drift cache from STORY-21 are logically separate concerns. Do not conflate the two cache tables — they serve different queries and have different TTLs (both happen to be 5 minutes, but that may diverge).
- In the single-tenant MVP (D3/Iron Rule 3), "all fleets the user has access to" means all three fleets (`alpin`, `dostoneu`, `dani`). No per-fleet access scoping is applied. This must not be "future-proofed" with customer_id columns — that is a phase-3 ADR.
