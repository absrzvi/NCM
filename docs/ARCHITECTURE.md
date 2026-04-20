# Architecture — NMS+ Config MVP
Status: APPROVED

> Produced by the architect agent on 2026-04-20. Set Status to APPROVED to unblock the scrum-master agent.
> D1–D16 are pre-locked from the System Design Brief §5. New ADRs start at ADR-017.
> All terminology in this document follows the Domain Glossary in CLAUDE.md:
> - "fleet" = an NMS+ scope unit (alpin/dostoneu/dani).
> - "Puppet environment" (always qualified) = an r10k branch deployment target (devel/staging).
> A bare "environment" in new content is a review blocker.

---

## 1. System Overview

NMS+ Config is a single-tenant internal web application that gives Nomad project engineers a structured UI for reading and updating fleet hieradata, viewing Puppet run status, and forcing bench Puppet runs — all through a backend-for-frontend (BFF) that enforces JWT auth and server-side validation before any downstream system is written. The browser never communicates with GitLab, PuppetDB, Puppet Server, Keycloak, or Postgres directly; every call is proxied through `/api/*` on the BFF (Iron Rule 1). nginx terminates TLS, serves the built React bundle from `/`, and reverse-proxies `/api/*` to the BFF on the same Docker Compose network. All four services (nginx, bff, postgres, keycloak) run as containers on a single Linux VM in the Nomad DC (D8). No Kubernetes, no service mesh, no second BFF instance.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Browser (React 18 SPA + keycloak-js)                                       │
│  Routes: / /compliance /audit /policies /policies/history /deployments      │
└──────────────────────────────┬──────────────────────────────────────────────┘
                               │ HTTPS (TLS terminated at nginx)
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  nginx (container)                                                          │
│  • Serves static React bundle from /                                        │
│  • Reverse-proxies /api/* → BFF:8000                                        │
│  • /readyz gate before marking BFF pool healthy (Compose depends_on)        │
└──────────────────────────────┬──────────────────────────────────────────────┘
                               │ HTTP (Docker network: nmsplus_net)
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  BFF — FastAPI (single container, restart: unless-stopped)  D8              │
│                                                                             │
│  Middleware stack (applied to every request):                               │
│    1. Keycloak JWT validation (RS256, JWKS cached hourly)   D2              │
│    2. Idempotency-Key check on every write endpoint         D4              │
│    3. Rate limiter on write endpoints                                       │
│                                                                             │
│  Routers:                                                                   │
│    /api/policies/*    /api/deployments/*    /api/compliance/*               │
│    /api/audit/*       /healthz  /readyz                                     │
│                                                                             │
│  Shared helpers:                                                            │
│    bff/envelopes/safety_envelope.py         (D13)                           │
│    bff/history/parameter_history.py         (D16)                           │
│    bff/validation/{yaml_parse, yamllint,                                    │
│                    key_shape, byte_diff_drift, secret_scan}.py  (D14)       │
│    bff/middleware/idempotency.py            (D4)                            │
└──────┬────────┬──────────────┬───────────────┬────────────────┬────────────┘
       │        │              │               │                │
       ▼        ▼              ▼               ▼                ▼
  ┌─────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐
  │ GitLab  │ │ PuppetDB │ │ Puppet   │ │ Keycloak │ │ Postgres 16      │
  │ CE API  │ │ PQL/REST │ │ Server   │ │ OIDC     │ │ (named volume)   │
  │(httpx)  │ │ (httpx)  │ │ /run-    │ │ JWKS     │ │ audit_events     │
  │D6,D4,D5 │ │ read-only│ │  force   │ │ (cached) │ │ idempotency_keys │
  │         │ │ token    │ │ (httpx)  │ │          │ │ draft_change_sets│
  │         │ │          │ │ D11,D13  │ │          │ │ param_hist_cache │
  └─────────┘ └──────────┘ └──────────┘ └──────────┘ │ user_preferences │
                                                       │ environment_     │
                                                       │   configs        │
                                                       └──────────────────┘
```

**Docker Compose service topology (single VM):**
```
services: nginx | bff | postgres | keycloak
network:  nmsplus_net (bridge)
volumes:  postgres_data (named, persisted)
secrets:  /etc/nmsplus/secrets/*.env (host-side, mode 0600, via env_file)
```

---

## 2. Module Breakdown

### BFF Modules

#### policies
- **Router file:** `bff/routers/policies_router.py`
- **Responsibility:** Exposes hieradata read, draft staging, Apply All (MR creation), and parameter history; owns the D12 draft change-set lifecycle and D16 history cache.
- **Downstream calls:** GitLab API (read files, create branch, push commit, open MR, commit log); Postgres (draft_change_sets, parameter_history_cache, idempotency_keys).
- **D-decisions touched:** D4 (idempotency), D5 (ruamel.yaml), D6 (python-gitlab), D7 (three-way merge on stale branch), D10 (hiera.yaml layer parsing), D12 (draft change sets), D14 (five validation gates), D15 (branch write restrictions), D16 (parameter history cache).
- **SLO:** Write endpoints (`POST .../apply`, `POST .../drafts`): **write-path ≥99%**. Read endpoints (`GET /api/policies/*`, `GET /api/policies/history`): **read-path p95 <500ms**.

#### deployments
- **Router file:** `bff/routers/deployments_router.py`
- **Responsibility:** Surfaces merged MR deployment status and PuppetDB post-merge run results; provides the force Puppet run endpoint (D11/D13).
- **Downstream calls:** GitLab API (merged MR list); PuppetDB (run status per certname); Puppet Server `/run-force` exclusively via `bff/envelopes/safety_envelope.py`; Postgres (audit_events, idempotency_keys).
- **D-decisions touched:** D4 (idempotency on force-run), D9 (httpx), D11 (run-force only trigger), D13 (safety envelope), D15 (branch guard).
- **SLO:** Force-run (`POST /api/deployments/puppet-runs`): **write-path ≥99%** (primary); PuppetDB-backed reads: **read-path p95 <500ms AND PuppetDB staleness <5min** (degrade gracefully).

#### compliance
- **Router file:** `bff/routers/compliance_router.py`
- **Responsibility:** Returns per-device drift classification and Puppet fact summaries sourced from PuppetDB; degrades gracefully when PuppetDB is unreachable.
- **Downstream calls:** PuppetDB (per-device reports, facts, drift reports — read-only token only).
- **D-decisions touched:** D9 (httpx).
- **SLO:** **read-path p95 <500ms AND PuppetDB staleness <5min** (degrade gracefully when exceeded).

#### audit
- **Router file:** `bff/routers/audit_router.py`
- **Responsibility:** Joins Postgres UI event log with GitLab commit/MR history to produce a unified audit log; flags external edits (commits not authored by the NMS+ service account).
- **Downstream calls:** Postgres (audit_events); GitLab API (commit/MR history on target branches).
- **D-decisions touched:** D6 (python-gitlab), D9 (httpx).
- **SLO:** **read-path p95 <500ms** (deep pagination pages explicitly excluded per PRD SLO table).

#### health
- **Router file:** `bff/routers/health_router.py`
- **Responsibility:** Liveness (`/healthz`) and readiness (`/readyz`) probes; `/readyz` checks Postgres, Keycloak JWKS, and GitLab API base reachability but not PuppetDB.
- **Downstream calls:** Postgres (`SELECT 1`); Keycloak JWKS endpoint; GitLab API base URL — all within `/readyz` only. `/healthz` makes no downstream calls.
- **D-decisions touched:** None (infrastructure probes).
- **SLO:** **SLO: none** (reason: infra probes, not user-facing).

---

### Frontend Modules

#### Overview (`/`)
- **Component file:** `frontend/src/pages/Overview/Overview.tsx`
- **Responsibility:** Landing dashboard showing fleet KPIs (drift counts, recent Puppet runs) and recent GitLab MR/commit activity for the selected fleet.
- **BFF endpoints consumed:** `GET /api/compliance/summary`, `GET /api/deployments/recent-runs`, `GET /api/audit/recent-mrs`.
- **D-decisions touched:** D1 (no direct downstream calls), D3 (single-tenant user context).
- **SLO:** Governed by upstream endpoints — read-path p95 <500ms; PuppetDB data subject to staleness <5min with degraded-mode banner.

#### Compliance (`/compliance`)
- **Component file:** `frontend/src/pages/Compliance/Compliance.tsx`
- **Responsibility:** Table of all certnames with drift classification (in-sync/drifted/unreported) and last Puppet report timestamp; CSV-on-demand export.
- **BFF endpoints consumed:** `GET /api/compliance/drift`.
- **D-decisions touched:** D1, D3.
- **SLO:** read-path p95 <500ms AND PuppetDB staleness <5min.

#### Audit (`/audit`)
- **Component file:** `frontend/src/pages/Audit/Audit.tsx`
- **Responsibility:** Paginated unified audit log (UI events + GitLab commits/MRs); filterable by fleet, user, date range, and event type.
- **BFF endpoints consumed:** `GET /api/audit/events`.
- **D-decisions touched:** D1, D3.
- **SLO:** read-path p95 <500ms (deep pagination pages excluded per SLO definition).

#### PolicyTree (`/policies`)
- **Component file:** `frontend/src/pages/PolicyTree/PolicyTree.tsx`
- **Responsibility:** Structured hieradata editor rendering the fleet's hiera.yaml layer hierarchy; manages the staged-edit draft lifecycle and triggers Apply All; renders secret fields as redacted and `hiera_mysql`-routed keys as `external_db` badges.
- **BFF endpoints consumed:** `GET /api/policies/tree`, `POST /api/policies/drafts`, `PUT /api/policies/drafts/{id}`, `DELETE /api/policies/drafts/{id}`, `POST /api/policies/drafts/{id}/apply`.
- **D-decisions touched:** D1, D4 (idempotency key sent by frontend on all writes), D10, D12, D14, D15.
- **SLO:** Tree reads: read-path p95 <500ms. Apply All: write-path ≥99%.

#### Deployments (`/deployments`)
- **Component file:** `frontend/src/pages/Deployments/Deployments.tsx`
- **Responsibility:** Lists merged MRs with their post-merge Puppet run status per certname; provides the Force Run action (bench-only, Puppet environments devel/staging only).
- **BFF endpoints consumed:** `GET /api/deployments/status`, `POST /api/deployments/puppet-runs`.
- **D-decisions touched:** D1, D4, D11, D13, D15.
- **SLO:** Status reads: read-path p95 <500ms with PuppetDB staleness tolerance. Force-run: write-path ≥99%.

#### History (`/policies/history?key_path=...`)
- **Component file:** `frontend/src/pages/PolicyTree/HistoryPanel.tsx`
- **Responsibility:** Side panel (lazy-loaded on expand) showing per-key-path GitLab commit log with old/new values, author, timestamp, and MR link; respects `hiera_file` and `hiera_mysql` routing notes.
- **BFF endpoints consumed:** `GET /api/policies/history`.
- **D-decisions touched:** D1, D16.
- **SLO:** read-path p95 <500ms.

---

## 3. Data Model

All tables live in the single Postgres 16 container. The BFF owns the schema. Migrations managed via Alembic; run by the BFF container on startup (not in CI — alembic upgrade is a manual/startup operation per D8 simplicity principle).

---

### `audit_events`

| Column | Type | Nullable | Purpose |
|--------|------|----------|---------|
| `id` | `uuid` | NOT NULL | Primary key, generated by BFF |
| `created_at` | `timestamptz` | NOT NULL | Wall-clock time of the event (UTC) |
| `fleet` | `text` | NOT NULL | Fleet name (alpin/dostoneu/dani) |
| `puppet_environment` | `text` | NULL | Puppet environment target (devel/staging) if applicable |
| `event_type` | `text` | NOT NULL | Enum-style: fleet_opened, edit_staged, edit_discarded, draft_submitted, mr_created, force_run_triggered, policy_tree_viewed, external_edit_flagged |
| `user_sub` | `text` | NOT NULL | Keycloak subject (user identity, no PII) |
| `user_role` | `text` | NOT NULL | JWT role at time of action |
| `detail` | `jsonb` | NULL | Event-specific payload (key_paths affected, MR URL, certname, run UUID, commit SHA, etc.) — no hieradata values, no secrets |
| `correlation_id` | `text` | NOT NULL | Request correlation ID for incident investigation |
| `source` | `text` | NOT NULL | `ui` for NMS+ events; `gitlab` for ingested external commits |

**Indexes:**
- PK on `id`
- `(fleet, created_at DESC)` — primary query pattern for audit log pagination
- `(user_sub, created_at DESC)` — user-scoped audit queries
- `(event_type, created_at DESC)` — event type filtering

**Retention policy:** 2 years. Rows older than 2 years may be archived to a flat file by a periodic job and then deleted. GitLab remains the authoritative long-horizon record. No automated purge in MVP — operator-run script in `deploy/scripts/audit_archive.sh`.

---

### `idempotency_keys`

| Column | Type | Nullable | Purpose |
|--------|------|----------|---------|
| `key` | `text` | NOT NULL | The `Idempotency-Key` header value (UUID) |
| `fingerprint` | `text` | NOT NULL | RFC 8785 JCS hash of the request body |
| `endpoint` | `text` | NOT NULL | BFF route path (e.g. `/api/policies/drafts/{id}/apply`) |
| `user_sub` | `text` | NOT NULL | Keycloak subject — keys are user-scoped |
| `status_code` | `int` | NOT NULL | HTTP status of the original response |
| `response_body` | `jsonb` | NOT NULL | Cached response body returned on replay |
| `created_at` | `timestamptz` | NOT NULL | When the key was first recorded |
| `expires_at` | `timestamptz` | NOT NULL | `created_at + 24h` (D4 TTL) |

**Indexes:**
- PK on `(key, user_sub)` — lookup on replay
- `expires_at` — for the TTL purge job

**Retention policy:** 24h TTL (D4). A periodic job (or BFF startup sweep) deletes rows where `expires_at < NOW()`.

---

### `draft_change_sets`

| Column | Type | Nullable | Purpose |
|--------|------|----------|---------|
| `id` | `uuid` | NOT NULL | Primary key |
| `fleet` | `text` | NOT NULL | Fleet this draft targets |
| `puppet_environment` | `text` | NOT NULL | Puppet environment (devel/staging) |
| `user_sub` | `text` | NOT NULL | Owner (one active draft per fleet per user) |
| `status` | `text` | NOT NULL | `ACTIVE`, `SUBMITTED`, `DISCARDED` |
| `created_at` | `timestamptz` | NOT NULL | Draft creation time |
| `updated_at` | `timestamptz` | NOT NULL | Last staged edit or status change |
| `submitted_at` | `timestamptz` | NULL | Set when status transitions to SUBMITTED |
| `jira_issue` | `text` | NULL | NCD-<n> from Apply All form; required at submit time |
| `mr_url` | `text` | NULL | GitLab MR URL once submitted |
| `branch_sha_at_creation` | `text` | NOT NULL | Branch tip SHA when draft was created (for D7 three-way merge baseline) |
| `edits` | `jsonb` | NOT NULL | Array of `{key_path, file_path, layer, old_value, new_value, staged_at}` entries; no secrets |

**Indexes:**
- PK on `id`
- `(user_sub, fleet, status)` WHERE `status = 'ACTIVE'` — unique partial index enforcing one active draft per user per fleet
- `(fleet, status, created_at DESC)` — fleet-scoped draft listing for admin views

**Retention policy:** `SUBMITTED` and `DISCARDED` drafts retained for 90 days, then eligible for deletion. `ACTIVE` drafts are never auto-deleted.

---

### `parameter_history_cache`

| Column | Type | Nullable | Purpose |
|--------|------|----------|---------|
| `id` | `uuid` | NOT NULL | Primary key |
| `cache_key` | `text` | NOT NULL | Hash of `(fleet, puppet_environment, branch, key_path, limit)` |
| `fleet` | `text` | NOT NULL | Fleet the history was fetched for |
| `puppet_environment` | `text` | NOT NULL | Puppet environment |
| `branch` | `text` | NOT NULL | Git branch target |
| `key_path` | `text` | NOT NULL | Hiera key path (e.g. `ntpd::service_ntpd_enable`) |
| `history_json` | `jsonb` | NOT NULL | Array of commit entries `{commit_sha, committed_at, author_email, old_value, new_value, mr_url}` |
| `fetched_at` | `timestamptz` | NOT NULL | When the GitLab API was queried |
| `expires_at` | `timestamptz` | NOT NULL | `fetched_at + 5min` (D16 TTL) |

**Indexes:**
- PK on `id`
- Unique on `cache_key` — lookup on cache hit
- `expires_at` — TTL sweep

**Retention policy:** 5-minute TTL (D16). Expired rows swept on read or by a periodic lightweight job.

---

### `user_preferences`

| Column | Type | Nullable | Purpose |
|--------|------|----------|---------|
| `user_sub` | `text` | NOT NULL | Keycloak subject — PK |
| `last_fleet` | `text` | NULL | Last-selected fleet (alpin/dostoneu/dani) for UX restore |
| `last_puppet_environment` | `text` | NULL | Last-selected Puppet environment (devel/staging) |
| `policy_tree_collapsed` | `jsonb` | NULL | Map of `{layer_id: bool}` for collapsed state (no PII, no tokens) |
| `updated_at` | `timestamptz` | NOT NULL | Last preference write |

**Indexes:**
- PK on `user_sub`

**Retention policy:** No expiry. Rows persist as long as the user exists. Phase-2 admin tooling may add a purge-on-offboard flow.

---

### `environment_configs`

| Column | Type | Nullable | Purpose |
|--------|------|----------|---------|
| `fleet` | `text` | NOT NULL | Fleet name (alpin/dostoneu/dani) — part of PK |
| `puppet_environment` | `text` | NOT NULL | Puppet environment target (devel/staging) — part of PK |
| `gitlab_project_id` | `int` | NOT NULL | GitLab project numeric ID (1211=alpin, 1136=dostoneu, 778=dani) |
| `gitlab_project_path` | `text` | NOT NULL | GitLab project path (e.g. `env/environment-alpin`) |
| `target_branch` | `text` | NOT NULL | Default Git branch for this Puppet environment (devel/staging); never master |
| `layer_count` | `int` | NOT NULL | Number of hiera.yaml layers (3/4/9) |
| `hiera_yaml_path` | `text` | NOT NULL | Path within the GitLab repo to the `hiera.yaml` file |
| `bench_allowlist` | `jsonb` | NOT NULL | Regex patterns for certnames allowed in force-run (D13) |
| `known_keys_path` | `text` | NOT NULL | Config path to the known_keys file used in D14 key-shape gate |
| `active` | `bool` | NOT NULL | Whether this fleet+Puppet environment combo is enabled in the UI |
| `created_at` | `timestamptz` | NOT NULL | Row creation time |
| `updated_at` | `timestamptz` | NOT NULL | Last modification time |

**Indexes:**
- PK on `(fleet, puppet_environment)`
- Index on `active` — UI fleet-picker only shows active combos

**Retention policy:** No expiry. Phase-2 admin onboarding wizard writes rows here. MVP rows are hand-authored by the operator at deploy time (alpin + dostoneu only).

---

## 4. API Surface (stub — full detail in docs/API_CONTRACTS.md)

All endpoints are prefixed `/api/`. Auth required = Keycloak JWT (RS256) on every row. Missing JWT → 401. Role enforcement is additional to auth.

| Method | Path | Auth | Role Required | Idempotency-Key | SLO | D-Decisions |
|--------|------|------|---------------|-----------------|-----|-------------|
| GET | `/api/policies/tree` | ✅ | viewer+ | — | read-path p95 <500ms | D1, D6, D10 |
| GET | `/api/policies/history` | ✅ | viewer+ | — | read-path p95 <500ms | D1, D6, D16 |
| GET | `/api/policies/drafts` | ✅ | editor+ | — | read-path p95 <500ms | D1, D12 |
| POST | `/api/policies/drafts` | ✅ | editor+ | Required | write-path ≥99% | D1, D4, D12 |
| PUT | `/api/policies/drafts/{id}` | ✅ | editor+ | Required | write-path ≥99% | D1, D4, D12 |
| DELETE | `/api/policies/drafts/{id}` | ✅ | editor+ | Required | write-path ≥99% | D1, D4, D12 |
| POST | `/api/policies/drafts/{id}/apply` | ✅ | editor+ | Required | write-path ≥99% | D1, D4, D5, D6, D7, D12, D14, D15 |
| GET | `/api/deployments/status` | ✅ | viewer+ | — | read-path p95 <500ms + PuppetDB <5min | D1, D6, D9 |
| GET | `/api/deployments/recent-runs` | ✅ | viewer+ | — | read-path p95 <500ms + PuppetDB <5min | D1, D9 |
| POST | `/api/deployments/puppet-runs` | ✅ | editor+ | Required | write-path ≥99% | D1, D4, D11, D13, D15 |
| GET | `/api/compliance/drift` | ✅ | viewer+ | — | read-path p95 <500ms + PuppetDB <5min | D1, D9 |
| GET | `/api/compliance/summary` | ✅ | viewer+ | — | read-path p95 <500ms + PuppetDB <5min | D1, D9 |
| GET | `/api/audit/events` | ✅ | viewer+ | — | read-path p95 <500ms | D1, D6 |
| GET | `/api/audit/recent-mrs` | ✅ | viewer+ | — | read-path p95 <500ms | D1, D6 |
| GET | `/healthz` | — | none | — | SLO: none (infra probe) | — |
| GET | `/readyz` | — | none | — | SLO: none (infra probe) | — |

Notes:
- All write endpoints (POST/PUT/PATCH/DELETE) enforce `Idempotency-Key` header via `bff/middleware/idempotency.py`. Missing header → 400.
- `viewer+` means viewer, editor, or admin. `editor+` means editor or admin.
- PuppetDB-backed reads degrade gracefully: response includes `puppetdb_stale: true` and `last_fetched_at` when data exceeds 5-min staleness threshold.
- Full request/response schemas, error shapes, and pagination contracts are in `docs/API_CONTRACTS.md`.

---

## 5. D-Decision Conformance Matrix

| ID | Summary | Architecture Conformance |
|----|---------|------------------------|
| D1 | React 18 SPA + FastAPI BFF — browser never calls downstreams | All downstream clients (`gitlab_client.py`, `puppetdb_client.py`, `puppet_server_client.py`, `keycloak_jwks.py`) live exclusively in `bff/clients/`. nginx routes only `/api/*` to the BFF. The React bundle has no GitLab/PuppetDB/Puppet Server URLs baked in. Iron Rule 1 enforced. |
| D2 | Keycloak JWT (RS256) + keycloak-js silent refresh 60s before expiry | `bff/middleware/` validates JWT on every request using `bff/clients/keycloak_jwks.py` (JWKS cached hourly). Frontend uses `keycloak-js` with `onTokenExpired` triggering silent refresh 60s before `exp`. |
| D3 | Single-tenant MVP — `get_current_user` (no `customer_id`) | Every endpoint calls `get_current_user` (returns `sub` + `roles` from JWT). No `customer_id` field in any schema. Iron Rule 3 documented. Multi-tenancy deferred to phase-3 ADR. |
| D4 | GitLab as hieradata source of truth; Idempotency-Key header on writes, 24h TTL | `idempotency_keys` table stores `(key, fingerprint, user_sub, response_body, expires_at)`. `bff/middleware/idempotency.py` enforces presence on all write methods. Same key + same fingerprint → cached response. Same key + different fingerprint → 409. Missing → 400. 24h TTL enforced via `expires_at`. |
| D5 | ruamel.yaml round-trip for hieradata writes | All hieradata writes in `bff/routers/policies_router.py` call `ruamel.yaml` with `typ='rt'`. `yaml.safe_dump` is banned (Iron Rule 11). The week-1 ruamel spike populates `bff/config/ruamel_tolerance.yaml` before any D5 implementation story is scoped. |
| D6 | python-gitlab for all GitLab operations | All GitLab API interactions go through `bff/clients/gitlab_client.py` which uses the `python-gitlab` library. No direct `httpx` calls to GitLab — those are wrapped inside `gitlab_client.py`. |
| D7 | Server-side three-way merge on stale-branch conflict | `draft_change_sets.branch_sha_at_creation` records the tip SHA at draft creation. At Apply All time, `policies_router.py` re-reads each affected file from the current branch tip and performs key-path-level conflict detection (not file-level) before writing. Conflicts return structured 409 listing only the conflicting `key_path` entries. |
| D8 | Single BFF container — no second instance, no autoscaling, no HA pair | Docker Compose declares `deploy: replicas: 1` (or no scale flag). `restart: unless-stopped` is set. No load-balanced pair, no HPA, no leader election. Drafts, history cache, and idempotency keys in Postgres; a second BFF would fragment state. Routine host reboot → brief outage (~10s); acceptable and documented on service status page. CLAUDE.md §No Horizontal Scaling is the enforcement reference. |
| D9 | httpx for all outbound HTTP | `bff/clients/{gitlab_client,puppetdb_client,puppet_server_client,keycloak_jwks}.py` all use `httpx.AsyncClient`. `requests` and `aiohttp` are banned (Iron Rule 9). |
| D10 | hiera.yaml parsed at load time — per-fleet dynamic layering (3/4/9 layers) | `bff/routers/policies_router.py` reads and parses the fleet's `hiera.yaml` at request time (cached per fleet per branch). Layer counts: alpin=3, dostoneu=4, dani=9. **Blocked on week-1 spike (see §6):** D10 implementation stories must not be scoped until the `hiera_file` plugin spike confirms no conditional/dynamic logic. If the plugin is dynamic, escalate to a new ADR rather than proceeding. |
| D11 | Puppet Server /run-force is the only catalog-apply trigger MVP supports | No other Puppet-apply mechanism exists in the BFF. Puppet Server calls are only in `bff/envelopes/safety_envelope.py` and invoked only from `deployments_router.py` via the shared `force_run` helper. Iron Rule 12 enforced. |
| D12 | Postgres-persisted draft change sets; key-path conflict detection | `draft_change_sets` table stores the full edit array as JSONB. One active draft per user per fleet enforced via unique partial index. Conflict detection at Apply All time is key-path-level (not file-level), returning structured 409. |
| D13 | Force-run safety envelope: three pre-flight checks + abort-on-drift | `bff/envelopes/safety_envelope.py` implements all three checks: (1) target branch ∈ {devel, staging}, (2) certname matches fleet bench allowlist regex, (3) JWT role ∈ {editor, admin}. All three must pass. `certname` validated against `^[a-z0-9][a-z0-9-]*(\.[a-z0-9-]+)*$` before the envelope check. Bench allowlists in `bff/config/bench_allowlists/<fleet>.yaml`. No inline httpx call to Puppet Server is permitted. |
| D14 | Server-side validation gates (5 of them) — no client-side pre-commit | `bff/validation/{yaml_parse.py, yamllint.py, key_shape.py, byte_diff_drift.py, secret_scan.py}` run in order before any GitLab write. Any failure → 422 with gate code and no GitLab API call is made. Gate error messages are canonical; frontend displays `message` verbatim. 100% line coverage required per gate module. |
| D15 | Per-env target branch config; hardcoded refuse for master/ODEG | `environment_configs.target_branch` stores the writable branch per fleet+Puppet environment. The safety envelope and policies router hard-refuse any branch not in `{devel, staging}` with no override path. GitLab service account scope is limited to `env/environment-alpin` and `env/environment-dostoneu` for MVP. |
| D16 | Parameter history endpoint — GitLab commit log scoped per key_path, 5-min Postgres cache | `bff/history/parameter_history.py` fetches GitLab commit log, filters to commits touching the relevant file, extracts before/after values for the key_path. Results cached in `parameter_history_cache` with 5-min TTL. `hiera_file`-routed keys include a note pointing to the routed file path. `hiera_mysql`-routed keys return the opaque note. History panel is lazy-loaded in the frontend (only fetches on expand). |

---

## 6. Week-1 Spike Tasks

These are prerequisite investigations, not feature stories. Each produces a pass/fail verdict and an artifact. No D10 or D5 implementation story may be scoped until the relevant spike delivers its verdict.

### Spike 1 — `hiera_file` Plugin Inventory
**What it must produce:**
- `bff/config/hiera_file_inventory/alpin.yaml` and `bff/config/hiera_file_inventory/dostoneu.yaml` — complete enumeration of key paths routed through the `hiera_file` plugin, with the routed file path for each key.
- Pass verdict: plugin contains no conditional logic, no per-fact branches, no environment-aware routing. The static reconstruction in D10 will match Puppet's runtime resolution.
- Fail verdict: plugin contains dynamic logic → **escalate to architect for new ADR before any D10 story is written.** Do not proceed to D10 implementation.

**Blocks:** D10 implementation stories; the `hiera_file` routing display in PolicyTree; the parameter history `hiera_file` note in D16.

### Spike 2 — `ruamel.yaml` Round-Trip Fidelity
**What it must produce:**
- Every hieradata YAML file in `tests/fixtures/alpin/` and `tests/fixtures/dostoneu/` run through `YAML(typ='rt')` load → dump and byte-diffed against the original.
- `bff/config/ruamel_tolerance.yaml` — whitelist of any benign drift patterns observed (e.g. trailing newline normalisation, comment spacing).
- Pass verdict: all diffs are in the whitelist or there are no diffs. D14 `byte_diff_drift` gate is safe to implement using this tolerance file.
- Fail verdict: unexpected structural drift found → **escalate to architect.** D5 and D14 implementation are blocked until resolved.

**Blocks:** D5 implementation (ruamel write path); D14 `byte_diff_drift` gate implementation; Apply All stories.

### Spike 3 — `hiera_mysql` Opaque Rendering Validation (dani — investigation only)
**What it must produce:**
- Written confirmation from at least one project engineer (PE) that rendering `hiera_mysql`-routed keys as an `external_db` badge with the message "value resolved at runtime from Puppet DB — MVP cannot show the effective value" is acceptable for the dani phase-2 rollout.
- Scoped notes on what a phase-2 DB-read path would require (connection details, query shape, secret handling) — captured in `docs/stories/` as a phase-2 spike placeholder.

**Blocks:** dani fleet onboarding (phase-2 only). Does not block alpin or dostoneu MVP stories.

### Spike 4 — Test Fixture Capture
**What it must produce:**
- `tests/fixtures/alpin/` — full hieradata snapshot at a recorded commit SHA for the alpin fleet (3-layer).
- `tests/fixtures/dostoneu/` — full hieradata snapshot at a recorded commit SHA for the dostoneu fleet (4-layer).
- `tests/fixtures/gitlab_mock/` — canned GitLab API responses for MR creation, commit log, and branch operations.
- All fixtures scrubbed of secrets by `scripts/refresh_fixture.py` before commit.
- Fixtures committed in an explicit PR authored by a named operator; the refresh script must not run in CI.

**Blocks:** All integration tests (every BFF integration test must run against these fixtures, never against live services). No BFF story can reach Definition of Done without fixtures present.

---

## 7. ADR-017 Stub

### ADR-017: [Decision Title — to be filled when first new architectural decision is needed]
Date: YYYY-MM-DD
Status: PROPOSED
D-decisions touched: [list Dxx if any]

#### Context
[What situation or requirement is driving this decision? Be specific — reference the story or spike that surfaced the need.]

#### Decision
[What exactly are we building or changing? One declarative sentence minimum.]

#### Consequences
[What does this affect? What becomes easier or harder? What tests or documents must change?]

#### Rejected Alternatives
[What else was considered? Why was each alternative rejected?]

> Note: Fill this stub when the first story or spike requires a new architectural decision. Do not file a new ADR to re-examine D1–D16. If a week-1 spike returns a fail verdict (e.g. D10 plugin is dynamic), open ADR-017 immediately with the spike findings as context.

---

## 8. Open Blockers

The PRD closed all open questions from the System Design Brief §9 as of 2026-04-20. The following items must be resolved before any implementation story is scoped, but they are known and owned:

1. **Week-1 Spike 1 verdict** (`hiera_file` plugin): D10 stories and PolicyTree `hiera_file` routing stories are blocked until the pass verdict is in hand. If fail, ADR-017 must be filed before proceeding.
2. **Week-1 Spike 2 verdict** (`ruamel.yaml` round-trip): D5 and D14 `byte_diff_drift` gate stories are blocked until `bff/config/ruamel_tolerance.yaml` is committed.
3. **Week-1 Spike 4 fixture capture**: All BFF integration tests require fixtures. No story can reach Done without them.
4. **Hand-authored per-fleet config files**: `bff/config/known_keys/{alpin,dostoneu}.yaml`, `bff/config/environments/{alpin,dostoneu}.yaml`, and `bff/config/bench_allowlists/{alpin,dostoneu}.yaml` must be authored by the operator before any story that reads them is implemented. Content is derived from the §9a discovery data in the System Design Brief.
5. **`docs/ARCHITECTURE.md` Status: APPROVED** — this document must be approved by a human before the scrum-master agent writes any story files (Human Gate 2 in CLAUDE.md).

No other blockers exist. All architectural decisions required for MVP are captured above or locked in D1–D16.

---

## Pre-Locked Decisions (reference index — do not relitigate)

| ID | Summary |
|---|---|
| D1 | React 18 SPA + FastAPI BFF — browser never calls downstreams |
| D2 | Keycloak JWT (RS256) + keycloak-js silent refresh 60s before expiry |
| D3 | Single-tenant MVP — Iron Rule 3; `get_current_user`; no `customer_id` |
| D4 | GitLab as hieradata source of truth; Idempotency-Key on writes, 24h TTL |
| D5 | ruamel.yaml round-trip for hieradata writes |
| D6 | python-gitlab for all GitLab operations |
| D7 | Server-side three-way merge on stale-branch conflict |
| D8 | Single BFF container on one Linux VM — no second instance, no autoscaling, no HA pair |
| D9 | httpx for all outbound HTTP |
| D10 | hiera.yaml parsed at load time — per-fleet layering (3/4/9). Week-1 spike dependency. |
| D11 | Puppet Server /run-force is the only catalog-apply trigger |
| D12 | Postgres draft change sets; key-path conflict detection |
| D13 | Force-run safety envelope: three checks + abort-on-drift |
| D14 | Server-side validation gates (5 of them) — no client-side pre-commit |
| D15 | Per-Puppet-environment target branch config; hardcoded refuse for master/ODEG |
| D16 | Parameter history endpoint — GitLab commit log scoped per key_path, 5-min Postgres cache |
