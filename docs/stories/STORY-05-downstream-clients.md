# Story: [STORY-05] Downstream Client Wrappers
Status: READY
D-decisions touched: D6 (python-gitlab), D9 (httpx for all HTTP), D1 (BFF proxies all downstream calls)

## Why (from PRD)
The BFF calls four downstream services: GitLab (D6 python-gitlab), PuppetDB (httpx), Puppet Server (httpx), and Keycloak JWKS (httpx for RS256 key fetch). D9 mandates httpx for all outbound HTTP. Iron Rule 1 requires the frontend never calls these services directly. This story creates the four client wrappers with connection pooling, timeout enforcement, and error handling.

## Assumptions (inherited from PRD + ARCHITECTURE)
- All downstream credentials are loaded from environment variables pointing to host-side secret files (`/etc/nmsplus/secrets/*.env`, mode 0600).
- GitLab service account PAT has `api` scope on `env/environment-alpin` (1211) and `env/environment-dostoneu` (1136) only.
- PuppetDB token is read-only.
- Puppet Server token is write-capable (separate secret file from PuppetDB).
- Keycloak JWKS URI is public (no auth required for JWKS fetch).
- All clients use `httpx.AsyncClient` with connection pooling (max 10 connections per client).
- Default timeout: 10s for GitLab, 10s for PuppetDB, 10s for Puppet Server, 10s for Keycloak JWKS.
- `/readyz` health check timeout: 5s (overrideable per call).
- Error handling: all clients wrap exceptions and raise `HTTPException(502, detail="Downstream error: <service> <summary>")` with correlation ID logged.

## What to Build
Four client modules in `bff/clients/`:

1. `gitlab_client.py` — wraps `python-gitlab` library:
   - `async def get_gitlab_client() -> gitlab.Gitlab` — returns configured `python-gitlab` client
   - Environment variables: `GITLAB_URL`, `GITLAB_TOKEN`
   - Timeout: 10s default
   - Error wrapper: converts `gitlab.exceptions.GitlabError` to `HTTPException(502)`

2. `puppetdb_client.py` — httpx-based PQL client:
   - `async def query_puppetdb(pql: str) -> list[dict]` — executes PQL query
   - `async def get_node_facts(certname: str) -> dict` — fetches facts for certname
   - Environment variables: `PUPPETDB_URL`, `PUPPETDB_TOKEN`
   - Timeout: 10s default
   - Error wrapper: converts `httpx.TimeoutException`, `httpx.ConnectError` to `HTTPException(502)`

3. `puppet_server_client.py` — httpx-based `/run-force` client:
   - `async def trigger_puppet_run(certname: str, environment: str) -> dict` — calls Puppet Server `/run-force` (NOTE: this story only creates the client; D13 envelope logic is STORY-12)
   - Environment variables: `PUPPET_SERVER_URL`, `PUPPET_SERVER_TOKEN`
   - Timeout: 10s default
   - Error wrapper: converts httpx exceptions to `HTTPException(502)`

