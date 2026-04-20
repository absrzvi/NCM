# Spike: [SPIKE-04] Test Fixture Capture
Status: READY
D-decisions touched: None (test infrastructure only)

## Why (from PRD)
All BFF integration tests must run against captured fixtures, never against live GitLab/PuppetDB/Puppet Server (CLAUDE.md §What Agents Must NEVER Do). This spike produces the complete fixture corpus for alpin and dostoneu fleets, plus canned GitLab API responses for MR/commit operations.

## Assumptions
- The operator has read access to the live GitLab projects: `env/environment-alpin` (1211) and `env/environment-dostoneu` (1136).
- The operator has a GitLab PAT with `read_api` scope for these projects.
- The `scripts/refresh_fixture.py` script exists and includes secret scrubbing logic (strips secret-flagged keys, redacts tokens/passwords, sanitises email addresses).
- Fixtures are captured at a specific commit SHA for reproducibility.
- Fixtures are committed in an explicit PR authored by a named operator; the refresh script must NOT run in CI (CLAUDE.md Human Gate 5).

## What to Capture
Run `scripts/refresh_fixture.py` for each fleet:
```bash
python scripts/refresh_fixture.py \
  --fleet alpin \
  --project-id 1211 \
  --branch devel \
  --output tests/fixtures/alpin/ \
  --scrub-secrets
```

```bash
python scripts/refresh_fixture.py \
  --fleet dostoneu \
  --project-id 1136 \
  --branch devel \
  --output tests/fixtures/dostoneu/ \
  --scrub-secrets
```

Fixture directory structure:
```
tests/fixtures/alpin/
  hieradata/
    common.yaml
    nodes/
      box1-t100.alpin.21net.com.yaml
      box1-t101.alpin.21net.com.yaml
      ...
    files/
      [any hiera_file routed content]
  hiera.yaml
  capture_metadata.yaml  # SHA, date, operator, scrubbed keys list

tests/fixtures/dostoneu/
  hieradata/
    common.yaml
    actions.yaml
    nodes/
      box1-t121.dostoneu-bench.21net.com.yaml
      ...
    files/
      [any hiera_file routed content]
  hiera.yaml
  capture_metadata.yaml

tests/fixtures/gitlab_mock/
  mr_create_response.json       # Canned POST /projects/:id/merge_requests response
  commit_log_response.json      # Canned GET /projects/:id/repository/commits response
  branch_create_response.json   # Canned POST /projects/:id/repository/branches response
  file_get_response.json        # Canned GET /projects/:id/repository/files/:path response
```

Each `capture_metadata.yaml`:
```yaml
fleet: alpin
project_id: 1211
project_path: "env/environment-alpin"
branch: devel
commit_sha: "<SHA at time of capture>"
captured_at: "2026-04-20T14:32:00Z"
captured_by: "<operator name>"
scrubbed_keys:
  - "engineering_pages::credentials_password"
  - "engineering_pages::ssl_key"
  - "obn::secret"
  - "portal::autologin_salt_hash"
  - "mar3_captiveportal_api::salt_hash"
  - "snmpd::usersv3"
  - "mqtt_bridge::brokers.*.credentials"
notes: |
  All secret-flagged keys have been replaced with the placeholder: "REDACTED_IN_FIXTURE"
```

## Pass Criteria
- `tests/fixtures/alpin/` contains complete hieradata snapshot with all files, correct directory structure, and `capture_metadata.yaml`.
- `tests/fixtures/dostoneu/` contains complete hieradata snapshot with all files, correct directory structure, and `capture_metadata.yaml`.
- `tests/fixtures/gitlab_mock/` contains at least 4 canned GitLab API responses (MR create, commit log, branch create, file get).
- All secret-flagged keys are scrubbed (replaced with `REDACTED_IN_FIXTURE` or removed).
- No real tokens, passwords, or PII in any fixture file.
- Fixtures committed in an explicit PR authored by the operator who ran the script.

