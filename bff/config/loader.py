"""
Environment config loader — reads per-fleet YAML config files at BFF startup
and provides helpers for certname validation and bench-allowlist checks (D13/D15).
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# D15: these branch names are unconditionally refused.
_FORBIDDEN_BRANCHES: frozenset[str] = frozenset({"master", "ODEG"})

# Valid certname pattern (CLAUDE.md Security Depth section).
_CERTNAME_RE: re.Pattern[str] = re.compile(
    r"^[a-z0-9][a-z0-9-]*(\.[a-z0-9-]+)*$"
)

_CONFIG_DIR = Path(__file__).parent
_ENV_DIR = _CONFIG_DIR / "environments"
_ALLOWLIST_DIR = _CONFIG_DIR / "bench_allowlists"


# ---------------------------------------------------------------------------
# Internal data structures
# ---------------------------------------------------------------------------

class PuppetEnvironmentConfig:
    """Parsed config for a single fleet + Puppet environment combination."""

    def __init__(self, fleet: str, puppet_environment: str, data: dict[str, Any]) -> None:
        self.fleet: str = fleet
        self.puppet_environment: str = puppet_environment
        self.gitlab_project_id: int = int(data["gitlab_project_id"])
        self.gitlab_project_path: str = data["gitlab_project_path"]
        self.target_branch: str = data["target_branch"]
        self.layer_count: int = int(data["layer_count"])
        self.hiera_yaml_path: str = data["hiera_yaml_path"]
        self.bench_allowlist: list[str] = list(data.get("bench_allowlist", []))
        self.known_keys_path: str = data["known_keys_path"]
        self.active: bool = bool(data.get("active", True))


# ---------------------------------------------------------------------------
# File-level loaders
# ---------------------------------------------------------------------------

def load_fleet_configs(env_dir: Path = _ENV_DIR) -> list[PuppetEnvironmentConfig]:
    """
    Read all .yaml files under *env_dir* and return a flat list of
    PuppetEnvironmentConfig objects.  Malformed files are logged and skipped.
    """
    configs: list[PuppetEnvironmentConfig] = []
    for path in sorted(env_dir.glob("*.yaml")):
        try:
            with path.open() as fh:
                doc: dict[str, Any] = yaml.safe_load(fh)
            fleet: str = doc["fleet"]
            puppet_envs: dict[str, Any] = doc["puppet_environments"]
            for pe_name, pe_data in puppet_envs.items():
                cfg = PuppetEnvironmentConfig(fleet, pe_name, pe_data)
                configs.append(cfg)
                logger.info(
                    "Loaded fleet config: fleet=%s puppet_environment=%s "
                    "project_id=%d target_branch=%s layer_count=%d",
                    fleet, pe_name, cfg.gitlab_project_id,
                    cfg.target_branch, cfg.layer_count,
                )
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to load fleet config from %s: %s", path, exc)
    return configs


def load_bench_allowlists(
    allowlist_dir: Path = _ALLOWLIST_DIR,
) -> dict[str, list[str]]:
    """
    Read all .yaml files under *allowlist_dir* and return a mapping of
    fleet → list[regex pattern string].  Malformed files are logged and skipped.
    """
    allowlists: dict[str, list[str]] = {}
    for path in sorted(allowlist_dir.glob("*.yaml")):
        try:
            with path.open() as fh:
                doc: dict[str, Any] = yaml.safe_load(fh)
            fleet: str = doc["fleet"]
            patterns: list[str] = [str(p) for p in doc.get("patterns", [])]
            allowlists[fleet] = patterns
            logger.info(
                "Loaded bench allowlist: fleet=%s patterns=%d", fleet, len(patterns)
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to load bench allowlist from %s: %s", path, exc)
    return allowlists


# ---------------------------------------------------------------------------
# Validation helpers (used by D13 envelope / force-run endpoint)
# ---------------------------------------------------------------------------

def validate_certname(node_target: str) -> bool:
    """Return True if *node_target* matches the permitted certname pattern."""
    return bool(_CERTNAME_RE.match(node_target))


def is_bench_certname(node_target: str, fleet: str, allowlists: dict[str, list[str]]) -> bool:
    """
    Return True if *node_target* matches at least one pattern in the bench
    allowlist for *fleet*.

    Caller must already have verified the certname is syntactically valid
    (validate_certname) before calling this function.
    """
    patterns = allowlists.get(fleet, [])
    return any(re.match(pattern, node_target) for pattern in patterns)


def assert_target_branch_allowed(target_branch: str) -> None:
    """
    Raise ValueError if *target_branch* is in the forbidden set (D15).

    Refused branches: master, ODEG — hardcoded per D15.
    """
    if target_branch in _FORBIDDEN_BRANCHES:
        raise ValueError(
            f"Target branch '{target_branch}' is not permitted (D15). "
            f"Only devel and staging are writable."
        )
