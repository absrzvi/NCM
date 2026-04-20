from __future__ import annotations

import re

from bff.validation.models import GateResult

# Patterns: (name, compiled_regex)
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("gcp_service_account_key", re.compile(r'"private_key"')),
    ("pem_private_key", re.compile(r"-----BEGIN .{0,30}PRIVATE KEY-----")),
    ("gitlab_pat", re.compile(r"glpat-[0-9a-zA-Z_\-]{20}")),
    # Generic high-entropy token: base64 or hex run >40 chars not prefixed by REDACTED marker
    ("high_entropy_token", re.compile(r"(?<!\bREDACTED_IN_FIXTURE\b)[A-Za-z0-9+/=]{41,}")),
]

_FIXTURE_SCRUB = re.compile(r"REDACTED_IN_FIXTURE")


def validate_secret_scan(diff_content: str) -> GateResult:
    """Gate 5 of 5: scan the full file diff for secret-like patterns.

    The matched value is NEVER included in the returned message — only the
    line number and pattern type are reported.
    """
    for lineno, line in enumerate(diff_content.splitlines(), start=1):
        # Lines that contain the fixture scrub marker are safe — skip entirely.
        if _FIXTURE_SCRUB.search(line):
            continue
        for pattern_name, pattern in _PATTERNS:
            if pattern.search(line):
                return GateResult(
                    passed=False,
                    code="secret_leak_blocked",
                    message=f"potential secret detected at line {lineno} (type: {pattern_name})",
                )
    return GateResult(passed=True, code=None, message=None)
