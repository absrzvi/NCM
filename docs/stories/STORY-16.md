# STORY-16: Parameter History Endpoint (GET /api/policies/history, D16)

**Status**: READY
**Tier**: 3 — Policies Module
**Module**: `bff/routers/policies_router.py`, `bff/history/parameter_history.py`

---

## Summary

Implement `GET /api/policies/history` with query parameters:

```
GET /api/policies/history?fleet=<fleet>&branch=<branch>&key_path=<path>&limit=20
```

This endpoint returns the GitLab commit log scoped to a specific `key_path` within the fleet's hieradata. Results are cached in the `parameter_history_cache` Postgres table (created by STORY-04) with a 5-minute TTL (D16).

Special handling by key backend:
- **`hiera_file` keys**: return the commit log from the routed hieradata file. Include a note in each response entry: `"source_note": "history lives in routed file"` plus the `routed_file` path.
- **`hiera_mysql` keys**: do not attempt to query GitLab. Return an empty history list with a top-level note: `"source_note": "value is external — history not visible from GitLab"`.

The `limit` parameter defaults to 20, maximum 100. If omitted, default to 20.

---

## Assumptions

1. STORY-05 is DONE: `gitlab_client` exposes an async method to fetch the GitLab commit log for a file path scoped to a project and branch.
2. STORY-04 is DONE: the `parameter_history_cache` table exists with columns including at minimum `cache_key` (unique), `fleet`, `branch`, `key_path`, `payload` (JSONB), `cached_at` (timestamp).
3. The cache key is computed as `sha256(fleet + branch + key_path)` (hex). Cache hit: `cached_at > NOW() - INTERVAL '5 minutes'`. On hit, return the cached payload without calling GitLab.
4. GitLab commit log "scoped to key_path" means: retrieve the commit log for the hieradata file that contains the key_path (determined from the hiera.yaml layer structure parsed by STORY-13's logic), then filter commits to only those that actually touch the specific key in that file. If filtering at the GitLab API level is not available, fetch the commit log for the file and post-filter in BFF. The response includes only commits where the key_path's value changed.
5. The `branch` parameter accepts `devel` and `staging` only. Unknown branch values → 422.
6. Fleet names are validated against `{alpin, dostoneu, dani}`. Unknown fleet → 404.
7. `hiera_mysql` key detection: the BFF knows a key is `hiera_mysql`-backed by inspecting the layer structure from `hiera.yaml` (same logic as STORY-13). If STORY-13's tree endpoint is available, the history endpoint may reuse that layer-parsing logic by importing the shared parser; do not duplicate it.
8. `limit` is capped at 100 server-side regardless of what the client sends. Values above 100 are silently capped (not an error).

---

## Dependencies

| Dependency | Status Required | Notes |
|---|---|---|
| STORY-05 (downstream clients) | DONE | `gitlab_client` required for commit log queries |
| STORY-04 (DB schema) | DONE | `parameter_history_cache` table required |

---

## Acceptance Criteria

### AC-1: Successful history query for a hiera_file key

**Given** a valid Keycloak JWT (any role), fleet `alpin`, branch `devel`, and `key_path=role::ntp::servers` which is sourced from a `hiera_file` layer,
**When** `GET /api/policies/history?fleet=alpin&branch=devel&key_path=role::ntp::servers&limit=20` is called,
**Then** the response is HTTP 200 with a body containing:
- `"source_backend": "hiera_file"`
- `"routed_file": "<relative path to the hieradata file>"`
- `"source_note": "history lives in routed file"`
- `"history": [...]` — array of up to 20 commit objects, each with at minimum: `sha`, `author_name`, `committed_at`, `message`, `old_value`, `new_value`

### AC-2: History query for a hiera_mysql key returns empty history with note

**Given** fleet `dani`, branch `devel`, and `key_path=some::mysql_backed_key` sourced from a `hiera_mysql` layer,
**When** `GET /api/policies/history?fleet=dani&branch=devel&key_path=some::mysql_backed_key` is called with a valid JWT,
**Then** the response is HTTP 200 with:
- `"source_backend": "hiera_mysql"`
- `"external_db": true`
- `"source_note": "value is external — history not visible from GitLab"`
- `"history": []`
No GitLab commit log call is made.

### AC-3: Cache hit avoids GitLab call

**Given** the `parameter_history_cache` table has a fresh entry (< 5 minutes old) for `(alpin, devel, role::ntp::servers)`,
**When** `GET /api/policies/history?fleet=alpin&branch=devel&key_path=role::ntp::servers` is called,
**Then** the response is HTTP 200 served from cache. No GitLab API call is made (verifiable via mock assertion in unit test).

### AC-4: Cache miss populates cache

**Given** no cache entry exists for the requested `(fleet, branch, key_path)`,
**When** `GET /api/policies/history` is called and GitLab returns results,
**Then** the result is stored in `parameter_history_cache` with `cached_at = NOW()` and the response is returned. A subsequent call within 5 minutes hits the cache (AC-3).

### AC-5: limit defaults to 20, caps at 100

**Given** a valid request with no `limit` parameter,
**When** `GET /api/policies/history?fleet=alpin&branch=devel&key_path=role::ntp::servers` is called,
**Then** the response includes at most 20 history entries.

**Given** `limit=500` in the query,
**When** the request is processed,
**Then** the response includes at most 100 history entries (silently capped, not an error).

### AC-6: Unknown fleet returns 404

**Given** `fleet=unknown` in the query string,
**When** `GET /api/policies/history` is called with a valid JWT,
**Then** the response is HTTP 404 with `{ "detail": "fleet not found" }`.

### AC-7: Unknown branch returns 422

**Given** `branch=master` or any branch not in `{devel, staging}`,
**When** `GET /api/policies/history` is called,
**Then** the response is HTTP 422 with `{ "detail": "invalid_branch" }`.

### AC-8: Unauthenticated request returns 401

**Given** no Authorization header or expired/malformed JWT,
**When** `GET /api/policies/history` is called,
**Then** the response is HTTP 401. Shape is identical regardless of token failure reason.

### AC-9: GitLab unreachable returns 502 (cache miss scenario)

**Given** the cache has no entry for the requested key and GitLab is unreachable,
**When** `GET /api/policies/history` is called,
**Then** the response is HTTP 502 with `{ "detail": "upstream_unavailable" }`. No partial result is returned.

---

## Definition of Done

- [ ] Python mypy passes with zero errors
- [ ] All security tests pass:
  - [ ] Unauthenticated → 401
  - [ ] Expired/malformed JWT → 401
  - [ ] Valid JWT, any role → 200 (read-only endpoint; all roles may read history)
- [ ] BFF unit tests cover:
  - [ ] `hiera_file` key — returns history with `routed_file` and `source_note`
  - [ ] `hiera_mysql` key — returns empty history with `source_note`, no GitLab call
  - [ ] Cache hit — no GitLab call
  - [ ] Cache miss — GitLab call made, cache populated
  - [ ] Cache TTL expiry — stale entry triggers fresh GitLab call
  - [ ] `limit` default (20) and cap (100)
  - [ ] Unknown fleet → 404
  - [ ] Unknown branch → 422
  - [ ] GitLab unreachable (cache miss) → 502
- [ ] Integration tests run against fixtures and a Postgres test database (never real downstream services)
- [ ] BFF coverage ≥90% (`pytest --cov --cov-fail-under=90`)
- [ ] All Playwright E2E: history panel renders for hiera_file key; shows correct note for hiera_mysql key; auth failure
- [ ] QA score ≥ 85/100
- [ ] Code Reviewer agent approved (no Critical issues)
- [ ] Security Sentinel agent approved (no Critical issues)
- [ ] `docs/API_CONTRACTS.md` updated with history endpoint contract
- [ ] Story file Status set to DONE

---

## D-Decisions Touched

| Decision | How it applies |
|---|---|
| **D16** | Parameter history endpoint: GitLab commit log scoped per key_path; 5-minute Postgres cache in `parameter_history_cache` table; `hiera_mysql` keys return empty history with note. |
| **D6** | All GitLab operations (commit log retrieval) use `python-gitlab` via `gitlab_client` wrapper. Never raw httpx calls to GitLab. |

---

## SLO Assignment

**Governing SLO**: Read-path p95 < 500ms (excluding PuppetDB — PuppetDB is not called by this endpoint).

The 5-minute Postgres cache is the primary mechanism for meeting this SLO. Cache hits are expected to dominate production traffic. The uncached path (GitLab commit log call) may be slower; monitor p95 on cache-miss requests separately and consider tightening the cache TTL if needed.

---

## Implementation Notes (for bff-dev)

- Route file: `bff/routers/policies_router.py`
- History logic: `bff/history/parameter_history.py` (module already exists per CLAUDE.md file structure)
- Models: `HistoryResponse`, `HistoryEntry` in `bff/models/policies.py` (Pydantic v2, strict, no `any`)
- Use `get_current_user` (D3); history is read-only so any authenticated role is permitted
- Cache key: `hashlib.sha256(f"{fleet}:{branch}:{key_path}".encode()).hexdigest()`
- Cache read: `SELECT payload, cached_at FROM parameter_history_cache WHERE cache_key = $1` — check `cached_at > NOW() - INTERVAL '5 minutes'`
- Cache write: upsert on `cache_key`
- `hiera_mysql` detection: reuse the layer-parsing logic from STORY-13 (import, do not duplicate)
- GitLab commit log: `gitlab_client.get_commits(project_path, file_path, branch, limit)` — async
- Post-filtering commits: load each commit's diff for the file and check if the key_path's value changed (ruamel.yaml parse of before/after). This is the most expensive part — cache hit avoidance is essential.
- Never log hieradata values in commit diffs; log only `sha`, `author`, `committed_at`
- No file exceeds 500 lines; split `parameter_history.py` if cache + filtering logic grows large
