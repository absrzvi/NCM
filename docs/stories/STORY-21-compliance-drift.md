# STORY-21: GET /api/compliance/drift

**Status:** READY

---

## Summary

Implement the `GET /api/compliance/drift` endpoint on the BFF. This endpoint executes a PQL query against PuppetDB to retrieve per-device drift reports for a given fleet, returning a structured drift classification per certname. The endpoint powers the Compliance page (`/compliance`).

It must degrade gracefully when PuppetDB is unreachable: return the last cached result from Postgres with a staleness banner rather than an error, consistent with the PuppetDB staleness SLO (<5 min).

---

## Assumptions

1. `STORY-05` is DONE and `bff/clients/puppetdb_client.py` exposes `async def query_puppetdb(pql: str) -> list[dict]`.
2. `STORY-04` is DONE and Postgres is available for caching drift results per fleet.
3. "Drift" is defined as a certname where the last Puppet run reported `status = "failed"` or where resource-level corrective changes were applied. The PQL query targets the `reports` or `events` endpoint of PuppetDB — the exact PQL is determined by the PuppetDB version available in the DC (implementer must verify against the instance). The response model must abstract over PuppetDB internals.
4. Drift classification values are: `"drifted"` (corrective changes applied), `"failed"` (run failed), `"compliant"` (no drift, run succeeded). These are the only three values emitted to the frontend.
5. Authentication is mandatory: all roles (viewer, editor, admin) may call this endpoint.
6. The endpoint is read-only; no `Idempotency-Key` header is required.
7. If PuppetDB is unreachable and the cache is empty, return HTTP 503 with `{ "error_code": "puppetdb_unavailable", "detail": "PuppetDB unreachable and no cached data available" }`.
8. Raw PuppetDB response fields are validated and mapped to `DriftRecord` Pydantic v2 model before returning — never proxy raw PuppetDB JSON to the frontend.
9. `fleet` is a required query parameter; unknown fleet values → 422.

---

## Dependencies

| Dependency | Type | Unblock Condition |
|---|---|---|
| STORY-05 (puppetdb_client) | Hard — PuppetDB queries require the client wrapper | STORY-05 Status = DONE |
| STORY-04 (Postgres schema) | Hard — staleness cache requires a Postgres table | STORY-04 Status = DONE |
| STORY-02 (JWT middleware) | Hard — `get_current_user` dependency injection | STORY-02 Status = DONE |

---

## Acceptance Criteria

### AC-1: Happy path — PuppetDB reachable, returns drift records

**Given** a valid Keycloak JWT with any role  
**And** PuppetDB is reachable and returns drift data for the requested fleet  
**When** `GET /api/compliance/drift?fleet=alpin` is called  
**Then** the response is HTTP 200  
**And** the body contains a list of `DriftRecord` objects with fields: `certname`, `classification` (`"drifted"` | `"failed"` | `"compliant"`), `last_run_at` (ISO-8601), `resource_count` (integer count of drifted resources, 0 if compliant)  
**And** the response includes `"stale": false`  
**And** the result is written to the Postgres cache

### AC-2: Graceful degradation — PuppetDB unreachable, cache populated

**Given** a valid Keycloak JWT  
**And** PuppetDB is unreachable  
**And** a prior successful fetch is in the Postgres cache for the requested fleet  
**When** `GET /api/compliance/drift?fleet=alpin` is called  
**Then** the response is HTTP 200  
**And** the cached drift records are returned  
**And** the response includes `"stale": true` and `"stale_since": <ISO-8601 timestamp>`  
**And** no 502 or 500 is returned

### AC-3: Graceful degradation — PuppetDB unreachable, cache empty

**Given** a valid Keycloak JWT  
**And** PuppetDB is unreachable  
**And** no cached data exists for the requested fleet  
**When** `GET /api/compliance/drift?fleet=alpin` is called  
**Then** the response is HTTP 503  
**And** the body is `{ "error_code": "puppetdb_unavailable", "detail": "PuppetDB unreachable and no cached data available" }`

### AC-4: Missing or invalid JWT

**Given** no `Authorization` header, or an expired/malformed JWT  
**When** `GET /api/compliance/drift?fleet=alpin` is called  
**Then** the response is HTTP 401  
**And** the response body shape is identical to a 403 response

### AC-5: Invalid fleet parameter

**Given** a valid Keycloak JWT  
**And** `fleet` query parameter is not one of `alpin`, `dostoneu`, `dani`  
**When** `GET /api/compliance/drift?fleet=unknown` is called  
**Then** the response is HTTP 422  
**And** the body identifies the invalid `fleet` value

### AC-6: Missing fleet parameter

**Given** a valid Keycloak JWT  
**And** `fleet` query parameter is absent  
**When** `GET /api/compliance/drift` is called  
**Then** the response is HTTP 422  
**And** the body identifies `fleet` as a required parameter

---

## Definition of Done

- [ ] `bff/routers/compliance.py` contains `GET /api/compliance/drift` route
- [ ] `DriftRecord` Pydantic v2 model: `certname: str`, `classification: Literal["drifted", "failed", "compliant"]`, `last_run_at: datetime`, `resource_count: int`
- [ ] `DriftResponse` model: `records: list[DriftRecord]`, `stale: bool`, `stale_since: datetime | None`
- [ ] Postgres cache read/write for graceful degradation implemented
- [ ] `fleet` query parameter validated against known fleet list; unknown → 422; missing → 422
- [ ] `get_current_user` injected; unauthenticated → 401
- [ ] All PuppetDB calls use `puppetdb_client.query_puppetdb` — no inline httpx calls
- [ ] BFF unit tests: happy path, PuppetDB unreachable + cache hit, PuppetDB unreachable + cache miss, invalid fleet, missing fleet, unauthenticated
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

Rationale: this endpoint queries PuppetDB (soft dependency, 5-minute staleness tolerance). Graceful degradation to cache is mandatory when PuppetDB exceeds the staleness window. Response must not exceed 500ms p95 under normal operating conditions.

---

## File Locations

- Router: `bff/routers/compliance.py`
- Models: `bff/models/compliance.py`
- Unit tests: `tests/unit/routers/test_compliance_drift.py`
- Integration tests: `tests/integration/routers/test_compliance_drift_integration.py`
- PuppetDB fixtures: `tests/fixtures/alpin/` (drift report PQL response)

---

## Notes for Implementer

- The PQL query for drift is fleet-scoped; filter by `catalog_environment` or `facts.environment` depending on how the DC PuppetDB is configured. Verify against the actual PuppetDB API version before coding.
- Classification logic: if `status = "changed"` with corrective resources → `"drifted"`; if `status = "failed"` → `"failed"`; if `status = "unchanged"` or `status = "changed"` with no corrective resources → `"compliant"`.
- Cache writes are async — no blocking Postgres I/O from the async route handler.
- Use `"puppet_environment"` (qualified) in code comments and variable names when referring to the r10k branch. Never bare `"environment"`.
- The `resource_count` field for `"failed"` records may be 0 (the run failed before resource application); this is valid and must not be treated as an error.
