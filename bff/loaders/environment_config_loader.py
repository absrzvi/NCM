"""
Startup loader — reads fleet YAML config files and upserts rows into the
environment_configs Postgres table (STORY-06).

Call load_environment_configs(db) once from the FastAPI lifespan event.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from bff.config.loader import load_fleet_configs

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_UPSERT_SQL = """
INSERT INTO environment_configs (
    fleet, puppet_environment, gitlab_project_id, gitlab_project_path,
    target_branch, layer_count, hiera_yaml_path, bench_allowlist,
    known_keys_path, active, created_at, updated_at
) VALUES (
    :fleet, :puppet_environment, :gitlab_project_id, :gitlab_project_path,
    :target_branch, :layer_count, :hiera_yaml_path, :bench_allowlist::jsonb,
    :known_keys_path, :active, NOW(), NOW()
)
ON CONFLICT (fleet, puppet_environment) DO UPDATE SET
    gitlab_project_id   = EXCLUDED.gitlab_project_id,
    gitlab_project_path = EXCLUDED.gitlab_project_path,
    target_branch       = EXCLUDED.target_branch,
    layer_count         = EXCLUDED.layer_count,
    hiera_yaml_path     = EXCLUDED.hiera_yaml_path,
    bench_allowlist     = EXCLUDED.bench_allowlist,
    known_keys_path     = EXCLUDED.known_keys_path,
    active              = EXCLUDED.active,
    updated_at          = NOW()
"""


async def load_environment_configs(db: "Session") -> None:
    """
    Load all fleet YAML configs and upsert into environment_configs table.

    Intended to be called once from the FastAPI lifespan startup event.
    Malformed YAML files are logged and skipped — the loader continues.
    """
    import json

    configs = load_fleet_configs()
    if not configs:
        logger.warning("No fleet configs found — environment_configs table not populated")
        return

    for cfg in configs:
        params = {
            "fleet": cfg.fleet,
            "puppet_environment": cfg.puppet_environment,
            "gitlab_project_id": cfg.gitlab_project_id,
            "gitlab_project_path": cfg.gitlab_project_path,
            "target_branch": cfg.target_branch,
            "layer_count": cfg.layer_count,
            "hiera_yaml_path": cfg.hiera_yaml_path,
            "bench_allowlist": json.dumps(cfg.bench_allowlist),
            "known_keys_path": cfg.known_keys_path,
            "active": cfg.active,
        }
        db.execute(_UPSERT_SQL, params)
        logger.info(
            "Upserted environment_configs: fleet=%s puppet_environment=%s",
            cfg.fleet, cfg.puppet_environment,
        )

    db.commit()
    logger.info("environment_configs load complete: %d rows upserted", len(configs))
