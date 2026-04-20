# STORY-17: Conflict Detection (D7)

**Status**: READY
**Tier**: 3 — Policies Module
**Module**: `bff/routers/policies_router.py`, `bff/clients/gitlab_client.py`

---

## Summary

Implement server-side 3-way merge conflict detection as a first-class API concern. When a user's draft was created against a `base_sha` that has since been superseded by new commits on the target Puppet environment branch, and those new commits modify the same key_paths as the draft's edits, the apply must be blocked with a structured 409 response.

This story implements the conflict detection logic as a reusable internal function that is called by the Apply All endpoint (STORY-15). It may also be surfaced as a standalone pre-flight check endpoint `POST /api/policies/drafts/{id}/check-conflicts` to allow the frontend to warn users before they attempt an apply.

The 409 response must list **conflicting `key_paths` only** — not file paths, not line numbers. The user sees the logical key names they care about, not implementation details of which hieradata file was touched.

---

## Assumptions

1. STORY-14 is DONE: draft records in Postgres contain `base_sha` (the GitLab commit SHA at the time the draft was created) and `fleet`, `edits` (JSONB list of key-path edits).
2. STORY-05 is DONE: `gitlab_client` can fetch file contents at a specific SHA and the current tip SHA for a branch.
3. "Stale branch" means: the current tip SHA of the target Puppet environment branch differs from the draft's `base_sha`. If they are equal, there is no conflict (fast-forward scenario, no 3-way merge needed).
4. "Conflicting key_path" means: a key_path that appears in the draft's edits AND was also modified in the commits between `base_sha` and the current tip SHA. Keys changed only in the new commits but NOT in the draft are not conflicts (they represent unrelated changes; the apply can proceed for the draft's keys).
5. Conflict detection operates at the key_path level, not the YAML file level. Two drafts can touch the same file without conflicting if their key_paths are disjoint.
6. The pre-flight check endpoint `POST /api/policies/drafts/{id}/check-conflicts` (if implemented) is a read-style operation (it only reads from GitLab and Postgres, writes nothing). It does not consume idempotency keys. It returns 200 with `{ "has_conflicts": false }` or 200 with `{ "has_conflicts": true, "conflicting_key_paths": [...] }`. It is not a 409 — the 409 is only returned by the apply endpoint when it detects conflicts.
7. The `check-conflicts` endpoint is **optional** in this story — if the Apply All endpoint (STORY-15) already performs the check inline, the `check-conflicts` endpoint is a bonus. The acceptance criteria for this story focus on the core conflict detection logic and the 409 response from the apply path.

---

## Dependencies

| Dependency | Status Required | Notes |
|---|---|---|
| STORY-14 (draft lifecycle) | DONE | Draft record with `base_sha` required |
| STORY-05 (downstream clients) | DONE | `gitlab_client.get_file(project, path, ref)` required for tip SHA comparison |

---

## Acceptance Criteria

### AC-1: No conflict — tip SHA unchanged since draft creation

**Given** a draft whose `base_sha` equals the current tip SHA of the target Puppet environment branch,
**When** conflict detection is run (either via apply or via `check-conflicts`),
**Then** no conflict is reported. The apply proceeds (for STORY-15) or `check-conflicts` returns `{ "has_conflicts": false }`.

### AC-2: No conflict — tip SHA advanced but disjoint key_paths

**Given** a draft with edits to `role::ntp::servers` and `base_sha = abc123`, and the current tip SHA is `def456` (advanced), but the commits between `abc123` and `def456` only modified key_path `role::dns::nameservers` (a different key),
**When** conflict detection is run,
**Then** no conflict is reported. The two key_paths are disjoint; the apply proceeds.

### AC-3: Conflict — overlapping key_path in diverged commits

**Given** a draft with an edit to `role::ntp::servers` and `base_sha = abc123`, and the current tip SHA is `def456`, and the commits between `abc123` and `def456` include a change to `role::ntp::servers`,
**When** conflict detection is run,
**Then** a conflict is detected. If called from the apply path → HTTP 409 with `{ "detail": "merge_conflict", "conflicting_key_paths": ["role::ntp::servers"] }`. If called from `check-conflicts` → HTTP 200 with `{ "has_conflicts": true, "conflicting_key_paths": ["role::ntp::servers"] }`.

### AC-4: Conflict response lists key_paths, not file paths

**Given** a conflict exists on key_path `role::ntp::servers` which lives in `hieradata/common.yaml`,
**When** the conflict 409 response is returned,
**Then** the `conflicting_key_paths` array contains `"role::ntp::servers"`, NOT `"hieradata/common.yaml"`. File paths must not appear in the conflict response.

