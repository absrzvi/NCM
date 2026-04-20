# STORY-10: byte_diff_drift D14 Gate

**Status:** BLOCKED — requires SPIKE-02 pass verdict

---

## Summary

Implement Gate 4 of 5 in the D14 server-side validation pipeline. This gate detects unintended byte-level changes in a hieradata file by comparing `original` and `modified` YAML strings. Only the key_paths declared as the intended edit targets are allowed to differ. Any change outside the declared `intended_key_paths` — including comment reformatting, key reordering, whitespace drift, or anchor expansion — is a blocking error.

The gate loads `ruamel_tolerance.yaml` (produced by SPIKE-02) to account for known benign round-trip normalisation artefacts before flagging residual drift.

This story is **blocked** until SPIKE-02 delivers a pass verdict (`unexpected_diffs: []`) and commits `ruamel_tolerance.yaml`.

---

## Assumptions

1. SPIKE-02 has delivered a pass verdict. If SPIKE-02 delivers a fail verdict (unexpected diffs detected), this story must not proceed — escalate to architect for ADR before implementing.
2. `ruamel_tolerance.yaml` is committed to the repository (location decided by SPIKE-02 author; assumed `bff/validation/ruamel_tolerance.yaml`).
3. `GateResult` Pydantic v2 model is defined (by STORY-07 or earlier in the pipeline).
4. `original` is the YAML string as read from GitLab before any edit. `modified` is the YAML string after the BFF applies the declared key_path changes using `ruamel.yaml` round-trip mode.
5. `intended_key_paths` is a list of dot-notation key_path strings that were explicitly edited. Changes to these keys are expected and must not trigger the gate.
6. The gate does not call GitLab, PuppetDB, or the database.
7. SPIKE-04 fixtures are committed and available for integration tests.

---

## Dependencies

| Dependency | Type | Unblock Condition |
|---|---|---|
| **SPIKE-02** (ruamel.yaml round-trip fidelity) | **Hard blocker** — tolerance file required | Pass verdict (`unexpected_diffs: []`) AND `ruamel_tolerance.yaml` committed |
| SPIKE-04 (test fixtures) | Hard — integration tests require fixtures | Fixtures committed in operator-authored PR |
| STORY-07 (yaml_parse gate) | Soft — `GateResult` model must exist | STORY-07 defines the model |

---

## Acceptance Criteria

### AC-1: Modification limited to declared key_paths passes the gate

**Given** `original` and `modified` YAML strings where only the keys listed in `intended_key_paths` differ  
**And** any remaining diff is listed in `ruamel_tolerance.yaml` as a known benign normalisation  
**When** `validate_byte_diff_drift(original, modified, intended_key_paths)` is called  
**Then** the function returns `GateResult(passed=True, error_code=None, detail=None)`

### AC-2: Modification outside declared key_paths fails the gate

**Given** `original` and `modified` YAML strings where a key NOT in `intended_key_paths` has changed (e.g. a comment was altered, a key was reordered, an unrelated value changed)  
**And** the change is not listed in `ruamel_tolerance.yaml`  
**When** `validate_byte_diff_drift(original, modified, intended_key_paths)` is called  
**Then** the function returns `GateResult(passed=False, error_code="byte_diff_drift", detail=<description of unexpected change including key and context>)`  
**And** the `detail` does not include the actual hieradata values — only the key names and line positions

### AC-3: Known ruamel.yaml normalisation artefacts are tolerated

**Given** `original` and `modified` YAML strings that differ only in a way catalogued in `ruamel_tolerance.yaml` (e.g. trailing newline normalisation, quote style normalisation for a specific pattern)  
**And** no keys outside `intended_key_paths` have semantically changed  
**When** `validate_byte_diff_drift(original, modified, intended_key_paths)` is called  
**Then** the function returns `GateResult(passed=True, error_code=None, detail=None)`

### AC-4: Identical original and modified passes unconditionally

**Given** `original` and `modified` are byte-for-byte identical strings  
**When** `validate_byte_diff_drift(original, modified, intended_key_paths)` is called  
**Then** the function returns `GateResult(passed=True, error_code=None, detail=None)`

