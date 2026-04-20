# STORY-12: D13 Force-Run Safety Envelope

**Status:** READY

---

## Summary

Implement the D13 force-run safety envelope as a shared BFF helper function. Every call to Puppet Server `/run-force` in the MVP MUST be routed through this helper — Iron Rule 12 prohibits any inline construction of the httpx call. The helper enforces four ordered pre-flight checks before dispatching the force-run, and emits an audit event on every invocation regardless of outcome (pass or fail).

This function is the single authoritative gate for all Puppet Server force-run calls. STORY-20 (`POST /api/deployments/puppet-runs`) is the only consumer in MVP scope.

---

## Assumptions

1. STORY-05 (downstream client wrappers) has shipped and `bff.clients.puppet_server_client` exposes a function that calls Puppet Server `/run-force` via httpx. STORY-12 calls that client — it does not construct httpx calls inline.
2. STORY-06 (environment config loader) has shipped and provides the bench allowlist for a given fleet. The `db` parameter carries the Postgres session from which the allowlist is loaded if it is persisted there; or the config loader is called directly. Coordinate with STORY-06 on the calling convention — the envelope receives a ready-to-use `db: AsyncSession` (SQLAlchemy).
3. The `current_user` parameter is a Pydantic model with at least `sub: str` (Keycloak subject) and `roles: list[str]`. This is the output of `get_current_user` (D2/D3, STORY-02).
4. An audit event is written to the `audit_events` Postgres table (defined in STORY-04) on every call — including pre-flight failures. The event must record: timestamp, `current_user.sub`, `node_target`, `puppet_environment`, `fleet`, outcome (`pass` or `fail`), and the failing check name on failure. It must NOT record the Puppet Server token or any secret.
5. The `puppet_environment` parameter is one of `devel` or `staging`. The word "environment" in parameter names is permitted in Python code; the Domain Glossary prohibition on bare "environment" applies to prose and user-facing strings only.
6. The certname regex referenced in CLAUDE.md Enterprise Standards (`^[a-z0-9][a-z0-9-]*(\.[a-z0-9-]+)*$`) is enforced in pre-flight check 2.

---

## Dependencies

| Dependency | Type | Unblock Condition |
|---|---|---|
| **STORY-05** (puppet_server_client) | Hard — envelope calls this client | STORY-05 shipped and `puppet_server_client.run_force` callable |
| **STORY-06** (bench allowlists / environment config) | Hard — bench allowlist required for pre-flight check 3 | STORY-06 shipped and allowlist accessible via config loader or DB |
| STORY-04 (DB schema, audit_events table) | Hard — audit event write requires table | STORY-04 shipped and `audit_events` table migrated |
| STORY-02 (JWT middleware, `get_current_user`) | Hard — `current_user` type definition | STORY-02 shipped |

---

## Acceptance Criteria

### AC-1: Pre-flight check 1 — Puppet environment must be devel or staging

**Given** `puppet_environment` is any value other than `"devel"` or `"staging"` (e.g. `"master"`, `"ODEG"`, `"production"`, any other string)  
**When** `force_run(node_target, puppet_environment, fleet, current_user, db)` is called  
**Then** the function raises `PreFlightError(check="branch_not_allowed", detail="puppet_environment '<value>' is not in {devel, staging}")` without calling Puppet Server  
**And** an audit event with outcome `"fail"` and `failing_check="branch_not_allowed"` is written to the database

### AC-2: Pre-flight check 2 — certname must match allowed format

**Given** `puppet_environment` is `"devel"` or `"staging"`  
**And** `node_target` does NOT match `^[a-z0-9][a-z0-9-]*(\.[a-z0-9-]+)*$`  
**When** `force_run(node_target, puppet_environment, fleet, current_user, db)` is called  
**Then** the function raises `PreFlightError(check="certname_invalid", detail="node_target '<value>' does not match certname pattern")`  
**And** the actual `node_target` value appears in the `detail` only if it is safe to log (it is — certnames are not secret; they are node identifiers)  
**And** an audit event with outcome `"fail"` and `failing_check="certname_invalid"` is written