### AC-5: Multiple conflicting key_paths all listed

**Given** a draft with edits to three key_paths, and two of them conflict with diverged commits,
**When** a conflict 409 is returned,
**Then** the `conflicting_key_paths` array lists both conflicting keys. The non-conflicting key is not listed.

### AC-6: check-conflicts endpoint — unauthenticated returns 401

**Given** no Authorization header or an expired/malformed JWT,
**When** `POST /api/policies/drafts/{id}/check-conflicts` is called,
**Then** the response is HTTP 401.

### AC-7: check-conflicts endpoint — draft not found or wrong owner returns 404

**Given** a draft id that does not exist or belongs to a different user,
**When** `POST /api/policies/drafts/{id}/check-conflicts` is called,
**Then** the response is HTTP 404. Shape is identical whether draft doesn't exist or belongs to another user.

### AC-8: GitLab unreachable during conflict check returns 502

**Given** the GitLab API is unreachable (simulated by fixture),
**When** conflict detection is attempted,
**Then** the apply path returns HTTP 502 `{ "detail": "upstream_unavailable" }`. No branch is created.

---

## Definition of Done

- [ ] Python mypy passes with zero errors
- [ ] All security tests pass:
  - [ ] Unauthenticated → 401 on `check-conflicts` endpoint
  - [ ] Expired/malformed JWT → 401
  - [ ] Viewer role on `check-conflicts` → 200 (read-only; all roles may check conflicts)
- [ ] BFF unit tests cover:
  - [ ] No conflict: base_sha == tip SHA (fast-forward)
  - [ ] No conflict: tip SHA advanced, disjoint key_paths
  - [ ] Conflict: overlapping key_path in diverged commits
  - [ ] Conflict response contains only key_paths (not file paths)
  - [ ] Multiple conflicting key_paths all listed
  - [ ] Draft not found / wrong owner → 404
  - [ ] GitLab unreachable → 502
- [ ] Conflict detection logic is a standalone importable function in `bff/` (not inlined in the router) so STORY-15 can import and call it
- [ ] Integration tests run against fixtures (never real GitLab)
- [ ] BFF coverage ≥90% (`pytest --cov --cov-fail-under=90`)
- [ ] Playwright E2E: conflict scenario triggers 409 warning in the Apply All UI (or pre-flight warning from `check-conflicts`)
- [ ] QA score ≥ 85/100
- [ ] Code Reviewer agent approved (no Critical issues)
- [ ] Security Sentinel agent approved (no Critical issues)
- [ ] `docs/API_CONTRACTS.md` updated with `check-conflicts` contract (if endpoint is implemented)
- [ ] Story file Status set to DONE

---

## D-Decisions Touched

| Decision | How it applies |
|---|---|
| **D7** | Server-side 3-way merge conflict detection on stale-branch conflict. Returns structured 409 listing conflicting `key_paths` only. Never file-level conflict reporting. |

---

## SLO Assignment

**Governing SLO**: Write-path ≥99% rolling 7-day success rate. Conflict detection is part of the write path (it runs inside or before the apply). A valid draft that passes conflict detection must proceed to MR creation successfully ≥99% of the time.

The `check-conflicts` pre-flight endpoint (if implemented) is a read operation; it is governed by the **Read-path p95 < 500ms** SLO.

---

## Implementation Notes (for bff-dev)

- Conflict detection logic: implement as `detect_conflicts(draft: DraftChangeSet, current_tip_sha: str, gitlab_client: GitLabClient) -> list[str]` in `bff/policies_conflicts.py` (new module). Returns a list of conflicting key_path strings (empty list = no conflict).
- STORY-15 imports and calls `detect_conflicts` before running D14 gates.
- Computing the delta between `base_sha` and `current_tip_sha`: use `gitlab_client.compare(project_path, base_sha, current_tip_sha)` to get the diff. Then parse the diff to extract which key_paths changed. Use ruamel.yaml or a YAML-aware diff rather than line-level diff to correctly identify key_path changes.
- The `check-conflicts` endpoint (if implemented) does not require the `Idempotency-Key` header — it is idempotent by nature (no writes).
- Never log hieradata values from the diff; log only key_paths and SHAs.
- Role-based access: `check-conflicts` is readable by any authenticated user; it reveals only key_paths from the authenticated user's own draft.
- Module must not exceed 500 lines. If the YAML-aware diff logic is complex, split into `bff/policies_conflicts.py` (orchestration) and `bff/yaml_key_diff.py` (YAML parsing).
