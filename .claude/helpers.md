# Canonical Patterns — Human Reference

> For human developers and code review. Patterns are inlined directly in agent files for token efficiency — do not instruct agents to read this file.

---

## BFF: Mandatory JWT Pattern (Single-Tenant MVP — D3)

Every FastAPI endpoint must use this exact dependency injection. No exceptions.

```python
from fastapi import Depends, HTTPException, status
from bff.auth import get_current_user, User

@router.get("/api/policies/tree")
async def handler(user: User = Depends(get_current_user)):
    # user.sub is the Keycloak user id; user.roles is a list of assigned roles
    ...

@router.put("/api/policies/drafts")
async def write_handler(edit: DraftParameterEdit, user: User = Depends(get_current_user)):
    if "editor" not in user.roles and "admin" not in user.roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role")
    ...
```

See `docs/KEYCLOAK.md` for the full `get_current_user` implementation.

---

## BFF: Four Downstream Client Patterns

### 1. GitLab (python-gitlab, writes & MRs)
```python
import asyncio
from gitlab import Gitlab
def _gl() -> Gitlab: return Gitlab(GITLAB_URL, private_token=GITLAB_TOKEN, timeout=30)
async def create_mr(project_path: str, source: str, target: str, title: str) -> MRSummary:
    mr = await asyncio.to_thread(lambda: _gl().projects.get(project_path).mergerequests.create(
        {"source_branch": source, "target_branch": target, "title": title}))
    return MRSummary(iid=mr.iid, url=mr.web_url, state=mr.state)
```

### 2. PuppetDB (httpx, read-only, staleness-tolerant)
```python
async def fetch_node_status(certname: str) -> NodeStatus | None:
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            r = await client.get(f"{PUPPETDB_URL}/pdb/query/v4/nodes/{certname}",
                                 headers={"Authorization": f"Bearer {PUPPETDB_TOKEN}"})
            if r.status_code == 404: return None
            r.raise_for_status()
            return NodeStatus(**r.json())
        except httpx.HTTPError:
            return None  # soft dependency
```

### 3. Puppet Server — via D13 safety envelope ONLY
```python
from bff.envelopes.safety_envelope import force_run, EnvelopeRejection
result = await force_run(req=ForceRunRequest(env="devel", certname="node42.devel", user=user))
if isinstance(result, EnvelopeRejection):
    raise HTTPException(422, detail=f"envelope: {result.reason}")
```

### 4. Keycloak JWKS
Handled inside `bff.auth.get_current_user`. Cached hourly. Do not call Keycloak from your endpoint.

---

## BFF: Idempotency Middleware (D4)

Every write endpoint must be covered:
- Fingerprint: `sha256(method + path + canonical_json(body))` where `canonical_json` is **RFC 8785 JCS** (UTF-8, no BOM, lexicographic key sort by UTF-16 code units, no insignificant whitespace, ECMA-262 number serialization). Use the shared helper `bff.util.canonical_json` — do not hand-roll `json.dumps`, do not rely on `sort_keys=True` alone (it does not guarantee RFC 8785 numeric/string rules).
- Table: `idempotency_keys(key UUID PK, fingerprint TEXT, response_status INT, response_body JSONB, created_at TIMESTAMPTZ, expires_at TIMESTAMPTZ)`; TTL 24h
- Missing header → 400 `{"detail": "Idempotency-Key header required"}`
- Fresh key → execute, store, return
- Replay (same fingerprint) → return stored response (status + body)
- Replay (different fingerprint) → 409 `{"detail": "Idempotency-Key fingerprint mismatch"}`

---

## BFF: D13 Force-Run Safety Envelope

Shared helper in `bff/envelopes/safety_envelope.py`:
```python
async def force_run(req: ForceRunRequest) -> ForceRunResult | EnvelopeRejection:
    # Check 1: MR merged & pipeline green for target branch
    if not await gitlab.mr_merged_and_green(req.env, req.target_branch):
        return EnvelopeRejection(reason="mr_not_merged_or_pipeline_red")
    # Check 2: target branch allowed (devel or staging; never master/ODEG)
    if req.target_branch not in ALLOWED_BRANCHES:
        return EnvelopeRejection(reason="target_branch_rejected")
    # Check 3: no drift (requested_sha == HEAD)
    head = await gitlab.get_head(req.env, req.target_branch)
    if head != req.requested_sha:
        return EnvelopeRejection(reason="drift_detected")
    # Additional: certname in bench allowlist, role == config-engineer
    ...
    return await puppet_server.run_force(req.certname)
```

