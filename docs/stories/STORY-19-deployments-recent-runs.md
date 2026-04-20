# STORY-19: GET /api/deployments/recent-runs

**Status:** READY

---

## Summary

Implement the `GET /api/deployments/recent-runs` endpoint on the BFF. This endpoint queries PuppetDB for the most recent Puppet run records per fleet, returning run timestamps, exit status, and catalog-apply outcomes for each certname. It must degrade gracefully when PuppetDB is unreachable: return the last cached result from Postgres and attach a staleness banner to the response so the frontend can inform the user that data may be stale.

This endpoint feeds the Deployments page (`/deployments`) and the Overview page KPI cards (`/`).

---

## Assumptions

1. `STORY-05` is DONE and `bff/clients/puppetdb_client.py` exposes `async def query_puppetdb(pql: str) -> list[dict]` (httpx-based, raises `HTTPException(502)` on unreachable).
2. `STORY-04` is DONE and Postgres is available; the `recent_runs_cache` table (or equivalent column set on an existing table) is used to persist the last successful PuppetDB result per fleet.
3. "Last N runs per fleet" defaults to N=20. N is configurable via a BFF env var `RECENT_RUNS_LIMIT` (default `20`); it is not a query parameter exposed to the frontend in MVP.
4. Fleet values are the canonical NMS+ names: `alpin`, `dostoneu`, `dani`. These are resolved from the environment config loaded in `STORY-06`.
5. PuppetDB staleness tolerance is 5 minutes (CLAUDE.md §SLO). When the last successful fetch is older than 5 minutes, the response includes `"stale": true` and `"stale_since": <ISO-8601 timestamp>`.
6. The endpoint is read-only and does not require an `Idempotency-Key` header.
7. Authentication is mandatory: `get_current_user` from `STORY-02` is injected on the route. All roles (viewer, editor, admin) may call this endpoint.
8. Raw PuppetDB response fields are validated and mapped to the `RecentRunRecord` Pydantic v2 model before returning — never proxy the raw PuppetDB JSON to the frontend.
9. If the cache is also empty (cold start, first boot) and PuppetDB is unreachable, return HTTP 503 with `{ "error_code": "puppetdb_unavailable", "detail": "PuppetDB unreachable and no cached data available" }`.

---

## Dependencies

| Dependency | Type | Unblock Condition |
|---|---|---|
| STORY-05 (puppetdb_client) | Hard — PuppetDB queries require the client wrapper | STORY-05 Status = DONE |
| STORY-04 (Postgres schema) | Hard — staleness cache requires a Postgres table | STORY-04 Status = DONE |
| STORY-06 (env config loader) | Hard — fleet names and PuppetDB target branch config | STORY-06 Status = DONE |
| STORY-02 (JWT middleware) | Hard — `get_current_user` dependency injection | STORY-02 Status = DONE |

---

## Acceptance Criteria

### AC-1: Happy path — PuppetDB reachable, returns recent runs

**Given** a valid Keycloak JWT with any role (viewer, editor, or admin)  
**And** PuppetDB is reachable and returns run records for the requested fleet  
**When** `GET /api/deployments/recent-runs?fleet=alpin` is called  
**Then** the response is HTTP 200  
**And** the body contains a list of `RecentRunRecord` objects with fields: `certname`, `last_run_at` (ISO-8601), `status` (`succeeded` | `failed` | `unchanged`), `catalog_version`, `puppet_environment`  
**And** the response includes `"stale": false`  
**And** the result is written to the Postgres cache for subsequent graceful-degradation use

### AC-2: Graceful degradation — PuppetDB unreachable, cache populated

**Given** a valid Keycloak JWT  
**And** PuppetDB is unreachable (connection refused / timeout)  
**And** a prior successful fetch is stored in the Postgres cache for the requested fleet  
**When** `GET /api/deployments/recent-runs?fleet=alpin` is called  
**Then** the response is HTTP 200  
**And** the cached run records are returned  
**And** the response includes `"stale": true` and `"stale_since": <ISO-8601 timestamp of last successful fetch>`  
**And** no 502 or 500 is returned to the client

### AC-3: Graceful degradation — PuppetDB unreachable, cache empty

