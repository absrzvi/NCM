"""
Unit tests for STORY-06: environment config loader and helpers.

Tests:
- parse alpin.yaml → correct fields
- parse dostoneu.yaml → 4 layers
- loader skips malformed YAML and logs error
- certname validation: valid passes, invalid rejected (400-equivalent)
- bench allowlist: non-bench certname rejected (403-equivalent)
- D15: master branch refused
"""
from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Generator

import pytest
import yaml

from bff.config.loader import (
    PuppetEnvironmentConfig,
    assert_target_branch_allowed,
    is_bench_certname,
    load_bench_allowlists,
    load_fleet_configs,
    validate_certname,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_yaml(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(textwrap.dedent(content))
    return p


# ---------------------------------------------------------------------------
# Fleet config parsing — alpin
# ---------------------------------------------------------------------------

class TestLoadAlpinConfig:
    def test_fleet_name(self, tmp_path: Path) -> None:
        _write_yaml(tmp_path, "alpin.yaml", """
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
        """)
        configs = load_fleet_configs(tmp_path)
        assert len(configs) == 1
        assert configs[0].fleet == "alpin"

    def test_project_id(self, tmp_path: Path) -> None:
        _write_yaml(tmp_path, "alpin.yaml", """
            fleet: alpin
            puppet_environments:
              devel:
                gitlab_project_id: 1211
                gitlab_project_path: "env/environment-alpin"
                target_branch: devel
                layer_count: 3
                hiera_yaml_path: "hiera.yaml"
                bench_allowlist: []
                known_keys_path: "bff/config/known_keys/alpin.yaml"
                active: true
        """)
        configs = load_fleet_configs(tmp_path)
        assert configs[0].gitlab_project_id == 1211

    def test_layer_count(self, tmp_path: Path) -> None:
        _write_yaml(tmp_path, "alpin.yaml", """
            fleet: alpin
            puppet_environments:
              devel:
                gitlab_project_id: 1211
                gitlab_project_path: "env/environment-alpin"
                target_branch: devel
                layer_count: 3
                hiera_yaml_path: "hiera.yaml"
                bench_allowlist: []
                known_keys_path: "bff/config/known_keys/alpin.yaml"
                active: true
        """)
        configs = load_fleet_configs(tmp_path)
        assert configs[0].layer_count == 3

    def test_bench_allowlist(self, tmp_path: Path) -> None:
        _write_yaml(tmp_path, "alpin.yaml", """
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
        """)
        configs = load_fleet_configs(tmp_path)
        assert len(configs[0].bench_allowlist) == 1
        assert "alpin" in configs[0].bench_allowlist[0]

    def test_two_puppet_environments(self, tmp_path: Path) -> None:
        _write_yaml(tmp_path, "alpin.yaml", """
            fleet: alpin
            puppet_environments:
              devel:
                gitlab_project_id: 1211
                gitlab_project_path: "env/environment-alpin"
                target_branch: devel
                layer_count: 3
                hiera_yaml_path: "hiera.yaml"
                bench_allowlist: []
                known_keys_path: "bff/config/known_keys/alpin.yaml"
                active: true
              staging:
                gitlab_project_id: 1211
                gitlab_project_path: "env/environment-alpin"
                target_branch: staging
                layer_count: 3
                hiera_yaml_path: "hiera.yaml"
                bench_allowlist: []
                known_keys_path: "bff/config/known_keys/alpin.yaml"
                active: true
        """)
        configs = load_fleet_configs(tmp_path)
        assert len(configs) == 2
        pe_names = {c.puppet_environment for c in configs}
        assert pe_names == {"devel", "staging"}


# ---------------------------------------------------------------------------
# Fleet config parsing — dostoneu
# ---------------------------------------------------------------------------

class TestLoadDostoneuConfig:
    def test_layer_count_is_4(self, tmp_path: Path) -> None:
        _write_yaml(tmp_path, "dostoneu.yaml", """
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
        """)
        configs = load_fleet_configs(tmp_path)
        assert configs[0].layer_count == 4

    def test_project_id_is_1136(self, tmp_path: Path) -> None:
        _write_yaml(tmp_path, "dostoneu.yaml", """
            fleet: dostoneu
            puppet_environments:
              devel:
                gitlab_project_id: 1136
                gitlab_project_path: "env/environment-dostoneu"
                target_branch: devel
                layer_count: 4
                hiera_yaml_path: "hiera.yaml"
                bench_allowlist: []
                known_keys_path: "bff/config/known_keys/dostoneu.yaml"
                active: true
        """)
        configs = load_fleet_configs(tmp_path)
        assert configs[0].gitlab_project_id == 1136


# ---------------------------------------------------------------------------
# Loader robustness
# ---------------------------------------------------------------------------

class TestLoaderSkipsMalformedYaml:
    def test_malformed_yaml_is_skipped(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        bad = tmp_path / "bad.yaml"
        bad.write_text(": this: is: not: valid: yaml: [\n")
        good = tmp_path / "good.yaml"
        good.write_text(textwrap.dedent("""
            fleet: alpin
            puppet_environments:
              devel:
                gitlab_project_id: 1211
                gitlab_project_path: "env/environment-alpin"
                target_branch: devel
                layer_count: 3
                hiera_yaml_path: "hiera.yaml"
                bench_allowlist: []
                known_keys_path: "bff/config/known_keys/alpin.yaml"
                active: true
        """))
        with caplog.at_level("ERROR"):
            configs = load_fleet_configs(tmp_path)
        assert len(configs) == 1
        assert "bad.yaml" in caplog.text or "Failed" in caplog.text

    def test_missing_required_key_is_skipped(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        _write_yaml(tmp_path, "broken.yaml", "fleet: only_fleet_no_puppet_environments\n")
        with caplog.at_level("ERROR"):
            configs = load_fleet_configs(tmp_path)
        assert configs == []


# ---------------------------------------------------------------------------
# Certname validation — D15 / CLAUDE.md Security Depth
# ---------------------------------------------------------------------------

class TestValidateCertname:
    @pytest.mark.parametrize("certname", [
        "box1-t100.alpin.21net.com",
        "myhost",
        "host-01.example.com",
        "a",
        "a1-b2.c3-d4.e5",
    ])
    def test_valid_certname_passes(self, certname: str) -> None:
        assert validate_certname(certname) is True

    @pytest.mark.parametrize("certname", [
        "",
        "-startwithdash.example.com",
        "UPPERCASE.example.com",
        "has space.example.com",
        "has_underscore.example.com",
        "../etc/passwd",
        "host..double.dot.com",
    ])
    def test_invalid_certname_rejected(self, certname: str) -> None:
        # Invalid certname → caller should respond 400
        assert validate_certname(certname) is False


# ---------------------------------------------------------------------------
# Bench allowlist check — D13
# ---------------------------------------------------------------------------

class TestIsBenchCertname:
    _ALLOWLISTS = {
        "alpin": [r"^box1-t(100|101|125)\.alpin\.21net\.com$"],
        "dostoneu": [r"^box1-t(121|122|123|124|125|127)\.dostoneu-bench\.21net\.com$"],
    }

    @pytest.mark.parametrize("certname", [
        "box1-t100.alpin.21net.com",
        "box1-t101.alpin.21net.com",
        "box1-t125.alpin.21net.com",
    ])
    def test_valid_bench_certname_passes(self, certname: str) -> None:
        assert is_bench_certname(certname, "alpin", self._ALLOWLISTS) is True

    @pytest.mark.parametrize("certname", [
        "box1-t200.alpin.21net.com",
        "prod-server.alpin.21net.com",
        "box1-t100.alpin.21net.com.evil.com",
    ])
    def test_non_bench_certname_rejected(self, certname: str) -> None:
        # Non-bench certname → caller should respond 403
        assert is_bench_certname(certname, "alpin", self._ALLOWLISTS) is False

    def test_unknown_fleet_returns_false(self) -> None:
        assert is_bench_certname("box1-t100.alpin.21net.com", "dani", self._ALLOWLISTS) is False


# ---------------------------------------------------------------------------
# D15: master / ODEG branch enforcement
# ---------------------------------------------------------------------------

class TestAssertTargetBranchAllowed:
    def test_devel_is_allowed(self) -> None:
        assert_target_branch_allowed("devel")  # must not raise

    def test_staging_is_allowed(self) -> None:
        assert_target_branch_allowed("staging")  # must not raise

    def test_master_is_refused(self) -> None:
        with pytest.raises(ValueError, match="master"):
            assert_target_branch_allowed("master")

    def test_ODEG_is_refused(self) -> None:
        with pytest.raises(ValueError, match="ODEG"):
            assert_target_branch_allowed("ODEG")


# ---------------------------------------------------------------------------
# Bench allowlist file loader
# ---------------------------------------------------------------------------

class TestLoadBenchAllowlists:
    def test_loads_fleet_and_patterns(self, tmp_path: Path) -> None:
        _write_yaml(tmp_path, "alpin.yaml", """
            fleet: alpin
            patterns:
              - '^box1-t(100|101|125)\\.alpin\\.21net\\.com$'
        """)
        allowlists = load_bench_allowlists(tmp_path)
        assert "alpin" in allowlists
        assert len(allowlists["alpin"]) == 1

    def test_malformed_file_skipped(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        bad = tmp_path / "bad.yaml"
        bad.write_text(": [\n")
        with caplog.at_level("ERROR"):
            allowlists = load_bench_allowlists(tmp_path)
        assert allowlists == {}
