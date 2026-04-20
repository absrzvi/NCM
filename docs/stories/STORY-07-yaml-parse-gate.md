# STORY-07: yaml_parse D14 Gate

**Status:** READY

---

## Summary

Implement Gate 1 of 5 in the D14 server-side validation pipeline. This gate parses the incoming hieradata content string using `ruamel.yaml` in round-trip mode (`typ='rt'`) and rejects any content that is not valid YAML before any downstream gate runs.

The gate is a pure Python function with no I/O side-effects. It is consumed by the Apply All endpoint (STORY-15) and may be called from the local validation script (`scripts/validate_local.py`).

---

## Assumptions

1. `SPIKE-04` (test fixture capture) has a pass verdict and fixtures are committed under `tests/fixtures/` before this story's integration tests are written.
2. `ruamel.yaml` is already declared as a BFF dependency (it is required by Iron Rule 11 and D5).
3. `GateResult` is a shared Pydantic v2 model defined in `bff/validation/__init__.py` (or a dedicated `bff/validation/models.py`). If it does not exist, this story defines it there. Shape: `{ passed: bool, error_code: str | None, detail: str | None }`.
4. The gate operates only on the raw YAML string — it does not write to disk, call GitLab, or touch the database.
5. Anchor/alias round-trip preservation is a correctness goal but is not independently tested here — that is covered by SPIKE-02 and STORY-10.

---

## Dependencies

| Dependency | Type | Unblock Condition |
|---|---|---|
| SPIKE-04 (test fixtures) | Hard — integration tests require fixtures | Fixtures committed in operator-authored PR |
| `ruamel.yaml` package | Hard — must be in `requirements.txt` / `pyproject.toml` | Already present (Iron Rule 11) |

---

## Acceptance Criteria

### AC-1: Valid YAML passes the gate

**Given** a well-formed YAML string (correct syntax, valid anchors, no tab characters in indentation)  
**When** `validate_yaml_parse(content)` is called  
**Then** the function returns `GateResult(passed=True, error_code=None, detail=None)`

### AC-2: Invalid YAML fails the gate with the correct error code

**Given** a malformed YAML string (e.g. unmatched braces, bad indentation, duplicate anchor reference)  
**When** `validate_yaml_parse(content)` is called  
**Then** the function returns `GateResult(passed=False, error_code="yaml_parse_failed", detail=<human-readable parse error message>)`  
**And** the `detail` field contains the line/column from the `ruamel.yaml` exception when available  
**And** no exception propagates out of `validate_yaml_parse`

### AC-3: Empty string is treated as valid YAML

**Given** an empty string `""`  
**When** `validate_yaml_parse(content)` is called  
**Then** the function returns `GateResult(passed=True, error_code=None, detail=None)`  
(An empty document is valid YAML; the key_shape gate handles semantic emptiness.)

### AC-4: ruamel.yaml round-trip mode is always used

**Given** any invocation of `validate_yaml_parse`  
**When** the source is inspected  
**Then** the `ruamel.yaml` YAML instance is constructed with `typ='rt'` only — never `typ='safe'`, never `yaml.safe_load`, never `pyyaml`

### AC-5: Gate integrates correctly with D14 pipeline ordering

**Given** the Apply All endpoint calls D14 gates in sequence  
**When** `validate_yaml_parse` returns `passed=False`  
**Then** the pipeline halts and returns HTTP 422 with body `{ "error_code": "yaml_parse_failed", "detail": "<message>" }` — no subsequent D14 gates are called

---

## Definition of Done

- [ ] `bff/validation/yaml_parse.py` exists with public function `validate_yaml_parse(content: str) -> GateResult`
- [ ] `GateResult` Pydantic v2 model defined (in `bff/validation/models.py` or `bff/validation/__init__.py`)
- [ ] `ruamel.yaml` `typ='rt'` is the sole parser — no `pyyaml` import anywhere in `yaml_parse.py`
- [ ] Unit tests cover: valid YAML, invalid YAML (syntax error), empty string, multi-document YAML, YAML with anchors/aliases
- [ ] Unit tests verify `error_code == "yaml_parse_failed"` on all failure cases
- [ ] Integration test uses a fixture file from `tests/fixtures/alpin/` as the valid-YAML input
- [ ] `pytest --cov --cov-fail-under=90` passes on `bff/validation/yaml_parse.py`
- [ ] `mypy` passes with zero errors on `bff/validation/yaml_parse.py`
- [ ] No exception escapes `validate_yaml_parse` — all `ruamel.yaml` exceptions are caught and translated to `GateResult`
- [ ] Story Status set to DONE

---

## D-Decisions Touched

| Decision | Relevance |
|---|---|
| **D14** | This story implements Gate 1 of the 5 mandatory server-side validation gates |
| **D5** | `ruamel.yaml` round-trip mode (`typ='rt'`) is mandated by Iron Rule 11; this gate enforces that only round-trip-safe YAML enters the write pipeline |

---

## SLO Assignment

**Write-path ≥99%** (rolling 7-day MR creation success rate)

Rationale: this gate sits on the hieradata write path. A gate crash or false-positive rejection would contribute to write-path failures. The gate must not raise unhandled exceptions.

---

## File Locations

- Implementation: `bff/validation/yaml_parse.py`
- Shared model: `bff/validation/models.py` (create if absent; extend if present)
- Unit tests: `tests/unit/validation/test_yaml_parse.py`
- Integration tests: `tests/integration/validation/test_yaml_parse_integration.py`
- Fixtures consumed: `tests/fixtures/alpin/` (any valid hieradata file)

---

## Notes for Implementer

- Do not import `yaml` (pyyaml). The only YAML library in this codebase is `ruamel.yaml` (Iron Rule 11).
- `ruamel.yaml` with `typ='rt'` raises `ruamel.yaml.YAMLError` (and subclasses) on parse failure. Catch the base class.
- The `detail` field should be `str(exc)` from the caught exception — this gives line/column context without leaking secrets (the exception message contains positional info, not values).
- This function is synchronous (pure CPU-bound parsing, no I/O). It is called from an `async` FastAPI route via `asyncio.get_event_loop().run_in_executor` or directly if the BFF route is not latency-sensitive for this gate. Coordinate with STORY-15 on the calling convention.
- Gate ordering in D14 pipeline: yaml_parse (this) → yamllint → key_shape → byte_diff_drift → secret_scan. Halt on first failure.
