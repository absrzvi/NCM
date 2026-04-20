"""Integration tests for the database schema.

These tests require a live Postgres 16 instance. Set DATABASE_URL in the
environment before running:

    export DATABASE_URL="postgresql://nmsplus:secret@localhost:5432/nmsplus_test"
    cd bff && python -m pytest tests/integration/test_schema.py -v

The fixture creates a fresh schema via Alembic before each test module and
tears it down afterward.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

DATABASE_URL = os.environ.get("DATABASE_URL", "")

_REPO_ROOT = Path(__file__).parent.parent.parent
_ALEMBIC_DIR = str(_REPO_ROOT / "bff" / "alembic")


def _skip_if_no_db():
    if not DATABASE_URL:
        pytest.skip("DATABASE_URL not set — skipping Postgres integration tests")


@pytest.fixture(scope="module")
def pg_engine():
    _skip_if_no_db()
    engine = create_engine(DATABASE_URL)

    cfg = Config()
    cfg.set_main_option("script_location", _ALEMBIC_DIR)
    cfg.set_main_option("sqlalchemy.url", DATABASE_URL)

    # Fresh schema
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")

    yield engine

    command.downgrade(cfg, "base")
    engine.dispose()


@pytest.fixture()
def session(pg_engine):
    with Session(pg_engine) as s:
        yield s
        s.rollback()


# ---------------------------------------------------------------------------
# Table existence
# ---------------------------------------------------------------------------

def test_audit_events_table_exists(pg_engine):
    insp = inspect(pg_engine)
    cols = {c["name"] for c in insp.get_columns("audit_events")}
    assert {"id", "created_at", "fleet", "puppet_environment", "event_type",
            "user_sub", "user_role", "detail", "source"} <= cols


def test_idempotency_keys_table_exists(pg_engine):
    insp = inspect(pg_engine)
    cols = {c["name"] for c in insp.get_columns("idempotency_keys")}
    assert {"key", "user_sub", "fingerprint", "endpoint", "status_code",
            "response_body", "created_at", "expires_at"} <= cols


def test_draft_change_sets_table_exists(pg_engine):
    insp = inspect(pg_engine)
    cols = {c["name"] for c in insp.get_columns("draft_change_sets")}
    assert {"id", "fleet", "puppet_environment", "user_sub", "status",
            "created_at", "updated_at", "edits"} <= cols


def test_parameter_history_cache_table_exists(pg_engine):
    insp = inspect(pg_engine)
    cols = {c["name"] for c in insp.get_columns("parameter_history_cache")}
    assert {"id", "cache_key", "fleet", "puppet_environment", "branch",
            "key_path", "history_json", "fetched_at", "expires_at"} <= cols


def test_user_preferences_table_exists(pg_engine):
    insp = inspect(pg_engine)
    cols = {c["name"] for c in insp.get_columns("user_preferences")}
    assert {"user_sub", "last_fleet", "last_puppet_environment",
            "policy_tree_collapsed", "updated_at"} <= cols


def test_environment_configs_table_exists(pg_engine):
    insp = inspect(pg_engine)
    cols = {c["name"] for c in insp.get_columns("environment_configs")}
    assert {"fleet", "puppet_environment", "gitlab_project_id", "target_branch",
            "layer_count", "hiera_yaml_path", "bench_allowlist", "active",
            "created_at", "updated_at"} <= cols


# ---------------------------------------------------------------------------
# Index existence
# ---------------------------------------------------------------------------

def _index_names(engine, table: str) -> set[str]:
    insp = inspect(engine)
    return {idx["name"] for idx in insp.get_indexes(table)}


def test_audit_events_indexes_exist(pg_engine):
    names = _index_names(pg_engine, "audit_events")
    assert "ix_audit_events_fleet_created_at" in names
    assert "ix_audit_events_user_sub_created_at" in names
    assert "ix_audit_events_event_type_created_at" in names


def test_idempotency_keys_expires_at_index(pg_engine):
    names = _index_names(pg_engine, "idempotency_keys")
    assert "ix_idempotency_keys_expires_at" in names


def test_draft_change_sets_active_partial_index(pg_engine):
    names = _index_names(pg_engine, "draft_change_sets")
    assert "uq_draft_change_sets_active_user_fleet" in names


def test_parameter_history_cache_expires_at_index(pg_engine):
    names = _index_names(pg_engine, "parameter_history_cache")
    assert "ix_parameter_history_cache_expires_at" in names


def test_environment_configs_active_index(pg_engine):
    names = _index_names(pg_engine, "environment_configs")
    assert "ix_environment_configs_active" in names


# ---------------------------------------------------------------------------
# Constraint tests
# ---------------------------------------------------------------------------

_NOW = datetime.now(timezone.utc)


def test_idempotency_keys_pk(session):
    """PK on (key, user_sub) — duplicate insert raises IntegrityError."""
    key = uuid.uuid4()
    row = {
        "key": key,
        "user_sub": "sub|test",
        "fingerprint": "abc123",
        "endpoint": "/api/test",
        "status_code": 200,
        "response_body": "{}",
        "created_at": _NOW,
        "expires_at": _NOW,
    }
    session.execute(
        text(
            "INSERT INTO idempotency_keys"
            " (key, user_sub, fingerprint, endpoint, status_code, response_body, created_at, expires_at)"
            " VALUES (:key, :user_sub, :fingerprint, :endpoint, :status_code,"
            "         CAST(:response_body AS jsonb), :created_at, :expires_at)"
        ),
        row,
    )
    with pytest.raises(IntegrityError):
        session.execute(
            text(
                "INSERT INTO idempotency_keys"
                " (key, user_sub, fingerprint, endpoint, status_code, response_body, created_at, expires_at)"
                " VALUES (:key, :user_sub, :fingerprint, :endpoint, :status_code,"
                "         CAST(:response_body AS jsonb), :created_at, :expires_at)"
            ),
            row,
        )
        session.flush()


def test_draft_change_sets_unique_active_constraint(session):
    """At most one ACTIVE draft per user+fleet — second insert raises IntegrityError."""

    def _insert_active(extra_id: uuid.UUID) -> None:
        session.execute(
            text(
                "INSERT INTO draft_change_sets"
                " (id, fleet, puppet_environment, user_sub, status, created_at, updated_at, edits)"
                " VALUES (:id, 'alpin', 'devel', 'sub|u1', 'ACTIVE', :ts, :ts, '[]')"
            ),
            {"id": extra_id, "ts": _NOW},
        )
        session.flush()

    _insert_active(uuid.uuid4())
    with pytest.raises(IntegrityError):
        _insert_active(uuid.uuid4())


def test_parameter_history_cache_unique_cache_key(session):
    """Unique constraint on cache_key — duplicate insert raises IntegrityError."""
    common = {
        "id": uuid.uuid4(),
        "cache_key": "alpin:devel:main:module::param",
        "fleet": "alpin",
        "puppet_environment": "devel",
        "branch": "main",
        "key_path": "module::param",
        "history_json": "{}",
        "fetched_at": _NOW,
        "expires_at": _NOW,
    }
    session.execute(
        text(
            "INSERT INTO parameter_history_cache"
            " (id, cache_key, fleet, puppet_environment, branch, key_path,"
            "  history_json, fetched_at, expires_at)"
            " VALUES (:id, :cache_key, :fleet, :puppet_environment, :branch,"
            "         :key_path, CAST(:history_json AS jsonb), :fetched_at, :expires_at)"
        ),
        common,
    )
    session.flush()

    duplicate = dict(common, id=uuid.uuid4())
    with pytest.raises(IntegrityError):
        session.execute(
            text(
                "INSERT INTO parameter_history_cache"
                " (id, cache_key, fleet, puppet_environment, branch, key_path,"
                "  history_json, fetched_at, expires_at)"
                " VALUES (:id, :cache_key, :fleet, :puppet_environment, :branch,"
                "         :key_path, CAST(:history_json AS jsonb), :fetched_at, :expires_at)"
            ),
            duplicate,
        )
        session.flush()


def test_user_preferences_pk(session):
    """PK on user_sub — duplicate insert raises IntegrityError."""
    row = {"user_sub": "sub|pref1", "policy_tree_collapsed": "{}", "updated_at": _NOW}
    session.execute(
        text(
            "INSERT INTO user_preferences (user_sub, policy_tree_collapsed, updated_at)"
            " VALUES (:user_sub, CAST(:policy_tree_collapsed AS jsonb), :updated_at)"
        ),
        row,
    )
    session.flush()
    with pytest.raises(IntegrityError):
        session.execute(
            text(
                "INSERT INTO user_preferences (user_sub, policy_tree_collapsed, updated_at)"
                " VALUES (:user_sub, CAST(:policy_tree_collapsed AS jsonb), :updated_at)"
            ),
            row,
        )
        session.flush()


def test_environment_configs_pk(session):
    """PK on (fleet, puppet_environment) — duplicate insert raises IntegrityError."""
    row = {
        "fleet": "alpin",
        "puppet_environment": "devel",
        "gitlab_project_id": 1,
        "gitlab_project_path": "env/environment-alpin",
        "target_branch": "devel",
        "layer_count": 3,
        "hiera_yaml_path": "hiera.yaml",
        "bench_allowlist": "[]",
        "active": True,
        "created_at": _NOW,
        "updated_at": _NOW,
    }
    session.execute(
        text(
            "INSERT INTO environment_configs"
            " (fleet, puppet_environment, gitlab_project_id, gitlab_project_path,"
            "  target_branch, layer_count, hiera_yaml_path, bench_allowlist,"
            "  active, created_at, updated_at)"
            " VALUES (:fleet, :puppet_environment, :gitlab_project_id, :gitlab_project_path,"
            "         :target_branch, :layer_count, :hiera_yaml_path,"
            "         CAST(:bench_allowlist AS jsonb), :active, :created_at, :updated_at)"
        ),
        row,
    )
    session.flush()
    with pytest.raises(IntegrityError):
        session.execute(
            text(
                "INSERT INTO environment_configs"
                " (fleet, puppet_environment, gitlab_project_id, gitlab_project_path,"
                "  target_branch, layer_count, hiera_yaml_path, bench_allowlist,"
                "  active, created_at, updated_at)"
                " VALUES (:fleet, :puppet_environment, :gitlab_project_id, :gitlab_project_path,"
                "         :target_branch, :layer_count, :hiera_yaml_path,"
                "         CAST(:bench_allowlist AS jsonb), :active, :created_at, :updated_at)"
            ),
            row,
        )
        session.flush()
