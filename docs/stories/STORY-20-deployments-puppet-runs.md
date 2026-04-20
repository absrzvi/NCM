# STORY-20: POST /api/deployments/puppet-runs

**Status:** READY

---

## Summary

Implement the `POST /api/deployments/puppet-runs` endpoint on the BFF. This endpoint triggers a forced Puppet run for a specified certname via the D13 safety envelope (`bff/envelopes/safety_envelope.py`). It is the only catalog-apply trigger supported in MVP (D11). The endpoint:

- Requires `editor` or `admin` role (viewer role → 403).
- Requires an `Idempotency-Key` header (D4); missing header → 400.
- Validates `node_target` against the DNS-safe regex before the envelope is called.
- Delegates the actual `/run-force` HTTP call to the D13 safety envelope — never constructs an inline httpx call.
- Writes an audit event to the Postgres `audit_events` table after a successful trigger.

---

## Assumptions

1. `STORY-12` is DONE and `bff/envelopes/safety_envelope.py` exposes `async def force_run(node_target: str, puppet_environment: str, user_sub: str) -> ForceRunResult`. The envelope performs the three pre-flight checks and aborts on drift.
2. `STORY-03` is DONE and the idempotency middleware is active on all write endpoints. The middleware rejects missing `Idempotency-Key` with HTTP 400 before the route handler is called.
3. `STORY-04` is DONE and the `audit_events` table exists with columns: `id`, `event_type`, `fleet`, `certname`, `user_sub`, `created_at`, `payload` (JSONB).
4. `STORY-02` is DONE and `get_current_user` returns `{ sub: str, roles: list[str] }`.
5. Role values are the canonical Keycloak role strings: `viewer`, `editor`, `admin`. Role check is performed in the route handler before the envelope is called.
6. `node_target` must match `^[a-z0-9][a-z0-9-]*(\.[a-z0-9-]+)*$` (CLAUDE.md Security Depth). Any value failing this pattern → HTTP 400, even before role checking.
7. `puppet_environment` in the request body is the r10k target branch (`devel` or `staging`). The D13 envelope (STORY-12) enforces that only these values are accepted; `master` and `ODEG` are hard-rejected by the envelope.
8. The audit event is written only on a successful trigger (envelope returns without raising). A failed or rejected run does not write an audit event — the error is returned to the caller.
9. Idempotency fingerprint is over the canonical JSON of `{ node_target, puppet_environment }` (RFC 8785 JCS). Two requests with the same `Idempotency-Key` but different payloads → HTTP 409.

---

## Dependencies

| Dependency | Type | Unblock Condition |
|---|---|---|
| STORY-12 (D13 safety envelope) | Hard — force-run must go through the envelope | STORY-12 Status = DONE |
| STORY-03 (idempotency middleware) | Hard — `Idempotency-Key` enforcement | STORY-03 Status = DONE |
| STORY-04 (Postgres / audit_events table) | Hard — audit event write | STORY-04 Status = DONE |
| STORY-02 (JWT middleware) | Hard — role-based authorisation | STORY-02 Status = DONE |

---

## Acceptance Criteria

### AC-1: Happy path — editor triggers a force run

**Given** a valid Keycloak JWT with `editor` role  
**And** a valid `Idempotency-Key` header  
**And** request body `{ "node_target": "mynode.example.com", "puppet_environment": "devel" }`  
**And** the D13 envelope's pre-flight checks all pass  
**When** `POST /api/deployments/puppet-runs` is called  
**Then** the response is HTTP 202  
**And** the body contains `{ "status": "triggered", "node_target": "mynode.example.com", "puppet_environment": "devel", "run_id": "<uuid from envelope>" }`  
**And** an audit event is written to `audit_events` with `event_type = "force_run_triggered"`, `certname = "mynode.example.com"`, and `user_sub` from the JWT

### AC-2: Viewer role is rejected

**Given** a valid Keycloak JWT with `viewer` role only  
**And** a valid `Idempotency-Key` header  
**When** `POST /api/deployments/puppet-runs` is called  
**Then** the response is HTTP 403  
**And** no envelope call is made  
**And** no audit event is written

### AC-3: Missing Idempotency-Key header

**Given** a valid Keycloak JWT with `editor` role  
**And** no `Idempotency-Key` header  
**When** `POST /api/deployments/puppet-runs` is called  
**Then** the response is HTTP 400  
**And** the body identifies the missing header

### AC-4: Invalid node_target rejected before envelope

**Given** a valid Keycloak JWT with `editor` role  
**And** a valid `Idempotency-Key` header  
**And** request body contains `node_target` that fails the DNS-safe regex (e.g. `"../etc/passwd"`, `"MYNODE"`, `"node target"`)  
**When** `POST /api/deployments/puppet-runs` is called  
**Then** the response is HTTP 400  
**And** the body includes `{ "error_code": "invalid_node_target", "detail": "node_target must match ^[a-z0-9][a-z0-9-]*(\\.[a-z0-9-]+)*$" }`  
**And** the D13 envelope is not called

### AC-5: D13 envelope rejects the run (e.g. master branch)

