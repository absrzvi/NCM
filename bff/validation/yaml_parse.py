from __future__ import annotations

import io

from ruamel.yaml import YAML

from bff.validation.models import GateResult


def validate_yaml_parse(content: str) -> GateResult:
    """Gate 1 of 5: parse the YAML content using ruamel.yaml in round-trip mode.

    Returns GateResult with passed=True and data set to the parsed object on
    success, or passed=False with code='yaml_parse_failed' on any parse error.
    """
    yaml = YAML(typ="rt")
    try:
        data = yaml.load(io.StringIO(content))
    except Exception as exc:
        return GateResult(passed=False, code="yaml_parse_failed", message=str(exc))
    return GateResult(passed=True, data=data)
