"""Tests for D14 Gate 3: key_shape validation."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from bff.validation.key_shape import validate_key_shape
from bff.validation.models import GateResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _patch_known_keys(data: dict | None):
    """Context-manager that replaces _load_known_keys with a fixed return."""
    return patch("bff.validation.key_shape._load_known_keys", return_value=data)


# ---------------------------------------------------------------------------
# Known key — correct type passes
# ---------------------------------------------------------------------------

class TestKnownKeyCorrectType:
    def test_bool_passes(self):
        with _patch_known_keys({"ntpd::service_ntpd_enable": {"type": "bool"}}):
            result = validate_key_shape("ntpd::service_ntpd_enable", True, "alpin")
        assert result.passed is True
        assert result.code is None

    def test_list_passes(self):
        with _patch_known_keys({"ntp::servers": {"type": "list"}}):
            result = validate_key_shape("ntp::servers", ["10.0.0.1"], "alpin")
        assert result.passed is True

    def test_hash_passes(self):
        with _patch_known_keys({"docker::containers": {"type": "hash"}}):
            result = validate_key_shape("docker::containers", {"web": {}}, "alpin")
        assert result.passed is True

    def test_int_passes(self):
        with _patch_known_keys({"syslog::port": {"type": "int"}}):
            result = validate_key_shape("syslog::port", 514, "alpin")
        assert result.passed is True

    def test_string_passes(self):
        with _patch_known_keys({"syslog::remote_host": {"type": "string"}}):
            result = validate_key_shape("syslog::remote_host", "10.2.0.100", "alpin")
        assert result.passed is True

    def test_scalar_with_int_passes(self):
        with _patch_known_keys({"some::scalar_key": {"type": "scalar"}}):
            result = validate_key_shape("some::scalar_key", 42, "alpin")
        assert result.passed is True

    def test_scalar_with_string_passes(self):
        with _patch_known_keys({"some::scalar_key": {"type": "scalar"}}):
            result = validate_key_shape("some::scalar_key", "hello", "alpin")
        assert result.passed is True


# ---------------------------------------------------------------------------
# Known key — wrong type returns key_shape_mismatch
# ---------------------------------------------------------------------------

class TestKnownKeyWrongType:
    def test_list_where_bool_expected(self):
        with _patch_known_keys({"ntpd::service_ntpd_enable": {"type": "bool"}}):
            result = validate_key_shape("ntpd::service_ntpd_enable", ["a"], "alpin")
        assert result.passed is False
        assert result.code == "key_shape_mismatch"
        assert "expected bool" in result.message
        assert "got list" in result.message

    def test_string_where_list_expected(self):
        with _patch_known_keys({"ntp::servers": {"type": "list"}}):
            result = validate_key_shape("ntp::servers", "10.0.0.1", "alpin")
        assert result.passed is False
        assert result.code == "key_shape_mismatch"
        assert "expected list" in result.message
        assert "got string" in result.message

    def test_bool_where_int_expected(self):
        """bool is a subclass of int in Python; must still fail."""
        with _patch_known_keys({"syslog::port": {"type": "int"}}):
            result = validate_key_shape("syslog::port", True, "alpin")
        assert result.passed is False
        assert result.code == "key_shape_mismatch"
        assert "expected int" in result.message
        assert "got bool" in result.message

    def test_dict_where_list_expected(self):
        with _patch_known_keys({"ntp::servers": {"type": "list"}}):
            result = validate_key_shape("ntp::servers", {"a": 1}, "alpin")
        assert result.passed is False
        assert result.code == "key_shape_mismatch"

    def test_int_where_hash_expected(self):
        with _patch_known_keys({"docker::containers": {"type": "hash"}}):
            result = validate_key_shape("docker::containers", 99, "alpin")
        assert result.passed is False
        assert result.code == "key_shape_mismatch"
        assert "expected hash" in result.message


# ---------------------------------------------------------------------------
# Unknown key passes with warning
# ---------------------------------------------------------------------------

class TestUnknownKey:
    def test_unknown_key_passes_with_warning(self):
        with _patch_known_keys({"ntp::servers": {"type": "list"}}):
            result = validate_key_shape("some::undeclared_key", "anything", "alpin")
        assert result.passed is True
        assert result.warning == "unknown_key"

    def test_unknown_key_any_value_type(self):
        with _patch_known_keys({}):
            result = validate_key_shape("completely::new_key", {"nested": True}, "dostoneu")
        assert result.passed is True
        assert result.warning == "unknown_key"


# ---------------------------------------------------------------------------
# Missing known_keys file handled gracefully
# ---------------------------------------------------------------------------

class TestMissingKnownKeysFile:
    def test_missing_file_returns_passed(self):
        with _patch_known_keys(None):
            result = validate_key_shape("ntp::servers", ["x"], "nonexistent_fleet")
        assert result.passed is True
        assert result.warning is not None
        assert "nonexistent_fleet" in result.warning

    def test_missing_file_does_not_raise(self):
        """Ensure no exception leaks from a fleet with no config file."""
        with _patch_known_keys(None):
            result = validate_key_shape("any::key", {}, "unknown_fleet")
        assert isinstance(result, GateResult)


# ---------------------------------------------------------------------------
# Integration: real config files are loadable (sanity, no mock)
# ---------------------------------------------------------------------------

class TestRealConfigFiles:
    def test_alpin_config_file_exists_and_parseable(self):
        config_path = (
            Path(__file__).parent.parent
            / "bff" / "config" / "known_keys" / "alpin.yaml"
        )
        assert config_path.exists(), f"Missing {config_path}"

    def test_dostoneu_config_file_exists_and_parseable(self):
        config_path = (
            Path(__file__).parent.parent
            / "bff" / "config" / "known_keys" / "dostoneu.yaml"
        )
        assert config_path.exists(), f"Missing {config_path}"

    def test_alpin_known_key_passes_end_to_end(self):
        result = validate_key_shape("ntp::servers", ["10.0.0.1"], "alpin")
        assert result.passed is True

    def test_alpin_known_key_mismatch_end_to_end(self):
        result = validate_key_shape("ntp::servers", "not-a-list", "alpin")
        assert result.passed is False
        assert result.code == "key_shape_mismatch"

    def test_alpin_unknown_key_end_to_end(self):
        result = validate_key_shape("totally::unknown", "value", "alpin")
        assert result.passed is True
        assert result.warning == "unknown_key"