### AC-3: Pre-flight check 3 — node_target must be in bench allowlist

**Given** checks 1 and 2 pass  
**And** `node_target` is NOT present in the bench allowlist for the given `fleet`  
**When** `force_run(node_target, puppet_environment, fleet, current_user, db)` is called  
**Then** the function raises `PreFlightError(check="not_in_bench_allowlist", detail="node_target '<value>' is not in bench allowlist for fleet '<fleet>'")`  
**And** an audit event with outcome `"fail"` and `failing_check="not_in_bench_allowlist"` is written

### AC-4: Pre-flight check 4 — caller must have editor or admin role

**Given** checks 1, 2, and 3 pass  
**And** `current_user.roles` does NOT contain `"editor"` or `"admin"`  
**When** `force_run(node_target, puppet_environment, fleet, current_user, db)` is called  
**Then** the function raises `PreFlightError(check="insufficient_role", detail="user does not have editor or admin role")`  
**And** the error response does NOT reveal the user's actual roles  
**And** an audit event with outcome `"fail"` and `failing_check="insufficient_role"` is written

### AC-5: All four checks pass — Puppet Server is called and audit event written

**Given** all four pre-flight checks pass  
**When** `force_run(node_target, puppet_environment, fleet, current_user, db)` is called  
**Then** `puppet_server_client.run_force(node_target, puppet_environment)` is called exactly once  
**And** an audit event with outcome `"pass"` is written to the database  
**And** the function returns the response from `puppet_server_client.run_force`

### AC-6: Audit event written on every call — including Puppet Server failures

**Given** all four pre-flight checks pass  
**And** `puppet_server_client.run_force` raises an exception (network error, 5xx from Puppet Server)  
**When** `force_run(node_target, puppet_environment, fleet, current_user, db)` handles the exception  
**Then** an audit event with outcome `"fail"` and `failing_check="puppet_server_error"` is written  
**And** the exception is re-raised (not swallowed) so the caller can return an appropriate HTTP error

### AC-7: Checks are evaluated in strict order (1 → 2 → 3 → 4)

**Given** `puppet_environment` is invalid AND `node_target` is also invalid  
**When** `force_run` is called  
**Then** the function halts at check 1 (`branch_not_allowed`) and does NOT evaluate check 2  
**And** the audit event records `failing_check="branch_not_allowed"` only

### AC-8: Puppet Server token never appears in logs or error responses

**Given** any invocation of `force_run`  
**When** the audit event is written or an exception is raised  
**Then** no log line and no exception message contains the Puppet Server API token  
(The token lives in `/etc/nmsplus/secrets/puppet-server.env` and is accessed via `puppet_server_client` — the envelope must not handle the token directly.)

---

## Definition of Done

- [ ] `bff/envelopes/safety_envelope.py` exists with public async function `force_run(node_target: str, puppet_environment: str, fleet: str, current_user: CurrentUser, db: AsyncSession) -> PuppetRunResponse`
- [ ] `PreFlightError` exception class defined (in `bff/envelopes/safety_envelope.py` or `bff/envelopes/exceptions.py`) with `check: str` and `detail: str` fields
- [ ] Four ordered pre-flight checks implemented: branch ∈ {devel,staging}, certname regex, bench allowlist, role ∈ {editor,admin}
- [ ] Audit event written on every call (pass and fail) to `audit_events` table — no secrets in event payload
- [ ] Unit tests cover all four pre-flight failure cases (one test per check), pass-through to Puppet Server client, Puppet Server error path
- [ ] Unit tests verify strict check ordering (check 1 blocks before check 2 is evaluated, etc.)
- [ ] Unit tests verify no Puppet Server call is made on any pre-flight failure
- [ ] Security tests: unauthenticated caller → JWT middleware rejects before envelope is reached (tested at router level); viewer role → `insufficient_role`; editor role → passes check 4; admin role → passes check 4
- [ ] Integration test uses `tests/fixtures/` bench allowlist data and `puppet_server_client` mock — never calls real Puppet Server
- [ ] `pytest --cov --cov-fail-under=90` passes on `bff/envelopes/safety_envelope.py`
- [ ] `mypy` passes with zero errors
- [ ] `force_run` is the only place in the codebase that calls `puppet_server_client.run_force` — grep confirms no inline httpx calls to `/run-force`
- [ ] Story Status set to DONE

