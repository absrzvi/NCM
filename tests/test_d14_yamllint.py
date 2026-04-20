from __future__ import annotations

from pathlib import Path

import pytest

from bff.validation.yamllint_gate import validate_yamllint

FIXTURE_COMMON = (
    Path(__file__).parent / "fixtures" / "alpin" / "hieradata" / "common.yaml"
)


def test_valid_yaml_passes() -> None:
    content = "---\nkey: value\nanother: 123\n"
    result = validate_yamllint(content)
    assert result.passed is True
    assert result.code is None


def test_duplicate_key_fails_with_yamllint_failed_and_line_number() -> None:
    content = "---\nfoo: 1\nfoo: 2\n"
    result = validate_yamllint(content)
    assert result.passed is False
    assert result.code == "yamllint_failed"
    assert result.message is not None
    # message must contain a line number
    parts = result.message.split(":")
    assert len(parts) >= 3, f"Expected rule:line:col format, got: {result.message}"
    assert parts[1].isdigit(), f"Expected line number, got: {parts[1]}"


def test_tab_indentation_fails() -> None:
    content = "---\nparent:\n\tchild: value\n"
    result = validate_yamllint(content)
    assert result.passed is False
    assert result.code == "yamllint_failed"


def test_trailing_spaces_fail() -> None:
    content = "---\nkey: value   \nanother: ok\n"
    result = validate_yamllint(content)
    assert result.passed is False
    assert result.code == "yamllint_failed"


def test_alpin_common_hieradata_passes() -> None:
    content = FIXTURE_COMMON.read_text(encoding="utf-8")
    result = validate_yamllint(content)
    assert result.passed is True, f"Fixture failed yamllint: {result.message}"
