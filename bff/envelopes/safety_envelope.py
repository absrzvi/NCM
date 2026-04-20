"""D13 force-run safety envelope.

ALL callers of Puppet Server /run-force MUST use force_run() from this module.
Iron Rule 12: never construct the httpx call inline.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from bff.clients import puppet_server_client
from bff.config.loader import (
    is_bench_certname,
    load_bench_allowlists,
    validate_certname,
)
from bff.models.user import CurrentUser

logger = logging.getLogger(__name__)

# D15 — only devel and staging are writable Puppet environments.
_ALLOWED_PUPPET_ENVIRONMENTS: frozenset[str] = frozenset({"devel", "staging"})

# Bench allowlists are loaded once at module import.  Tests may monkeypatch
# _BENCH_ALLOWLISTS to inject fixtures without touching the filesystem.
_BENCH_ALLOWLISTS: dict[str, list[str]] = load_bench_allowlists()


class EnvelopeError(Exception):
    """Raised by the safety envelope when a pre-flight check fails."""

    def __init__(self, code: str, status: int) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


class ForceRunResult(BaseModel):
    run_uuid: str
    status: str


async def force_run(
    node_target: str,
    puppet_environment: str,
    fleet: str,
    current_user: CurrentUser,
    db: AsyncSession,
) -> ForceRunResult:
    """Execute a Puppet force-run with all D13 pre-flight checks.

    Writes an audit event for every invocation (pass and fail).
    Raises EnvelopeError (never HTTPException) so the caller controls the
    HTTP response shape.
    """
    failure_code: str | None = None

    try:
        # Pre-flight 1 — Puppet environment must be devel or staging (D15).
        if puppet_environment not in _ALLOWED_PUPPET_ENVIRONMENTS:
            failure_code = "target_branch_not_allowed"
            raise EnvelopeError(code=failure_code, status=403)

        # Pre-flight 2 — certname must match the permitted pattern.
        if not validate_certname(node_target):
            failure_code = "certname_invalid_format"
            raise EnvelopeError(code=failure_code, status=400)

        # Pre-flight 3 — certname must be on the fleet's bench allowlist.
        if not is_bench_certname(node_target, fleet, _BENCH_ALLOWLISTS):
            failure_code = "not_a_bench_target"
            raise EnvelopeError(code=failure_code, status=403)

        # Pre-flight 4 — caller must hold editor or admin role.
        if not {"editor", "admin"}.intersection(current_user.roles):
            failure_code = "role_missing"
            raise EnvelopeError(code=failure_code, status=403)

        # All checks passed — call Puppet Server.
        raw: dict[str, Any] = await puppet_server_client.trigger_puppet_run(
            node_target, puppet_environment
        )
        result = ForceRunResult(
            run_uuid=raw.get("run_uuid", raw.get("id", "")),
            status="pass",
        )
        await _write_audit(
            db=db,
            user_sub=current_user.sub,
            fleet=fleet,
            puppet_environment=puppet_environment,
            target=f"{fleet}/{node_target}",
            result="pass",
            failure_code=None,
        )
        return result

    except EnvelopeError:
        await _write_audit(
            db=db,
            user_sub=current_user.sub,
            fleet=fleet,
            puppet_environment=puppet_environment,
            target=f"{fleet}/{node_target}",
            result="fail",
            failure_code=failure_code,
        )
        raise


async def _write_audit(
    db: AsyncSession,
    user_sub: str,
    fleet: str,
    puppet_environment: str,
    target: str,
    result: str,
    failure_code: str | None,
) -> None:
    """Insert a force_run audit event into Postgres."""
    from bff.models.db import AuditEvent  # local import avoids circular dep at module load

    detail: dict[str, Any] = {"target": target, "result": result}
    if failure_code is not None:
        detail["failure_code"] = failure_code

    event = AuditEvent(
        created_at=datetime.now(timezone.utc),
        fleet=fleet,
        puppet_environment=puppet_environment,
        event_type="force_run",
        user_sub=user_sub,
        user_role="",  # roles stored in JWT; not duplicated here
        detail=detail,
        source="safety_envelope",
    )
    try:
        db.add(event)
        await db.commit()
    except Exception:  # noqa: BLE001
        logger.exception(
            "Failed to write audit event for force_run user=%s target=%s",
            user_sub,
            target,
        )
        await db.rollback()