**Given** a valid Keycloak JWT with `editor` role  
**And** a valid `Idempotency-Key` header  
**And** request body `{ "node_target": "mynode.example.com", "puppet_environment": "master" }`  
**When** `POST /api/deployments/puppet-runs` is called  
**Then** the D13 envelope returns an error  
**And** the BFF returns HTTP 422 with the envelope's rejection reason  
**And** no audit event is written

### AC-6: Idempotency replay returns cached response

**Given** a prior successful trigger using `Idempotency-Key: abc123`  
**When** `POST /api/deployments/puppet-runs` is called again with the same `Idempotency-Key: abc123` and identical payload  
**Then** the response is HTTP 202 with the original cached response body  
**And** the envelope is not called a second time  
**And** no duplicate audit event is written

### AC-7: Idempotency key reuse with different payload

**Given** a prior successful trigger using `Idempotency-Key: abc123`  
**When** `POST /api/deployments/puppet-runs` is called with `Idempotency-Key: abc123` but a different `node_target`  
**Then** the response is HTTP 409  
**And** the body indicates fingerprint mismatch

### AC-8: Unauthenticated request

**Given** no `Authorization` header or an expired/malformed JWT  
**When** `POST /api/deployments/puppet-runs` is called  
**Then** the response is HTTP 401  
**And** the response body shape is identical to a 403 response (no resource-existence leakage)

---

## Definition of Done

- [ ] `bff/routers/deployments.py` contains `POST /api/deployments/puppet-runs` route
- [ ] `PuppetRunRequest` Pydantic v2 model: `node_target: str`, `puppet_environment: Literal["devel", "staging"]`
- [ ] `PuppetRunResponse` Pydantic v2 model: `status: Literal["triggered"]`, `node_target: str`, `puppet_environment: str`, `run_id: str`
- [ ] `node_target` validated against `^[a-z0-9][a-z0-9-]*(\.[a-z0-9-]+)*$` before envelope call; failure → 400 with `invalid_node_target`
- [ ] Role check: `editor` or `admin` only; `viewer` → 403
- [ ] `get_current_user` injected; unauthenticated → 401
- [ ] All force-run calls go through `safety_envelope.force_run` — no inline httpx calls to Puppet Server
- [ ] Audit event written to `audit_events` on successful trigger
- [ ] Idempotency middleware active; missing header → 400
- [ ] Idempotency fingerprint is RFC 8785 JCS over `{ node_target, puppet_environment }`
- [ ] Unit tests cover: editor happy path, admin happy path, viewer rejected, missing Idempotency-Key, invalid node_target patterns, envelope rejection, idempotency replay, idempotency conflict, unauthenticated
- [ ] Integration tests mock the D13 envelope and audit write; no real Puppet Server calls
- [ ] Security tests: unauthenticated → 401, viewer role → 403, missing Idempotency-Key → 400, replayed key → 202 (cached), key + different payload → 409
- [ ] `pytest --cov --cov-fail-under=90` passes on new modules
- [ ] `mypy` passes with zero errors on new modules
- [ ] `docs/API_CONTRACTS.md` updated with this endpoint's request/response shape
- [ ] Story Status set to DONE

---

## D-Decisions Touched

| Decision | Relevance |
|---|---|
| **D11** | Puppet Server `/run-force` is the only catalog-apply trigger MVP supports; this endpoint is the sole BFF surface for it |
| **D13** | Every force-run call must go through `bff/envelopes/safety_envelope.py`; this story wires the route to the envelope |
| **D4** | Idempotency-Key header is mandatory on all write endpoints; 24h TTL on idempotency keys in Postgres |
| **D1** | Browser never calls Puppet Server directly; this BFF endpoint is the only path |

---

## SLO Assignment

**Write-path ≥99%** (rolling 7-day success rate)

Rationale: this is a write endpoint (triggers a catalog apply). The D13 envelope may add latency but must not cause spurious failures. Envelope rejections (pre-flight check failures) are not counted as write-path failures — only transport errors and BFF crashes are.

---

## File Locations

- Router: `bff/routers/deployments.py`
- Envelope (pre-existing): `bff/envelopes/safety_envelope.py`
- Idempotency middleware (pre-existing): `bff/middleware/idempotency.py`
- Unit tests: `tests/unit/routers/test_deployments_puppet_runs.py`
- Integration tests: `tests/integration/routers/test_deployments_puppet_runs_integration.py`

---

## Notes for Implementer

- Iron Rule 12: "Every call to Puppet Server `/run-force` MUST go through the shared D13 safety envelope helper (`bff.puppet_server_client.force_run`). Never construct the httpx call inline." Violating this is a code-review hard block.
- Iron Rule 13: "Every write endpoint (POST/PUT/PATCH/DELETE) MUST use the Idempotency-Key middleware. Missing header → 400." The middleware handles this before the route is called; no manual check is needed in the route handler.
- The `node_target` regex check must happen in the route handler (or a Pydantic validator) before calling the envelope — the envelope is not responsible for sanitising the input.
- Do not log the Puppet Server token or the full `node_target` value in error logs — log only the correlation ID and a truncated certname prefix (e.g. first 8 chars).
- The `puppet_environment` field in the request body uses the qualified term (not "fleet" and not "environment" bare). Code comments and variable names must use `puppet_environment` or `target_branch`.
