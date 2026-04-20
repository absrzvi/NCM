#!/usr/bin/env bash
set -euo pipefail

# Run Alembic migrations before starting the BFF (STORY-04 / D8).
# DATABASE_URL is injected via Docker Compose env_file from /etc/nmsplus/secrets/postgres.env.
echo "[entrypoint] Running Alembic migrations..."
cd /app/bff
alembic upgrade head
echo "[entrypoint] Migrations complete."

exec uvicorn bff.main:app --host 0.0.0.0 --port 8000
