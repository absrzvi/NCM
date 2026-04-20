# Story Index — NMS+ Config MVP

This index lists all 40 stories for NMS+ Config MVP, organized by dependency tier and module.

## Week-1 Spikes (Tier 0 — prerequisite investigations)
- **SPIKE-01**: hiera_file plugin inventory → blocks D10 stories
- **SPIKE-02**: ruamel.yaml round-trip fidelity → blocks D5, D14 byte-diff gate
- **SPIKE-03**: hiera_mysql opaque rendering validation → phase-2 gate (non-blocking for MVP)
- **SPIKE-04**: test fixture capture → blocks all integration tests

## Foundation (Tier 1 — no dependencies)
- **STORY-01**: Health probes (/healthz, /readyz) → D-decisions: none
- **STORY-02**: JWT middleware + get_current_user → D-decisions: D2, D3
- **STORY-03**: Idempotency middleware → D-decisions: D4
- **STORY-04**: Database schema + Alembic migrations → D-decisions: D8, D12, D4, D16
- **STORY-05**: Downstream client wrappers (gitlab, puppetdb, puppet_server, keycloak_jwks) → D-decisions: D6, D9, D1
- **STORY-06**: Environment config loader → D-decisions: D15, D13

## Validation Gates (Tier 2 — depends on Tier 1; D14 mandate)
- **STORY-07**: yaml_parse gate → depends: SPIKE-04 (for test fixtures)
- **STORY-08**: yamllint gate → depends: SPIKE-04
- **STORY-09**: key_shape gate → depends: STORY-06 (environment config)
- **STORY-10**: byte_diff_drift gate → depends: SPIKE-02 (ruamel tolerance), SPIKE-04
- **STORY-11**: secret_scan gate → depends: SPIKE-04

## D13 Safety Envelope (Tier 2 — depends on Tier 1)
- **STORY-12**: Force-run safety envelope → depends: STORY-05 (puppet_server_client), STORY-06 (bench allowlists)

## Policies Module (Tier 3 — depends on Tier 1, Tier 2)
- **STORY-13**: GET /api/policies/tree (D10 hiera.yaml parsing) → depends: SPIKE-01 (hiera_file inventory), STORY-05 (gitlab_client)
- **STORY-14**: Draft lifecycle endpoints (POST/PUT/DELETE /api/policies/drafts, D12) → depends: STORY-04 (draft_change_sets table), STORY-03 (idempotency)
- **STORY-15**: Apply All endpoint (POST /api/policies/drafts/{id}/apply, D5/D7/D14/D15) → depends: SPIKE-02 (ruamel), STORY-07–STORY-11 (all D14 gates), STORY-14 (drafts), STORY-05 (gitlab_client)
- **STORY-16**: Parameter history endpoint (GET /api/policies/history, D16) → depends: STORY-05 (gitlab_client), STORY-04 (parameter_history_cache)
- **STORY-17**: Conflict detection (D7) → depends: STORY-14 (drafts), STORY-05 (gitlab_client)

## Deployments Module (Tier 3 — depends on Tier 1, Tier 2)
- **STORY-18**: GET /api/deployments/status → depends: STORY-05 (gitlab_client, puppetdb_client)
- **STORY-19**: GET /api/deployments/recent-runs → depends: STORY-05 (puppetdb_client)
- **STORY-20**: POST /api/deployments/puppet-runs (D11/D13) → depends: STORY-12 (D13 envelope), STORY-03 (idempotency)

## Compliance Module (Tier 3 — depends on Tier 1)
- **STORY-21**: GET /api/compliance/drift → depends: STORY-05 (puppetdb_client)
- **STORY-22**: GET /api/compliance/summary → depends: STORY-05 (puppetdb_client)

## Audit Module (Tier 3 — depends on Tier 1)
- **STORY-23**: GET /api/audit/events → depends: STORY-04 (audit_events table), STORY-05 (gitlab_client)
- **STORY-24**: GET /api/audit/recent-mrs → depends: STORY-05 (gitlab_client)

## Frontend Core (Tier 4 — depends on BFF Tier 1)
- **STORY-25**: Auth wrapper + keycloak-js integration → depends: STORY-02 (JWT middleware live)
- **STORY-26**: Zustand stores + data-fetching hooks → depends: STORY-25 (auth wrapper)
- **STORY-27**: CSS foundation + design tokens → no dependencies (can run in parallel with Tier 1)

