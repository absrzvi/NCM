"""Tests for STORY-12 — D13 force-run safety envelope.

Acceptance criteria:
  - master branch (or any non-devel/staging) → 403 target_branch_not_allowed
  - invalid certname format → 400 certname_invalid_format
  - valid certname but not on bench allowlist → 403 not_a_bench_target
  - viewer role → 403 role_missing
  - all checks pass → puppet_server_client.trigger_puppet_run called once
  - audit event written on every call including failures
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bff.envelopes.safety_envelope import EnvelopeError, ForceRunResult, force_run
from bff.models.user import CurrentUser

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FLEET = "alpin"
VALID_CERTNAME = "bench-node-01.alpin.example.com"
VALID_ENV = "devel"

_EDITOR_USER = CurrentUser(sub="user-sub-editor", roles=["editor"])
_VIEWER_USER = CurrentUser(sub="user-sub-viewer", roles=["viewer"])

# Bench allowlist that matches VALID_CERTNAME.
_BENCH_ALLOWLISTS = {FLEET: [r"^bench-.*"]}


def _make_db() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    return db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _patch_allowlists():
    """Patch the module-level _BENCH_ALLOWLISTS to use test fixtures."""
    return patch("bff.envelopes.safety_envelope._BENCH_ALLOWLISTS", _BENCH_ALLOWLISTS)


def _patch_trigger(return_value: dict | None = None):
    return patch(
        "bff.envelopes.safety_envelope.puppet_server_client.trigger_puppet_run",
        new_callable=AsyncMock,
        return_value=return_value or {"run_uuid": "abc-123", "id": "abc-123"},
    )


# ---------------------------------------------------------------------------
# Pre-flight 1 — Puppet environment must be devel or staging
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_master_branch_raises_target_branch_not_allowed():
    db = _make_db()
    with _patch_allowlists(), _patch_trigger():
        with pytest.raises(EnvelopeError) as exc_info:
            await force_run(
                node_target=VALID_CERTNAME,
                puppet_environment="master",
                fleet=FLEET,
                current_user=_EDITOR_USER,
                db=db,
            )
    assert exc_info.value.code == "target_branch_not_allowed"
    assert exc_info.value.status == 403
    # Audit event must still be written.
    db.add.assert_called_once()
    db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_odeg_branch_raises_target_branch_not_allowed():
    db = _make_db()
    with _patch_allowlists(), _patch_trigger():
        with pytest.raises(EnvelopeError) as exc_info:
            await force_run(
                node_target=VALID_CERTNAME,
                puppet_environment="ODEG",
                fleet=FLEET,
                current_user=_EDITOR_USER,
                db=db,
            )
    assert exc_info.value.code == "target_branch_not_allowed"
    assert exc_info.value.status == 403
    db.add.assert_called_once()


# ---------------------------------------------------------------------------
# Pre-flight 2 — certname format validation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("bad_certname", [
    "UPPER.case.node",
    "-starts-with-dash",
    "has spaces",
    "trailing.dot.",
    "",
    "has_underscore",
])
async def test_invalid_certname_format_raises_400(bad_certname: str):
    db = _make_db()
    with _patch_allowlists(), _patch_trigger():
        with pytest.raises(EnvelopeError) as exc_info:
            await force_run(
                node_target=bad_certname,
                puppet_environment=VALID_ENV,
                fleet=FLEET,
                current_user=_EDITOR_USER,
                db=db,
            )
    assert exc_info.value.code == "certname_invalid_format"
    assert exc_info.value.status == 400
    db.add.assert_called_once()


# ---------------------------------------------------------------------------
# Pre-flight 3 — certname must be on the bench allowlist
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_non_bench_certname_raises_not_a_bench_target():
    db = _make_db()
    with _patch_allowlists(), _patch_trigger():
        with pytest.raises(EnvelopeError) as exc_info:
            await force_run(
                node_target="prod-node-01.alpin.example.com",  # valid format, not bench
                puppet_environment=VALID_ENV,
                fleet=FLEET,
                current_user=_EDITOR_USER,
                db=db,
            )
    assert exc_info.value.code == "not_a_bench_target"
    assert exc_info.value.status == 403
    db.add.assert_called_once()


# ---------------------------------------------------------------------------
# Pre-flight 4 — role check
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_viewer_role_raises_role_missing():
    db = _make_db()
    with _patch_allowlists(), _patch_trigger():
        with pytest.raises(EnvelopeError) as exc_info:
            await force_run(
                node_target=VALID_CERTNAME,
                puppet_environment=VALID_ENV,
                fleet=FLEET,
                current_user=_VIEWER_USER,
                db=db,
            )
    assert exc_info.value.code == "role_missing"
    assert exc_info.value.status == 403
    db.add.assert_called_once()


# ---------------------------------------------------------------------------
# Happy path — all checks pass
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_all_checks_pass_calls_trigger_once_and_returns_result():
    db = _make_db()
    with _patch_allowlists(), _patch_trigger({"run_uuid": "uuid-xyz", "id": "uuid-xyz"}) as mock_trigger:
        result = await force_run(
            node_target=VALID_CERTNAME,
            puppet_environment=VALID_ENV,
            fleet=FLEET,
            current_user=_EDITOR_USER,
            db=db,
        )
    mock_trigger.assert_awaited_once_with(VALID_CERTNAME, VALID_ENV)
    assert isinstance(result, ForceRunResult)
    assert result.run_uuid == "uuid-xyz"
    assert result.status == "pass"
    # Audit event written on success.
    db.add.assert_called_once()
    db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_admin_role_also_allowed():
    db = _make_db()
    admin_user = CurrentUser(sub="admin-sub", roles=["admin"])
    with _patch_allowlists(), _patch_trigger() as mock_trigger:
        result = await force_run(
            node_target=VALID_CERTNAME,
            puppet_environment="staging",
            fleet=FLEET,
            current_user=admin_user,
            db=db,
        )
    mock_trigger.assert_awaited_once()
    assert result.status == "pass"


# ---------------------------------------------------------------------------
# Audit event written on EVERY call (including failures)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_audit_written_for_every_failure_type():
    """Each pre-flight failure must produce exactly one audit event."""
    cases = [
        dict(puppet_environment="master", node_target=VALID_CERTNAME, current_user=_EDITOR_USER),
        dict(puppet_environment=VALID_ENV, node_target="INVALID_", current_user=_EDITOR_USER),
        dict(puppet_environment=VALID_ENV, node_target="prod-node-01.alpin.example.com", current_user=_EDITOR_USER),
        dict(puppet_environment=VALID_ENV, node_target=VALID_CERTNAME, current_user=_VIEWER_USER),
    ]
    for kwargs in cases:
        db = _make_db()
        with _patch_allowlists(), _patch_trigger():
            with pytest.raises(EnvelopeError):
                await force_run(fleet=FLEET, db=db, **kwargs)
        assert db.add.call_count == 1, f"Expected 1 audit event for {kwargs}"
        assert db.commit.call_count == 1
