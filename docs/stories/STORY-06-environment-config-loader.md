# Story: [STORY-06] Environment Config Loader
Status: READY
D-decisions touched: D15 (per-Puppet-environment target branch config), D13 (bench allowlists)

## Why (from PRD)
The `environment_configs` table stores per-fleet, per-Puppet-environment configuration: GitLab project IDs, target branches, layer counts, bench allowlists (D13), and known_keys paths (D14). This story creates the loader that reads hand-authored config files at BFF startup and populates the `environment_configs` table. MVP supports alpin (3 layers) and dostoneu (4 layers) only.

## Assumptions (inherited from PRD + ARCHITECTURE)
- Hand-authored config files exist in `bff/config/environments/` before BFF startup: `alpin.yaml` and `dostoneu.yaml`.
- Each file structure:
  ```yaml
  fleet: alpin
  puppet_environments:
    devel:
      gitlab_project_id: 1211
      gitlab_project_path: "env/environment-alpin"
      target_branch: devel
      layer_count: 3
      hiera_yaml_path: "hiera.yaml"
      bench_allowlist:
        - '^box1-t(100|101|125)\.alpin\.21net\.com$'
      known_keys_path: "bff/config/known_keys/alpin.yaml"
      active: true
    staging:
      gitlab_project_id: 1211
      gitlab_project_path: "env/environment-alpin"
      target_branch: staging
      layer_count: 3
      hiera_yaml_path: "hiera.yaml"
      bench_allowlist:
        - '^box1-t(100|101|125)\.alpin\.21net\.com$'
      known_keys_path: "bff/config/known_keys/alpin.yaml"
      active: true
  ```
- Bench allowlists are regex patterns stored as JSONB arrays.
- Loader runs once at BFF startup (not on every request).
- If a fleet+Puppet-environment combo already exists in the table, the loader updates it (upsert behaviour).
- dani fleet config is NOT written yet (phase-2).

## What to Build
1. `bff/config/environments/alpin.yaml` — hand-authored config for alpin fleet (content provided by operator from System Design Brief §9a data)
2. `bff/config/environments/dostoneu.yaml` — hand-authored config for dostoneu fleet
3. `bff/loaders/environment_config_loader.py` — loader logic:
   - `async def load_environment_configs(db: Session)` — reads all `.yaml` files in `bff/config/environments/`, parses each, upserts rows into `environment_configs` table
   - Upsert: `ON CONFLICT (fleet, puppet_environment) DO UPDATE`
   - Logs each loaded config at INFO level
4. `bff/main.py` lifespan event — call `load_environment_configs` on startup

## Affected Files
- bff/config/environments/alpin.yaml → create (hand-authored by operator)
- bff/config/environments/dostoneu.yaml → create (hand-authored by operator)
- bff/loaders/environment_config_loader.py → create (new loader)
- bff/main.py → modify (lifespan startup event calls loader)
- tests/test_environment_config_loader.py → create (unit tests)
- tests/integration/test_environment_config_upsert.py → create (integration tests)

## BFF Endpoint Spec
Not an endpoint — this is a startup loader.

## Cross-Cutting Concerns

| Concern | Owner | Coordinates With | Detail |
|---------|-------|-----------------|--------|
| Config file authoring | operator | bff-dev | alpin.yaml and dostoneu.yaml are hand-authored from System Design Brief §9a data before BFF first start |
| Upsert vs insert-only | bff-dev | bff-dev (migrations) | Loader uses upsert so re-starting BFF doesn't error on duplicate key |
| Phase-2 dani config | operator | bff-dev | dani.yaml will be authored in phase-2; loader already supports it (reads all `.yaml` in directory) |
| Bench allowlist format | bff-dev | STORY-12 (D13 envelope) | Regex patterns stored as JSONB array; D13 envelope compiles and tests each pattern |

## Validation Commands

BFF agent:
```bash
cd bff && python -m mypy . && python -m pytest tests/test_environment_config_loader.py tests/integration/test_environment_config_upsert.py -v --cov --cov-fail-under=90
# Smoke test loader:
python -m bff.loaders.environment_config_loader  # should upsert alpin and dostoneu rows
psql $DATABASE_URL -c "SELECT * FROM environment_configs;"  # should list 4 rows (alpin devel/staging, dostoneu devel/staging)
```

## Tests Required

Unit (`tests/test_environment_config_loader.py`):
- `test_load_alpin_config` — parse `alpin.yaml`, assert fleet, project_id, layer_count, bench_allowlist
- `test_load_dostoneu_config` — parse `dostoneu.yaml`, assert 4 layers
- `test_loader_upserts_existing_row` — insert a row, run loader, assert row is updated (not duplicate created)
- `test_loader_skips_malformed_yaml` — inject malformed YAML, assert loader logs error and continues

Integration (`tests/integration/test_environment_config_upsert.py`):
- `test_loader_against_mock_postgres` — fixture provides Postgres, run loader, assert 4 rows inserted (alpin devel/staging, dostoneu devel/staging)
- `test_loader_upsert_updates_existing` — insert alpin devel with old layer_count, run loader, assert layer_count updated to 3

Coverage targets:
- BFF new business logic: ≥90% line coverage (`pytest --cov --cov-fail-under=90`)

## Acceptance Criteria
- [ ] Given `bff/config/environments/alpin.yaml` exists with correct structure, when the loader runs at BFF startup, then 2 rows are upserted into `environment_configs` (alpin devel, alpin staging)
- [ ] Given `bff/config/environments/dostoneu.yaml` exists with correct structure, when the loader runs at BFF startup, then 2 rows are upserted into `environment_configs` (dostoneu devel, dostoneu staging)
- [ ] Given an `environment_configs` row already exists for alpin devel, when the loader runs again, then the row is updated (not duplicated)
- [ ] Given a malformed YAML file exists in `bff/config/environments/`, when the loader runs, then an error is logged and the loader continues processing other files
- [ ] Given the BFF starts, when the loader completes, then all active fleet+Puppet-environment combos are queryable from `environment_configs`

## Definition of Done
- [ ] All acceptance criteria pass
- [ ] Python mypy passes with zero errors
- [ ] All unit tests green (`tests/test_environment_config_loader.py`)
- [ ] All integration tests green (`tests/integration/test_environment_config_upsert.py`)
- [ ] BFF coverage ≥90% (`pytest --cov --cov-fail-under=90`)
- [ ] `alpin.yaml` and `dostoneu.yaml` committed with correct hand-authored content
- [ ] Loader runs at BFF startup (lifespan event)
- [ ] Upsert behaviour tested (no duplicate key errors on re-run)
- [ ] Code Reviewer agent approved
- [ ] Security Sentinel agent approved
