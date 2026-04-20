# STORY-24: GET /api/audit/recent-mrs

**Status:** READY

---

## Summary

Implement the `GET /api/audit/recent-mrs` endpoint on the BFF. This endpoint fetches recent merge requests from GitLab for the selected fleet and Puppet environment (target branch). The response includes MR status, author, `created_at`, and `merged_at`. It feeds the Overview page recent-activity panel and the Audit page MR timeline.

---

## Assumptions

1. `STORY-05` is DONE and `bff/clients/gitlab_client.py` exposes access to the `python-gitlab` client (D6).
2. Fleet maps to GitLab project path `env/environment-<fleet>`. Project IDs: `env/environment-alpin` (1211), `env/environment-dostoneu` (1136). `dani` project ID to be confirmed from the environment config (STORY-06).
3. `puppet_environment` query parameter selects which target branch's MRs to return (`devel` or `staging`). This maps to the GitLab MR `target_branch` filter.
4. Default result limit is 20 MRs. Configurable via `RECENT_MRS_LIMIT` env var (default `20`). This is not a query parameter exposed to the frontend in MVP.
5. Returned MR states are: `opened`, `merged`, `closed`. All states are returned by default; the frontend filters as needed.
6. Authentication is mandatory: all roles (viewer, editor, admin) may call this endpoint.
7. The endpoint is read-only; no `Idempotency-Key` required.
8. If GitLab is unreachable, return HTTP 502 with `{ "error_code": "gitlab_unavailable", "detail": "GitLab API unreachable" }`. Unlike PuppetDB, there is no Postgres cache for MR data — GitLab is the source of truth and its unavailability is not gracefully degraded (MR data is not safety-critical for the Overview).
9. Raw GitLab MR responses are mapped to the `MergeRequestSummary` Pydantic v2 model before returning — never proxy raw python-gitlab objects to the frontend.

---

## Dependencies

| Dependency | Type | Unblock Condition |
|---|---|---|
| STORY-05 (gitlab_client) | Hard — MR history requires the client wrapper | STORY-05 Status = DONE |
| STORY-02 (JWT middleware) | Hard — `get_current_user` dependency injection | STORY-02 Status = DONE |

---

## Acceptance Criteria

### AC-1: Happy path — returns recent MRs for fleet and Puppet environment

**Given** a valid Keycloak JWT with any role  
**And** GitLab is reachable  
**When** `GET /api/audit/recent-mrs?fleet=alpin&puppet_environment=devel` is called  
**Then** the response is HTTP 200  
**And** the body contains a list of `MergeRequestSummary` objects with fields: `mr_id` (GitLab MR IID), `title`, `state` (`opened` | `merged` | `closed`), `author_username`, `created_at` (ISO-8601), `merged_at` (ISO-8601 | null), `web_url`  
**And** only MRs targeting the `devel` branch of the `env/environment-alpin` project are returned  
**And** results are ordered by `created_at` descending

### AC-2: Default Puppet environment is devel

**Given** a valid Keycloak JWT  
**And** GitLab is reachable  
**When** `GET /api/audit/recent-mrs?fleet=alpin` is called (no `puppet_environment`)  
**Then** the response is HTTP 200  
**And** MRs targeting the `devel` branch are returned (default)

### AC-3: Missing or invalid JWT

**Given** no `Authorization` header or an expired/malformed JWT  
**When** `GET /api/audit/recent-mrs?fleet=alpin` is called  
**Then** the response is HTTP 401  
**And** the response body shape is identical to a 403 response

### AC-4: Invalid fleet parameter

**Given** a valid Keycloak JWT  
**And** `fleet` is not one of `alpin`, `dostoneu`, `dani`  
**When** `GET /api/audit/recent-mrs?fleet=unknown` is called  
**Then** the response is HTTP 422

### AC-5: Invalid puppet_environment parameter

**Given** a valid Keycloak JWT  
**And** `puppet_environment` is not one of `devel`, `staging`  
**When** `GET /api/audit/recent-mrs?fleet=alpin&puppet_environment=master` is called  
**Then** the response is HTTP 422

