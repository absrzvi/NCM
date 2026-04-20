"""Tests for D14 Gate 5: secret_scan."""
from __future__ import annotations

import pytest

from bff.validation.secret_scan import validate_secret_scan


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _diff(line: str) -> str:
    return f"+{line}\n"


# ---------------------------------------------------------------------------
# Pattern detection tests
# ---------------------------------------------------------------------------

def test_aws_access_key_detected():
    diff = _diff("aws_access_key_id: AKIAIOSFODNN7EXAMPLE")
    result = validate_secret_scan(diff)
    assert result.passed is False
    assert result.code == "secret_leak_blocked"
    assert "aws_access_key" in result.message
    assert "line 1" in result.message


def test_gcp_service_account_key_detected():
    diff = _diff('  "private_key": "-----BEGIN RSA PRIVATE KEY-----\\nMIIE..."')
    result = validate_secret_scan(diff)
    assert result.passed is False
    assert result.code == "secret_leak_blocked"
    assert "gcp_service_account_key" in result.message


def test_pem_private_key_detected():
    diff = _diff("-----BEGIN RSA PRIVATE KEY-----")
    result = validate_secret_scan(diff)
    assert result.passed is False
    assert result.code == "secret_leak_blocked"
    assert "pem_private_key" in result.message


def test_gitlab_pat_detected():
    diff = _diff("token: glpat-abcdefghij1234567890")
    result = validate_secret_scan(diff)
    assert result.passed is False
    assert result.code == "secret_leak_blocked"
    assert "gitlab_pat" in result.message


def test_high_entropy_token_detected():
    # 50-char base64-ish string
    long_token = "A" * 50
    diff = _diff(f"api_token: {long_token}")
    result = validate_secret_scan(diff)
    assert result.passed is False
    assert result.code == "secret_leak_blocked"
    assert "high_entropy_token" in result.message


# ---------------------------------------------------------------------------
# Clean content passes
# ---------------------------------------------------------------------------

def test_clean_content_passes():
    diff = (
        "+key: value\n"
        "+another_key: some_normal_value\n"
        "+list:\n"
        "+  - item_one\n"
    )
    result = validate_secret_scan(diff)
    assert result.passed is True
    assert result.code is None
    assert result.message is None


def test_empty_diff_passes():
    result = validate_secret_scan("")
    assert result.passed is True


# ---------------------------------------------------------------------------
# REDACTED_IN_FIXTURE scrub marker must NOT trigger
# ---------------------------------------------------------------------------

def test_redacted_fixture_marker_does_not_trigger():
    # Simulate a fixture line that was scrubbed by refresh_fixture.py
    diff = _diff("aws_access_key_id: REDACTED_IN_FIXTURE")
    result = validate_secret_scan(diff)
    assert result.passed is True


def test_redacted_fixture_marker_gcp_does_not_trigger():
    diff = _diff('"private_key": "REDACTED_IN_FIXTURE"')
    result = validate_secret_scan(diff)
    assert result.passed is True


def test_redacted_fixture_marker_long_token_does_not_trigger():
    long_placeholder = "REDACTED_IN_FIXTURE" + "A" * 45
    diff = _diff(f"token: {long_placeholder}")
    result = validate_secret_scan(diff)
    assert result.passed is True


# ---------------------------------------------------------------------------
# Error message must NEVER contain the matched secret value
# ---------------------------------------------------------------------------

def test_error_message_never_contains_matched_value_aws():
    secret = "AKIAIOSFODNN7EXAMPLE"
    diff = _diff(f"key: {secret}")
    result = validate_secret_scan(diff)
    assert result.passed is False
    assert secret not in (result.message or "")


def test_error_message_never_contains_matched_value_gitlab_pat():
    secret = "glpat-abcdefghij1234567890"
    diff = _diff(f"token: {secret}")
    result = validate_secret_scan(diff)
    assert result.passed is False
    assert secret not in (result.message or "")


def test_error_message_never_contains_matched_value_high_entropy():
    secret = "Z" * 50
    diff = _diff(f"password: {secret}")
    result = validate_secret_scan(diff)
    assert result.passed is False
    assert secret not in (result.message or "")


# ---------------------------------------------------------------------------
# Line number accuracy
# ---------------------------------------------------------------------------

def test_line_number_reported_correctly():
    diff = (
        "+clean: value\n"
        "+also_clean: fine\n"
        "+bad: AKIAIOSFODNN7EXAMPLE\n"
    )
    result = validate_secret_scan(diff)
    assert result.passed is False
    assert "line 3" in result.message
