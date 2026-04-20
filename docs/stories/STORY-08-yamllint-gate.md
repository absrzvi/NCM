# STORY-08: yamllint D14 Gate

**Status:** READY

---

## Summary

Implement Gate 2 of 5 in the D14 server-side validation pipeline. This gate runs `yamllint` against the incoming hieradata content string and rejects content that violates style rules. The line-length rule is explicitly disabled (hieradata values can be long). Failures are reported with the rule name, line number, and column number to enable precise editorial correction.

The gate is a pure Python function with no I/O side-effects. It is consumed by the Apply All endpoint (STORY-15).

---

## Assumptions

1. `SPIKE-04` (test fixture capture) has a pass verdict and fixtures are committed before integration tests are written.
2. `yamllint` Python package is added to BFF dependencies in this story if not already present.
3. `GateResult` Pydantic v2 model is defined by STORY-07 (or defined here if STORY-07 ships first; the model must not be duplicated).
4. The gate operates only on the raw YAML string — no disk I/O, no GitLab calls, no database access.
5. Gate 1 (`yaml_parse`) has already passed when this gate is called; content is guaranteed parseable YAML at this point.

---

## Dependencies

| Dependency | Type | Unblock Condition |
|---|---|---|
| SPIKE-04 (test fixtures) | Hard — integration tests require fixtures | Fixtures committed in operator-authored PR |
| STORY-07 (yaml_parse gate) | Soft — `GateResult` model must exist | STORY-07 defines the shared model; if STORY-08 ships first, define model here |
| `yamllint` package | Hard | Added to `requirements.txt` / `pyproject.toml` in this story |

---

## Acceptance Criteria

### AC-1: Style-valid YAML passes the gate

**Given** a YAML string that passes all enabled yamllint rules (including any rules active in the project yamllint config)  
**When** `validate_yamllint(content)` is called  
**Then** the function returns `GateResult(passed=True, error_code=None, detail=None)`

### AC-2: Style-invalid YAML fails with the correct error code and location

**Given** a YAML string that violates a yamllint rule (e.g. trailing spaces, missing document-start marker if required, duplicate keys)  
**When** `validate_yamllint(content)` is called  
**Then** the function returns `GateResult(passed=False, error_code="yamllint_failed", detail=<rule:line:col message>)`  
**And** the `detail` field contains the yamllint rule name, line number, and column number  
**And** no exception propagates out of `validate_yamllint`

### AC-3: Line-length rule is disabled

**Given** a YAML string containing a line longer than 80 (or 120) characters  
**When** `validate_yamllint(content)` is called  
**Then** the function returns `GateResult(passed=True, ...)` — the long line does not cause failure  
(Hieradata values including certificate thumbprints and long strings must not be rejected on length grounds.)

### AC-4: yamllint config is inline or co-located — no reliance on a user home directory config

**Given** the BFF process running inside Docker  
**When** `validate_yamllint` is invoked  
**Then** the yamllint configuration used is either passed as a `YamlLintConfig` object constructed in code or read from a committed project config file (e.g. `bff/validation/yamllint_config.yaml`)  
**And** no user-home-directory `.yamllint` file is read

### AC-5: Gate integrates correctly with D14 pipeline ordering

**Given** Gate 1 (`yaml_parse`) has passed and the Apply All endpoint calls Gate 2  
**When** `validate_yamllint` returns `passed=False`  
**Then** the pipeline halts and returns HTTP 422 with body `{ "error_code": "yamllint_failed", "detail": "<rule:line:col>" }` — Gate 3 (`key_shape`) is not called

---

## Definition of Done

- [ ] `bff/validation/yamllint_gate.py` exists with public function `validate_yamllint(content: str) -> GateResult`
- [ ] Line-length rule is disabled in the yamllint config used by this gate
- [ ] `yamllint` package declared in BFF dependencies
- [ ] Failure `detail` format is `<rule>:<line>:<col> <message>` (e.g. `"trailing-spaces:14:1 trailing spaces"`)
- [ ] Unit tests cover: valid YAML, trailing-spaces violation, duplicate-key violation, long-line accepted (line-length disabled)
- [ ] Unit tests verify `error_code == "yamllint_failed"` on all failure cases
- [ ] Integration test uses a fixture file from `tests/fixtures/alpin/` as the valid-YAML input
- [ ] `pytest --cov --cov-fail-under=90` passes on `bff/validation/yamllint_gate.py`
- [ ] `mypy` passes with zero errors
- [ ] No exception escapes `validate_yamllint`
- [ ] Story Status set to DONE

---

## D-Decisions Touched

| Decision | Relevance |
|---|---|
| **D14** | This story implements Gate 2 of the 5 mandatory server-side validation gates |

---

## SLO Assignment

**Write-path ≥99%** (rolling 7-day MR creation success rate)

Rationale: this gate sits on the hieradata write path. A crash or misconfigured rule that rejects valid hieradata would contribute to write-path failures.

---

## File Locations

- Implementation: `bff/validation/yamllint_gate.py`
- yamllint config (if file-based): `bff/validation/yamllint_config.yaml`
- Shared model: `bff/validation/models.py`
- Unit tests: `tests/unit/validation/test_yamllint_gate.py`
- Integration tests: `tests/integration/validation/test_yamllint_gate_integration.py`
- Fixtures consumed: `tests/fixtures/alpin/`

---

## Notes for Implementer

- Use `yamllint.linter.run(content, config)` with a `YamlLintConfig` object. Do not shell out to the `yamllint` CLI binary.
- Construct the config with `YamlLintConfig('extends: default\nrules:\n  line-length: disable\n')` or load from a committed YAML file. Either approach is acceptable; the committed-file approach is preferred for auditability.
- `yamllint` yields problem objects with `.rule`, `.line`, `.column`, `.message`. Format `detail` as `f"{p.rule}:{p.line}:{p.col} {p.message}"` for the first problem found (do not enumerate all problems — return on first failure to keep the pipeline fast).
- This function is synchronous (CPU-bound). Same calling-convention note as STORY-07 regarding `run_in_executor`.
- Gate ordering: yaml_parse → yamllint (this) → key_shape → byte_diff_drift → secret_scan.