### AC-6: GitLab unreachable

**Given** a valid Keycloak JWT  
**And** GitLab is unreachable  
**When** `GET /api/audit/recent-mrs?fleet=alpin` is called  
**Then** the response is HTTP 502  
**And** the body is `{ "error_code": "gitlab_unavailable", "detail": "GitLab API unreachable" }`

### AC-7: Missing fleet parameter

**Given** a valid Keycloak JWT  
**And** `fleet` query parameter is absent  
**When** `GET /api/audit/recent-mrs` is called  
**Then** the response is HTTP 422  
**And** the body identifies `fleet` as a required parameter

---

## Definition of Done

- [ ] `bff/routers/audit.py` contains `GET /api/audit/recent-mrs` route (alongside STORY-23 events route)
- [ ] `MergeRequestSummary` Pydantic v2 model: `mr_id: int`, `title: str`, `state: Literal["opened", "merged", "closed"]`, `author_username: str`, `created_at: datetime`, `merged_at: datetime | None`, `web_url: str`
- [ ] `fleet` query parameter required; invalid value → 422
- [ ] `puppet_environment` query parameter optional; default `"devel"`; must be `"devel"` or `"staging"`; other values → 422
- [ ] `RECENT_MRS_LIMIT` env var respected (default 20)
- [ ] All GitLab calls use `gitlab_client` (D6) — no direct httpx calls to the GitLab REST API
- [ ] GitLab unreachable → HTTP 502 with `gitlab_unavailable` error code
- [ ] `get_current_user` injected; unauthenticated → 401
- [ ] Results ordered by `created_at` descending
- [ ] BFF unit tests: happy path (with devel and staging), default puppet_environment, GitLab unreachable, invalid fleet, invalid puppet_environment, missing fleet, unauthenticated
- [ ] Integration tests use GitLab MR list fixtures (no real GitLab calls)
- [ ] Security tests: unauthenticated → 401, malformed JWT → 401
- [ ] `pytest --cov --cov-fail-under=90` passes on new modules
- [ ] `mypy` passes with zero errors on new modules
- [ ] `docs/API_CONTRACTS.md` updated with this endpoint's request/response shape
- [ ] Story Status set to DONE

---

## D-Decisions Touched

| Decision | Relevance |
|---|---|
| **D1** | Browser never calls GitLab directly; this BFF endpoint is the only path |
| **D6** | All GitLab MR operations use `python-gitlab` via `gitlab_client.py` |

---

## SLO Assignment

**Read-path p95 <500ms**

Rationale: this endpoint calls GitLab only (no PuppetDB). GitLab API latency is the bottleneck; limiting to 20 MRs per request and a single GitLab project call per request keeps response times well within the 500ms p95 target under normal operating conditions.

---

## File Locations

- Router: `bff/routers/audit.py`
- Models: `bff/models/audit.py`
- Unit tests: `tests/unit/routers/test_audit_recent_mrs.py`
- Integration tests: `tests/integration/routers/test_audit_recent_mrs_integration.py`
- GitLab fixtures: `tests/fixtures/alpin/` (MR list response)

---

## Notes for Implementer

- Use `project.mergerequests.list(target_branch="devel", order_by="created_at", sort="desc", per_page=<LIMIT>)` with python-gitlab.
- The GitLab MR `iid` (project-scoped integer) is used as `mr_id`, not the global `id`. This matches what GitLab Web UI displays in URLs.
- `merged_at` is `None` for `opened` and `closed` MRs — this is valid and must not be treated as an error by the frontend.
- Do not log MR titles or author names — they may contain sensitive information. Log only `mr_id` and correlation IDs.
- Variable and parameter names in code must use `puppet_environment` (qualified), not bare `environment`.
- This endpoint does not apply any caching — GitLab is the authoritative source and MR state can change rapidly (e.g. CI status updates). Caching here would risk showing stale MR states on the Overview page.
