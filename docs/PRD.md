# Product Requirements Document — NMS+ Config MVP
Status: APPROVED

> Produced from `NMS+_SystemDesign_Brief.md` (2026-04-20). Set Status to APPROVED to unblock the architect agent.
> All open questions from §9 of the brief are **closed**. No further interview is needed before architecting.

---

## Problem Statement

Project engineers today manage Nomad's fleet edge configuration by editing hieradata YAML in GitLab directly — with zero merge requests in the reference repo's history, no CI pipeline, and client-side-only validators. To know what a fleet is actually running, or whether a change applied cleanly, engineers navigate GitLab files by hand and read Puppet reports manually.

**NMS+ Config MVP** gives project engineers a single UI to:
1. **Understand** a fleet's configuration — rendered as a structured tree instead of raw YAML files.
2. **Update** selected parameters — through a structured form that runs server-side validators, commits to a non-production branch, and opens an MR in GitLab.
3. **See** deployment status and drift — Puppet run results and drift classifications from PuppetDB, surfaced per-train.
4. **Force a Puppet run** — only on bench certnames, only from `devel` or `staging`. Production branches are hard-refused server-side.

**What the app does NOT do:**
- Does not replace Git or GitLab — GitLab is the source of truth for hieradata.
- Does not replace Puppet — we read its reports and (MVP) can trigger a run against bench targets.
- Does not enforce formal approvals (GitLab CE has no Approvals API). The two-human merge discipline (submitter ≠ merger) is a **team convention backed by audit trail**, not a technical control. Do not represent it as an enforced security control in compliance materials.
- Does not write directly to devices — every change flows: UI → validate → GitLab commit → MR → merge → Puppet run.

---

## User Roles & Personas

Single-tenant MVP — Nomad-internal only. No customer-facing users.

| Persona | Description | App Role |
|---------|-------------|----------|
| Project engineer (primary, ~80%) | Reads fleet config, drafts parameter changes, reviews drift, submits MRs from the app | `editor` |
| Config approver | Reviews and merges MRs — in GitLab, not our UI | GitLab role only (no app role) |
| Auditor / compliance reader | Read-only; queries audit log | `viewer` |
| Platform admin | Onboards environments, rescans, archives (phase-2) | `admin` |

**Keycloak JWT roles (simplified names):**
- `viewer` — read everything; cannot submit MRs
- `editor` — read + submit MRs + force Puppet runs on bench targets
- `admin` — same as editor plus environment onboarding / rescan / archive (phase-2)

---

## Functional Requirements

### FR1 — Five Core Views (MVP)

| View | Route | Write? | Data Sources |
|------|-------|--------|-------------|
| Overview | `/` | No | PuppetDB (drift counts, recent runs) + GitLab (recent MRs + commits on target env branch) |
| Compliance | `/compliance` | No | PuppetDB (per-device reports, facts) |
| Audit Log | `/audit` | No | GitLab commit/MR history + our UI event log (Postgres) |
| Policy Tree | `/policies/...` | **Yes** — stages edits; Apply All creates branch + MR against `devel` or `staging` | GitLab (hieradata files + commit log for D16 history) |
| Deployments | `/deployments/...` | **Yes** — force Puppet run (bench-only, non-prod branches) | GitLab (merged MRs) + PuppetDB (post-merge run status) + Puppet Server API (force-run, D13) |

### FR2 — Policy Tree: Hieradata Editor

The Policy Tree is driven by the fleet's actual `hiera.yaml` — **not a hardcoded schema**. Layer counts differ per fleet:

| Fleet | Layers | Hierarchy (highest → lowest precedence) | Lookup Plugins |
|-------|--------|----------------------------------------|---------------|
| alpin | 3 | `nodes/<certname>.yaml` → `hiera_file` plugin → `common.yaml` | `hiera_file` |
| dostoneu | 4 | `nodes/<certname>.yaml` → `hiera_file` → `actions.yaml` → `common.yaml` | `hiera_file` |
| dani (phase-2) | 9 | nodes → pipeline-box → pipeline → box → actions-pipeline → actions → `hiera_file` → `hiera_mysql` → `common.yaml` | `hiera_file` + `hiera_mysql` |

