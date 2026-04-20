# STORY-15: Apply All Endpoint (POST /api/policies/drafts/{id}/apply)

**Status**: READY
**Tier**: 3 — Policies Module
**Module**: `bff/routers/policies_router.py`, `bff/validation/`, `bff/clients/gitlab_client.py`

---

## Summary

Implement `POST /api/policies/drafts/{id}/apply` — the "Apply All" endpoint that takes an active draft and materialises its edits as a GitLab merge request.

The full sequence is:

1. **Fetch current tip**: Read hieradata files at the current tip SHA of the target Puppet environment branch (`devel` or `staging`) via `gitlab_client`.
2. **3-way merge conflict detection** (D7): Detect stale-branch conflicts by comparing the tip SHA at draft creation time vs. current tip SHA. If any file edited by this draft has diverged, return a structured 409 listing conflicting `key_paths` only (not file paths).
3. **Apply edits via ruamel.yaml** (D5): For each key-path edit in the draft, modify the target hieradata file using `ruamel.yaml` round-trip mode. Never use `yaml.safe_dump`.
4. **Run all 5 D14 validation gates in order** — abort on first failure and return 422 with the gate's error code:
   - `yaml_parse` (STORY-07)
   - `yamllint` (STORY-08)
   - `key_shape` (STORY-09)
   - `byte_diff_drift` (STORY-10)
   - `secret_scan` (STORY-11)
5. **Create branch**: `nms/<user>-<fleet>-<shortid>` branched off the target Puppet environment branch (`devel` or `staging` per fleet config). Never create branches off `master` or `ODEG` (D15).
6. **Commit**: Commit subject must be prefixed `NCD-<n>: ` where `<n>` is the Jira issue number — this is a required field in the request body. Reject requests without a valid Jira issue number with 422.
7. **Open MR**: Create a GitLab MR from the new branch to the target Puppet environment branch.
8. **Mark draft SUBMITTED**: Update the draft's `status` to `submitted` in Postgres.

The endpoint requires `config-engineer` role and the `Idempotency-Key` header.

---

## Assumptions

1. SPIKE-02 has passed: ruamel.yaml round-trip fidelity is confirmed; the tolerance file is committed. If byte-level drift beyond the tolerance is detected, the `byte_diff_drift` gate will block the apply.
2. STORY-07 through STORY-11 are DONE: all 5 D14 gate functions are importable from `bff/validation/`.
3. STORY-14 is DONE: draft lifecycle exists and the draft record in Postgres contains the `base_sha` (the GitLab commit SHA at draft creation time) required for 3-way merge comparison.
4. STORY-05 is DONE: `gitlab_client` exposes async methods for `get_file`, `create_branch`, `create_commit`, `create_merge_request`.
5. The Jira issue number validation pattern is `^[A-Z]+-\d+$` (e.g. `NCD-42`). This is the only format accepted. If the project uses a different Jira project key prefix, a follow-up story must update this pattern.
6. The target Puppet environment branch (`devel` or `staging`) is determined by the fleet's environment config (STORY-06). The fleet config is loaded from Postgres or a config file; no hardcoding of branch names in this router.
7. "Abort on first D14 gate failure" means gates run sequentially in the order listed above. If `yaml_parse` fails, `yamllint` is not run. Do not parallelize the gates within a single apply call.
8. The MR description is auto-generated from the draft's edit list. The MR title is the commit subject.

---

## Dependencies

| Dependency | Status Required | Notes |
|---|---|---|
| SPIKE-02 (ruamel.yaml round-trip fidelity) | PASS verdict committed | Blocks D5 apply and byte_diff_drift gate |
| STORY-07 (yaml_parse gate) | DONE | Gate 1 in D14 chain |
| STORY-08 (yamllint gate) | DONE | Gate 2 in D14 chain |
| STORY-09 (key_shape gate) | DONE | Gate 3 in D14 chain |
| STORY-10 (byte_diff_drift gate) | DONE | Gate 4 in D14 chain |
| STORY-11 (secret_scan gate) | DONE | Gate 5 in D14 chain |
| STORY-14 (draft lifecycle) | DONE | Draft record + `base_sha` required |
| STORY-05 (downstream clients) | DONE | `gitlab_client` required for all GitLab operations |

---

## Acceptance Criteria

### AC-1: Successful apply — end-to-end happy path

