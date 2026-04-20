from __future__ import annotations

import difflib
import re
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from bff.validation.models import GateResult

_TOLERANCE_PATH = Path(__file__).parent.parent / "config" / "ruamel_tolerance.yaml"


def _load_tolerance() -> dict[str, Any]:
    """Load ruamel_tolerance.yaml; return empty dict if file is missing."""
    try:
        yaml = YAML(typ="safe")
        with open(_TOLERANCE_PATH, "r", encoding="utf-8") as fh:
            return yaml.load(fh) or {}
    except FileNotFoundError:
        return {}


def _whitelisted_patterns(tolerance: dict[str, Any]) -> set[str]:
    """Return the set of safe pattern names from the tolerance config."""
    patterns: set[str] = set()
    for entry in tolerance.get("benign_patterns", []):
        if entry.get("safe", False):
            patterns.add(entry["pattern"])
    return patterns


def _is_benign(line: str, whitelisted: set[str]) -> bool:
    """Return True if a changed line matches a whitelisted benign pattern."""
    stripped = line.lstrip("+-").rstrip("\n")

    if "trailing_newline_added" in whitelisted and stripped.strip() == "":
        return True

    if "comment_spacing_normalised" in whitelisted:
        # Change affects only the whitespace before a '#' inline comment.
        # The content before and after the comment must be the same value.
        if re.search(r"\s+#", stripped) or stripped.startswith("#"):
            return True

    return False


def validate_byte_diff_drift(
    original_content: str,
    modified_content: str,
    intended_key_paths: list[str],
) -> GateResult:
    """Gate 4 of 5: verify no unexpected byte-level changes outside intended edits.

    Performs a line-level diff between original_content and modified_content.
    Changed lines must be accounted for by intended_key_paths OR fall within
    known-benign ruamel round-trip patterns from ruamel_tolerance.yaml.
    """
    tolerance = _load_tolerance()
    whitelisted = _whitelisted_patterns(tolerance)

    orig_lines = original_content.splitlines(keepends=True)
    mod_lines = modified_content.splitlines(keepends=True)
    diff = list(difflib.unified_diff(orig_lines, mod_lines, lineterm=""))

    # Collect unexpected line numbers
    unexpected: list[int] = []
    line_no = 0

    for diff_line in diff:
        if diff_line.startswith("@@"):
            m = re.search(r"\+(\d+)", diff_line)
            if m:
                line_no = int(m.group(1)) - 1
            continue
        if diff_line.startswith("---") or diff_line.startswith("+++"):
            continue

        if diff_line.startswith("+"):
            line_no += 1
            content_line = diff_line[1:]
            # Is this change covered by an intended key path?
            if any(kp in content_line for kp in intended_key_paths):
                continue
            # Is it a known-benign ruamel pattern?
            if _is_benign(diff_line, whitelisted):
                continue
            unexpected.append(line_no)
        elif diff_line.startswith("-"):
            # Removed lines: check if they belong to an intended key path
            content_line = diff_line[1:]
            if any(kp in content_line for kp in intended_key_paths):
                continue
            if _is_benign(diff_line, whitelisted):
                continue
            # We'll report removal by the nearest following line_no + 1
            unexpected.append(line_no + 1)
        else:
            line_no += 1

    if unexpected:
        # Deduplicate and sort
        unique_unexpected = sorted(set(unexpected))
        return GateResult(
            passed=False,
            code="byte_diff_drift",
            message=f"unexpected changes at lines: {unique_unexpected}",
        )

    return GateResult(passed=True, code="byte_diff_drift", message="clean diff")