**Editor behaviour:**
- Nodes are sparse (2–3 keys) — default view shows common-layer value; node overrides render as diffs
- `docker::containers` (~500 lines in `common.yaml`): bespoke container editor (name/image/env/mounts/ports/restart/healthcheck)
- `mar3_frontend::actions` (~2000-line flow DSL): read-only collapsed YAML pane + "open in GitLab" link — **opaque in MVP**
- Secret-flagged fields (`engineering_pages::credentials_password`, `engineering_pages::ssl_key`, `obn::secret`, `portal::autologin_salt_hash`, `mar3_captiveportal_api::salt_hash`, `snmpd::usersv3`, credential sub-keys in `mqtt_bridge::brokers`) default-redact; cannot be edited through NMS+
- `hiera_mysql`-routed keys render as `external_db` badge: "value resolved at runtime from Puppet DB — MVP cannot show the effective value" — not editable (phase-2 may add read-only DB client)

### FR3 — Apply All (Batched Parameter Edits, D12)

Users accumulate edits in a **server-persisted draft change set** before committing. One active draft per fleet per user at a time; drafts persist across sessions.

**Apply All flow:**
1. BFF re-reads each affected file from the target branch at current tip SHA
2. Key-path-level conflict detection (not file-level) — returns structured 409 listing conflicting paths only
3. Creates one branch (`nms/<user>-<fleet>-<shortid>` off `devel` or `staging` — **never `master`**)
4. Applies all edits via `ruamel.yaml` (round-trip mode)
5. Opens one MR with rich description (all changed parameters, levels affected, submitter attribution); commit subject prefixed `NCD-<n>: ` where `<n>` is the submitter's Jira issue number (required field in the Apply All form)
6. Marks draft `SUBMITTED`, returns MR URL

**Apply All is the only path to MR creation** — no per-parameter commit. Apply All and discard actions are both audit events.

**Idempotency:** every write endpoint accepts `Idempotency-Key: <uuid>` header (D4). Same key + same fingerprint → return cached response. Same key + different fingerprint → 409. Missing header → 400. 24h TTL.

### FR4 — Server-Side Validation Gates (D14)

Before any GitLab write, BFF runs five gates in order; any failure returns 422 with the gate code and no GitLab write is attempted:

| Gate | Code | User-facing title |
|------|------|------------------|
| YAML parse | `yaml_parse_failed` | "Can't read this file" |
| yamllint | `yamllint_failed` | "Style check failed" |
| Key shape (known_keys) | `key_shape_mismatch` | "Value doesn't match expected shape" |
| Byte-diff drift | `byte_diff_drift` | "Edit touches unrelated lines" |
| Secret leak | `secret_leak_blocked` | "Can't edit this through NMS+" |

Server-side gate messages are canonical — frontend displays `message` verbatim without constructing its own copy.

### FR5 — Force Puppet Run (D13)

Endpoint: `POST /api/deployments/puppet-runs`

Hard three-check safety envelope (all server-side, all audited):
1. Target branch ∈ `{devel, staging}` — else 403 `target_branch_not_allowed`
2. Certname matches per-fleet bench allowlist (`bff/config/bench_allowlists/<fleet>.yaml`) — else 403 `not_a_bench_target`
3. JWT role = `editor` or `admin` — else 403 `role_missing`

Initial bench allowlists:
- **alpin**: `'^box1-t(100|101|125)\.alpin\.21net\.com$'`
- **dostoneu**: `'^box1-t(121|122|123|124|125|127)\.dostoneu-bench\.21net\.com$'`

All three checks must pass. Force-run against `master`, `ODEG`, or any production ref is hard-refused with no override path.

### FR6 — Parameter History (D16)

Every parameter in the Policy Tree exposes a History side panel: who changed it, when, from what value to what, on which branch, linked to the GitLab commit/MR.

Endpoint: `GET /api/policies/history?env=<env>&branch=<branch>&key_path=<path>&limit=20`

- Result cached in Postgres `parameter_history_cache` with 5-min TTL
- Keys routed by `hiera_file`: show note "history lives in routed file: `hieradata/files/...`"
- Keys routed by `hiera_mysql`: show note "value is external — history not visible from GitLab"
- Panel is default-collapsed (lazy load); panel only fetches on expand

### FR7 — Audit Log

Joins three sources: our Postgres `audit_event` table, GitLab commit/MR history, PuppetDB run records. Events include: fleet opened, edit staged, edit discarded, draft submitted, MR created, force-run triggered (with certname + run UUID), policy tree viewed. Commits to `devel`/`staging`/`master` not authored by the NMS+ service account are flagged "external edit".

### FR8 — Health Probes

