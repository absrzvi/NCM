# STORY-13: GET /api/policies/tree (D10 hiera.yaml parsing)

**Status**: READY
**Tier**: 3 — Policies Module
**Module**: `bff/routers/policies_router.py`, `bff/clients/gitlab_client.py`

---

## Summary

Implement `GET /api/policies/tree?fleet=<fleet>` which reads the fleet's `hiera.yaml` at load time (from GitLab via `gitlab_client`), reconstructs the dynamic layer structure (3, 4, or 9 layers depending on fleet), fetches the hieradata files for each layer, and returns a structured tree of keys.

Keys sourced from `hiera_file` layers must carry a `routed_file` note indicating which file the value lives in. Keys sourced from `hiera_mysql` layers must carry an `external_db` badge indicating the value is external and not editable through this UI.

**This story is blocked on SPIKE-01 passing** (verdict: `plugin_is_static: true` and inventory files committed). Do not begin implementation until the SPIKE-01 pass verdict exists in the repository.

---

## Assumptions

1. SPIKE-01 has passed: the `hiera_file` plugin contains no conditional logic, no per-fact branches, and no environment-aware routing. If SPIKE-01 fails, D10's static reconstruction will diverge from Puppet's runtime resolution and this story must be escalated for a new ADR before proceeding.
2. STORY-05 is DONE: `gitlab_client.py` exposes async methods for fetching file contents and listing project files.
3. `hiera.yaml` lives at the repository root of each fleet's GitLab project (`env/environment-<fleet>`). If it lives elsewhere, this assumption must be corrected and a blocker raised before implementation.
4. Fetching `hiera.yaml` and all hieradata files in a single request cycle is acceptable latency-wise for the p95 <500ms read-path SLO; if not, a short-lived parse cache (in-process, TTL configurable) may be introduced but only if benchmarks show it is needed.
5. Fleet names in this MVP are `alpin` (3 layers), `dostoneu` (4 layers), and `dani` (9 layers). No other fleets are in scope.

---

## Dependencies

| Dependency | Status Required | Notes |
|---|---|---|
| SPIKE-01 (hiera_file plugin inventory) | PASS verdict committed | Blocks D10 static reconstruction |
| STORY-05 (downstream client wrappers) | DONE | `gitlab_client` required |

---

## Acceptance Criteria

### AC-1: Successful tree render for a 3-layer fleet

**Given** a valid Keycloak JWT (viewer role or above) and fleet `alpin` whose `hiera.yaml` declares 3 layers,
**When** `GET /api/policies/tree?fleet=alpin` is called,
**Then** the response is HTTP 200 with a JSON body containing exactly 3 layer objects, each with a `layer_name`, `layer_index`, `backend` field (`hiera_file` or `hiera_mysql`), and a `keys` array of key objects.

### AC-2: Successful tree render for a 9-layer fleet

**Given** a valid Keycloak JWT and fleet `dani` whose `hiera.yaml` declares 9 layers,
**When** `GET /api/policies/tree?fleet=dani` is called,
**Then** the response is HTTP 200 with exactly 9 layer objects.

### AC-3: hiera_file keys carry routed-file note

**Given** a key resolved from a `hiera_file` backend layer,
**When** the tree response is returned,
**Then** the key object includes `"source_backend": "hiera_file"` and a `"routed_file"` field containing the relative path of the hieradata file that holds the key (e.g. `"hieradata/common.yaml"`).

### AC-4: hiera_mysql keys carry external_db badge

**Given** a key resolved from a `hiera_mysql` backend layer,
**When** the tree response is returned,
**Then** the key object includes `"source_backend": "hiera_mysql"` and `"external_db": true`. No value is returned for this key — the value field is omitted or null.

### AC-5: Unknown fleet returns 404

**Given** a valid JWT and a fleet name not in `{alpin, dostoneu, dani}`,
**When** `GET /api/policies/tree?fleet=unknown` is called,
**Then** the response is HTTP 404 with a consistent error shape `{ "detail": "fleet not found" }`.

### AC-6: Missing or invalid JWT returns 401

**Given** a request with no Authorization header or an expired/malformed JWT,
**When** `GET /api/policies/tree` is called,
**Then** the response is HTTP 401. The response body is identical in shape whether the token is absent, expired, or malformed (never reveal which).

