# Phase-2: dani Fleet + hiera_mysql Read Path
Status: SCOPING (not a story — placeholder for phase-2)
D-decisions touched: D10 (extended)

## PE Feedback (from SPIKE-03)
- 2026-04-20 Agent-executed review (no live PE available at spike execution time): The opaque rendering proposal was reviewed against the D10 architecture and the dani fleet's 9-layer hiera.yaml structure. The proposal is technically sound: `hiera_mysql`-routed keys cannot be statically resolved by the NMS+ BFF without a direct MySQL connection, so surfacing them as `external_db` badges with an informational tooltip is the correct MVP-safe approach. A live PE review must be scheduled before phase-2 stories are scoped; this note records the architectural rationale and pre-populates the scoping template for that conversation.
- Acceptable for phase-2? yes (pending live PE confirmation)
- Read-only value display required? unknown — to be determined by PE review before phase-2 sprint planning

## If Read-Only Display Required
- Puppet MySQL DB endpoint: [host:port — to be captured from dani fleet PE / infra runbook]
- Credentials: [to be confirmed — likely K8s Secret or host-side env file at /etc/nmsplus/secrets/puppet-mysql.env; must NOT be stored in source]
- Query shape: [SQL statement — expected form: `SELECT value FROM hiera_data WHERE key = ? AND environment = ? LIMIT 1`; exact schema to be verified with PE]
- Secret rotation: [to be confirmed — rotation cadence, owner (Ops or PE), and whether a service account or shared credential is used]
- Estimated effort: [3–5 story points for a read-only `puppet_mysql_client.py` module in bff/clients/; includes D14 secret_scan gate extension and integration test fixtures]
- Security review required: yes — new downstream with read-capable credentials against the Puppet DB requires Security Sentinel sign-off before implementation stories are raised

## Recommendation
Proceed with opaque `external_db` badge rendering for phase-2 dani fleet onboarding; schedule a 30-minute PE review session to confirm acceptability and, if read-only value display is required, capture the DB endpoint, query shape, and credential details before raising a phase-2 implementation story.
