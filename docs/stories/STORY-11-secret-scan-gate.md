# STORY-11: secret_scan D14 Gate

**Status:** READY

---

## Summary

Implement Gate 5 of 5 in the D14 server-side validation pipeline. This gate scans the diff content of a hieradata change for credential patterns before the change is committed to GitLab. If any of the five registered patterns match, the write is blocked with `secret_leak_blocked`. Matched values are never written to logs, audit events, or error responses — only the pattern name and location (file line number if available) are reported.

This is the final gate in the D14 pipeline. It runs only after all four preceding gates have passed.

---

## Assumptions

1. `SPIKE-04` (test fixture capture) has a pass verdict and fixtures are committed before integration tests are written.
2. `GateResult` Pydantic v2 model is defined (by STORY-07 or earlier in the pipeline).
3. The `diff_content` parameter is the unified diff string (or the raw new-file content) that would be committed. The caller (STORY-15) determines whether to pass the full file or only the diff lines; either form is acceptable as long as the gate documentation is consistent with the caller's choice. This story documents the gate as receiving the full modified YAML string (not a unified diff) for simplicity — if the caller changes this, update both files in the same PR.
4. The gate does not call GitLab, PuppetDB, or the database.
5. The five mandatory patterns are specified below in the AC. Additional patterns may be added in future stories — do not hard-code the list in a way that prevents extension.

---

## Dependencies

| Dependency | Type | Unblock Condition |
|---|---|---|
| SPIKE-04 (test fixtures) | Hard — integration tests require real fixture YAML to confirm no false positives | Fixtures committed in operator-authored PR |
| STORY-07 (yaml_parse gate) | Soft — `GateResult` model must exist | STORY-07 defines the model |

---

## Acceptance Criteria

### AC-1: Content with no secret patterns passes the gate

**Given** a YAML string containing no credential-like values  
**When** `validate_secret_scan(diff_content)` is called  
**Then** the function returns `GateResult(passed=True, error_code=None, detail=None)`

### AC-2: AWS Access Key ID is detected and blocked

**Given** a YAML string containing a value matching the AWS Access Key ID pattern (`AKIA[0-9A-Z]{16}`)  
**When** `validate_secret_scan(diff_content)` is called  
**Then** the function returns `GateResult(passed=False, error_code="secret_leak_blocked", detail="pattern:aws_access_key line:<n>")`  
**And** the matched value itself does NOT appear in the `detail` string or in any log output

### AC-3: GCP Service Account key is detected and blocked

**Given** a YAML string containing a value matching the GCP Service Account key pattern (JSON blob containing `"private_key_id"` and `"client_email"` fields characteristic of a GCP SA JSON)  
**When** `validate_secret_scan(diff_content)` is called  
**Then** the function returns `GateResult(passed=False, error_code="secret_leak_blocked", detail="pattern:gcp_sa_key line:<n>")`

### AC-4: PEM private key is detected and blocked

**Given** a YAML string containing a value matching `-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----`  
**When** `validate_secret_scan(diff_content)` is called  
**Then** the function returns `GateResult(passed=False, error_code="secret_leak_blocked", detail="pattern:pem_private_key line:<n>")`

### AC-5: GitLab Personal Access Token is detected and blocked

**Given** a YAML string containing a value matching the GitLab PAT pattern (`glpat-[0-9a-zA-Z\-_]{20}`)  
**When** `validate_secret_scan(diff_content)` is called  
**Then** the function returns `GateResult(passed=False, error_code="secret_leak_blocked", detail="pattern:gitlab_pat line:<n>")`

### AC-6: High-entropy token is detected and blocked

**Given** a YAML string containing a bare token value with Shannon entropy ≥ 4.5 bits/char and length ≥ 32 characters that does not resemble a known-benign pattern (e.g. a UUID or a base64-encoded certificate thumbprint)  
**When** `validate_secret_scan(diff_content)` is called  
**Then** the function returns `GateResult(passed=False, error_code="secret_leak_blocked", detail="pattern:high_entropy_token line:<n>")`

### AC-7: Matched values never appear in logs or error responses

**Given** any call to `validate_secret_scan` that returns `passed=False`  
**When** the BFF logs the gate failure or returns the 422 error response  
**Then** no log line and no field in the HTTP response body contains the matched secret value  
**And** the `detail` field contains only the pattern name and line number