### AC-7: GitLab unreachable returns 502

**Given** the GitLab API is unreachable (simulated by fixture that raises `httpx.ConnectError`),
**When** `GET /api/policies/tree?fleet=alpin` is called with a valid JWT,
**Then** the response is HTTP 502 with `{ "detail": "upstream_unavailable" }`. No stack trace is exposed.

### AC-8: hiera.yaml parse error returns 422

**Given** a fleet whose `hiera.yaml` content is malformed (not valid YAML),
**When** `GET /api/policies/tree?fleet=alpin` is called,
**Then** the response is HTTP 422 with `{ "detail": "hiera_yaml_parse_failed" }`.

---

## Definition of Done

- [ ] TypeScript compiles with zero errors (`npx tsc --noEmit`) — not applicable to this BFF-only story; mark N/A
- [ ] Python mypy passes with zero errors on all new/modified modules
- [ ] All security tests pass:
  - [ ] Unauthenticated request → 401
  - [ ] Expired JWT → 401
  - [ ] Malformed JWT → 401
  - [ ] Valid JWT, viewer role → 200 (read-only endpoint; viewer may read)
- [ ] BFF unit tests cover:
  - [ ] `hiera.yaml` parsing logic for 3, 4, and 9 layer configs
  - [ ] `hiera_file` key annotation (routed_file)
  - [ ] `hiera_mysql` key annotation (external_db badge)
  - [ ] Unknown fleet → 404
  - [ ] GitLab unavailable → 502
  - [ ] Malformed hiera.yaml → 422
- [ ] Integration tests run against fixtures (never real GitLab); fixture data committed in SPIKE-04 PR
- [ ] BFF coverage ≥90% (`pytest --cov --cov-fail-under=90`) on new business logic
- [ ] All Playwright E2E: happy path tree render + auth failure + malformed hiera.yaml error display
- [ ] QA score ≥ 85/100
- [ ] Code Reviewer agent approved (no Critical issues)
- [ ] Security Sentinel agent approved (no Critical issues)
- [ ] `docs/API_CONTRACTS.md` updated with `GET /api/policies/tree` contract
- [ ] Story file Status set to DONE

---

## D-Decisions Touched

| Decision | How it applies |
|---|---|
| **D10** | `hiera.yaml` parsed at BFF load time (or per-request with short cache); static layer reconstruction; no runtime Puppet resolution. Must not proceed if SPIKE-01 fails. |
| **D1** | Browser never calls GitLab directly; BFF fetches hieradata via `gitlab_client` and returns structured JSON. |
| **D6** | All GitLab operations use `python-gitlab` via the shared `gitlab_client` wrapper (never raw `httpx` calls to GitLab). |

---

## SLO Assignment

**Governing SLO**: Read-path p95 < 500ms (excluding PuppetDB — PuppetDB is not called by this endpoint).

The endpoint fetches `hiera.yaml` plus N hieradata files (N = layer count × files-per-layer). For the 9-layer dani fleet this may involve significant GitLab calls. If benchmarking during integration testing shows the p95 target cannot be met without caching, introduce an in-process parse cache (TTL ≤ 60s, invalidated on MR merge webhook if feasible) — but only if the benchmark data justifies it. Do not add the cache speculatively.

---

## Implementation Notes (for bff-dev)

- Route file: `bff/routers/policies_router.py`
- Response model: `PolicyTreeResponse` in `bff/models/policies.py` (Pydantic v2, no `any`)
- Use `get_current_user` (Iron Rule 2); no `customer_id` scoping (D3 / Iron Rule 3)
- All GitLab calls via `gitlab_client.get_file(project_path, file_path, ref)` — async, no blocking I/O (Iron Rule 5)
- The fleet-to-project mapping is `env/environment-<fleet>` (e.g. `alpin` → `env/environment-alpin`). Accept legacy "env project" path on read; emit `fleet` in response.
- Never call `yaml.safe_load` on hieradata files — only use `ruamel.yaml` for any YAML write operation (Iron Rule 11 applies to writes; reads may use `yaml.safe_load` but be consistent with D5 for anything that will be round-tripped)
- Tests must use fixtures from `tests/fixtures/alpin/`, `tests/fixtures/dostoneu/`, `tests/fixtures/dani/` — never make real GitLab calls (Iron Rule final bullet)