### AC-5: Gate integrates correctly with D14 pipeline ordering

**Given** Gates 1–3 have passed and the Apply All endpoint calls Gate 4  
**When** `validate_byte_diff_drift` returns `passed=False`  
**Then** the pipeline halts and returns HTTP 422 with body `{ "error_code": "byte_diff_drift", "detail": "<message>" }`  
**And** Gate 5 (`secret_scan`) is not called

---

## Definition of Done

- [ ] `bff/validation/byte_diff_drift.py` exists with public function `validate_byte_diff_drift(original: str, modified: str, intended_key_paths: list[str]) -> GateResult`
- [ ] `ruamel_tolerance.yaml` is loaded at module import time (or lazily with `lru_cache`) from its committed location
- [ ] Unintended changes outside `intended_key_paths` produce `error_code="byte_diff_drift"`
- [ ] `detail` field on failure describes the unexpected change without echoing hieradata values
- [ ] Unit tests cover: no change (pass), only intended keys changed (pass), unintended key changed (fail), tolerance-listed normalisation (pass)
- [ ] Integration test uses a fixture pair from `tests/fixtures/alpin/` — read original, apply a known edit via ruamel.yaml, verify gate passes; then apply an unintended edit, verify gate fails
- [ ] `pytest --cov --cov-fail-under=90` passes on `bff/validation/byte_diff_drift.py`
- [ ] `mypy` passes with zero errors
- [ ] No exception escapes `validate_byte_diff_drift`
- [ ] SPIKE-02 pass verdict confirmed (architect sign-off recorded in story before implementation begins)
- [ ] Story Status set to DONE

---

## D-Decisions Touched

| Decision | Relevance |
|---|---|
| **D14** | This story implements Gate 4 of the 5 mandatory server-side validation gates |
| **D5** | The gate enforces that ruamel.yaml round-trip mode produces only the intended changes; directly depends on SPIKE-02's verification of D5 correctness |

---

## SLO Assignment

**Write-path ≥99%** (rolling 7-day MR creation success rate)

Rationale: this gate sits on the hieradata write path. A false-positive drift detection would block legitimate writes. The `ruamel_tolerance.yaml` exemption list exists specifically to prevent SPIKE-02-catalogued normalisation artefacts from degrading write-path success.

---

## File Locations

- Implementation: `bff/validation/byte_diff_drift.py`
- Tolerance file (committed by SPIKE-02): `bff/validation/ruamel_tolerance.yaml`
- Shared model: `bff/validation/models.py`
- Unit tests: `tests/unit/validation/test_byte_diff_drift.py`
- Integration tests: `tests/integration/validation/test_byte_diff_drift_integration.py`
- Fixtures consumed: `tests/fixtures/alpin/`

---

## Notes for Implementer

- **Do not begin implementation until SPIKE-02 architect sign-off is recorded in this file.** Update Status from BLOCKED to READY at that point.
- Diff strategy: parse both `original` and `modified` with `ruamel.yaml` `typ='rt'`, walk the resulting `CommentedMap` trees, collect all keys that differ (value or comment), subtract `intended_key_paths`, subtract the tolerance list. Any remainder is a drift violation.
- The tolerance list in `ruamel_tolerance.yaml` should express patterns conservatively. If uncertain whether a diff is benign, SPIKE-02 should mark it blocking rather than tolerated.
- Do not use Python `difflib` on raw strings as the primary diff mechanism — structural YAML-aware diffing is required to correctly identify which key changed. Raw-string diff may be used as a secondary sanity check.
- `detail` on failure: `"Unexpected change outside intended_key_paths at key '<key>' (line <n>)"` — no values, no YAML content.
- Gate ordering: yaml_parse → yamllint → key_shape → byte_diff_drift (this) → secret_scan.
- Principle 3 (Surgical Changes) is operationalised by this gate: any diff that touches keys beyond the declared `intended_key_paths` is a code-review block and a gate block simultaneously.