### AC-8: False-positive rate against real fixtures is zero

**Given** all fixture YAML files committed under `tests/fixtures/alpin/` and `tests/fixtures/dostoneu/`  
**When** `validate_secret_scan` is run against each fixture file  
**Then** every call returns `GateResult(passed=True, ...)` — no fixture file triggers a false positive

### AC-9: Gate integrates correctly as the final D14 gate

**Given** Gates 1–4 have passed and the Apply All endpoint calls Gate 5  
**When** `validate_secret_scan` returns `passed=False`  
**Then** the pipeline halts and returns HTTP 422 with body `{ "error_code": "secret_leak_blocked", "detail": "pattern:<name> line:<n>" }`  
**When** `validate_secret_scan` returns `passed=True`  
**Then** the D14 pipeline is complete and the write proceeds to GitLab

---

## Definition of Done

- [ ] `bff/validation/secret_scan.py` exists with public function `validate_secret_scan(diff_content: str) -> GateResult`
- [ ] All five patterns implemented: `aws_access_key`, `gcp_sa_key`, `pem_private_key`, `gitlab_pat`, `high_entropy_token`
- [ ] Matched values never appear in `detail`, log output, or any downstream error response
- [ ] Unit tests cover: clean content (pass), each of the 5 patterns individually (fail), content with multiple patterns (fail on first match)
- [ ] Unit tests verify `error_code == "secret_leak_blocked"` on all failure cases
- [ ] Unit test verifies that `detail` does not contain the matched value string
- [ ] Integration test runs all fixture files from `tests/fixtures/alpin/` and `tests/fixtures/dostoneu/` and asserts zero false positives
- [ ] `pytest --cov --cov-fail-under=90` passes on `bff/validation/secret_scan.py`
- [ ] `mypy` passes with zero errors
- [ ] No exception escapes `validate_secret_scan`
- [ ] Story Status set to DONE

---

## D-Decisions Touched

| Decision | Relevance |
|---|---|
| **D14** | This story implements Gate 5 (final gate) of the 5 mandatory server-side validation gates |

---

## SLO Assignment

**Write-path ≥99%** (rolling 7-day MR creation success rate)

Rationale: this gate sits on the hieradata write path. An excessive false-positive rate (e.g. high-entropy threshold too aggressive) would block legitimate writes. The high-entropy threshold (≥4.5 bits/char, length ≥32) must be tuned against the fixture corpus before shipping.

---

## File Locations

- Implementation: `bff/validation/secret_scan.py`
- Shared model: `bff/validation/models.py`
- Unit tests: `tests/unit/validation/test_secret_scan.py`
- Integration tests: `tests/integration/validation/test_secret_scan_integration.py`
- Fixtures consumed: `tests/fixtures/alpin/`, `tests/fixtures/dostoneu/`

---

## Notes for Implementer

- Use Python `re` compiled patterns. Define patterns as module-level constants so they compile once.
- Five pattern constants:
  - `AWS_ACCESS_KEY`: `r'AKIA[0-9A-Z]{16}'`
  - `GCP_SA_KEY`: `r'"private_key_id"\s*:\s*"[^"]+"'` (detect presence of the GCP SA JSON field — a JSON blob embedded in YAML is a strong signal)
  - `PEM_PRIVATE_KEY`: `r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'`
  - `GITLAB_PAT`: `r'glpat-[0-9a-zA-Z\-_]{20}'`
  - `HIGH_ENTROPY_TOKEN`: entropy calculation using `math.log2` over character frequency; apply only to bare string values ≥32 chars that are not hex SHA digests or UUIDs (add an allow-list regex for those forms)
- For the `detail` field: use `re.sub` or group slicing to extract only the line number — never include `match.group(0)` or `match.group()` in any output path.
- High-entropy false-positive mitigation: SHA-256 hex digests (64 hex chars), UUIDs (`[0-9a-f-]{36}`), and base64 certificate thumbprints often exceed the entropy threshold. Add a pre-check regex that allows these known-benign forms through before computing entropy. Tune against fixtures (AC-8).
- The `CLAUDE.md` Enterprise Standards section mandates: "D14 secret_leak gate must run against every committed file diff, not just 'obviously suspicious' keys."
- Gate ordering: yaml_parse → yamllint → key_shape → byte_diff_drift → secret_scan (this — final gate).
