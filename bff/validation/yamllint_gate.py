from __future__ import annotations

from pathlib import Path

from yamllint import linter
from yamllint.config import YamlLintConfig

from bff.validation.models import GateResult

_CONFIG_PATH = Path(__file__).parent / "yamllint_config.yaml"
_LINT_CONFIG = YamlLintConfig(file=str(_CONFIG_PATH))


def validate_yamllint(content: str) -> GateResult:
    problems = list(linter.run(content, _LINT_CONFIG))
    if not problems:
        return GateResult(passed=True)

    first = problems[0]
    rule = first.rule or "unknown"
    message = f"{rule}:{first.line}:{first.column} {first.message}"
    return GateResult(passed=False, code="yamllint_failed", message=message)
