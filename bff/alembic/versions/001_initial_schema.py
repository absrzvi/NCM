"""Initial schema — all six tables.

Revision ID: 001
Revises:
Create Date: 2026-04-20
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001"
down_revision = None
branch_labels = None
depends_on = None

# Detect the active dialect so we can use Postgres-specific DDL only when
# connected to Postgres. The migration still applies cleanly to SQLite (used
# in unit tests) by falling back to plain column lists.
def _is_postgres() -> bool:
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


def upgrade() -> None:
    # ------------------------------------------------------------------
    # audit_events
    # ------------------------------------------------------------------
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Text(), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fleet", sa.Text(), nullable=False),
        sa.Column("puppet_environment", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("user_sub", sa.Text(), nullable=False),
        sa.Column("user_role", sa.Text(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("correlation_id", sa.Text(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
    )
    if _is_postgres():
        op.execute(
            "CREATE INDEX ix_audit_events_fleet_created_at"
            " ON audit_events (fleet, created_at DESC)"
        )
        op.execute(
            "CREATE INDEX ix_audit_events_user_sub_created_at"
            " ON audit_events (user_sub, created_at DESC)"
        )
        op.execute(
            "CREATE INDEX ix_audit_events_event_type_created_at"
            " ON audit_events (event_type, created_at DESC)"
        )
    else:
        op.create_index("ix_audit_events_fleet_created_at", "audit_events", ["fleet", "created_at"])
        op.create_index("ix_audit_events_user_sub_created_at", "audit_events", ["user_sub", "created_at"])
        op.create_index("ix_audit_events_event_type_created_at", "audit_events", ["event_type", "created_at"])

    # ------------------------------------------------------------------
    # idempotency_keys
    # ------------------------------------------------------------------
    op.create_table(
        "idempotency_keys",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("user_sub", sa.Text(), nullable=False),
        sa.Column("fingerprint", sa.Text(), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("response_body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key", "user_sub"),
    )
    op.create_index("ix_idempotency_keys_expires_at", "idempotency_keys", ["expires_at"])

    # ------------------------------------------------------------------
    # draft_change_sets
    # ------------------------------------------------------------------
    op.create_table(
        "draft_change_sets",
        sa.Column("id", sa.Text(), primary_key=True, nullable=False),
        sa.Column("fleet", sa.Text(), nullable=False),
        sa.Column("puppet_environment", sa.Text(), nullable=False),
        sa.Column("user_sub", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("jira_issue", sa.Text(), nullable=True),
        sa.Column("mr_url", sa.Text(), nullable=True),
        sa.Column("branch_sha_at_creation", sa.Text(), nullable=True),
        sa.Column("edits", sa.Text(), nullable=False, server_default="[]"),
    )
    op.create_index(
        "ix_draft_change_sets_fleet_status_created_at",
        "draft_change_sets",
        ["fleet", "status", "created_at"],
    )
    if _is_postgres():
        op.execute(
            "CREATE UNIQUE INDEX uq_draft_change_sets_active_user_fleet"
            " ON draft_change_sets (user_sub, fleet)"
            " WHERE status = 'ACTIVE'"
        )
    else:
        # SQLite: emulate with a plain unique index; partial WHERE is unsupported
        op.create_index(
            "uq_draft_change_sets_active_user_fleet",
            "draft_change_sets",
            ["user_sub", "fleet", "status"],
            unique=True,
        )

    # ------------------------------------------------------------------
    # parameter_history_cache
    # ------------------------------------------------------------------
    op.create_table(
        "parameter_history_cache",
        sa.Column("id", sa.Text(), primary_key=True, nullable=False),
        sa.Column("cache_key", sa.Text(), nullable=False, unique=True),
        sa.Column("fleet", sa.Text(), nullable=False),
        sa.Column("puppet_environment", sa.Text(), nullable=False),
        sa.Column("branch", sa.Text(), nullable=False),
        sa.Column("key_path", sa.Text(), nullable=False),
        sa.Column("history_json", sa.Text(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_parameter_history_cache_expires_at", "parameter_history_cache", ["expires_at"]
    )

    # ------------------------------------------------------------------
    # user_preferences
    # ------------------------------------------------------------------
    op.create_table(
        "user_preferences",
        sa.Column("user_sub", sa.Text(), primary_key=True, nullable=False),
        sa.Column("last_fleet", sa.Text(), nullable=True),
        sa.Column("last_puppet_environment", sa.Text(), nullable=True),
        sa.Column("policy_tree_collapsed", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ------------------------------------------------------------------
    # environment_configs
    # ------------------------------------------------------------------
    op.create_table(
        "environment_configs",
        sa.Column("fleet", sa.Text(), nullable=False),
        sa.Column("puppet_environment", sa.Text(), nullable=False),
        sa.Column("gitlab_project_id", sa.Integer(), nullable=False),
        sa.Column("gitlab_project_path", sa.Text(), nullable=False),
        sa.Column("target_branch", sa.Text(), nullable=False),
        sa.Column("layer_count", sa.Integer(), nullable=False),
        sa.Column("hiera_yaml_path", sa.Text(), nullable=False),
        sa.Column("bench_allowlist", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("known_keys_path", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("fleet", "puppet_environment"),
    )
    op.create_index("ix_environment_configs_active", "environment_configs", ["active"])


def downgrade() -> None:
    op.drop_table("environment_configs")
    op.drop_table("user_preferences")
    op.drop_table("parameter_history_cache")
    op.drop_table("draft_change_sets")
    op.drop_table("idempotency_keys")
    op.drop_table("audit_events")
