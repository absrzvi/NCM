# BFF API Contracts

> Maintained by architect and bff-dev agents.
> Frontend-dev reads this as the source of truth for all response types.
> Any change here must be communicated to frontend-dev immediately.

---

## Contract Template

### [METHOD] /api/[module]/[resource]
Auth: Keycloak JWT required via `get_current_user`
Role: viewer | editor | admin
Idempotency-Key required: yes (write) | no (read)
SLO: write-path | read-path | none (reason)
Request: [Pydantic model or "none"]
Response: [Pydantic model]
Downstream: [GitLab | PuppetDB | Puppet Server | Keycloak] at [endpoint]
D14 gates triggered (if hieradata write): [list]
Error codes:
- 401: JWT invalid or expired
- 403: Insufficient role
- 400: Idempotency-Key header required (write endpoints only)
- 409: Idempotency-Key fingerprint mismatch (write endpoints only)
- 422: D14 gate failure (hieradata writes) or validation error
- 502: downstream service unavailable
