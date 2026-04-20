# STORY-23: GET /api/audit/events

**Status:** READY

---

## Summary

Implement the `GET /api/audit/events` endpoint on the BFF. This endpoint returns a unified audit event log by joining two sources:

1. **Postgres `audit_events` table** — UI-initiated events written by BFF write endpoints (force-run triggers, draft applies, etc.).
2. **GitLab commit/MR history** — commits and MRs on the fleet's hieradata repo (via `python-gitlab`, D6).

Events from GitLab that were not authored by the NMS+ service account are flagged as `"external_edit": true` — these represent commits made directly to the repo outside of the NMS+ Config UI (e.g. a developer pushing directly to `devel`).

The endpoint is filterable by fleet, action type, date range, and `user_sub`. It powers the Audit page (`/audit`).

---

## Assumptions

1. `STORY-04` is DONE and the `audit_events` table exists with columns: `id` (UUID), `event_type` (string), `fleet` (string), `certname` (string | NULL), `user_sub` (string), `created_at` (timestamp), `payload` (JSONB).
2. `STORY-05` is DONE and `bff/clients/gitlab_client.py` exposes access to the `python-gitlab` client.
3. GitLab commit/MR history is fetched from the fleet's hieradata project (`env/environment-<fleet>`). The BFF service account PAT has `api` scope on these projects.
4. "NMS+ service account" is the GitLab user whose PAT is stored in `GITLAB_TOKEN`. Any commit/MR where `author.username != GITLAB_SERVICE_ACCOUNT_USERNAME` (a BFF env var) is flagged as `external_edit: true`.
5. Both data sources are merged in the BFF and returned as a single time-sorted list. GitLab pagination is resolved server-side; the combined result is paginated using `limit` and `offset` query parameters (defaults: `limit=50`, `offset=0`).
6. Filters are AND-combined. Omitted filters match all values.
7. Authentication is mandatory: all roles may call this endpoint.
8. The endpoint is read-only; no `Idempotency-Key` required.
9. GitLab API errors (e.g. project not found, token expired) must not crash the endpoint. If GitLab is unreachable, return Postgres-only results with a partial-data flag in the response: `"gitlab_available": false`.
10. Raw GitLab and Postgres responses are mapped to `AuditEvent` Pydantic v2 model before returning — never proxy raw API responses to the frontend.

---

## Dependencies

| Dependency | Type | Unblock Condition |
|---|---|---|
| STORY-04 (audit_events table) | Hard — Postgres source for UI-initiated events | STORY-04 Status = DONE |
| STORY-05 (gitlab_client) | Hard — GitLab commit/MR history requires client wrapper | STORY-05 Status = DONE |
| STORY-02 (JWT middleware) | Hard — `get_current_user` dependency injection | STORY-02 Status = DONE |

---

## Acceptance Criteria

### AC-1: Happy path — both sources available, no filters

**Given** a valid Keycloak JWT with any role  
**And** both Postgres and GitLab are reachable  
**When** `GET /api/audit/events?fleet=alpin` is called  
**Then** the response is HTTP 200  
**And** the body contains `{ "events": [...], "total": <int>, "limit": 50, "offset": 0, "gitlab_available": true }`  
**And** `events` is a time-sorted (descending) list of `AuditEvent` objects  
**And** events originating from GitLab commits not by the service account have `"external_edit": true`  
**And** events originating from UI actions (Postgres) have `"external_edit": false`

### AC-2: Filtering by action type

**Given** a valid Keycloak JWT  
**When** `GET /api/audit/events?fleet=alpin&action=force_run_triggered` is called  
**Then** only events with `event_type = "force_run_triggered"` are returned  
**And** GitLab commits are excluded from this filtered result (they do not have a matching action type)

### AC-3: Filtering by date range

**Given** a valid Keycloak JWT  
**When** `GET /api/audit/events?fleet=alpin&from=2026-01-01T00:00:00Z&to=2026-02-01T00:00:00Z` is called  
**Then** only events with `created_at` within `[from, to)` are returned from both sources

### AC-4: Filtering by user_sub

**Given** a valid Keycloak JWT  
**When** `GET /api/audit/events?fleet=alpin&user_sub=abc123` is called  
**Then** only events where `user_sub = "abc123"` are returned from Postgres  
**And** GitLab commits where the author's GitLab user maps to `user_sub = "abc123"` are also included (mapping by NMS+ service account username convention — see Notes)

### AC-5: GitLab unreachable — partial result

**Given** a valid Keycloak JWT  
**And** GitLab is unreachable  
**When** `GET /api/audit/events?fleet=alpin` is called  
**Then** the response is HTTP 200  
**And** only Postgres events are returned  
**And** the response includes `"gitlab_available": false`  
**And** no 502 or 500 is returned

### AC-6: Pagination

