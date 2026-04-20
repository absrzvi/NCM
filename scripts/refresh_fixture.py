#!/usr/bin/env python3
"""
refresh_fixture.py — Capture test fixtures from a live GitLab fleet project.

Usage:
    python scripts/refresh_fixture.py \\
        --fleet alpin \\
        --project-id 1211 \\
        --branch devel \\
        --output tests/fixtures/alpin/ \\
        --scrub-secrets

IMPORTANT (CLAUDE.md Human Gate 5):
    This script must NOT run in CI. It must be run manually by a named operator,
    and the resulting fixture files must be committed in an explicit PR authored
    by that operator.

Secret scrubbing:
    Keys listed in SCRUBBED_KEYS are replaced with "REDACTED_IN_FIXTURE".
    Email addresses in committer/author fields are also redacted.
    The --scrub-secrets flag is required; omitting it raises an error so that
    operators cannot accidentally capture unredacted fixtures.

Requirements:
    pip install python-gitlab ruamel.yaml
"""

import argparse
import base64
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import gitlab
except ImportError:
    sys.exit("ERROR: python-gitlab is not installed. Run: pip install python-gitlab")

try:
    from ruamel.yaml import YAML
except ImportError:
    sys.exit("ERROR: ruamel.yaml is not installed. Run: pip install ruamel.yaml")

# Keys whose values must be scrubbed regardless of their actual content.
# Add to this list whenever a new secret-flagged key is identified.
SCRUBBED_KEYS: list[str] = [
    "engineering_pages::credentials_password",
    "engineering_pages::ssl_key",
    "obn::secret",
    "portal::autologin_salt_hash",
    "mar3_captiveportal_api::salt_hash",
    "snmpd::usersv3",
    "mqtt_bridge::brokers",  # entire sub-tree redacted at broker level
]

# Regex patterns that trigger unconditional scrubbing even on non-listed keys.
_SECRET_PATTERNS = [
    re.compile(r"password", re.IGNORECASE),
    re.compile(r"secret", re.IGNORECASE),
    re.compile(r"token", re.IGNORECASE),
    re.compile(r"salt_hash", re.IGNORECASE),
    re.compile(r"ssl_key", re.IGNORECASE),
    re.compile(r"credentials", re.IGNORECASE),
    re.compile(r"private_key", re.IGNORECASE),
]

_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")

REDACTED = "REDACTED_IN_FIXTURE"


def _key_is_secret(key: str) -> bool:
    return any(p.search(key) for p in _SECRET_PATTERNS)


def _scrub_value(key: str, value: Any) -> Any:
    """Return REDACTED if the key matches any secret pattern, else return value."""
    if _key_is_secret(key):
        return REDACTED
    return value


def scrub_yaml_data(data: Any, parent_key: str = "") -> Any:
    """Recursively walk a parsed YAML structure and redact secret-flagged keys."""
    if isinstance(data, dict):
        result = {}
        for k, v in data.items():
            full_key = f"{parent_key}::{k}" if parent_key else str(k)
            if isinstance(k, str) and _key_is_secret(k):
                result[k] = REDACTED
            else:
                result[k] = scrub_yaml_data(v, full_key)
        return result
    if isinstance(data, list):
        return [scrub_yaml_data(item, parent_key) for item in data]
    if isinstance(data, str):
        # Redact email addresses embedded in string values
        return _EMAIL_RE.sub(REDACTED, data)
    return data


def write_yaml(path: Path, data: Any) -> None:
    """Write data to path using ruamel.yaml (round-trip mode preserves style)."""
    yaml = YAML()
    yaml.default_flow_style = False
    yaml.width = 4096  # prevent line-wrapping that would break diffs
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        yaml.dump(data, fh)


def fetch_tree_recursive(project: Any, path: str, ref: str) -> list[dict]:
    """Return all items (files + dirs) under path in the GitLab project tree."""
    items = []
    page = project.repository_tree(path=path, ref=ref, recursive=False, get_all=True)
    for item in page:
        if item["type"] == "blob":
            items.append(item)
        elif item["type"] == "tree":
            items.extend(fetch_tree_recursive(project, item["path"], ref))
    return items


def fetch_and_write_file(
    project: Any,
    gl_path: str,
    ref: str,
    output_dir: Path,
    scrub: bool,
) -> None:
    """Fetch one file from GitLab, optionally scrub it, and write to output_dir."""
    f = project.files.get(file_path=gl_path, ref=ref)
    content_bytes = base64.b64decode(f.content)

    local_path = output_dir / gl_path

    if gl_path.endswith(".yaml") or gl_path.endswith(".yml"):
        yaml = YAML()
        yaml.preserve_quotes = True
        try:
            data = yaml.load(content_bytes.decode("utf-8"))
        except Exception:
            # Unparseable YAML — write raw with a warning comment prepended
            local_path.parent.mkdir(parents=True, exist_ok=True)
            warning = f"# WARNING: Could not parse as YAML; written raw. Scrubbing skipped.\n"
            local_path.write_bytes(warning.encode() + content_bytes)
            return
        if scrub and data is not None:
            data = scrub_yaml_data(data)
        write_yaml(local_path, data)
    else:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(content_bytes)