## Frontend Views (Tier 5 — depends on Tier 4 + corresponding BFF module)
- **STORY-28**: Overview page (/) → depends: STORY-26 (stores), STORY-22 (compliance summary), STORY-19 (recent runs), STORY-24 (recent MRs)
- **STORY-29**: Compliance page (/compliance) → depends: STORY-26 (stores), STORY-21 (compliance drift)
- **STORY-30**: Audit page (/audit) → depends: STORY-26 (stores), STORY-23 (audit events)
- **STORY-31**: PolicyTree page (/policies — editor UI) → depends: STORY-26 (stores), STORY-13 (policies tree), STORY-14 (drafts), STORY-15 (apply all)
- **STORY-32**: Deployments page (/deployments — force-run UI) → depends: STORY-26 (stores), STORY-18 (deployment status), STORY-20 (puppet-runs)
- **STORY-33**: HistoryPanel component (/policies/history) → depends: STORY-26 (stores), STORY-16 (parameter history)

## Integration & E2E (Tier 6 — depends on all prior tiers)
- **STORY-34**: BFF integration tests vs fixtures → depends: SPIKE-04 (fixtures), all BFF module stories (STORY-13–STORY-24)
- **STORY-35**: Frontend integration tests → depends: all frontend stories (STORY-25–STORY-33)
- **STORY-36**: E2E Playwright test suite → depends: STORY-34, STORY-35 (all integration tests green)

---

## Dependency Graph (Visual)

```
Tier 0 (Spikes)
├─ SPIKE-01 (hiera_file) ──────────────┐
├─ SPIKE-02 (ruamel) ──────────────┐   │
├─ SPIKE-03 (hiera_mysql) [phase-2]│   │
└─ SPIKE-04 (fixtures) ────────────┼───┼──────────────────────┐
                                   │   │                      │
Tier 1 (Foundation)                │   │                      │
├─ STORY-01 (health)               │   │                      │
├─ STORY-02 (JWT)                  │   │                      │
├─ STORY-03 (idempotency)          │   │                      │
├─ STORY-04 (DB schema)            │   │                      │
├─ STORY-05 (clients) ─────────────┼───┼──────────┐           │
└─ STORY-06 (env config) ──────────┼───┼──┐       │           │
                                   │   │  │       │           │
Tier 2 (Gates + Envelope)          │   │  │       │           │
├─ STORY-07 (yaml_parse) ──────────┼───┼──┼───────┼───────────┤
├─ STORY-08 (yamllint) ────────────┼───┼──┼───────┼───────────┤
├─ STORY-09 (key_shape) ───────────┼───┼──┤       │           │
├─ STORY-10 (byte_diff) ───────────┴───┤  │       │           │
├─ STORY-11 (secret_scan) ─────────────┼──┼───────┼───────────┤
└─ STORY-12 (D13 envelope) ────────────┼──┴───────┤           │
                                       │          │           │
Tier 3 (BFF Modules)                   │          │           │
Policies:                              │          │           │
├─ STORY-13 (GET tree) ────────────────┴──────────┤           │
├─ STORY-14 (drafts) ──────────────────────────────┤           │
├─ STORY-15 (apply all) [gates dep] ──────────────┤           │
├─ STORY-16 (history) ─────────────────────────────┤           │
└─ STORY-17 (conflict) ────────────────────────────┤           │
Deployments:                                       │           │
├─ STORY-18 (status) ──────────────────────────────┤           │
├─ STORY-19 (recent runs) ─────────────────────────┤           │
└─ STORY-20 (puppet-runs) ─────────────────────────┤           │
Compliance:                                        │           │
├─ STORY-21 (drift) ───────────────────────────────┤           │
└─ STORY-22 (summary) ─────────────────────────────┤           │
Audit:                                             │           │
├─ STORY-23 (events) ──────────────────────────────┤           │
└─ STORY-24 (recent MRs) ──────────────────────────┤           │
                                                   │           │
Tier 4 (Frontend Core)                             │           │
├─ STORY-25 (auth wrapper) ────────────────────────┤           │
├─ STORY-26 (stores + hooks) ──────────────────────┤           │
└─ STORY-27 (CSS) [parallel] ──────────────────────┤           │
                                                   │           │
Tier 5 (Frontend Views)                            │           │
├─ STORY-28 (Overview) ────────────────────────────┤           │
├─ STORY-29 (Compliance) ──────────────────────────┤           │
├─ STORY-30 (Audit) ───────────────────────────────┤           │
├─ STORY-31 (PolicyTree) ──────────────────────────┤           │
├─ STORY-32 (Deployments) ─────────────────────────┤           │
└─ STORY-33 (HistoryPanel) ────────────────────────┤           │
                                                   │           │
Tier 6 (Integration & E2E)                         │           │
├─ STORY-34 (BFF integration) ─────────────────────┴───────────┤
├─ STORY-35 (Frontend integration) ────────────────────────────┤
└─ STORY-36 (E2E Playwright) ──────────────────────────────────┘
```

