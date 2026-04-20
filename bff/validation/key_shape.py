from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from bff.validation.models import GateResult

_KNOWN_KEYS_DIR = Path(__file__).parent.parent / "config" / "known_keys"

# Maps declared type name → acceptable Python type(s).
# Note: bool must be checked before int because bool is a subclass of int.
_TYPE_CHECKERS: dict[str, type | tuple[type, ...]] = {
    "bool": bool,
    "int": int,
    "string": str,
    "scalar": (bool, int, float, str),
    "list": list,
    "hash": dict,
}


def _actual_type_name(value: Any) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "hash"
    return type(value).__name__


def _load_known_keys(fleet: str) -> dict[str, Any] | None:
    path = _KNOWN_KEYS_DIR / f"{fleet}.yaml"
    if not path.exists():
        return None
    with path.open() as fh:
        return yaml.safe_load(fh) or {}


def _matches_declared_type(value: Any, declared_type: str) -> bool:
    expected = _TYPE_CHECKERS.get(declared_type)
    if expected is None:
        return True  # unrecognised type — pass through
    # bool is a subclass of int; a bool value must NOT satisfy "int"
    if declared_type == "int" and isinstance(value, bool):
        return False
    return isinstance(value, expected)


def validate_key_shape(key_path: str, value: Any, fleet: str) -> GateResult:
    known_keys = _load_known_keys(fleet)

    if known_keys is None:
        return GateResult(passed=True, warning=f"no_known_keys_config_for_fleet:{fleet}")

    if key_path not in known_keys:
        return GateResult(passed=True, warning="unknown_key")

    declared_type: str | None = known_keys[key_path].get("type")
    if declared_type is None:
        return GateResult(passed=True, warning="unknown_key")

    if not _matches_declared_type(value, declared_type):
        actual = _actual_type_name(value)
        return GateResult(
            passed=False,
            code="key_shape_mismatch",
            message=f"expected {declared_type}, got {actual}",
        )

    return GateResult(passed=True)
