"""
SPIKE-02: ruamel.yaml round-trip fidelity check.

For every .yaml file in tests/fixtures/alpin/ and tests/fixtures/dostoneu/:
  1. Load with ruamel.yaml round-trip mode
  2. Dump back to a string
  3. Byte-diff against the original
  4. Classify each diff as Perfect / Benign / Structural

Exits with code 0 on PASS, 1 on FAIL (structural drift found).

Usage:
    python scripts/spike_ruamel_roundtrip.py [--fixtures-root tests/fixtures]
"""
from __future__ import annotations

import argparse
import difflib
import io
import re
import sys
from pathlib import Path
from typing import Literal

from ruamel.yaml import YAML


# ---------------------------------------------------------------------------
# Diff classification helpers
# ---------------------------------------------------------------------------

_TRAILING_NEWLINE_ONLY = re.compile(r"^\n$")
_COMMENT_SPACING = re.compile(r"^[+-]\s*#")


DiffClass = Literal["perfect", "benign", "structural"]


def _classify_diff(original: str, roundtripped: str) -> tuple[DiffClass, list[str]]:
    """Return (classification, list-of-diff-lines)."""
    if original == roundtripped:
        return "perfect", []

    diff_lines = list(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            roundtripped.splitlines(keepends=True),
            fromfile="original",
            tofile="roundtripped",
            lineterm="",
        )
    )

    changed = [l for l in diff_lines if l.startswith("+") or l.startswith("-")]
    changed = [l for l in changed if not l.startswith("---") and not l.startswith("+++")]

    # Benign check 1: only a trailing newline was added/removed
    if len(changed) == 1 and changed[0] in ("+\n", "-\n", "+", "-"):
        return "benign", diff_lines

    # Benign check 2: all changes are comment-spacing adjustments
    if all(_COMMENT_SPACING.match(l) for l in changed):
        return "benign", diff_lines

    # Benign check 3: trailing newline + comment spacing only
    non_comment = [l for l in changed if not _COMMENT_SPACING.match(l)]
    if len(non_comment) == 1 and non_comment[0] in ("+\n", "-\n", "+", "-"):
        return "benign", diff_lines

    return "structural", diff_lines


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _roundtrip(path: Path) -> tuple[str, str]:
    """Return (original_text, roundtripped_text)."""
    original = path.read_text(encoding="utf-8")
    yaml = YAML(typ="rt")
    yaml.preserve_quotes = True
    data = yaml.load(original)
    buf = io.StringIO()
    yaml.dump(data, buf)
    return original, buf.getvalue()


def run(fixtures_root: Path) -> bool:
    """
    Run the round-trip check.
    Returns True on PASS (no structural drift), False on FAIL.
    """
    fleets = ["alpin", "dostoneu"]
    results: dict[str, dict] = {}  # path → {class, diff_lines}

    for fleet in fleets:
        fleet_dir = fixtures_root / fleet
        if not fleet_dir.exists():
            print(f"  [WARN] fixtures dir not found: {fleet_dir}", file=sys.stderr)
            continue
        yaml_files = sorted(fleet_dir.rglob("*.yaml"))
        if not yaml_files:
            print(f"  [WARN] no .yaml files found under {fleet_dir}", file=sys.stderr)
            continue
        for fpath in yaml_files:
            rel = fpath.relative_to(fixtures_root.parent.parent)
            try:
                original, roundtripped = _roundtrip(fpath)
                cls, diff = _classify_diff(original, roundtripped)
            except Exception as exc:  # noqa: BLE001
                cls = "structural"
                diff = [f"ERROR loading/dumping: {exc}"]
            results[str(rel)] = {"classification": cls, "diff": diff}

    # Summarise
    perfect = [k for k, v in results.items() if v["classification"] == "perfect"]
    benign = [k for k, v in results.items() if v["classification"] == "benign"]
    structural = [k for k, v in results.items() if v["classification"] == "structural"]

    print(f"\nFiles checked : {len(results)}")
    print(f"  Perfect     : {len(perfect)}")
    print(f"  Benign      : {len(benign)}")
    print(f"  Structural  : {len(structural)}")

    if benign:
        print("\nBenign diffs:")
        for path in benign:
            print(f"  {path}")
            for line in results[path]["diff"][:10]:
                print(f"    {line.rstrip()}")

    if structural:
        print("\nSTRUCTURAL DIFFS (FAIL):")
        for path in structural:
            print(f"  {path}")
            for line in results[path]["diff"][:20]:
                print(f"    {line.rstrip()}")

    verdict = "PASS" if not structural else "FAIL"
    print(f"\nVerdict: {verdict}")
    return verdict == "PASS"


def main() -> None:
    parser = argparse.ArgumentParser(description="SPIKE-02: ruamel round-trip fidelity")
    parser.add_argument(
        "--fixtures-root",
        default="tests/fixtures",
        help="Path to fixtures root (default: tests/fixtures)",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).parent.parent
    fixtures_root = repo_root / args.fixtures_root

    passed = run(fixtures_root)
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
