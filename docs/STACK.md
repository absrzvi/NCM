# Technology Stack Decisions

## Frontend
- React 18 + TypeScript (strict) + Vite: modern, fast, type-safe
- React Router v6: five Config routes
- Zustand: lightweight global state, no boilerplate
- Recharts: for any chart in Compliance / Deployments dashboards
- CSS Modules + CSS custom properties: scoped styles, zero runtime cost
- keycloak-js (@react-keycloak/web): JWT acquisition + silent refresh 60s before expiry

Not used (do not add): react-leaflet, Tailwind, Redux, Material UI, any chart lib other than Recharts.

## BFF
- Python FastAPI: async-native, auto-generates OpenAPI docs, Pydantic integration
- httpx: async HTTP client
- python-jose: Keycloak JWT validation
- Pydantic v2: strict validation, serialisation
- python-gitlab: all GitLab operations (wrapped via asyncio.to_thread)
- ruamel.yaml (round-trip): all hieradata writes
- yamllint (library): D14 gate 2

## Data
- PostgreSQL 16 — single container on the Linux host (single primary, named data volume, nightly `pg_dump` backup to `/var/backups/nmsplus/pg/`, 30-day retention). No operator, no replicas, no failover cluster.
- Tables owned by BFF: draft_change_sets, draft_parameter_edits, audit_events, parameter_history_cache, idempotency_keys, user_preferences, environment_configs

## Infrastructure
- GitLab CE monorepo: single source of truth for all code (hieradata lives in separate per-fleet projects)
- **Deployment host: one Linux VM in our DC.** Docker Engine + Docker Compose orchestrate the app. No Kubernetes, no ingress controller, no service mesh.
- Containers on the host: `nginx` (reverse proxy + static frontend), `bff` (FastAPI), `postgres` (data), `keycloak` (auth), `postgres-backup` (cron sidecar).
- Docker: reproducible builds per service (each Dockerfile in `bff/` and `frontend/`), images pushed to GitLab Container Registry, pulled on the host.
- Single BFF container per host — `restart: unless-stopped`, no second instance, no autoscaling (D8).
- Secrets on host: `/etc/nmsplus/secrets/*.env` (mode 0600), loaded via Compose `env_file:`. Not in images, not in Git, not in Compose literal `environment:` blocks.
- Keycloak: company-wide SSO (OIDC, RS256). Realm import JSON at `deploy/keycloak/realm-nmsplus.json`.

## Key Architectural Decisions
- The browser speaks only to the BFF. The BFF holds all downstream credentials.
- Single-tenant MVP — authZ is by role, not tenant scope.
- Single-pod BFF with Postgres-backed state (drafts, history cache, idempotency) — no horizontal scaling.