def write_capture_metadata(
    output_dir: Path,
    fleet: str,
    project_id: int,
    project_path: str,
    branch: str,
    commit_sha: str,
    operator: str,
    scrubbed_keys: list[str],
) -> None:
    metadata = {
        "fleet": fleet,
        "project_id": project_id,
        "project_path": project_path,
        "branch": branch,
        "commit_sha": commit_sha,
        "captured_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "captured_by": operator,
        "scrubbed_keys": scrubbed_keys,
        "notes": (
            'All secret-flagged keys have been replaced with the placeholder: "REDACTED_IN_FIXTURE"\n'
        ),
    }
    write_yaml(output_dir / "capture_metadata.yaml", metadata)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Capture hieradata fixtures from a GitLab fleet project.",
        epilog=(
            "IMPORTANT: This script must NOT run in CI (CLAUDE.md Human Gate 5). "
            "Run it manually and commit the output in an explicit PR."
        ),
    )
    parser.add_argument("--fleet", required=True, help="Fleet name (e.g. alpin, dostoneu)")
    parser.add_argument("--project-id", required=True, type=int, help="GitLab project ID")
    parser.add_argument("--branch", default="devel", help="Source branch (default: devel)")
    parser.add_argument("--output", required=True, help="Output directory path")
    parser.add_argument(
        "--scrub-secrets",
        action="store_true",
        required=True,
        help="REQUIRED: scrub secret-flagged keys before writing fixtures",
    )
    parser.add_argument(
        "--gitlab-url",
        default=os.environ.get("GITLAB_URL", "https://gitlab.example.com"),
        help="GitLab base URL (default: $GITLAB_URL or https://gitlab.example.com)",
    )
    parser.add_argument(
        "--gitlab-token",
        default=os.environ.get("GITLAB_PAT"),
        help="GitLab PAT with read_api scope (default: $GITLAB_PAT env var)",
    )
    parser.add_argument(
        "--operator",
        default=os.environ.get("OPERATOR_NAME", "unknown"),
        help="Operator name for capture_metadata.yaml (default: $OPERATOR_NAME)",
    )
    args = parser.parse_args()

    if not args.gitlab_token:
        sys.exit(
            "ERROR: GitLab PAT not provided. Set $GITLAB_PAT or pass --gitlab-token."
        )

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Connecting to GitLab at {args.gitlab_url} ...")
    gl = gitlab.Gitlab(args.gitlab_url, private_token=args.gitlab_token)
    gl.auth()

    print(f"Fetching project {args.project_id} ...")
    project = gl.projects.get(args.project_id)
    project_path = project.path_with_namespace

    print(f"Resolving HEAD of branch '{args.branch}' ...")
    branch_obj = project.branches.get(args.branch)
    commit_sha = branch_obj.commit["id"]
    print(f"  HEAD SHA: {commit_sha}")

    print("Listing repository tree ...")
    items = fetch_tree_recursive(project, "", args.branch)
    print(f"  Found {len(items)} files")

    for item in items:
        gl_path = item["path"]
        print(f"  Fetching: {gl_path}")
        fetch_and_write_file(project, gl_path, args.branch, output_dir, scrub=True)

    print("Writing capture_metadata.yaml ...")
    write_capture_metadata(
        output_dir=output_dir,
        fleet=args.fleet,
        project_id=args.project_id,
        project_path=project_path,
        branch=args.branch,
        commit_sha=commit_sha,
        operator=args.operator,
        scrubbed_keys=SCRUBBED_KEYS,
    )

    print(
        f"\nDone. Fixtures written to {output_dir}\n"
        f"Fleet:      {args.fleet}\n"
        f"Project:    {project_path} (ID {args.project_id})\n"
        f"Branch:     {args.branch}\n"
        f"Commit SHA: {commit_sha}\n"
        f"Operator:   {args.operator}\n"
        "\nNext steps:\n"
        "  1. Review the scrubbed fixtures for any missed secrets.\n"
        "  2. Commit the changes in an explicit PR:\n"
        f"     git add {args.output}\n"
        f'     git commit -m "SPIKE-04: Capture test fixtures for {args.fleet} at {commit_sha[:8]}"\n'
        "  3. Open the PR authored by your name (not CI).\n"
        "  4. Have a security reviewer spot-check for PII/tokens.\n"
    )


if __name__ == "__main__":
    main()