---

## Stories Blocked by Spike Verdicts

| Spike | Blocks Stories | Unblock Condition |
|-------|----------------|-------------------|
| SPIKE-01 (hiera_file) | STORY-13, STORY-31, STORY-16 | Pass verdict: `plugin_is_static: true` and inventory files committed |
| SPIKE-02 (ruamel) | STORY-15, STORY-10 | Pass verdict: `unexpected_diffs: []` and tolerance file committed |
| SPIKE-03 (hiera_mysql) | None (phase-2 only) | PE approval captured; dani not in MVP |
| SPIKE-04 (fixtures) | STORY-07, STORY-08, STORY-10, STORY-11, STORY-34 (all integration tests) | Fixtures committed in operator-authored PR |

---

## Parallel Execution Opportunities (Principle 5)

The following stories have no dependencies on each other and can be implemented in parallel:

**Tier 1 (all 6 stories can run in parallel after DB is up):**
- STORY-01, STORY-02, STORY-03, STORY-04, STORY-05, STORY-06

**Tier 2 (all 6 stories can run in parallel after Tier 1 completes + SPIKE-02/SPIKE-04 pass):**
- STORY-07, STORY-08, STORY-09, STORY-10 (blocked by SPIKE-02), STORY-11, STORY-12

**Tier 3 modules (each module's stories can run in parallel with other modules):**
- Policies block (STORY-13–STORY-17) can run in parallel with Deployments block (STORY-18–STORY-20), Compliance block (STORY-21–STORY-22), Audit block (STORY-23–STORY-24)

**Tier 4 (STORY-27 CSS can run in parallel with STORY-25 auth wrapper; STORY-26 waits for STORY-25):**
- STORY-25 + STORY-27 in parallel → then STORY-26

**Tier 5 (all 6 view stories can run in parallel after Tier 4 + corresponding BFF module completes):**
- STORY-28, STORY-29, STORY-30, STORY-31, STORY-32, STORY-33

---

## D-Decision Coverage Matrix

| D-Decision | Touched by Stories |
|------------|-------------------|
| D1 (BFF proxies all) | STORY-05, all module stories |
| D2 (Keycloak JWT) | STORY-02 |
| D3 (single-tenant) | STORY-02, STORY-04 |
| D4 (idempotency) | STORY-03, STORY-14, STORY-15, STORY-20 |
| D5 (ruamel) | STORY-15 |
| D6 (python-gitlab) | STORY-05, STORY-13, STORY-15, STORY-16, STORY-18, STORY-23, STORY-24 |
| D7 (3-way merge) | STORY-17 |
| D8 (single container) | STORY-04, STORY-06 |
| D9 (httpx) | STORY-05, all module stories |
| D10 (hiera.yaml parsing) | STORY-13 |
| D11 (run-force only) | STORY-20 |
| D12 (draft change sets) | STORY-14, STORY-15, STORY-17 |
| D13 (safety envelope) | STORY-12, STORY-20 |
| D14 (validation gates) | STORY-07, STORY-08, STORY-09, STORY-10, STORY-11, STORY-15 |
| D15 (branch config) | STORY-06, STORY-15, STORY-20 |
| D16 (parameter history) | STORY-16 |

---

## Implementation Order Recommendation

1. **Week 1**: Run all 4 spikes in parallel; wait for pass verdicts
2. **Sprint 1** (Foundation): STORY-01 through STORY-06 (all in parallel)
3. **Sprint 2** (Gates + Envelope): STORY-07 through STORY-12 (all in parallel after SPIKE-02/SPIKE-04 pass)
4. **Sprint 3** (BFF Modules): STORY-13 through STORY-24 (4 module blocks in parallel)
5. **Sprint 4** (Frontend): STORY-25 through STORY-33 (Core → Views)
6. **Sprint 5** (Testing): STORY-34 through STORY-36 (Integration → E2E)

Total estimated sprints: 5 (assuming 2-week sprints, 6-8 story points per sprint, 2 devs per lane).