4. `keycloak_jwks.py` — httpx-based JWKS fetcher (already partially covered in STORY-02; this story ensures it's in `clients/` with proper error handling):
   - `async def fetch_jwks() -> dict` — fetches JWKS from Keycloak
   - Environment variables: `KEYCLOAK_JWKS_URI`
   - Timeout: 10s default (5s for `/readyz` calls)
   - Error wrapper: converts httpx exceptions to `HTTPException(502)`

All clients use a shared httpx connection pool per client instance (singleton pattern or FastAPI lifespan context).

## Affected Files
- bff/clients/gitlab_client.py → create (new client)
- bff/clients/puppetdb_client.py → create (new client)
- bff/clients/puppet_server_client.py → create (new client)
- bff/clients/keycloak_jwks.py → modify or create (ensure proper error handling)
- bff/main.py → modify (lifespan context to initialise httpx clients)
- tests/test_clients.py → create (unit tests with mocked httpx)
- tests/integration/test_clients_error_handling.py → create (integration tests with fixture error injection)

## BFF Endpoint Spec
Not an endpoint — these are shared client libraries used by routers.

## Cross-Cutting Concerns

| Concern | Owner | Coordinates With | Detail |
|---------|-------|-----------------|--------|
| Secret storage | devops | bff-dev | All tokens loaded from `/etc/nmsplus/secrets/*.env` via Docker Compose `env_file` directive |
| Connection pooling | bff-dev | bff-dev (all routers) | One httpx.AsyncClient per downstream service, max 10 connections per client |
| Timeout enforcement | bff-dev | all routers | Default 10s; `/readyz` overrides to 5s |
| Error message sanitisation | bff-dev | security-sentinel | 502 detail never leaks downstream URLs, tokens, or stack traces — only service name + generic error |

## Validation Commands

BFF agent:
```bash
cd bff && python -m mypy . && python -m pytest tests/test_clients.py tests/integration/test_clients_error_handling.py -v --cov --cov-fail-under=90
```

## Security Tests (mandatory)
- [ ] GitLab client error does not leak `GITLAB_TOKEN` in exception message
- [ ] PuppetDB client error does not leak `PUPPETDB_TOKEN` in exception message
- [ ] Puppet Server client error does not leak `PUPPET_SERVER_TOKEN` in exception message
- [ ] All clients return 502 with sanitised `detail` (no downstream URLs, no tokens, no stack traces)
- [ ] GitLab client enforces 10s timeout (mock 15s delay, assert TimeoutException converted to 502)
- [ ] PuppetDB client enforces 10s timeout
- [ ] Puppet Server client enforces 10s timeout
- [ ] Keycloak JWKS client enforces 10s timeout (or 5s when called from `/readyz`)

## Tests Required

Unit (`tests/test_clients.py`):
- `test_gitlab_client_success` — mock gitlab library, assert client returns expected data
- `test_gitlab_client_timeout` — mock 15s delay, assert 502
- `test_gitlab_client_connection_error` — mock connection refused, assert 502
- `test_puppetdb_client_pql_query` — mock httpx response, assert PQL result parsed
- `test_puppetdb_client_timeout` — mock timeout, assert 502
- `test_puppet_server_client_run_force` — mock httpx POST /run-force, assert response
- `test_puppet_server_client_connection_error` — mock connection error, assert 502
- `test_keycloak_jwks_fetch` — mock httpx GET, assert JWKS returned
- `test_keycloak_jwks_timeout` — mock timeout, assert 502

Integration (`tests/integration/test_clients_error_handling.py`):
- `test_all_clients_sanitise_error_details` — inject errors across all four clients, assert 502 detail contains no URLs, no tokens, no stack traces
- `test_connection_pooling` — make 20 concurrent requests to GitLab client, assert max 10 connections used

Coverage targets:
- BFF new business logic: ≥90% line coverage (`pytest --cov --cov-fail-under=90`)

## Acceptance Criteria
- [ ] Given the GitLab client is called with valid credentials, when a GitLab API operation succeeds, then the expected data is returned
- [ ] Given the GitLab client is called and GitLab times out after 15 seconds, when the timeout occurs, then the response is 502 with `detail: "Downstream error: GitLab timeout"` and no token is leaked
- [ ] Given the PuppetDB client executes a PQL query, when PuppetDB returns results, then the results are parsed and returned
- [ ] Given the PuppetDB client times out, when the timeout occurs, then the response is 502 with sanitised detail
- [ ] Given the Puppet Server client calls `/run-force`, when the call succeeds, then the run UUID is returned
- [ ] Given the Puppet Server client encounters a connection error, when the error occurs, then the response is 502 with sanitised detail
- [ ] Given the Keycloak JWKS client fetches JWKS, when Keycloak is reachable, then the JWKS is returned and cached
- [ ] Given 20 concurrent GitLab API calls are made, when the connection pool is observed, then no more than 10 connections are open at once

## Definition of Done
- [ ] All acceptance criteria pass
- [ ] Python mypy passes with zero errors
- [ ] All security tests pass (token leakage, error sanitisation, timeout enforcement)
- [ ] All unit tests green (`tests/test_clients.py`)
- [ ] All integration tests green (`tests/integration/test_clients_error_handling.py`)
- [ ] BFF coverage ≥90% (`pytest --cov --cov-fail-under=90`)
- [ ] All four clients use httpx.AsyncClient with connection pooling
- [ ] All clients enforce 10s default timeout (5s for `/readyz` calls)
- [ ] Code Reviewer agent approved
- [ ] Security Sentinel agent approved