Callers MUST use this helper. Direct httpx calls to `/run-force` are a code-review block.

---

## BFF: D14 Validation Gates (canonical error codes)

Run in order on every hieradata write; abort on first failure.

| Gate | Code | Trigger |
|---|---|---|
| 1 | `yaml_parse_failed` | ruamel.load raises |
| 2 | `yamllint_failed` | yamllint rule violation |
| 3 | `key_shape_mismatch` | value shape disagrees with known_keys schema |
| 4 | `byte_diff_drift` | diff touches paths outside declared key_paths |
| 5 | `secret_leak_blocked` | regex match for AWS/GCP/PEM/token |

UI copy is canonical and lives on the server — frontend displays `message` verbatim.

---

## BFF: ruamel.yaml Round-Trip (D5)

```python
from ruamel.yaml import YAML
from io import StringIO
yaml = YAML(typ="rt")
yaml.preserve_quotes = True
yaml.width = 4096
yaml.indent(mapping=2, sequence=4, offset=2)
yaml.default_flow_style = False

data = yaml.load(text)
# edit in place
buf = StringIO(); yaml.dump(data, buf); new_text = buf.getvalue()
```

Never use `yaml.safe_dump` / `yaml.dump`. The byte_diff_drift gate exists to catch this.

---

## BFF: Health Probes

```python
@router.get("/healthz")  # liveness — unauthenticated, rate-limited
async def healthz(): return {"status": "ok"}

@router.get("/readyz")   # readiness — unauthenticated, rate-limited
async def readyz():
    pg_ok, jwks_ok, gitlab_ok = await asyncio.gather(
        check_postgres(), check_jwks(), check_gitlab_base())
    # Do NOT check PuppetDB — soft dependency
    if not (pg_ok and jwks_ok and gitlab_ok):
        raise HTTPException(503, detail={"postgres": pg_ok, "jwks": jwks_ok, "gitlab": gitlab_ok})
    return {"status": "ready"}
```

---

## Frontend: CSS Custom Properties

All colours must use these variables (defined in `frontend/src/styles/globals.css`):

| Variable | Use |
|---|---|
| `--navy` | Primary dark background |
| `--blue` | Primary accent / interactive elements |
| `--purple` | Secondary accent |
| `--sec` | Secondary text |
| `--status-ok` | Compliance healthy state |
| `--status-warn` | Compliance drift state |
| `--status-critical` | Compliance failure state |
| `--status-unknown` | Compliance unknown state |

Never use hardcoded hex values. Never use Tailwind classes.

---

## Frontend: keycloak-js Authed Fetch Pattern

```typescript
import { useKeycloak } from '@react-keycloak/web'
export function useAuthedFetch() {
  const { keycloak } = useKeycloak()
  return async (path: string, init?: RequestInit) => {
    if (keycloak.isTokenExpired(60)) await keycloak.updateToken(60)
    return fetch(path, { ...init, headers: { ...init?.headers, Authorization: `Bearer ${keycloak.token}` } })
  }
}
```

On `updateToken` failure: redirect to login. Draft change sets in Zustand+localStorage survive the redirect.

---

## Frontend: Write Path with Idempotency-Key

```typescript
const idempotencyKey = useRef<string>(crypto.randomUUID())
const fetchAuthed = useAuthedFetch()

async function apply(payload: DraftApplyRequest) {
  return fetchAuthed('/api/policies/drafts/apply', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Idempotency-Key': idempotencyKey.current },
    body: JSON.stringify(payload),
  })
}
```

Reuse the same key on retry of the same attempt; generate a new one for a fresh attempt.

---

## Frontend: Data-Fetching Hook Pattern

Every BFF call must go through a custom hook in `frontend/src/hooks/`:

```typescript
export function use[Feature]() {
  const fetchAuthed = useAuthedFetch()
  const [data, setData] = useState<[ResponseType] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    fetchAuthed('/api/[module]/[resource]')
      .then(r => { if (!r.ok) throw new Error(r.statusText); return r.json() })
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])
  return { data, loading, error }
}
```

Every component using a data-fetching hook **must** render all three states: `loading`, `error`, and empty `data`.

---

## Downstream Services (canonical list — Config MVP)

GitLab, PuppetDB, Puppet Server (force-run only, D13), Keycloak, Postgres.

Removed from the broader NMS+ list (do not re-add in Config MVP): NMS API, Zabbix, SIEMonster, ServiceNow, BigQuery, ThoughtSpot, Asset DB.
