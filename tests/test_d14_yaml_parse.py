"""Tests for D14 Gate 1: yaml_parse."""
from __future__ import annotations

import io

import pytest
from ruamel.yaml import YAML

from bff.validation.yaml_parse import validate_yaml_parse


def test_valid_yaml_passes():
    content = "key: value\nlist:\n  - a\n  - b\n"
    result = validate_yaml_parse(content)
    assert result.passed is True
    assert result.code is None
    assert result.message is None
    assert result.data is not None
    assert result.data["key"] == "value"


def test_malformed_yaml_returns_yaml_parse_failed():
    content = "key: [\nunclosed bracket"
    result = validate_yaml_parse(content)
    assert result.passed is False
    assert result.code == "yaml_parse_failed"
    assert result.message  # non-empty error detail from ruamel


def test_empty_string_passes_with_none_data():
    # An empty YAML document is valid — it parses to None
    result = validate_yaml_parse("")
    assert result.passed is True
    assert result.data is None


def test_binary_non_utf8_handled():
    # Passing bytes decoded as latin-1 that contain non-YAML structure
    # We simulate the scenario: the content is already a str but contains
    # control characters that ruamel rejects as invalid YAML.
    bad_content = "\x00\x01\x02binary garbage"
    result = validate_yaml_parse(bad_content)
    # ruamel should raise on null bytes; gate must return failure, not exception
    assert result.passed is False
    assert result.code == "yaml_parse_failed"


def test_ruamel_preserves_comments_round_trip():
    content = (
        "# top-level comment\n"
        "key: value  # inline comment\n"
        "other: 42\n"
    )
    result = validate_yaml_parse(content)
    assert result.passed is True

    # Round-trip: dump back and verify comment survives
    yaml = YAML(typ="rt")
    out = io.StringIO()
    yaml.dump(result.data, out)
    dumped = out.getvalue()
    assert "# top-level comment" in dumped
    assert "# inline comment" in dumped
