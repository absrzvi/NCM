# STORY-09: key_shape D14 Gate

**Status:** READY

---

## Summary

Implement Gate 3 of 5 in the D14 server-side validation pipeline. This gate validates that the type and structural shape of a hieradata value matches the known schema for the given `key_path` within a given fleet. Unknown keys produce a warning (not a blocking error) because the `known_keys` registry may lag behind legitimate new keys added directly to hieradata. Shape mismatches (e.g. expected `str`, got `list`) are blocking errors.

The gate operates on an individual key-value pair (not the full file) because the Apply All endpoint validates each changed key_path independently.

---

## Assumptions

1. `SPIKE-04` (test fixture capture) has a pass verdict and fixtures are committed before integration tests are written.
2. `GateResult` is extended in this story to carry an optional `warnings: list[str]` field for non-blocking observations (unknown key). If STORY-07/08 already defined `GateResult`, extend it here without breaking existing callers.
3. The `known_keys` registry is a per-fleet mapping from `key_path` (dot-notation string) to expected Python type (`str`, `int`, `bool`, `list`, `dict`). It is loaded from `bff/validation/known_keys/<fleet>.yaml` — one file per fleet (`alpin.yaml`, `dostoneu.yaml`, `dani.yaml`). These files are committed as part of this story with the keys observable from `SPIKE-04` fixtures.
4. STORY-06 (environment config loader) provides the `fleet` string for a given request context. The gate receives `fleet` as a plain string parameter — it does not call the config loader directly.
5. The gate does not call GitLab, PuppetDB, or the database.
6. The `value` parameter is the already-parsed Python object (not a YAML string) — the caller (STORY-15) deserialises the YAML before calling this gate.

---

## Dependencies

| Dependency | Type | Unblock Condition |
|---|---|---|
| STORY-06 (environment config) | Soft — provides fleet context to the caller | Fleet string must be resolvable before STORY-15 calls this gate |
| SPIKE-04 (test fixtures) | Hard — integration tests require fixtures; `known_keys` files derived from fixtures | Fixtures committed in operator-authored PR |
| STORY-07 (yaml_parse gate) | Soft — `GateResult` model must exist | STORY-07 defines the model |

---

## Acceptance Criteria

### AC-1: Key with matching type passes the gate

**Given** a `key_path` listed in `known_keys/<fleet>.yaml` with expected type `str`  
**And** `value` is a Python `str`  
**When** `validate_key_shape(key_path, value, fleet)` is called  
**Then** the function returns `GateResult(passed=True, error_code=None, detail=None, warnings=[])`

### AC-2: Key with mismatched type fails the gate

**Given** a `key_path` listed in `known_keys/<fleet>.yaml` with expected type `str`  
**And** `value` is a Python `list`  
**When** `validate_key_shape(key_path, value, fleet)` is called  
**Then** the function returns `GateResult(passed=False, error_code="key_shape_mismatch", detail="<key_path>: expected str, got list", warnings=[])`

### AC-3: Unknown key produces a warning, not a blocking failure

**Given** a `key_path` that is NOT listed in `known_keys/<fleet>.yaml`  
**And** `value` is any Python object  
**When** `validate_key_shape(key_path, value, fleet)` is called  
**Then** the function returns `GateResult(passed=True, error_code=None, detail=None, warnings=["unknown key: <key_path> — not in known_keys registry for fleet <fleet>"])`

### AC-4: Unknown fleet does not crash — it warns

**Given** a `fleet` string that has no corresponding `known_keys/<fleet>.yaml` file  
**When** `validate_key_shape(key_path, value, fleet)` is called  
**Then** the function returns `GateResult(passed=True, error_code=None, detail=None, warnings=["no known_keys registry found for fleet <fleet> — skipping shape check"])`  
**And** no exception propagates out of `validate_key_shape`

### AC-5: Gate integrates correctly with D14 pipeline ordering

**Given** Gates 1 and 2 have passed and the Apply All endpoint calls Gate 3  
**When** `validate_key_shape` returns `passed=False`  
**Then** the pipeline halts and returns HTTP 422 with body `{ "error_code": "key_shape_mismatch", "detail": "<message>", "warnings": [] }`  
**When** `validate_key_shape` returns `passed=True` with warnings  
**Then** the pipeline continues to Gate 4 and the warnings are accumulated for inclusion in the final response

---

## Definition of Done

- [ ] `bff/validation/key_shape.py` exists with public function `validate_key_shape(key_path: str, value: object, fleet: str) -> GateResult`
- [ ] `GateResult` model includes optional `warnings: list[str]` field (default `[]`)
- [ ] `known_keys/` directory created under `bff/validation/` with at least `alpin.yaml` and `dostoneu.yaml` (populated from SPIKE-04 fixture observations)
- [ ] Unknown key → warning, not error; unknown fleet → warning, not error
- [ ] Unit tests cover: known key + correct type (pass), known key + wrong type (fail), unknown key (pass with warning), unknown fleet (pass with warning)
- [ ] Unit tests verify `error_code == "key_shape_mismatch"` on type-mismatch cases
- [ ] Integration test uses key_paths observed in `tests/fixtures/alpin/` fixtures
- [ ] `pytest --cov --cov-fail-under=90` passes on `bff/validation/key_shape.py`
- [ ] `mypy` passes with zero errors
- [ ] No exception escapes `validate_key_shape`
- [ ] Story Status set to DONE

---

## D-Decisions Touched

| Decision | Relevance |
|---|---|
| **D14** | This story implements Gate 3 of the 5 mandatory server-side validation gates |

---

## SLO Assignment

**Write-path ≥99%** (rolling 7-day MR creation success rate)

Rationale: this gate sits on the hieradata write path. An overly strict `known_keys` registry that blocks valid writes would degrade write-path success rate. The warn-not-block policy for unknown keys is specifically designed to prevent registry lag from causing write-path failures.

---

## File Locations

- Implementation: `bff/validation/key_shape.py`
- Known-keys registry: `bff/validation/known_keys/alpin.yaml`, `bff/validation/known_keys/dostoneu.yaml`, `bff/validation/known_keys/dani.yaml`
- Shared model: `bff/validation/models.py`
- Unit tests: `tests/unit/validation/test_key_shape.py`
- Integration tests: `tests/integration/validation/test_key_shape_integration.py`
- Fixtures consumed: `tests/fixtures/alpin/`, `tests/fixtures/dostoneu/`

---

## Notes for Implementer

- The `known_keys/<fleet>.yaml` format should be a flat mapping: `key_path: type_name` where `type_name` is one of `"str"`, `"int"`, `"bool"`, `"list"`, `"dict"`. Example:
  ```yaml
  classes: list
  ntp::servers: list
  role::base::motd: str
  ```
- Load the registry files at module import time (or lazily on first call) using `functools.lru_cache` keyed on fleet name to avoid repeated disk reads.
- Type checking: `isinstance(value, expected_python_type)` where the `type_name` string is mapped to the Python type via a simple dict. Do not use `type(value).__name__` comparison (fragile).
- `None` values (YAML null) should pass shape validation with a warning rather than hard fail — a null value for any key_path may be a valid hieradata reset.
- Gate ordering: yaml_parse → yamllint → key_shape (this) → byte_diff_drift → secret_scan.
- The `fleet` values in this codebase are `alpin`, `dostoneu`, `dani` (see Domain Glossary). Do not accept the full GitLab project path (`env/environment-alpin`) as the `fleet` parameter — validate it is the short form.
