Read-only prime for the bff-dev agent. Read these files and summarise:
- bff/main.py
- bff/auth.py
- bff/routers/ (one-line summary per router)
- bff/clients/gitlab_client.py
- bff/clients/puppetdb_client.py
- bff/clients/puppet_server_client.py
- bff/middleware/idempotency.py
- bff/envelopes/safety_envelope.py
- bff/validation/ (one-line summary per gate)
- bff/history/parameter_history.py
- docs/API_CONTRACTS.md
- docs/DATA_MODEL.md
- docs/HANDOFF.md

Output a compact summary:
- Endpoints currently implemented and their SLO assignments
- Pydantic models defined
- Downstream client methods available
- Any gaps: API contracts listed in API_CONTRACTS.md that have no router implementation
- D-decisions touched in current codebase

Do not read test files. This prime is intentionally scoped to source + contracts.