**Given** a valid Keycloak JWT  
**And** more than 50 combined audit events exist  
**When** `GET /api/audit/events?fleet=alpin&limit=20&offset=20` is called  
**Then** events 21–40 (0-indexed) are returned  
**And** `"total"` reflects the full combined count  
**And** `"limit": 20` and `"offset": 20` are echoed in the response

### AC-7: Missing or invalid JWT

**Given** no `Authorization` header or an expired/malformed JWT  
**When** `GET /api/audit/events?fleet=alpin` is called  
**Then** the response is HTTP 401  
**And** the response body shape is identical to a 403 response

### AC-8: Invalid fleet parameter

**Given** a valid Keycloak JWT  
**And** `fleet` query parameter is not one of `alpin`, `dostoneu`, `dani`  
**When** `GET /api/audit/events?fleet=unknown` is called  
**Then** the response is HTTP 422

---

## Definition of Done

- [ ] `bff/routers/audit.py` contains `GET /api/audit/events` route
- [ ] `AuditEvent` Pydantic v2 model: `id: str`, `event_type: str`, `fleet: str`, `certname: str | None`, `user_sub: str | None`, `created_at: datetime`, `source: Literal["postgres", "gitlab"]`, `external_edit: bool`, `payload: dict | None`
- [ ] `AuditEventsResponse` model: `events: list[AuditEvent]`, `total: int`, `limit: int`, `offset: int`, `gitlab_available: bool`
- [ ] GitLab commit/MR history fetched via `gitlab_client` (D6); no raw httpx calls to GitLab
- [ ] External edit detection: commits where `author.username != GITLAB_SERVICE_ACCOUNT_USERNAME` → `external_edit: true`
- [ ] Filters: `fleet` (required), `action` (optional), `from` / `to` ISO-8601 (optional), `user_sub` (optional)
- [ ] Pagination: `limit` (default 50, max 200), `offset` (default 0)
- [ ] GitLab unavailability handled gracefully; response includes `gitlab_available: false`
- [ ] `get_current_user` injected; unauthenticated → 401
- [ ] Results merged and sorted by `created_at` descending before pagination slice
- [ ] BFF unit tests: both sources available, GitLab unavailable, date range filter, action filter, user_sub filter, pagination, invalid fleet, unauthenticated
- [ ] Integration tests use GitLab fixtures and Postgres fixtures (no real external calls)
- [ ] Security tests: unauthenticated → 401, malformed JWT → 401
- [ ] `pytest --cov --cov-fail-under=90` passes on new modules
- [ ] `mypy` passes with zero errors on new modules
- [ ] `docs/API_CONTRACTS.md` updated with this endpoint's request/response shape
- [ ] Story Status set to DONE

---

## D-Decisions Touched

| Decision | Relevance |
|---|---|
| **D1** | Browser never calls GitLab or Postgres directly; this BFF endpoint is the only path |
| **D6** | All GitLab operations use `python-gitlab` via `gitlab_client.py`; no direct `httpx` calls to the GitLab REST API |

---

## SLO Assignment

**Read-path p95 <500ms**

Rationale: this endpoint does not query PuppetDB. Both Postgres and GitLab are synchronous reads. GitLab API latency may be the bottleneck; the endpoint must not fan out to more than one GitLab project per fleet per request, and GitLab pagination must be bounded (max 100 results per GitLab page, max 2 pages fetched per request in MVP).

---

## File Locations

- Router: `bff/routers/audit.py`
- Models: `bff/models/audit.py`
- Unit tests: `tests/unit/routers/test_audit_events.py`
- Integration tests: `tests/integration/routers/test_audit_events_integration.py`
- GitLab fixtures: `tests/fixtures/alpin/` (commit list, MR list responses)

---

## Notes for Implementer

- GitLab commits and MRs are separate GitLab API calls. Fetch commits from `project.commits.list(ref_name="devel", ...)` and MRs from `project.mergerequests.list(...)` using python-gitlab. Merge the results before sorting.
- User sub mapping for `user_sub` filter on GitLab events: in MVP, use GitLab `author.username` directly as the filter value. There is no Keycloak↔GitLab user mapping table in MVP; `user_sub` on GitLab-sourced events contains the GitLab username, not the Keycloak sub. Document this in the API contract.
- The `GITLAB_SERVICE_ACCOUNT_USERNAME` env var identifies the NMS+ service account in GitLab. Any commit/MR with a different author is an external edit.
- Never log hieradata values, commit file contents, or MR descriptions in BFF logs — log correlation IDs and event type only.
- The response must not expose raw JSONB `payload` fields that contain hieradata values. The `payload` field in `AuditEvent` is a sanitised subset of the stored JSONB — implementer must define which keys are safe to surface in MVP and strip the rest.
- "Puppet environment" in GitLab MR/commit context maps to the target branch (`devel` or `staging`). Use the qualified term in code.
