# STORY-14: Draft Lifecycle Endpoints (D12)

**Status**: READY
**Tier**: 3 — Policies Module
**Module**: `bff/routers/policies_router.py`, `bff/models/policies.py`

---

## Summary

Implement the three draft lifecycle endpoints that manage a user's staged edits to hieradata before they are applied to GitLab:

- `POST /api/policies/drafts` — create a new draft change set for a given fleet
- `PUT /api/policies/drafts/{id}` — update an existing draft with new or modified key-path edits
- `DELETE /api/policies/drafts/{id}` — discard (hard-delete) a draft

Drafts are persisted in the `draft_change_sets` Postgres table (created by STORY-04). The system enforces **one active draft per fleet per user** — attempting to create a second draft for the same (user, fleet) pair returns 409. Key-path conflict detection is enforced on `PUT`: if the incoming edit targets a key_path that conflicts with another user's active draft for the same fleet, the endpoint returns a structured 409 response listing the conflicting key_paths.

All three endpoints require the `Idempotency-Key` header (Iron Rule 13). Write endpoints are restricted to `config-engineer` role and above; viewer role → 403.

---

## Assumptions

1. STORY-04 is DONE: the `draft_change_sets` table exists with columns including at minimum `id`, `user_sub`, `fleet`, `status` (enum: `active` / `submitted` / `discarded`), `edits` (JSONB), `created_at`, `updated_at`.
2. STORY-03 is DONE: the idempotency middleware is active; missing `Idempotency-Key` header returns 400 before the handler is reached.
3. "One active draft per fleet per user" means one row in `draft_change_sets` with `status = 'active'` for a given `(user_sub, fleet)` pair. Submitted and discarded drafts do not count toward this limit.
4. Key-path conflict detection on `PUT` checks: does any *other* user's active draft for the same fleet already include any of the same key_paths being added/modified? If yes → 409 with conflict list. Two edits by the same user to the same key_path in one draft are not a conflict (last write wins within the same draft).
5. `DELETE` is a soft operation logically (sets `status = 'discarded'`) but the API returns 204 and the draft must not be retrievable by the user after deletion. Physical deletion vs. status update is an implementation choice; either is acceptable as long as the 204 contract holds.
6. Fleet names are validated against the known set `{alpin, dostoneu, dani}` — unknown fleet → 422.

---

## Dependencies

| Dependency | Status Required | Notes |
|---|---|---|
| STORY-04 (DB schema + Alembic migrations) | DONE | `draft_change_sets` table required |
| STORY-03 (Idempotency middleware) | DONE | All three write endpoints must enforce Idempotency-Key |

---

## Acceptance Criteria

### AC-1: Create draft — happy path

**Given** a valid Keycloak JWT with `config-engineer` role, no existing active draft for `(user, fleet)`, and a valid `Idempotency-Key` header,
**When** `POST /api/policies/drafts` is called with body `{ "fleet": "alpin", "edits": [] }`,
**Then** the response is HTTP 201 with a body containing the new draft's `id`, `fleet`, `status: "active"`, `edits: []`, `created_at`, and `updated_at`.

### AC-2: Create draft — duplicate active draft returns 409

**Given** the user already has an active draft for fleet `alpin`,
**When** `POST /api/policies/drafts` is called again for fleet `alpin` with a new `Idempotency-Key`,
**Then** the response is HTTP 409 with `{ "detail": "active_draft_exists", "existing_draft_id": "<id>" }`.

### AC-3: Update draft — happy path

**Given** an active draft with id `<id>` owned by the authenticated user, a valid `Idempotency-Key`, and no key-path conflicts with other users' active drafts,
**When** `PUT /api/policies/drafts/{id}` is called with a body containing one or more key-path edits,
**Then** the response is HTTP 200 with the updated draft object reflecting the new edits and an updated `updated_at` timestamp.

### AC-4: Update draft — key-path conflict returns 409

**Given** another user has an active draft for the same fleet that already includes key_path `role::ntp::servers`,
**When** `PUT /api/policies/drafts/{id}` is called with an edit targeting `role::ntp::servers`,
**Then** the response is HTTP 409 with `{ "detail": "key_path_conflict", "conflicting_key_paths": ["role::ntp::servers"] }`. The draft is not modified.

### AC-5: Update draft — draft not found returns 404

**Given** a draft id that does not exist or belongs to a different user,
**When** `PUT /api/policies/drafts/{id}` is called,
**Then** the response is HTTP 404. The response body is identical in shape whether the draft doesn't exist or belongs to another user (never reveal ownership to an unauthorised caller).

### AC-6: Discard draft — happy path

**Given** an active draft with id `<id>` owned by the authenticated user and a valid `Idempotency-Key`,
**When** `DELETE /api/policies/drafts/{id}` is called,
**Then** the response is HTTP 204. Subsequent `GET` of the draft (if such endpoint exists) returns 404.

### AC-7: Discard draft — already discarded or submitted

