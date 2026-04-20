# Runbook: Puppet Server Token Rotation

> Updated by bff-dev and devops when /run-force auth paths change.

## Scheduled rotation (every 90 days)
1. Create a new token in Puppet Server admin.
2. SSH to the Docker host as the `nmsplus` service user. Write the new token value to `/etc/nmsplus/secrets/puppet-server.env.new` (mode 0600) with the line `PUPPET_SERVER_TOKEN=<new value>`.
3. `cp /etc/nmsplus/secrets/puppet-server.env /etc/nmsplus/secrets/rotated/puppet-server-$(date +%Y%m%d).env` (keep the old file for 30 days as a rollback escape hatch, chmod 0400).
4. `mv /etc/nmsplus/secrets/puppet-server.env.new /etc/nmsplus/secrets/puppet-server.env` (atomic replace).
5. `docker compose -f deploy/docker-compose.yml restart bff` — single container, brief outage expected, typically <10s. `env_file` is re-read on restart.
6. Verify `/api/deployments/force-run` succeeds with a test certname in `devel` (use `/run-puppet` from the repo).
7. After 30 days, cron (`deploy/backup/rotated-secrets-purge.cron`) purges the `/etc/nmsplus/secrets/rotated/` file automatically.
8. Log the rotation in `audit_events` with action `token_rotated`.

## Unscheduled (suspected compromise)
1. Revoke the existing token in Puppet Server admin IMMEDIATELY.
2. Create a new token. On the host: `echo "PUPPET_SERVER_TOKEN=<new value>" > /etc/nmsplus/secrets/puppet-server.env && chmod 0600 /etc/nmsplus/secrets/puppet-server.env` (replace in place — no staged file for an emergency rotation).
3. `docker compose -f deploy/docker-compose.yml restart bff` — single container, brief outage expected, typically <10s.
4. Verify `/api/deployments/force-run` succeeds against a test certname.
5. Audit `bff_force_run_total` for anomalous volume in the window before revocation.
6. Open an incident report per `docs/runbooks/incident_response.md`.

## Observability
- `bff_puppet_token_age_days` gauge should alert at 80 days (scheduled rotation window)
- Any 401 from Puppet Server in BFF logs should alert immediately (token compromised or misconfigured)
