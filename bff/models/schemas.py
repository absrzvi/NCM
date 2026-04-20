"""Pydantic v2 schemas for all six BFF-owned tables."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AuditEventSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    fleet: str
    puppet_environment: str
    event_type: str
    user_sub: str
    user_role: str
    detail: dict[str, Any] = Field(default_factory=dict)
    correlation_id: uuid.UUID | None = None
    source: str


class IdempotencyKeySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: uuid.UUID
    user_sub: str
    fingerprint: str
    endpoint: str
    status_code: int
    response_body: dict[str, Any]
    created_at: datetime
    expires_at: datetime


class DraftChangeSetSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    fleet: str
    puppet_environment: str
    user_sub: str
    status: str
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None = None
    jira_issue: str | None = None
    mr_url: str | None = None
    branch_sha_at_creation: str | None = None
    edits: list[Any] = Field(default_factory=list)


class ParameterHistoryCacheSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    cache_key: str
    fleet: str
    puppet_environment: str
    branch: str
    key_path: str
    history_json: dict[str, Any]
    fetched_at: datetime
    expires_at: datetime


class UserPreferencesSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_sub: str
    last_fleet: str | None = None
    last_puppet_environment: str | None = None
    policy_tree_collapsed: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime


class EnvironmentConfigSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    fleet: str
    puppet_environment: str
    gitlab_project_id: int
    gitlab_project_path: str
    target_branch: str
    layer_count: int
    hiera_yaml_path: str
    bench_allowlist: list[Any] = Field(default_factory=list)
    known_keys_path: str | None = None
    active: bool
    created_at: datetime
    updated_at: datetime
