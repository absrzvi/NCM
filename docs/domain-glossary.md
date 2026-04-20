# Domain Glossary

> Maintained by requirements-analyst agent. All agents use these terms consistently.

| Term | Definition |
|------|-----------|
| BFF | Backend for Frontend — the Python FastAPI intermediary layer |
| hieradata | YAML files arranged by hierarchy layers that Puppet consults at compile time |
| hiera.yaml | The per-fleet config file that declares the lookup hierarchy and its layers |
| key_path | Colon-separated path identifying a single hieradata key (e.g., `ntp::servers`) |
| fleet | One of `alpin`, `dostoneu`, `dani`; each has its own GitLab project and a distinct hierarchy depth (3/4/9 layers). Canonical term for the NMS+ scope unit. |
| Puppet environment | An r10k branch deployment target — one of `devel`, `staging` (D15). Always qualify with "Puppet"; do not write bare "environment". |
| env project | Legacy synonym for a fleet's GitLab project (path `env/environment-<fleet>`). Accept on read; emit "fleet" on write. |
| target branch | One of `devel` or `staging`; writes target these only — never `master` or `ODEG`. Synonymous with "Puppet environment" for D15 purposes. |
| MR | GitLab Merge Request — how every hieradata change reaches `master` |
| force-run | A Puppet Server-triggered `/run-force` call against a target node; requires admin role + D13 envelope |
| drift | State where PuppetDB's reported catalog SHA differs from the expected branch HEAD |
| draft change set | Server-persisted set of pending key edits scoped to (user, fleet, branch) — D12 |
| safety envelope | The three pre-flight checks (D13) required before every force-run: MR merged + pipeline green, target branch match, no drift |
| D14 gate | One of the five server-side validation checks run on every hieradata write |
| Idempotency-Key | Client-generated UUID v4 on every write; 24h TTL in Postgres — D4 |
| parameter history | GitLab commit log scoped to a single key_path — D16 |
| known_keys | Per-fleet config describing expected shape of known hieradata keys |
| bench allowlist | Per-fleet list of certnames permitted for force-run |
| hiera_file / hiera_mysql | Backend-plugin keys; not supported by the parameter history endpoint |
| Iron Rules | The non-negotiable architectural constraints in CLAUDE.md |
| D-decision | One of D1–D16, pre-locked in System Design Brief §5 |
| Story | A single unit of implementable work, defined in docs/stories/ |
| Human Gate | A point in the workflow requiring explicit human approval before proceeding |
| viewer / editor / admin | The three roles; authZ is role-based (single-tenant MVP) |
