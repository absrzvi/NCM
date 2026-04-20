"""SQLAlchemy ORM models for all six BFF-owned tables."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fleet: Mapped[str] = mapped_column(Text, nullable=False)
    puppet_environment: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    user_sub: Mapped[str] = mapped_column(Text, nullable=False)
    user_role: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    correlation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"

    key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, nullable=False)
    user_sub: Mapped[str] = mapped_column(Text, primary_key=True, nullable=False)
    fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    response_body: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DraftChangeSet(Base):
    __tablename__ = "draft_change_sets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fleet: Mapped[str] = mapped_column(Text, nullable=False)
    puppet_environment: Mapped[str] = mapped_column(Text, nullable=False)
    user_sub: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    jira_issue: Mapped[str | None] = mapped_column(Text, nullable=True)
    mr_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    branch_sha_at_creation: Mapped[str | None] = mapped_column(Text, nullable=True)
    edits: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)


class ParameterHistoryCache(Base):
    __tablename__ = "parameter_history_cache"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cache_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    fleet: Mapped[str] = mapped_column(Text, nullable=False)
    puppet_environment: Mapped[str] = mapped_column(Text, nullable=False)
    branch: Mapped[str] = mapped_column(Text, nullable=False)
    key_path: Mapped[str] = mapped_column(Text, nullable=False)
    history_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class UserPreferences(Base):
    __tablename__ = "user_preferences"

    user_sub: Mapped[str] = mapped_column(Text, primary_key=True, nullable=False)
    last_fleet: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_puppet_environment: Mapped[str | None] = mapped_column(Text, nullable=True)
    policy_tree_collapsed: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EnvironmentConfig(Base):
    __tablename__ = "environment_configs"

    fleet: Mapped[str] = mapped_column(Text, primary_key=True, nullable=False)
    puppet_environment: Mapped[str] = mapped_column(Text, primary_key=True, nullable=False)
    gitlab_project_id: Mapped[int] = mapped_column(Integer, nullable=False)
    gitlab_project_path: Mapped[str] = mapped_column(Text, nullable=False)
    target_branch: Mapped[str] = mapped_column(Text, nullable=False)
    layer_count: Mapped[int] = mapped_column(Integer, nullable=False)
    hiera_yaml_path: Mapped[str] = mapped_column(Text, nullable=False)
    bench_allowlist: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    known_keys_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
