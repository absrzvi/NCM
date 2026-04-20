# STORY-18: GET /api/deployments/status

**Status**: READY
**Tier**: 3 — Deployments Module
**Module**: `bff/routers/deployments_router.py`, `bff/clients/gitlab_client.py`, `bff/clients/puppetdb_client.py`

---

## Summary

Implement `GET /api/deployments/status?fleet=<fleet>` which returns a combined view of:

1. **Merged MRs** from GitLab: MRs targeting the fleet's Puppet environment branch (`devel` or `staging`) that have been merged, enriched with merge metadata (merge SHA, merged_at, merged_by, MR title, Jira issue number from commit subject).
2. **PuppetDB post-merge run status** per certname: for each certname belonging to the fleet, the most recent Puppet run status (`changed`, `unchanged`, `failed`, `noop`) and last-run timestamp from PuppetDB.

**PuppetDB degraded gracefully**: if PuppetDB is unreachable or returns data older than 5 minutes (staleness tolerance), the response still returns with an HTTP 200, but includes a top-level `puppetdb_status` field: `{ "reachable": false, "banner": "PuppetDB unreachable — run status unavailable" }` or `{ "reachable": true, "stale": true, "banner": "PuppetDB data is stale (last update > 5 min ago)" }`. The GitLab MR data is returned regardless.

---

## Assumptions

1. STORY-05 is DONE: `gitlab_client` exposes an async method to list merged MRs for a project and branch. `puppetdb_client` exposes an async method to query node run statuses by fleet/certname.
2. Fleet-to-certname mapping: the BFF can enumerate certnames for a fleet by querying PuppetDB for nodes with a fact matching the fleet name. If PuppetDB is unreachable, certname list is empty and the banner is shown.
3. The "staleness" check: PuppetDB reports a `report_timestamp` per node. If `report_timestamp < NOW() - 5 minutes` for all nodes in a fleet, the data is considered stale. If some nodes are fresh and some are stale, include per-node staleness indicators in addition to the top-level banner.
4. "Merged MRs" scope: MRs created by the NMS+ Config BFF are identified by commit subject prefix `NCD-<n>: ` (from STORY-15). However, this story does not filter exclusively by that prefix — it returns all merged MRs to the target branch so operators have full visibility. The Jira issue field is `null` if the commit subject doesn't match the `NCD-<n>:` pattern.
5. The `fleet` parameter is optional. If omitted, return status for all fleets the authenticated user has access to. If provided, validate against `{alpin, dostoneu, dani}` → 404 if unknown.
6. This endpoint is read-only; all authenticated roles may access it.
7. The response is not cached in Postgres. It is a live composite query on each request. If latency becomes an issue, a caching layer can be introduced in a follow-up story — do not add it speculatively.

---

## Dependencies

| Dependency | Status Required | Notes |
|---|---|---|
| STORY-05 (downstream clients) | DONE | `gitlab_client` (MR list) and `puppetdb_client` (run status) required |

---

## Acceptance Criteria

### AC-1: Successful response — GitLab and PuppetDB both reachable

**Given** a valid Keycloak JWT (any role), fleet `alpin`, and both GitLab and PuppetDB are reachable and returning fresh data,
**When** `GET /api/deployments/status?fleet=alpin` is called,
**Then** the response is HTTP 200 with:
- `"fleet": "alpin"`
- `"puppetdb_status": { "reachable": true, "stale": false }`
- `"merged_mrs": [...]` — array of MR objects each with: `mr_id`, `title`, `merged_at`, `merged_by`, `merge_sha`, `jira_issue` (string or null)
- `"certname_statuses": [...]` — array of certname status objects each with: `certname`, `last_run_status` (one of `changed`, `unchanged`, `failed`, `noop`), `last_run_at`

### AC-2: PuppetDB unreachable — graceful degradation with banner

**Given** PuppetDB is unreachable (simulated by fixture raising `httpx.ConnectError`),
**When** `GET /api/deployments/status?fleet=alpin` is called with a valid JWT,
**Then** the response is HTTP 200 (not 502). The body contains:
- `"puppetdb_status": { "reachable": false, "banner": "PuppetDB unreachable — run status unavailable" }`
- `"merged_mrs": [...]` — GitLab MR data is still returned
- `"certname_statuses": []` — empty list (no certname data available)

### AC-3: PuppetDB data stale — graceful degradation with stale banner

**Given** PuppetDB is reachable but all node `report_timestamp` values are older than 5 minutes,
**When** `GET /api/deployments/status?fleet=alpin` is called,
**Then** the response is HTTP 200 with:
- `"puppetdb_status": { "reachable": true, "stale": true, "banner": "PuppetDB data is stale (last update > 5 min ago)" }`
- `"merged_mrs": [...]` — GitLab data still returned
- `"certname_statuses": [...]` — stale data returned with a per-entry `"stale": true` flag

### AC-4: GitLab unreachable returns 502

**Given** GitLab is unreachable,
**When** `GET /api/deployments/status` is called,
**Then** the response is HTTP 502 with `{ "detail": "upstream_unavailable" }`. PuppetDB graceful degradation does not apply here because GitLab is the primary data source for this endpoint.

### AC-5: Unknown fleet returns 404