## Fail Criteria
- Secret scrubbing missed a real token or password → security violation, fixtures must be re-captured.
- Fixture directory structure doesn't match the live GitLab project structure → integration tests will fail to find files.

## Affected Files
- tests/fixtures/alpin/ → create entire directory tree
- tests/fixtures/dostoneu/ → create entire directory tree
- tests/fixtures/gitlab_mock/ → create with canned responses
- scripts/refresh_fixture.py → must exist (written in a prior setup story or by operator)
- docs/stories/SPIKE-04-fixture-capture.md → this file (deliverable)

## Deliverables
1. `tests/fixtures/alpin/` committed with complete hieradata snapshot
2. `tests/fixtures/dostoneu/` committed with complete hieradata snapshot
3. `tests/fixtures/gitlab_mock/` committed with canned GitLab API responses
4. PR authored by named operator (not CI) with commit message: "SPIKE-04: Capture test fixtures for alpin and dostoneu at <SHA>"
5. Spike report appended to this file under "## Capture Report" section

## Capture Report
- Date: 2026-04-20
- Operator: Claude Code agent (SPIKE-04 implementation) — fixture structure created; real SHAs require operator to run `scripts/refresh_fixture.py`
- alpin commit SHA: FIXTURE_PLACEHOLDER_SHA (update after running refresh_fixture.py against live project 1211)
- dostoneu commit SHA: FIXTURE_PLACEHOLDER_SHA (update after running refresh_fixture.py against live project 1136)
- Scrubbed keys count: 7 (engineering_pages::credentials_password, engineering_pages::ssl_key, obn::secret, portal::autologin_salt_hash, mar3_captiveportal_api::salt_hash, snmpd::usersv3, mqtt_bridge::brokers.*.credentials)
- Any issues encountered:
  - No live GitLab access from the agent — real hieradata content and SHAs are not available.
  - Fixture files use representative structure and scrubbed placeholder values.
  - Operator must run `scripts/refresh_fixture.py` for each fleet to populate real content and update `capture_metadata.yaml` with the real commit SHA.
  - All placeholder values contain no real secrets, tokens, passwords, or PII.

## Verdict
PARTIAL — Fixture directory structure, scrubbed skeleton files, gitlab_mock canned responses, and `scripts/refresh_fixture.py` are all in place; operator must run the refresh script against live GitLab to populate real hieradata content and commit SHAs before STORY-34 integration tests can execute against non-trivial data.

## Blocks
- STORY-34 (BFF integration tests — all tests require fixtures)
- Any story with Definition of Done clause "integration tests pass" — cannot execute without fixtures

## Acceptance Criteria
- [ ] Given the operator has GitLab read access, when `scripts/refresh_fixture.py` is run for alpin, then a complete hieradata snapshot is written to `tests/fixtures/alpin/`
- [ ] Given the operator has GitLab read access, when `scripts/refresh_fixture.py` is run for dostoneu, then a complete hieradata snapshot is written to `tests/fixtures/dostoneu/`
- [ ] Given fixtures are captured, when secret scrubbing runs, then no real tokens, passwords, or PII exist in any fixture file
- [ ] Given fixtures are scrubbed, when `capture_metadata.yaml` is written, then the commit SHA, date, operator, and scrubbed keys list are recorded
- [ ] Given all fixtures are ready, when they are committed, then the PR is authored by the operator (not CI) and references SPIKE-04

## Definition of Done
- [ ] `tests/fixtures/alpin/` committed with complete hieradata and metadata
- [ ] `tests/fixtures/dostoneu/` committed with complete hieradata and metadata
- [ ] `tests/fixtures/gitlab_mock/` committed with canned GitLab API responses
- [ ] No secrets or PII in any fixture file (manual spot-check by security reviewer)
- [ ] PR authored by named operator, not CI
- [ ] Capture report section populated with SHA, operator, date, and scrubbed keys count
- [ ] Verdict: PASS
- [ ] STORY-34 and all integration-test-dependent stories unblocked
