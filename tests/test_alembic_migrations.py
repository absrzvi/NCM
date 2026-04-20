"""Unit tests for Alembic migration 001_initial_schema.

These tests use an in-process SQLite database so that they run without a live
Postgres instance. The migration script itself contains only standard
SQLAlchemy constructs; the few Postgres-specific types (UUID, JSONB) are
exercised in the integration suite (tests/integration/test_schema.py).

Usage:
    cd bff && python -m pytest tests/test_alembic_migrations.py -v
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

# Alembic scripts live under bff/alembic/ relative to the repo root.
_REPO_ROOT = Path(__file__).parent.parent
_ALEMBIC_DIR = str(_REPO_ROOT / "bff" / "alembic")

EXPECTED_TABLES = {
    "audit_events",
    "idempotency_keys",
    "draft_change_sets",
    "parameter_history_cache",
    "user_preferences",
    "environment_configs",
}


@pytest.fixture()
def alembic_cfg(tmp_path):
    """Return an Alembic Config pointing at a fresh SQLite database."""
    db_path = tmp_path / "test.db"
    db_url = f"sqlite:///{db_path}"

    cfg = Config()
    cfg.set_main_option("script_location", _ALEMBIC_DIR)
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg, db_url


def _tables_in_db(db_url: str) -> set[str]:
    engine = create_engine(db_url)
    insp = inspect(engine)
    return set(insp.get_table_names())


def test_initial_migration_upgradable(alembic_cfg):
    """Applying 001_initial_schema creates all six tables."""
    cfg, db_url = alembic_cfg
    command.upgrade(cfg, "head")
    assert EXPECTED_TABLES <= _tables_in_db(db_url)


def test_initial_migration_downgradable(alembic_cfg):
    """Downgrading from 001 to base drops all six tables."""
    cfg, db_url = alembic_cfg
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    remaining = _tables_in_db(db_url) & EXPECTED_TABLES
    assert remaining == set(), f"Tables still present after downgrade: {remaining}"


def test_migration_idempotent(alembic_cfg):
    """Running upgrade twice does not raise an error."""
    cfg, db_url = alembic_cfg
    command.upgrade(cfg, "head")
    # Second upgrade should be a no-op (already at head)
    command.upgrade(cfg, "head")
    assert EXPECTED_TABLES <= _tables_in_db(db_url)