**Given** `fleet=unknown`,
**When** `GET /api/deployments/status?fleet=unknown` is called,
**Then** the response is HTTP 404 with `{ "detail": "fleet not found" }`.

### AC-6: Fleet parameter omitted — all fleets returned

**Given** no `fleet` parameter,
**When** `GET /api/deployments/status` is called with a valid JWT,
**Then** the response is HTTP 200 with a `"fleets"` array, each element being a fleet status object (same shape as the single-fleet response, but nested under fleet name).

### AC-7: Unauthenticated request returns 401

**Given** no Authorization header or expired/malformed JWT,
**When** `GET /api/deployments/status` is called,
**Then** the response is HTTP 401.

### AC-8: jira_issue field is null for non-NCD commits

**Given** a merged MR whose commit subject is `Fix typo in common.yaml` (no `NCD-<n>: ` prefix),
**When** the MR appears in the response,
**Then** the MR object contains `"jira_issue": null`. No error is raised.

### AC-9: GitLab and PuppetDB calls run concurrently

**Given** a valid request where both GitLab and PuppetDB are reachable,
**When** the BFF processes the request,
**Then** the GitLab MR list call and the PuppetDB certname status call are dispatched concurrently (via `asyncio.gather`) — not sequentially. This is verifiable by unit test mock timing assertions or by asserting both calls are made within the same `gather` block.

---

## Definition of Done

- [ ] Python mypy passes with zero errors
- [ ] All security tests pass:
  - [ ] Unauthenticated → 401
  - [ ] Expired/malformed JWT → 401
  - [ ] Valid JWT, viewer role → 200 (read-only; all roles permitted)
- [ ] BFF unit tests cover:
  - [ ] Both GitLab and PuppetDB reachable — full response
  - [ ] PuppetDB unreachable → 200 with banner, GitLab data present, certname_statuses empty
  - [ ] PuppetDB stale → 200 with stale banner, per-entry stale flag
  - [ ] GitLab unreachable → 502
  - [ ] Unknown fleet → 404
  - [ ] Fleet omitted → all-fleets response
  - [ ] `jira_issue` null for non-NCD commit subjects
  - [ ] GitLab and PuppetDB calls dispatched concurrently (mock-verified)
- [ ] Integration tests run against fixtures (never real GitLab or PuppetDB)
- [ ] BFF coverage ≥90% (`pytest --cov --cov-fail-under=90`)
- [ ] All Playwright E2E: status page renders; PuppetDB banner shown when unreachable; auth failure
- [ ] QA score ≥ 85/100
- [ ] Code Reviewer agent approved (no Critical issues)
- [ ] Security Sentinel agent approved (no Critical issues)
- [ ] `docs/API_CONTRACTS.md` updated with deployment status endpoint contract
- [ ] Story file Status set to DONE

---

## D-Decisions Touched

| Decision | How it applies |
|---|---|
| **D1** | Browser never calls GitLab or PuppetDB directly. BFF fetches from both and returns a unified JSON response. |
| **D6** | All GitLab operations (merged MR listing) use `python-gitlab` via `gitlab_client`. Never raw httpx calls to GitLab. |

---

## SLO Assignment

**Governing SLOs** (two apply, both must be met):

1. **Read-path p95 < 500ms** — for the GitLab-only portion of the response. GitLab latency must not cause p95 to breach 500ms. PuppetDB latency is excluded from this SLO.
2. **PuppetDB staleness < 5 minutes** — PuppetDB data must be no older than 5 minutes. If data is stale or PuppetDB is unreachable, **degrade gracefully**: return HTTP 200 with the banner (not a 5xx). The SLO measures staleness of data returned, not endpoint uptime.

Both SLOs apply simultaneously. This endpoint is in the "reads that query PuppetDB" category per the CLAUDE.md SLO decision matrix.

---

## Implementation Notes (for bff-dev)

- Route file: `bff/routers/deployments_router.py`
- Models: `DeploymentStatusResponse`, `MergedMREntry`, `CertnameStatusEntry`, `PuppetDBStatus` in `bff/models/deployments.py` (Pydantic v2, strict, no `any`)
- Use `get_current_user` (D3); no `customer_id`
- Read-only endpoint; no `Idempotency-Key` required
- Concurrency: `await asyncio.gather(gitlab_client.get_merged_mrs(...), puppetdb_client.get_node_statuses(...))` — do not serialize (Iron Rule / Principle 5)
- PuppetDB call wrapped in try/except for `httpx.ConnectError`, `httpx.TimeoutException` → set `reachable = false`; PuppetDB staleness checked by comparing `report_timestamp` to `datetime.utcnow() - timedelta(minutes=5)`
- Jira issue extraction: `re.match(r'^([A-Z]+-\d+):\s', commit_subject)` → group 1 if match, else `None`
- Fleet-to-Puppet-environment-branch mapping from fleet config (STORY-06); do not hardcode branch names
- Never log PuppetDB node values or GitLab hieradata content; log only certnames, MR IDs, and status codes
- PuppetDB read token is stored separately from Puppet Server write token (per CLAUDE.md BFF Downstream Services section); never confuse the two
- All HTTP calls via `httpx` (D9); no direct network calls from tests (use fixtures)