**Given** a draft that has `status = 'discarded'` or `status = 'submitted'`,
**When** `DELETE /api/policies/drafts/{id}` is called,
**Then** the response is HTTP 409 with `{ "detail": "draft_not_active" }`.

### AC-8: Viewer role cannot create, update, or delete drafts

**Given** a valid JWT with `viewer` role,
**When** `POST`, `PUT`, or `DELETE` on draft endpoints is called,
**Then** the response is HTTP 403. Shape is identical to the 401 shape (never reveal whether the resource exists).

### AC-9: Missing Idempotency-Key returns 400

**Given** any authenticated request to `POST`, `PUT`, or `DELETE` draft endpoints with no `Idempotency-Key` header,
**When** the request is processed,
**Then** the response is HTTP 400 (handled by idempotency middleware before the handler runs).

### AC-10: Replayed Idempotency-Key returns cached response

**Given** a `POST /api/policies/drafts` that succeeded with `Idempotency-Key: abc123`,
**When** the same request is replayed with `Idempotency-Key: abc123` within the 24-hour TTL,
**Then** the response is HTTP 201 with the original cached response body. No duplicate draft is created.

### AC-11: Replayed Idempotency-Key with different fingerprint returns 409

**Given** `Idempotency-Key: abc123` was used for a `POST /api/policies/drafts` with fleet `alpin`,
**When** a new request uses `Idempotency-Key: abc123` but with a different request body (different fingerprint),
**Then** the response is HTTP 409.

---

## Definition of Done

- [ ] Python mypy passes with zero errors on all new/modified modules
- [ ] All security tests pass:
  - [ ] Unauthenticated → 401 on all three endpoints
  - [ ] Expired/malformed JWT → 401
  - [ ] Viewer role on POST/PUT/DELETE → 403
  - [ ] config-engineer role on POST/PUT/DELETE → 200/201/204 (happy path)
  - [ ] Missing Idempotency-Key → 400
  - [ ] Replayed Idempotency-Key (same fingerprint) → cached original response
  - [ ] Replayed Idempotency-Key (different fingerprint) → 409
  - [ ] Oversized or malformed payload → 422
- [ ] BFF unit tests cover:
  - [ ] Create draft happy path
  - [ ] Duplicate active draft → 409
  - [ ] Update draft happy path
  - [ ] Key-path conflict detection → 409 with conflict list
  - [ ] Draft not found / wrong owner → 404
  - [ ] Discard happy path → 204
  - [ ] Discard non-active draft → 409
  - [ ] One active draft per fleet per user invariant
- [ ] Integration tests run against Postgres test database (not real downstream services)
- [ ] BFF coverage ≥90% (`pytest --cov --cov-fail-under=90`) on new business logic
- [ ] All Playwright E2E: create draft → edit → discard flow; auth failure; conflict detection
- [ ] QA score ≥ 85/100
- [ ] Code Reviewer agent approved (no Critical issues)
- [ ] Security Sentinel agent approved (no Critical issues)
- [ ] `docs/API_CONTRACTS.md` updated with all three draft endpoint contracts
- [ ] Story file Status set to DONE

---

## D-Decisions Touched

| Decision | How it applies |
|---|---|
| **D12** | Draft change sets persisted in Postgres `draft_change_sets` table; key-path conflict detection enforced server-side on every `PUT`; one active draft per fleet per user invariant. |
| **D4** | `Idempotency-Key` header mandatory on all three write endpoints (POST/PUT/DELETE). 24-hour TTL. Fingerprint computed as RFC 8785 canonical JSON of the request body. Replayed key with same fingerprint → return cached response. Replayed key with different fingerprint → 409. |

---

## SLO Assignment

**Governing SLO**: Write-path ≥99% rolling 7-day success rate (MR creation end-to-end). Draft lifecycle endpoints are write operations that precede MR creation; they govern the write path. The 99% SLO applies to successful draft creation and update operations.

---

## Implementation Notes (for bff-dev)

- Route file: `bff/routers/policies_router.py`
- Models: `DraftCreateRequest`, `DraftUpdateRequest`, `DraftResponse` in `bff/models/policies.py` (Pydantic v2, strict, no `any`)
- Use `get_current_user` for `user_sub` extraction (D3); no `customer_id` (Iron Rule 3)
- Role check: require `config-engineer` or `admin` role on POST/PUT/DELETE; viewer → 403
- Postgres calls must be async (Iron Rule 5); use asyncpg or SQLAlchemy async engine consistent with STORY-04's migration
- Key-path conflict query: `SELECT key_paths FROM draft_change_sets WHERE fleet = $1 AND status = 'active' AND user_sub != $2` — collect all key_paths from other users' active drafts and intersect with incoming edits
- Edits JSONB schema: `[{ "key_path": "...", "value": ..., "operation": "set"|"delete" }]`
- Fleet validation: reject unknown fleet names with 422 before touching Postgres
- No GitLab calls in this story — drafts live in Postgres until Apply All (STORY-15)
- Rate-limit write endpoints at the BFF per Iron Rule (§Security Depth)