---

## D-Decisions Touched

| Decision | Relevance |
|---|---|
| **D13** | This story is the direct implementation of D13: "Force-run safety envelope: three pre-flight checks + abort-on-drift". Note: the MVP scope here implements four checks (D13 specifies three in the brief but STORY-12 scope adds the bench allowlist check per STORY-06 data; reconcile with architect if count differs from D13 spec). |
| **D11** | D11 mandates that Puppet Server `/run-force` is the only catalog-apply trigger. This envelope is the single chokepoint that enforces D11 — every caller must go through `force_run`. |

---

## SLO Assignment

**Write-path ≥99%** (rolling 7-day MR creation success rate)

Rationale: force-run is a write operation against Puppet Server. Pre-flight failures are correct rejections, not write-path failures. Write-path SLO applies to legitimate calls that reach Puppet Server — those must succeed ≥99% of the time in aggregate.

Secondary observation: Puppet Server availability is not under BFF control. If Puppet Server is down, the write path will degrade below 99%. This must be observable via the `puppet_server_error` audit events and should trigger an operator alert. SLO measurement excludes Puppet Server unavailability that is external to the BFF.

---

## File Locations

- Implementation: `bff/envelopes/safety_envelope.py`
- Exception class: `bff/envelopes/safety_envelope.py` (keep co-located unless it grows — do not pre-emptively extract)
- Unit tests: `tests/unit/envelopes/test_safety_envelope.py`
- Integration tests: `tests/integration/envelopes/test_safety_envelope_integration.py`
- Audit event schema: `bff/models/audit_event.py` (defined in STORY-04)

---

## Notes for Implementer

- `force_run` is an `async` function because it awaits `puppet_server_client.run_force` (which uses httpx async) and `db` writes (SQLAlchemy async session).
- The bench allowlist is fetched from the database or the config loader per STORY-06's design. Do not hard-code allowlist entries in the envelope — that would violate Principle 3 (Surgical Changes) and make STORY-06 redundant.
- The certname regex `^[a-z0-9][a-z0-9-]*(\.[a-z0-9-]+)*$` is specified in CLAUDE.md Enterprise Standards. Compile it once at module level with `re.compile`.
- Role check: `"editor" in current_user.roles or "admin" in current_user.roles`. Do not check for `"config-engineer"` — the Domain Glossary and Iron Rule 3 define the roles as `editor` and `admin` within the NMS+ JWT; `config-engineer` is a Puppet Server concept, not a Keycloak role.
- `PreFlightError` should be caught by the router (STORY-20) and translated to HTTP 403 for role failures and HTTP 400 for all other pre-flight failures. The envelope itself raises; the router maps to HTTP status codes.
- Audit events must write even if the DB session is in a failed state from a prior operation. Use a new savepoint or a separate DB connection if the session is dirty. Coordinate with STORY-04 on the audit event insert pattern.
- Iron Rule 12: "Every call to Puppet Server /run-force MUST go through the shared D13 safety envelope helper (`bff.puppet_server_client.force_run`)." Note — the canonical reference in CLAUDE.md says `bff.puppet_server_client.force_run` but the implementation location is `bff.envelopes.safety_envelope.force_run`. This is a documentation inconsistency. The correct module is `bff.envelopes.safety_envelope`; update CLAUDE.md Iron Rule 12 in the same PR.
