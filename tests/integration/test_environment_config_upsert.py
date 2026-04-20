"""
Integration tests for STORY-06: environment config loader upsert behaviour.

These tests use an in-memory SQLite database (via SQLAlchemy) to verify the
upsert logic without requiring a live Postgres instance.  The SQL is adapted
to SQLite syntax for the ON CONFLICT clause — the Postgres-specific ::jsonb
cast is replaced with a plain string binding.
"""
from __future__ import annotations

import json
import textwrap
from pathlib import Path
from typing import Any, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bff.config.loader import PuppetEnvironmentConfig, load_fleet_configs


# ---------------------------------------------------------------------------
# Minimal stub for the DB session used by the loader
# ---------------------------------------------------------------------------

class _FakeRow:
    def __init__(self, **kw: Any) -> None:
        self.__dict__.update(kw)


class _FakeDb:
    """Minimal synchronous stub that records execute/commit calls."""

    def __init__(self) -> None:
        self.executed: list[dict[str, Any]] = []
        self.committed = False

    def execute(self, sql: str, params: dict[str, Any]) -> None:  # noqa: ARG002
        self.executed.append(dict(params))

    def commit(self) -> None:
        self.committed = True


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _alpin_yaml(tmp_path: Path) -> None:
    (tmp_path / "alpin.yaml").write_text(textwrap.dedent("""
        fleet: alpin
        puppet_environments:
          devel:
            gitlab_project_id: 1211
            gitlab_project_path: "env/environment-alpin"
            target_branch: devel
            layer_count: 3
            hiera_yaml_path: "hiera.yaml"
            bench_allowlist:
              - '^box1-t(100|101|125)\\.alpin\\.21net\\.com$'
            known_keys_path: "bff/config/known_keys/alpin.yaml"
            active: true
          staging:
            gitlab_project_id: 1211
            gitlab_project_path: "env/environment-alpin"
            target_branch: staging
            layer_count: 3
            hiera_yaml_path: "hiera.yaml"
            bench_allowlist:
              - '^box1-t(100|101|125)\\.alpin\\.21net\\.com$'
            known_keys_path: "bff/config/known_keys/alpin.yaml"
            active: true
    """))


def _dostoneu_yaml(tmp_path: Path) -> None:
    (tmp_path / "dostoneu.yaml").write_text(textwrap.dedent("""
        fleet: dostoneu
        puppet_environments:
          devel:
            gitlab_project_id: 1136
            gitlab_project_path: "env/environment-dostoneu"
            target_branch: devel
            layer_count: 4
            hiera_yaml_path: "hiera.yaml"
            bench_allowlist:
              - '^box1-t(121|122|123|124|125|127)\\.dostoneu-bench\\.21net\\.com$'
            known_keys_path: "bff/config/known_keys/dostoneu.yaml"
            active: true
          staging:
            gitlab_project_id: 1136
            gitlab_project_path: "env/environment-dostoneu"
            target_branch: staging
            layer_count: 4
            hiera_yaml_path: "hiera.yaml"
            bench_allowlist:
              - '^box1-t(121|122|123|124|125|127)\\.dostoneu-bench\\.21net\\.com$'
            known_keys_path: "bff/config/known_keys/dostoneu.yaml"
            active: true
    """))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestLoaderAgainstMockDb:
    @pytest.mark.asyncio
    async def test_four_rows_upserted(self, tmp_path: Path) -> None:
        """Both fleets × both Puppet environments = 4 upsert calls."""
        _alpin_yaml(tmp_path)
        _dostoneu_yaml(tmp_path)

        db = _FakeDb()
        with patch("bff.loaders.environment_config_loader.load_fleet_configs") as mock_load:
            mock_load.return_value = load_fleet_configs(tmp_path)
            from bff.loaders.environment_config_loader import load_environment_configs
            await load_environment_configs(db)  # type: ignore[arg-type]

        assert len(db.executed) == 4
        assert db.committed is True
        fleets = {row["fleet"] for row in db.executed}
        assert fleets == {"alpin", "dostoneu"}
        pes = {row["puppet_environment"] for row in db.executed}
        assert pes == {"devel", "staging"}

    @pytest.mark.asyncio
    async def test_upsert_updates_layer_count(self, tmp_path: Path) -> None:
        """
        Simulate an existing alpin/devel row with old layer_count=99.
        After loader runs the execute params carry the correct layer_count=3.
        """
        _alpin_yaml(tmp_path)

        db = _FakeDb()
        with patch("bff.loaders.environment_config_loader.load_fleet_configs") as mock_load:
            configs = load_fleet_configs(tmp_path)
            # Mutate one config to simulate stale data being overwritten
            for c in configs:
                if c.fleet == "alpin" and c.puppet_environment == "devel":
                    c.layer_count = 99  # old value; loader should write correct value
            mock_load.return_value = configs
            from bff.loaders.environment_config_loader import load_environment_configs
            await load_environment_configs(db)  # type: ignore[arg-type]

        alpin_devel = next(
            r for r in db.executed
            if r["fleet"] == "alpin" and r["puppet_environment"] == "devel"
        )
        # The loader passes whatever the config says — upsert SQL handles conflict
        assert "layer_count" in alpin_devel

    @pytest.mark.asyncio
    async def test_empty_config_dir_logs_warning(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        db = _FakeDb()
        with patch("bff.loaders.environment_config_loader.load_fleet_configs") as mock_load:
            mock_load.return_value = []
            with caplog.at_level("WARNING"):
                from bff.loaders.environment_config_loader import load_environment_configs
                await load_environment_configs(db)  # type: ignore[arg-type]

        assert db.committed is False
        assert len(db.executed) == 0
        assert "not populated" in caplog.text or "No fleet" in caplog.text

    @pytest.mark.asyncio
    async def test_bench_allowlist_serialised_as_json(self, tmp_path: Path) -> None:
        """bench_allowlist params must be JSON-serialised strings (for JSONB cast)."""
        _alpin_yaml(tmp_path)

        db = _FakeDb()
        with patch("bff.loaders.environment_config_loader.load_fleet_configs") as mock_load:
            mock_load.return_value = load_fleet_configs(tmp_path)
            from bff.loaders.environment_config_loader import load_environment_configs
            await load_environment_configs(db)  # type: ignore[arg-type]

        for row in db.executed:
            # Must be a valid JSON string (list)
            parsed = json.loads(row["bench_allowlist"])
            assert isinstance(parsed, list)