- `GET /healthz` — liveness; 200 if process is up; no downstream checks; unauthenticated; rate-limited
- `GET /readyz` — readiness; checks Postgres (`SELECT 1`), Keycloak JWKS reachability, GitLab API base reachability; does NOT check PuppetDB (soft dependency); returns 503 with JSON body enumerating failed checks; unauthenticated; rate-limited

---

## Non-Functional Requirements

### Availability

- No hard availability target for MVP POC.
- Hard dependencies (outage = app outage): Keycloak, GitLab.
- PuppetDB is HA — not a single point of failure. PuppetDB outage degrades Overview, Compliance, and Deployments views but does not affect the write path. Each view has documented degraded-mode behaviour (banner + last-cached timestamp).
- BFF runs at `replicas: 1` (D8 single-pod constraint). Routine pod restart = brief outage (~10s), acceptable for POC.

### Performance

| Metric | Target |
|--------|--------|
| BFF read endpoints p95 | < 500ms |
| BFF write endpoints (MR creation) p95 | < 1500ms |
| Large hieradata parses | Background jobs with SSE/polling |
| Frontend initial load (Lighthouse) | ≥ 85 |
| Policy Tree rendering | Smooth at 500+ nodes (single large fleet) |

### SLOs (three only — each is an operational commitment)

| SLO | Target | Alert |
|-----|--------|-------|
| Write-path success rate (`POST .../apply` 2xx ratio, excl. 4xx user errors) | ≥ 99.0% rolling 7 days | 2h fast-burn 2× budget → page; 24h slow-burn 2× budget → page |
| Read p95 latency (all `GET /api/**` excl. deep audit pagination) | < 500ms | Sustained p95 > 500ms for 10 min → ticket |
| PuppetDB data staleness (max age of PuppetDB-sourced data in Overview/Compliance) | < 5 min | ≥ 15 min → page; ≥ 60 min → sev-2 incident |

Out-of-SLO items (documented, not targets): force-run success latency (Puppet Server dependency), GitLab commit-log pagination for D16 (GitLab API bound), SSE stream stability (polling fallback covers).

### Availability

- Target: 99.5% for POC
- Hard dependencies (outage = app outage): Keycloak, GitLab
- PuppetDB is a high-impact **soft dependency**: outage degrades Overview, Compliance, Deployments views but does not prevent write path. Each view has documented degraded-mode behaviour (see §4 of brief)
- BFF runs at `replicas: 1` for MVP (D8 — single-pod constraint). No HPA. Routine pod restart = brief outage (~10s), documented on service status page.

### Scale (POC)

- 1 tenant (Nomad), ~10–20 project engineers
- MVP day-one: alpin + dostoneu fleets (~250 trains combined); dani is phase-2
- Write volume: ~5–20 parameter changes/day
- Read volume: light — engineers open the app a few times per day

---

## Security Requirements

| Requirement | Detail |
|-------------|--------|
| AuthN | Keycloak OIDC, RS256 JWTs verified on every BFF request, no exceptions |
| AuthZ | Role claim → operation matrix below |
| Write gating | Only `editor` or `admin` can trigger Apply All and force-run |
| Secret fields | Never surface cleartext in Policy Tree; render as "redacted — use encrypted workflow" |
| D14 secret-leak gate | Runs on every preview and Apply All; catches AWS keys, GCP service account keys, PEM private keys, GitLab PATs, generic token patterns |
| Audit trail | Every write endpoint appends `audit_event` row; GitLab commit/MR history is the authoritative external record |
| Attribution | Commit messages always include `Submitted by: <user> via NMS+ Config on <timestamp>` even though GitLab service account is the Git author |
| Error discipline | Never leak downstream URLs or stack traces; 401/403 have identical bodies; correlation id on every error |
| Secrets storage | GitLab token, PuppetDB creds, Puppet Server token, Postgres creds in K8s Secrets; never hardcoded, never in images, never logged |
| GitLab service account scope | `api` on hieradata projects only: `env/environment-alpin` (1211) + `env/environment-dostoneu` (1136) for MVP; dani added in phase-2 |
| Two-human discipline | Submitter ≠ merger is a **team convention**, not a technical control; backed by audit trail only. Do not list as enforced in compliance documentation. |
| Audit retention | 2 years (our Postgres event log); GitLab remains the authoritative long-horizon record |

**Role → operation matrix:**

| Operation | viewer | editor | admin |
|-----------|:---:|:---:|:---:|
| Read Policy Tree, Overview, Compliance, Deployments | ✅ | ✅ | ✅ |
| Read Audit Log | ✅ | ✅ | ✅ |
| Stage parameter edit (draft) | — | ✅ | ✅ |
| Apply All (create MR) | — | ✅ | ✅ |
| Force Puppet run (bench only, D13) | — | ✅ | ✅ |
| Environment onboarding / rescan / archive (phase-2) | — | — | ✅ |

