# Project Constitution — NMS+ Config MVP

## The Iron Rules (Never Violate)
1. The browser NEVER calls downstream APIs (GitLab, PuppetDB, Puppet Server, Keycloak, Postgres). ALL calls go through /api/* on the BFF.
2. The BFF validates a Keycloak JWT on EVERY endpoint. No exceptions.
3. Single-tenant MVP: every BFF endpoint extracts the authenticated user via `get_current_user` (sub + roles from the Keycloak JWT). customer_id scoping is NOT applied in MVP — it will be re-introduced when the app becomes multi-tenant. Role-based authorisation on writes is still mandatory.
4. TypeScript strict mode throughout. No `any`. No type assertions without type guards.
5. Python async/await throughout. No blocking I/O in FastAPI routes.
6. CSS Modules + CSS custom properties (--navy, --blue, --purple, --sec, status colours) only. No inline styles. No Tailwind.
7. Recharts for ALL charts. No other charting libraries. react-leaflet is out of scope for Config MVP (no map surface).
8. All secrets via Docker Compose `env_file` directives pointing at host files under `/etc/nmsplus/secrets/*.env` (mode 0600, owned by the service user). Never hardcoded in source. Never committed to Git. Never baked into Docker images (no secret `ARG`/`ENV` in Dockerfile). Never passed as literal `environment:` values in `docker-compose.yml` — always via `env_file`.
9. httpx for all downstream HTTP calls in the BFF. Never requests. Never aiohttp.
10. Pydantic v2 for ALL BFF request/response models.
11. Every hieradata write MUST use ruamel.yaml in round-trip mode. Never `yaml.safe_dump` — it destroys comments, anchors, and key order.
12. Every call to Puppet Server `/run-force` MUST go through the shared D13 safety envelope helper (`bff.puppet_server_client.force_run`). Never construct the httpx call inline.
13. Every write endpoint (POST/PUT/PATCH/DELETE) MUST use the Idempotency-Key middleware. Missing header → 400.

## Four Universal Principles (Karpathy)

These four principles are constitutional. They sit alongside the Iron Rules and apply to every agent, every story, every PR. Derived from Andrej Karpathy's observations on where LLM coding agents go wrong: they make silent assumptions, they overcomplicate, they touch code they weren't asked to touch, and they fail to convert tasks into verifiable goals.

Reference: https://github.com/forrestchang/andrej-karpathy-skills

Tradeoff: these principles bias toward caution over speed. For trivial changes (typo fixes, one-line comment updates), apply them with judgment. For anything touching an Iron Rule or a D-decision, apply them in full.

### Principle 1 — Think Before Coding
**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before any code, ADR, story, or test:
- State your assumptions explicitly. If uncertain, ask — do not guess.
- If multiple interpretations exist, present them. Do not pick silently.
- If a simpler approach exists than the one requested, say so. Push back when warranted.
- If something is unclear, stop. Name what is confusing. Ask.

This is operationalised as the **Pre-Flight block** that every implementation and review agent must output before producing work. See individual agent files.

### Principle 2 — Simplicity First
**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you wrote 200 lines and 50 would do, rewrite it.
- If you wrote a factory/strategy/builder pattern for two call-sites, rewrite it as two functions.

The senior-engineer test: would a principal engineer say this is overcomplicated? If yes, simplify before shipping. `code-reviewer` applies this test on every PR.

Special-case for NMS+ Config: D8 (single-pod BFF) is the canonical Simplicity First constraint at the infra layer — do not add HPA, leader election, or multi-region "for future-proofing".

### Principle 3 — Surgical Changes
**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it in the PR description — don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Do NOT remove pre-existing dead code unless the story explicitly asks.

**The test:** every changed line must trace directly to the user's request or story acceptance criterion. `code-reviewer` enforces this.

Special-case for NMS+ Config: never "clean up" a hieradata file beyond the declared key_paths — the `byte_diff_drift` D14 gate will block it server-side, and any diff that touches unrelated YAML is a code-review block.

### Principle 4 — Goal-Driven Execution
**Define success criteria. Loop until verified.**

Transform imperative tasks into verifiable goals:

| Instead of...          | Transform to...                                               |
|------------------------|---------------------------------------------------------------|
| "Add validation"       | "Write tests for invalid inputs, then make them pass"         |
| "Fix the bug"          | "Write a test that reproduces it, then make it pass"          |
| "Refactor X"           | "Ensure tests pass before and after"                          |
| "Wire the envelope"    | "Write a test that rejects master/ODEG; make the envelope pass it" |
| "Add the history view" | "Write an E2E that drills into a key_path's commit log; make it green" |

For multi-step tasks, state a plan with verification checkpoints:

```
1. [Step] → verify: [command or observable check]
2. [Step] → verify: [command or observable check]
3. [Step] → verify: [command or observable check]
```

Strong success criteria let the agent loop independently. Weak criteria ("make it work") require constant clarification and produce drift. The `scrum-master` enforces this in story templates: every Acceptance Criterion must be a Given/When/Then, not a verb.

### Principle 5 — Parallelize When Independent
**Run independent work concurrently. Never serialize what has no ordering dependency.**

This is an NMS+ Config operational extension to the four Karpathy principles — it governs *execution efficiency* rather than correctness, but it is treated as constitutional because sequential-by-default behaviour is one of the largest sources of wall-clock waste in an agentic SDLC.

Apply it at three scopes:

**1. Within a single agent — parallel tool calls.**
When an agent needs multiple reads, searches, or greps that don't depend on each other's output, it MUST issue them in a single tool-call batch rather than one per turn. Examples:
- Reading docs/PRD.md + docs/ARCHITECTURE.md + docs/HANDOFF.md at stage entry → one batched Read.
- Grep for `customer_id` + `get_current_customer` + `class Customer` to enforce single-tenant → one batched Grep run (or one Grep with an alternation pattern).
- Validating Compose + nginx + systemd files in devops → `docker compose config`, `nginx -t`, `systemd-analyze verify` dispatched concurrently.

**2. Within an orchestrating step — parallel sub-agent invocations.**
When the work fans out across independent lanes, the orchestrator MUST invoke the sub-agents in parallel. The factory already does this in two places; extend the pattern wherever independent lanes exist:
- `/build` invokes `frontend-dev` and `bff-dev` in parallel on the same story.
- `/review-pr` invokes `code-reviewer` and `security-sentinel` in parallel on the same MR.
- When multiple READY stories exist with no cross-dependency, `/sprint-story` may invoke multiple implementation pairs in parallel (one pair per story) — but only after the scrum-master confirms independence.
- When a test suite partitions cleanly (unit / integration-vs-fixtures / security / D14 gate / D13 envelope / E2E), `tester` runs the partitions concurrently and aggregates results.

**3. Across the PR lifecycle — parallel independent validations.**
- CI runs lint + typecheck + unit tests + integration-vs-fixtures + security tests + D14 gate tests + D13 envelope tests as parallel CI stages, not serial. The only enforced ordering is: build image → parallel test fan-out → aggregate → (manual) E2E → (manual) deploy.

**When NOT to parallelize (hard exceptions):**
- Ordered stages that share human gates — PRD → ARCHITECTURE → STORY → BUILD are sequential by constitutional design (each stage has a human APPROVED gate).
- Destructive or stateful operations that contend on the same resource — no parallel `docker compose up -d`, no parallel `alembic upgrade head`, no parallel writes to the same hieradata branch, no parallel force-run against the same certname.
- Debugger-driven hypothesis testing — each hypothesis must be tested serially so the result is attributable.
- When parallel execution would exceed host CPU/memory and slow the whole pipeline (single-VM deploy context).

**The test:** before dispatching N tool calls or sub-agent invocations sequentially, ask "is there a data dependency between them, a shared mutable resource, or a human gate?" If no to all three, batch them. `code-reviewer` flags obvious serial-where-parallel-was-free cases, and `scrum-master` encourages parallel agent-team framing in story files when lanes are independent.

### How These Principles Are Enforced

| Principle                        | Enforced by                                                                         |
|----------------------------------|-------------------------------------------------------------------------------------|
| Think Before Coding              | Pre-Flight block on every agent; `/think` slash command; `requirements-analyst` 6-question interview with explicit assumptions |
| Simplicity First                 | `code-reviewer` senior-engineer test; `/simplify` slash command; 500-line file cap; D8 single-container constraint |
| Surgical Changes                 | `code-reviewer` "every line traces to request" check; `byte_diff_drift` D14 gate on hieradata |
| Goal-Driven Execution            | `scrum-master` story template (Given/When/Then Acceptance Criteria); Definition of Done with concrete test commands |
| Parallelize When Independent     | `/build` and `/review-pr` invoke agent pairs concurrently; `tester` runs test partitions concurrently; CI stages fan out in parallel after image build; `code-reviewer` flags serial-where-parallel-was-free |

### What Agents Must NEVER Do (Karpathy Extensions + NMS+ Additions)

- Silently choose between two interpretations of ambiguous input.
- Add speculative abstractions "in case we need them later".
- Modify code, comments, or formatting adjacent to a targeted change.
- Delete pre-existing dead code that their task did not create.
- Declare a story DONE without the Acceptance Criteria being executed as tests.
- Proceed past a Pre-Flight block that contains an unanswered open question.
- Serialize work that has no ordering dependency — batch independent tool calls, invoke independent sub-agents in parallel, fan out independent test partitions. Violating this does not break correctness but wastes wall-clock time and is a `code-reviewer` observation.

## Stack
- Frontend: React 18 + TypeScript (strict) + Vite + React Router v6 + Zustand + Recharts + CSS Modules + keycloak-js
- BFF: Python FastAPI + httpx + python-jose (JWT) + Pydantic v2 + python-gitlab + ruamel.yaml
- Data: PostgreSQL 16 — single container on the Linux host, single primary, named volume for `/var/lib/postgresql/data`, nightly `pg_dump` backup to `/var/backups/nmsplus/pg/`. No operator, no replicas, no failover cluster. Brief outage on host reboot is acceptable (D8).
- Infra: GitLab monorepo; **single Linux VM in our DC**; Docker Engine + Docker Compose orchestrate four services — nginx (reverse proxy + static frontend), bff, postgres, keycloak. nginx terminates TLS and routes `/api/*` to the BFF and `/` to the built frontend bundle. No Kubernetes, no ingress controller, no service mesh.

## Module Routes (React Router v6)
- /            → Overview (KPIs, recent MRs, recent Puppet activity)
- /compliance  → Compliance table (drift from PuppetDB)
- /audit       → Audit log (GitLab history + UI events)
- /policies    → Policy Tree (hieradata editor — stages edits, Apply All creates MR)
- /policies/history?key_path=... → Parameter history drill-in (D16)
- /deployments → Deployment status (merged MRs + PuppetDB post-merge runs)

## BFF Downstream Services
- **GitLab API**: hieradata read/write, branch creation, MR creation, MR status. Primary downstream. Writes target `devel` or `staging` only; never `master`.
- **PuppetDB**: per-device Puppet run status, facts, drift reports. Read-only token. Never blocks the write path; p95 tolerance is 5 minutes (§4 SLO).
- **Puppet Server API**: force Puppet run. Called only through the D13 safety envelope (target_branch ∈ {devel, staging} AND certname ∈ bench allowlist AND role = config-engineer). Write-capable token, stored in a separate host-side env file (`/etc/nmsplus/secrets/puppet-server.env`) from PuppetDB's read token.
- **Keycloak**: JWT validation (OIDC). JWKS cached hourly.
- **Postgres**: BFF-owned state — draft change sets (D12), audit events, parameter history cache (D16), idempotency keys (D4), user preferences, environment configs.

> Not in Config MVP (previously in NMS+ suite — do not re-add): NMS API, Zabbix, SIEMonster, ServiceNow, BigQuery, ThoughtSpot, Asset DB.

## Locked Decisions (D1–D16 from System Design Brief §5)
D1–D16 are architecturally locked. Do not relitigate. New ADRs start at ADR-017. When a story touches any D-decision, the story file must name it explicitly so downstream agents can verify conformance.

| ID | Summary |
|---|---|
| D1 | React 18 SPA + FastAPI BFF — browser never calls downstreams |
| D2 | Keycloak JWT (RS256) + keycloak-js silent refresh 60s before expiry |
| D3 | Single-tenant MVP — Iron Rule 3 overridden; `get_current_user` |
| D4 | GitLab as hieradata source of truth; Idempotency-Key header on writes, 24h TTL |
| D5 | ruamel.yaml round-trip for hieradata writes |
| D6 | python-gitlab for all GitLab operations |
| D7 | Server-side three-way merge on stale-branch conflict |
| D8 | Single BFF container on one Linux VM — no second instance, no autoscaling, no HA pair; `restart: unless-stopped` in Compose |
| D9 | httpx for all outbound HTTP, no requests/aiohttp |
| D10 | hiera.yaml parsed at load time — per-env dynamic layering (3/4/9 layers). **Blocked on week-1 spike:** architect must verify the `hiera_file` plugin contains no conditional logic (no per-fact branches, no environment-aware routing) before any D10 implementation story is scoped. If the plugin is dynamic, D10's static reconstruction will diverge from Puppet's runtime resolution — escalate for ADR rather than proceeding. |
| D11 | Puppet Server /run-force is the only catalog-apply trigger MVP supports |
| D12 | Postgres-persisted draft change sets; key-path conflict detection |
| D13 | Force-run safety envelope: three pre-flight checks + abort-on-drift |
| D14 | Server-side validation gates (5 of them) — no client-side pre-commit |
| D15 | Per-env target branch config; hardcoded refuse for master/ODEG |
| D16 | Parameter history endpoint — GitLab commit log scoped per key_path, 5-min Postgres cache |

## No Horizontal Scaling (D8)
The BFF runs as **one Docker Compose service with a single container** — `deploy: replicas: 1` in swarm mode or simply no `scale` flag in plain Compose. Never launch a second BFF container alongside it. Do not add a load-balanced BFF pair. Do not add leader election. Drafts, history cache, and idempotency keys are stored in Postgres; a second BFF instance would fragment state and break UX. When asked to "add autoscaling" or "run a second BFF behind a load balancer", refuse and reference D8.

Always set `restart: unless-stopped` on the BFF service and ensure the host's `docker.service` is enabled on boot (`systemctl enable docker`). Routine host reboots produce a brief editor outage (<60s); document it in the service status page. There is no PDB, no node-drain protection, and no HA — this is an intentional simplicity tradeoff locked by D8.

## Domain Glossary (read before writing code or prose)
The word "environment" is overloaded in this domain; two distinct concepts share it. Use the canonical terms below in all code, story files, commit messages, and agent output.

| Term | Canonical meaning | Do not confuse with |
|---|---|---|
| **Fleet** | An NMS+ scope unit — one of `alpin`, `dostoneu`, `dani`. One GitLab project, one hieradata repo, one layer-count (3/4/9). This is the user-visible unit. | Puppet environment. |
| **Puppet environment** (always qualified) | An r10k branch deployment target — one of `devel`, `staging`. D15 constrains which branches are writable. | Fleet. Never write "environment" bare; always "Puppet environment" or "fleet". |
| **env project** | Legacy synonym for fleet's GitLab project (path `env/environment-<fleet>`). Accept on read; emit "fleet" on write. | — |
| **certname** | A Puppet agent node identifier. A certname belongs to exactly one fleet and reports under one Puppet environment at a time. | Hostname (may differ). |
| **Layer** | A hiera.yaml hierarchy level. Fleets have 3, 4, or 9 layers. D10 reconstructs these statically. | D-decision (unrelated numbering). |
| **D-decision** | An architecturally locked decision from System Design Brief §5 (D1–D16). New ADRs start at ADR-017. | ADR (ADRs are the format; D-decisions are the locked subset). |
| **Iron Rule** | A never-violated behavioural constraint (see CLAUDE.md). | D-decision (D-decisions are architectural; Iron Rules are behavioural). |
| **Canonical JSON** | RFC 8785 JCS. Used for idempotency fingerprinting. | `json.dumps(sort_keys=True)` — insufficient. |
| **Write-path SLO** | ≥99% rolling 7-day MR creation success. Governs write endpoints. | Read-path SLO. |
| **Read-path SLO** | p95 <500ms excluding PuppetDB. Governs read endpoints. | PuppetDB staleness SLO. |
| **PuppetDB staleness** | <5min tolerance; read path must degrade gracefully when exceeded. | Read-path latency (separate SLO). |

When in doubt, write "fleet" for the NMS+ unit and "Puppet environment" (two words, qualified) for the r10k unit. A bare "environment" in new content is a review blocker.

## Naming Conventions
- React components: PascalCase (e.g. PolicyTree.tsx)
- Custom hooks: camelCase prefixed "use" (e.g. usePolicyDraft.ts)
- CSS Module files: match component name (e.g. PolicyTree.module.css)
- Python modules: snake_case (e.g. policies_router.py)
- Pydantic models: PascalCase (e.g. DraftChangeSet)
- API routes: /api/[module]/[resource] in kebab-case
- Branch names: `config/<issue-id>-<slug>` (created from target branch — devel or staging)

## File Locations
- frontend/                React 18 application
- bff/                     FastAPI BFF application
- bff/routers/             One router per module (policies, deployments, compliance, audit, health)
- bff/clients/             Downstream clients: gitlab_client.py, puppetdb_client.py, puppet_server_client.py, keycloak_jwks.py
- bff/middleware/          idempotency.py, rate_limit.py
- bff/validation/          D14 gates: yaml_parse.py, yamllint.py, key_shape.py, byte_diff_drift.py, secret_scan.py
- bff/envelopes/           safety_envelope.py (D13 shared helper)
- bff/history/             parameter_history.py (D16)
- deploy/                  Docker Compose files, nginx config, systemd unit, backup cron, upgrade runbooks
- e2e/                     Playwright E2E test specs
- tests/fixtures/alpin/    Captured hieradata fixtures (3-layer fleet). Note: fixtures use the short fleet name (`alpin`); the GitLab project path is `env/environment-alpin`. These are different namespaces — do not conflate.
- tests/fixtures/dostoneu/ Captured hieradata fixtures (4-layer fleet). GitLab project: `env/environment-dostoneu`.
- tests/fixtures/dani/     Captured hieradata fixtures (9-layer fleet, includes hiera_mysql). GitLab project: `env/environment-dani`.
- scripts/refresh_fixture.py   Explicit-PR refresh with secret scrubbing
- scripts/validate_local.py    Local D14 gate simulation (/validate)
- scripts/run_puppet_local.py  Local D13 envelope simulation (/run-puppet, dev-only)
- docs/                    PRD, architecture, API contracts, stories
- docs/stories/            One .md file per story/feature unit
- docs/runbooks/           Operator runbooks (token rotation, etc.)
- wireframes/              HTML prototypes from architect agent

## What Agents Must NEVER Do
- Call downstream APIs from the frontend
- Skip JWT validation on any BFF endpoint
- Store secrets or credentials in source code
- Store sensitive data in localStorage or sessionStorage (draft change sets may be stored there — no PII, no tokens)
- Use hardcoded hex colours (use CSS custom properties)
- Use inline styles
- Break existing BFF API contracts without updating docs/API_CONTRACTS.md first
- Write migration scripts or run `docker compose up -d` / `docker compose pull` / image promotion against prod without human review
- Mark a story DONE unless ALL Definition of Done criteria are checked
- Add a second BFF container, a load-balanced BFF pair, any autoscaling, or leader-election logic (D8)
- Call Puppet Server /run-force without the D13 envelope helper
- Write hieradata YAML via `yaml.safe_dump` (destroys round-trip fidelity — use ruamel)
- Re-introduce `customer_id` scoping "for future multi-tenancy" — that is a phase-3 ADR, not a current concern
- Make real GitLab/PuppetDB/Puppet Server calls from a test (use fixtures)

## Code Standards
- No file may exceed 500 lines. Split into focused modules before hitting the limit.
- Module organisation: one responsibility per file. Router files contain routes only. Model files contain schemas only. No mixed concerns.
- No TODO or FIXME in production code. Raise a story instead.

## Enterprise Standards

### Test Coverage
Every story must meet these minimums before marking DONE:
- BFF unit tests: ≥90% line coverage on new business logic (`pytest --cov`)
- Frontend unit tests: every component, hook, and store action covered
- Integration tests: every downstream service call tested against fixtures (never real services)
- Security tests (mandatory on every BFF endpoint):
  - Unauthenticated request → 401
  - Valid JWT, viewer role, write endpoint → 403
  - Valid JWT, admin-only endpoint with editor role → 403
  - Malformed/expired JWT → 401
  - Missing Idempotency-Key on write → 400
  - Replayed Idempotency-Key (same fingerprint) → original cached response
  - Replayed Idempotency-Key (different fingerprint) → 409
  - Any write endpoint rejects oversized or malformed payload with 422
- D14 validation gate tests (on every hieradata write endpoint):
  - Malformed YAML → 422 with `yaml_parse_failed`
  - yamllint failure → 422 with `yamllint_failed`
  - Key shape mismatch vs known_keys → 422 with `key_shape_mismatch`
  - Unexpected byte-level drift → 422 with `byte_diff_drift`
  - Secret-like value → 422 with `secret_leak_blocked`
- E2E tests: happy path + at least one auth failure + one validation-gate failure per feature

### Security Depth
Beyond the Iron Rules, every implementation must:
- Log all auth failures with enough context for incident investigation (no PII in logs, no tokens, no hieradata values)
- Return identical error shapes for 401 and 403 — never reveal whether a resource exists to an unauthorised caller
- Validate and sanitise all downstream API responses before passing to frontend — never proxy raw responses
- Rate-limit all write endpoints at the BFF
- The node_target parameter passed to Puppet Server /run-force must match `^[a-z0-9][a-z0-9-]*(\.[a-z0-9-]+)*$`; reject anything else with 400
- Never log or echo the GitLab service token or Puppet Server token
- D14 secret_leak gate must run against every committed file diff, not just "obviously suspicious" keys

### Performance SLOs (§4)
- Write-path success rate: ≥99% rolling 7-day (MR creation end-to-end)
- Read-path p95 latency: < 500ms (excluding PuppetDB queries)
- PuppetDB staleness tolerance: < 5 minutes (read path must degrade gracefully when exceeded)
- Every new endpoint added by bff-dev must specify which SLO it's governed by (or explicitly mark `SLO: none` with a reason)

#### SLO → endpoint mapping (decision matrix)
Use this table to pick the correct SLO for a new endpoint. When an endpoint spans categories (e.g. a write that fans out to PuppetDB), pick the **strictest applicable SLO** and list the others in the story file as secondary observations.

| Endpoint category | Examples | Governing SLO |
|---|---|---|
| Hieradata writes (create MR, apply diff, draft commit) | `POST /api/policies/commit`, `POST /api/policies/draft` | **write-path ≥99%** |
| Force-run trigger (D11/D13) | `POST /api/deployments/run-force` | **write-path ≥99%** (primary); PuppetDB staleness observed but not gating |
| Synchronous reads not touching PuppetDB | `GET /api/policies/*`, `GET /api/policies/history`, `GET /api/audit`, `GET /api/compliance/*` (static) | **read-path p95 <500ms** |
| Reads that query PuppetDB | `GET /api/compliance/drift`, fleet status views | **read-path p95 <500ms** AND **PuppetDB staleness <5min** (degrade gracefully when exceeded) |
| Health / infrastructure | `/healthz`, `/readyz` | **SLO: none** (reason: infra probes, not user-facing) |
| Admin-only utilities | token rotation, cache purge | **SLO: none** (reason: operator tools) |

If an endpoint truly fits none of the above, declare `SLO: none` in the story and state the reason explicitly — do not leave it implicit.

## Health Probes (§8)
- `/healthz` — liveness. Returns 200 if the process is up. No downstream checks. Unauthenticated. Rate-limited.
- `/readyz` — readiness. Checks Postgres connectivity, Keycloak JWKS reachability, GitLab API base reachability. Does NOT block on PuppetDB (that is a soft dependency with staleness tolerance). Unauthenticated. Rate-limited.
- Docker Compose `healthcheck:` block on the BFF service hits `/healthz` every 10s (3 retries, 5s timeout). nginx upstream pool checks `/readyz` before marking the BFF pool healthy; Compose's `depends_on: { bff: { condition: service_healthy } }` is what gates the nginx service boot. No Kubernetes probes (there is no Kubernetes).

## Token Efficiency Conventions

### docs/HANDOFF.md
Written by each agent at stage completion. The next agent reads this first instead of re-reading all upstream docs. Only record what isn't already in the story file or CLAUDE.md: scope constraints, decisions made, D-decisions touched, and open blockers. Append to the Handoff Log — never overwrite prior entries.

### .claude/helpers.md
Human reference doc containing canonical code patterns (JWT auth, four downstream client patterns, CSS variables, data-fetching hook, idempotency middleware, D13 envelope, D14 gates). For human developers and code review only — agents do not read this file; patterns are inlined directly in agent files.

### Self-contained story files
Story files in docs/stories/ must be fully self-contained. The scrum-master inlines all required context so that frontend-dev and bff-dev only need to read one file per implementation task. Stories must never say "see PRD" or "see ARCHITECTURE".

## Human Gates (mandatory — never auto-proceed past these)
1. docs/PRD.md must have Status: APPROVED before architecture begins
2. docs/ARCHITECTURE.md must have Status: APPROVED before story files are written
3. Security Sentinel must output APPROVED before a PR is raised
4. Production deployments are always a manual job in GitLab CI — never automated
5. Test fixture refresh requires an explicit PR authored by a named operator; the refresh script must not be run in CI

## Definition of Done (all must be true before marking a story DONE)
- [ ] TypeScript compiles with zero errors (`npx tsc --noEmit`)
- [ ] Python mypy passes with zero errors
- [ ] All security tests pass — 401/403/role/malformed-input/idempotency per endpoint
- [ ] All D14 validation gate tests pass for hieradata write endpoints
- [ ] BFF coverage ≥90% (`pytest --cov --cov-fail-under=90`)
- [ ] All frontend unit and integration tests green
- [ ] All Playwright E2E tests green (happy path + error path + auth path + validation-gate path)
- [ ] QA score >= 85/100
- [ ] Code Reviewer agent approved (no Critical issues)
- [ ] Security Sentinel agent approved (no Critical issues)
- [ ] docs/API_CONTRACTS.md updated if any endpoints changed
- [ ] Story file Status set to DONE
- [ ] If the story touches /run-force authentication, docs/runbooks/token_rotation.md is updated in the same PR
