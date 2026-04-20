"""Tests for D14 gate 4: byte_diff_drift."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from bff.validation.byte_diff_drift import validate_byte_diff_drift
from bff.validation.models import GateResult

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

ORIGINAL = """\
ntp::servers:
  - 0.pool.ntp.org
  - 1.pool.ntp.org
monitoring::interval: 300
dns::search: example.com
"""

# Modified: only ntp::servers changed (intended)
MODIFIED_CLEAN = """\
ntp::servers:
  - 0.pool.ntp.org
  - 1.pool.ntp.org
  - 2.pool.ntp.org
monitoring::interval: 300
dns::search: example.com
"""

# Modified: ntp::servers AND an adjacent unintended change to dns::search
MODIFIED_EXTRA = """\
ntp::servers:
  - 0.pool.ntp.org
  - 1.pool.ntp.org
  - 2.pool.ntp.org
monitoring::interval: 300
dns::search: changed.example.com
"""

# Modified: only trailing newline added (benign ruamel pattern)
ORIGINAL_NO_TRAILING_NL = "ntp::servers: 0.pool.ntp.org"
MODIFIED_TRAILING_NL = "ntp::servers: 0.pool.ntp.org\n"

# Modified: comment spacing normalised (benign ruamel pattern)
ORIGINAL_COMMENT = "monitoring::interval: 300 # seconds\n"
MODIFIED_COMMENT = "monitoring::interval: 300  # seconds\n"

# ---------------------------------------------------------------------------
# AC1: clean edit — only intended key path changed → passes
# ---------------------------------------------------------------------------


def test_clean_edit_passes() -> None:
    result = validate_byte_diff_drift(
        original_content=ORIGINAL,
        modified_content=MODIFIED_CLEAN,
        intended_key_paths=["ntp::servers"],
    )
    assert isinstance(result, GateResult)
    assert result.passed is True
    assert result.code == "byte_diff_drift"


def test_no_changes_passes() -> None:
    result = validate_byte_diff_drift(
        original_content=ORIGINAL,
        modified_content=ORIGINAL,
        intended_key_paths=["ntp::servers"],
    )
    assert result.passed is True


# ---------------------------------------------------------------------------
# AC2: edit that touches adjacent lines fails with byte_diff_drift
# ---------------------------------------------------------------------------


def test_adjacent_line_change_fails() -> None:
    result = validate_byte_diff_drift(
        original_content=ORIGINAL,
        modified_content=MODIFIED_EXTRA,
        intended_key_paths=["ntp::servers"],  # dns::search NOT declared
    )
    assert result.passed is False
    assert result.code == "byte_diff_drift"
    assert "unexpected changes at lines:" in (result.message or "")


def test_undeclared_key_path_fails() -> None:
    """A change to a key not in intended_key_paths must fail."""
    result = validate_byte_diff_drift(
        original_content=ORIGINAL,
        modified_content=MODIFIED_EXTRA,
        intended_key_paths=["dns::search"],  # ntp::servers NOT declared
    )
    assert result.passed is False
    assert result.code == "byte_diff_drift"


def test_declaring_both_key_paths_passes() -> None:
    result = validate_byte_diff_drift(
        original_content=ORIGINAL,
        modified_content=MODIFIED_EXTRA,
        intended_key_paths=["ntp::servers", "dns::search"],
    )
    assert result.passed is True


# ---------------------------------------------------------------------------
# AC3: tolerance patterns are whitelisted
# ---------------------------------------------------------------------------


def test_trailing_newline_whitelisted() -> None:
    result = validate_byte_diff_drift(
        original_content=ORIGINAL_NO_TRAILING_NL,
        modified_content=MODIFIED_TRAILING_NL,
        intended_key_paths=[],
    )
    assert result.passed is True


def test_comment_spacing_whitelisted() -> None:
    result = validate_byte_diff_drift(
        original_content=ORIGINAL_COMMENT,
        modified_content=MODIFIED_COMMENT,
        intended_key_paths=[],
    )
    assert result.passed is True


# ---------------------------------------------------------------------------
# AC4: missing ruamel_tolerance.yaml treated as empty whitelist
# ---------------------------------------------------------------------------


def test_missing_tolerance_file_treated_as_empty_whitelist() -> None:
    """When ruamel_tolerance.yaml is absent, benign patterns are NOT whitelisted."""
    with patch(
        "bff.validation.byte_diff_drift._load_tolerance", return_value={}
    ):
        # comment spacing is only whitelisted if tolerance file is loaded;
        # with empty tolerance, this change should fail
        result = validate_byte_diff_drift(
            original_content=ORIGINAL_COMMENT,
            modified_content=MODIFIED_COMMENT,
            intended_key_paths=[],
        )
        # With empty whitelist and no declared key path, comment-spacing diff fails
        assert result.passed is False
        assert result.code == "byte_diff_drift"


def test_missing_tolerance_file_clean_edit_still_passes() -> None:
    """A clean edit inside declared key_paths passes even with empty whitelist."""
    with patch(
        "bff.validation.byte_diff_drift._load_tolerance", return_value={}
    ):
        result = validate_byte_diff_drift(
            original_content=ORIGINAL,
            modified_content=MODIFIED_CLEAN,
            intended_key_paths=["ntp::servers"],
        )
        assert result.passed is True


# ---------------------------------------------------------------------------
# AC5: ruamel preserve_quotes=True is used (SPIKE-02 key finding)
# ---------------------------------------------------------------------------


def test_preserve_quotes_roundtrip() -> None:
    """A file with quoted strings round-trips without triggering byte_diff_drift."""
    original = "app::token: 'my-secret-token'\n"
    # Simulate a round-trip that changes a single-quoted value update
    modified = "app::token: 'new-token'\n"
    result = validate_byte_diff_drift(
        original_content=original,
        modified_content=modified,
        intended_key_paths=["app::token"],
    )
    assert result.passed is True