**Given** an active draft with at least one edit, a valid `config-engineer` JWT, a valid `Idempotency-Key`, a valid Jira issue number (e.g. `NCD-42`), and no conflicts with the current GitLab tip SHA,
**When** `POST /api/policies/drafts/{id}/apply` is called with `{ "jira_issue": "NCD-42" }`,
**Then** the response is HTTP 201 with `{ "mr_url": "<gitlab_mr_url>", "branch": "nms/<user>-<fleet>-<shortid>", "draft_status": "submitted" }`. The draft record in Postgres is updated to `status = 'submitted'`.

### AC-2: Jira issue number is required

**Given** a request body without a `jira_issue` field, or with `jira_issue: ""`, or with a value that does not match `^[A-Z]+-\d+$`,
**When** `POST /api/policies/drafts/{id}/apply` is called,
**Then** the response is HTTP 422 with `{ "detail": "jira_issue_required" }`. No branch is created, no MR is opened, no draft status change occurs.

### AC-3: Branch name follows the nms/<user>-<fleet>-<shortid> convention

**Given** a successful apply for user `jsmith` on fleet `alpin` with short id `a1b2c3`,
**When** the MR is created,
**Then** the branch name is exactly `nms/jsmith-alpin-a1b2c3`. The branch is created off `devel` (or `staging` per fleet config) — never off `master` or `ODEG`.

### AC-4: Commit subject is prefixed NCD-<n>:

**Given** a successful apply with `jira_issue: "NCD-42"`,
**When** the GitLab commit is created,
**Then** the commit message subject starts with `NCD-42: ` followed by a summary of the edits.

### AC-5: D14 gate failure — yaml_parse aborts at gate 1

**Given** a draft whose edit produces malformed YAML after ruamel.yaml application,
**When** `POST /api/policies/drafts/{id}/apply` is called,
**Then** the response is HTTP 422 with `{ "detail": "yaml_parse_failed" }`. No branch is created. The draft remains `active`.

### AC-6: D14 gate failure — secret_scan aborts at gate 5

**Given** a draft whose edit contains a value matching the secret_scan heuristic,
**When** `POST /api/policies/drafts/{id}/apply` is called,
**Then** the response is HTTP 422 with `{ "detail": "secret_leak_blocked" }`. No branch is created. The draft remains `active`.

### AC-7: D14 gate failure — byte_diff_drift aborts at gate 4

**Given** a draft whose ruamel.yaml-applied output has unexpected byte-level drift beyond the committed tolerance,
**When** `POST /api/policies/drafts/{id}/apply` is called,
**Then** the response is HTTP 422 with `{ "detail": "byte_diff_drift" }`. No branch created.

### AC-8: 3-way merge conflict returns 409 with key_path list

**Given** a draft whose `base_sha` differs from the current GitLab tip SHA for files containing key_paths in the draft,
**When** `POST /api/policies/drafts/{id}/apply` is called,
**Then** the response is HTTP 409 with `{ "detail": "merge_conflict", "conflicting_key_paths": ["role::ntp::servers", "..."] }`. The response lists key_paths, not file paths. No branch is created. The draft remains `active`.

### AC-9: Applying a non-active draft returns 409

**Given** a draft with `status = 'submitted'` or `status = 'discarded'`,
**When** `POST /api/policies/drafts/{id}/apply` is called,
**Then** the response is HTTP 409 with `{ "detail": "draft_not_active" }`.

### AC-10: Draft not found or belongs to another user returns 404

**Given** a draft id that does not exist or belongs to a different user,
**When** `POST /api/policies/drafts/{id}/apply` is called,
**Then** the response is HTTP 404. Shape is identical whether draft doesn't exist or belongs to another user.

### AC-11: Viewer role returns 403

**Given** a valid JWT with `viewer` role,
**When** `POST /api/policies/drafts/{id}/apply` is called,
**Then** the response is HTTP 403. Shape is identical to 401 shape.

### AC-12: Missing Idempotency-Key returns 400

**Given** no `Idempotency-Key` header,
**When** `POST /api/policies/drafts/{id}/apply` is called,
**Then** the response is HTTP 400 (handled by idempotency middleware).

### AC-13: Idempotent replay returns cached MR URL

**Given** a successful apply with `Idempotency-Key: abc123` that returned `{ "mr_url": "...", ... }`,
**When** the same key is replayed within 24h TTL,
**Then** the response is HTTP 201 with the original cached response. No second branch or MR is created.

### AC-14: Target branch is never master or ODEG

**Given** a fleet whose environment config (STORY-06) specifies any branch value other than `devel` or `staging`,
**When** `POST /api/policies/drafts/{id}/apply` is called,
**Then** the endpoint refuses with HTTP 422 `{ "detail": "forbidden_target_branch" }` and does not create the branch. This applies even if `master` or `ODEG` are passed in config — D15 hardcodes the refusal.