---

## Reference Environments (MVP Day-One Portfolio)

| Fleet | GitLab Project | Layers | Trains | Day-One? |
|-------|---------------|--------|--------|----------|
| alpin | `env/environment-alpin` (project 1211) | 3 | ~50 + t100/101/125 bench | ✅ |
| dostoneu | `env/environment-dostoneu` (project 1136) | 4 | 200+ + t121/122/123/124/125/127 bench | ✅ |
| dani | `env/environment-dani` (project 778) | 9 (incl. `hiera_mysql`) | 113 (day/night sub-fleets) | ❌ phase-2 |

Per-env config files (`known_keys/<env>.yaml`, `environments/<env>.yaml`, `bench_allowlists/<env>.yaml`, `hiera_file_inventory/<env>.yaml`) are **hand-authored** for alpin and dostoneu from the §9a discovery data in the brief. The onboarding wizard (phase-2) automates this for dani and future environments.

---

## Downstream Dependencies

| Downstream | Protocol | Auth | Used for |
|-----------|---------|------|---------|
| GitLab (`git-nc.nomadrail.com`, CE 18.10.1) | REST | Service account PAT (alpin + dostoneu scope) | Policies, audit, deployments |
| PuppetDB | PQL/REST | Read-only token | Overview, compliance, deployments |
| Puppet Server | REST | Write-capable token (separate K8s Secret) | Force-run only (D13) |
| Keycloak | OIDC | Realm config | Auth (all endpoints) |
| Postgres (CloudNativePG in-cluster) | PG protocol | Password in K8s Secret | Draft change sets, audit events, caches, idempotency keys, user preferences |

Not in MVP (do not re-add): NMS API, Zabbix, SIEMonster, ServiceNow, BigQuery, ThoughtSpot, Asset DB.

---

## Out of Scope (MVP)

- Multi-tenancy (`customer_id` scoping) — deferred to phase-3; dependency shape kept in `get_current_user`
- Other NMS+ modules: `/monitor`, `/alerts`, `/reports`, `/secure`
- Force-run against production branches (`master`, `ODEG`, any customer ref)
- Rich canary/rollout orchestration (User Guide §6) — MVP shows status only; rollback = revert in GitLab
- `hiera-eyaml` secrets migration — Nomad SRE owns; app redacts + D14 guards
- GitLab EE Approvals integration (CE repo, no API)
- New-environment onboarding wizard (`/onboarding/*` routes, `platform` role, §7a) — phase-2
- `dani` fleet and `hiera_mysql` value resolution — phase-2
- Mark-override (phase-2), per-device local-override classification
- PDF and scheduled compliance exports — MVP ships CSV-on-demand only
- Structured editing of `mar3_frontend::actions` flow DSL — phase-2
- Real-time collaborative editing, offline mode / PWA, mobile / native app
- Deploy-window enforcement — policy-only; no BFF enforcement
- MAR3 actions-layer structured editor — read-only opaque block in MVP

---

## Week-1 Spike Tasks (for scrum-master to schedule first)

These are prerequisite investigations, not feature stories. Each produces a pass/fail verdict before implementation begins:

1. **`hiera_file` plugin inventory spike** — grep `nomad_connect` submodule, enumerate keys routed through `hiera_file`, write `bff/config/hiera_file_inventory/{alpin,dostoneu}.yaml`
2. **`ruamel.yaml` round-trip spike** — run every hieradata file in alpin + dostoneu through `YAML(typ='rt')` round-trip and diff against original; populate `bff/config/ruamel_tolerance.yaml` with any benign drift patterns; D10 must block on a clean verdict here before D14 byte-diff gate is implemented
3. **`hiera_mysql` opaque rendering (dani, investigation only)** — confirm opaque-render approach is acceptable to PEs; scope phase-2 DB-read path
4. **Test fixture capture** — run `scripts/refresh_fixture.py` against alpin + dostoneu at recorded SHAs; commit `tests/fixtures/{alpin,dostoneu}/` + `tests/fixtures/gitlab_mock/`

---

## Acceptance Criteria

### AC1 — Policy Tree loads for alpin fleet
Given an `editor` is authenticated and selects the alpin fleet on the `devel` branch, when the Policy Tree loads, then the tree renders 3 layers (Node → File-parameter override → Common) matching the actual `hiera.yaml` layer order, with no hardcoded layer count.