**Given** a valid Keycloak JWT  
**And** PuppetDB is unreachable  
**And** no cached data exists for the requested fleet  
**When** `GET /api/deployments/recent-runs?fleet=alpin` is called  
**Then** the response is HTTP 503  
**And** the body is `{ "error_code": "puppetdb_unavailable", "detail": "PuppetDB unreachable and no cached data available" }`

### AC-4: Missing or invalid JWT

**Given** no `Authorization` header, or an expired/malformed JWT  
**When** `GET /api/deployments/recent-runs?fleet=alpin` is called  
**Then** the response is HTTP 401  
**And** the response body shape is identical to a 403 response (no resource-existence leakage)

### AC-5: Invalid fleet parameter

**Given** a valid Keycloak JWT  
**And** `fleet` query parameter is not one of `alpin`, `dostoneu`, `dani`  
**When** `GET /api/deployments/recent-runs?fleet=unknown` is called  
**Then** the response is HTTP 422  
**And** the body includes a validation error identifying the invalid `fleet` value

### AC-6: PuppetDB staleness banner propagated

**Given** the last successful PuppetDB fetch for the fleet was more than 5 minutes ago  
**And** PuppetDB is currently reachable  
**When** `GET /api/deployments/recent-runs?fleet=alpin` is called and PuppetDB returns fresh data  
**Then** the cache timestamp is refreshed  
**And** the response includes `"stale": false` (data is now fresh)

---

## Definition of Done

- [ ] `bff/routers/deployments.py` contains `GET /api/deployments/recent-runs` route
- [ ] `bff/models/deployments.py` (or `bff/routers/deployments.py`) defines `RecentRunRecord` Pydantic v2 model with fields: `certname: str`, `last_run_at: datetime`, `status: Literal["succeeded", "failed", "unchanged"]`, `catalog_version: str | None`, `puppet_environment: str`
- [ ] Response model `RecentRunsResponse` contains: `runs: list[RecentRunRecord]`, `stale: bool`, `stale_since: datetime | None`
- [ ] Postgres cache read/write for graceful degradation is implemented
- [ ] `RECENT_RUNS_LIMIT` env var respected (default 20)
- [ ] `fleet` query parameter validated against known fleet list; unknown fleet → 422
- [ ] `get_current_user` injected; unauthenticated → 401
- [ ] All downstream PuppetDB calls use `puppetdb_client.query_puppetdb` — no inline httpx calls
- [ ] BFF unit tests cover: happy path, PuppetDB unreachable + cache hit, PuppetDB unreachable + cache miss, invalid fleet, unauthenticated
- [ ] Integration tests use PuppetDB fixture (no real PuppetDB calls)
- [ ] Security tests: unauthenticated → 401, malformed JWT → 401
- [ ] `pytest --cov --cov-fail-under=90` passes on new modules
- [ ] `mypy` passes with zero errors on new modules
- [ ] `npx tsc --noEmit` passes (no frontend changes in this story)
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

Rationale: this endpoint queries PuppetDB (a soft dependency with a 5-minute staleness tolerance). It must not block the frontend beyond 500ms p95. When PuppetDB exceeds the staleness window, the endpoint degrades to cached data and sets `stale: true` rather than returning an error.

---

## File Locations

- Router: `bff/routers/deployments.py`
- Models: `bff/models/deployments.py`
- Unit tests: `tests/unit/routers/test_deployments_recent_runs.py`
- Integration tests: `tests/integration/routers/test_deployments_recent_runs_integration.py`
- PuppetDB fixtures: `tests/fixtures/alpin/` (recent_runs PQL response)

---

## Notes for Implementer

- The PQL query for recent runs is: `nodes[certname, report_timestamp, status, catalog_uuid, environment] { catalog_environment = "<puppet_environment>" order by report_timestamp desc limit <N> }`. Adjust field names to match the PuppetDB version in the DC.
- Cache writes must be async (no blocking Postgres calls from a FastAPI route). Use `asyncpg` or the async SQLAlchemy session already established by STORY-04.
- The `stale_since` timestamp comes from the `fetched_at` column of the cache row, not from the PuppetDB record timestamps.
- Never log PuppetDB token or certname values at DEBUG level — log correlation IDs only.
- "Puppet environment" in the response field refers to the r10k branch (`devel`/`staging`), not the fleet. Use the qualified term in code comments.