---

## Definition of Done

- [ ] Python mypy passes with zero errors on all new/modified modules
- [ ] All security tests pass:
  - [ ] Unauthenticated → 401
  - [ ] Expired/malformed JWT → 401
  - [ ] Viewer role → 403
  - [ ] Missing Idempotency-Key → 400
  - [ ] Replayed key (same fingerprint) → cached 201
  - [ ] Replayed key (different fingerprint) → 409
  - [ ] Oversized/malformed payload → 422
- [ ] All D14 validation gate tests pass:
  - [ ] Malformed YAML → 422 `yaml_parse_failed`
  - [ ] yamllint failure → 422 `yamllint_failed`
  - [ ] Key shape mismatch → 422 `key_shape_mismatch`
  - [ ] Unexpected byte-level drift → 422 `byte_diff_drift`
  - [ ] Secret-like value → 422 `secret_leak_blocked`
- [ ] Additional apply-specific tests pass:
  - [ ] Jira issue missing/invalid → 422
  - [ ] 3-way merge conflict → 409 with key_path list (not file-level)
  - [ ] `master`/`ODEG` target branch → 422 (D15)
  - [ ] Branch naming convention verified
  - [ ] Commit subject prefix verified
  - [ ] Draft marked `submitted` after success
  - [ ] Draft remains `active` after any gate failure
  - [ ] Non-active draft → 409
  - [ ] Draft not found / wrong owner → 404
- [ ] Integration tests run against fixtures (never real GitLab/Postgres calls from tests)
- [ ] BFF coverage ≥90% (`pytest --cov --cov-fail-under=90`)
- [ ] All Playwright E2E: full apply happy path + conflict detection + gate failure + auth failure
- [ ] QA score ≥ 85/100
- [ ] Code Reviewer agent approved (no Critical issues)
- [ ] Security Sentinel agent approved (no Critical issues)
- [ ] `docs/API_CONTRACTS.md` updated with apply endpoint contract
- [ ] Story file Status set to DONE

---

## D-Decisions Touched

| Decision | How it applies |
|---|---|
| **D5** | ruamel.yaml in round-trip mode for every hieradata file write. Never `yaml.safe_dump`. |
| **D7** | Server-side 3-way merge conflict detection: compare `base_sha` (at draft creation) vs current tip SHA; return structured 409 listing `key_paths` (not files) on conflict. |
| **D14** | All 5 validation gates run in order before any GitLab write. Abort on first failure. Gates are in `bff/validation/`. |
| **D15** | Target Puppet environment branch determined by fleet config. Hardcoded refusal for `master` and `ODEG`. Branch created off `devel` or `staging` only. |
| **D4** | Idempotency-Key mandatory. 24-hour TTL. Cached response on replay. |

---

## SLO Assignment

**Governing SLO**: Write-path ≥99% rolling 7-day success rate (MR creation end-to-end). This endpoint IS the MR creation path. The 99% target applies to requests that pass all D14 gates and conflict checks (i.e. valid inputs) resulting in a successfully created GitLab MR.

Secondary observation: PuppetDB is not called by this endpoint. GitLab is the only downstream; if GitLab is unreachable, the endpoint returns 502 (not a write-path failure in the SLO sense, but must be logged for incident review).

---

## Implementation Notes (for bff-dev)

- Route file: `bff/routers/policies_router.py`
- Models: `ApplyRequest` (contains `jira_issue: str`), `ApplyResponse` in `bff/models/policies.py`
- Use `get_current_user` for `user_sub` and `username` (D3); no `customer_id`
- Role check: require `config-engineer` or `admin`; viewer → 403
- D14 gates: import from `bff/validation/yaml_parse.py`, `yamllint.py`, `key_shape.py`, `byte_diff_drift.py`, `secret_scan.py` — call in order, abort on first failure
- ruamel.yaml: load → apply edits in memory → dump; never write via `yaml.safe_dump`
- Short id generation: 6-character hex from `secrets.token_hex(3)` — simple, no UUID dependency
- Never log hieradata values, the GitLab service token, or the user's JWT claims beyond `sub` and `roles`
- All GitLab calls via `gitlab_client` (D6); all HTTP via `httpx` (D9)
- Tests: mock `gitlab_client` methods; use fixtures from `tests/fixtures/`
- No file in `bff/routers/policies_router.py` may exceed 500 lines (Iron Rule); split into sub-modules if needed