### AC2 — Parameter edit stages correctly
Given an `editor` has the alpin Policy Tree open, when they edit a scalar parameter (e.g. `ntpd::service_ntpd_enable`) and click Stage, then a `draft_parameter_edit` row is created in Postgres and the footer shows "1 staged change".

### AC3 — Apply All creates a GitLab MR
Given an `editor` has at least one staged edit, when they click Apply All, then: a branch `nms/<user>-alpin-<shortid>` is created off `devel`, a single commit is pushed with attribution, an MR is opened targeting `devel`, the draft transitions to `SUBMITTED`, and the MR URL is returned to the UI.

### AC4 — D14 secret-leak gate blocks a secret edit
Given an `editor` stages an edit to `engineering_pages::credentials_password`, when they click Apply All, then the BFF returns 422 with `gate: "secret_leak_blocked"` and no GitLab branch is created.

### AC5 — D14 yamllint gate blocks malformed YAML
Given an `editor` stages an edit that produces yamllint failures, when Apply All is called, then the BFF returns 422 with `gate: "yamllint_failed"` and the lint rule + line number in the `message` field.

### AC6 — Force-run bench allowlist check blocks a non-bench certname
Given an `editor` calls `POST /api/deployments/puppet-runs` with a production certname, when the request arrives, then the BFF returns 403 with detail `not_a_bench_target` and Puppet Server is not called.

### AC7 — Force-run blocked on master branch
Given an `editor` calls `POST /api/deployments/puppet-runs` with `environment: "master"`, when the request arrives, then the BFF returns 403 with detail `target_branch_not_allowed` and Puppet Server is not called.

### AC8 — Unauthenticated request returns 401
Given a request is made to any BFF endpoint without a JWT, when it arrives, then the response is 401 with no data payload.

### AC9 — Viewer cannot create MR
Given a `viewer` token, when `POST /api/policies/drafts/{id}/apply` is called, then the response is 403 with body `{"detail": "Insufficient role"}`.

### AC10 — Idempotency replay returns cached response
Given an `editor` calls Apply All with `Idempotency-Key: <uuid>` and the call succeeds, when the same request is retried with the same key and same body, then the BFF returns the original cached response without creating a second MR.

### AC11 — Parameter history returns commit log for a key
Given the `parameter_history_cache` is empty, when `GET /api/policies/history?env=alpin&branch=devel&key_path=ntpd::service_ntpd_enable` is called, then the response contains a list of commits where that key changed, each entry including `commit_sha`, `committed_at`, `author_email`, `old_value`, `new_value`.

### AC12 — PuppetDB outage degrades gracefully
Given PuppetDB is unreachable, when the Compliance view loads, then a "PuppetDB unreachable — data stale as of X" banner is shown with the last-cached timestamp and no uncaught errors occur.

### AC13 — `hiera_mysql` key renders as opaque (alpin/dostoneu not affected; future dani gate)
When D10 encounters a key routed via `hiera_mysql`, then the Policy Tree renders the key with an `external_db` badge and blocks edits with message "This key is set from the Puppet MySQL DB — MVP cannot show the effective value."

---

## Test Coverage Requirements

- BFF new business logic: ≥ 90% line coverage (`pytest --cov --cov-fail-under=90`)
- D14 gates: 100% line coverage on each gate module, per story that touches that gate
- Frontend new components and hooks: all branches covered (loading + error + empty + populated)
- Security tests: mandatory on every BFF endpoint (see CLAUDE.md §Enterprise Standards)
- E2E (Playwright): happy path + auth failure + D14 gate failure path per feature
- All tests run against `tests/fixtures/` — never against live GitLab/PuppetDB/Puppet Server

---

## Open Questions

None. All §9 open questions from the System Design Brief are resolved as of 2026-04-20. See brief §9 for the closed-question audit trail.

---

## Deferred to Requirements Analyst / Architect

The following items from the brief require architect decisions before implementation stories can be written:

- Exact `ruamel_tolerance.yaml` whitelist entries (output of the week-1 ruamel spike)
- `hiera_file_inventory/{alpin,dostoneu}.yaml` content (output of the week-1 hiera_file spike)
- Hand-authored per-env config files for alpin + dostoneu (`known_keys`, `environments`, `bench_allowlists`)
- ~~PuppetDB deployment topology confirmation~~ — **closed 2026-04-20**: PuppetDB is HA. No hard availability target for MVP POC. Availability section updated accordingly.
