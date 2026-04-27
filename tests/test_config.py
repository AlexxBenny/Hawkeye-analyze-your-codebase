"""Tests for configuration management (config.py)."""

import textwrap
from pathlib import Path

import pytest

from hawkeye.config import (DEFAULT_EXCLUDES, HawkeyeConfig, LayerConfig,
                            RulesConfig)


class TestDefaults:
    """Tests for default configuration values."""

    def test_default_excludes(self):
        config = HawkeyeConfig()
        assert "__pycache__" in config.exclude_dirs
        assert ".git" in config.exclude_dirs
        assert "venv" in config.exclude_dirs

    def test_default_format(self):
        config = HawkeyeConfig()
        assert config.output_format == "text"

    def test_default_no_rules(self):
        config = HawkeyeConfig()
        assert config.rules.layers is None
        assert config.rules.forbidden == []
        assert config.rules.independence == []


class TestFromToml:
    """Tests for TOML file loading."""

    def test_loads_scan_config(self, tmp_path: Path):
        toml = tmp_path / "hawkeye.toml"
        toml.write_text(textwrap.dedent("""\
            [scan]
            exclude_dirs = ["venv", "build"]
            exclude_patterns = ["*.tests.*"]
            include_patterns = ["myproject.*"]
        """), encoding="utf-8")

        config = HawkeyeConfig.from_toml(toml)
        assert config.exclude_dirs == {"venv", "build"}
        assert config.exclude_patterns == ["*.tests.*"]
        assert config.include_patterns == ["myproject.*"]

    def test_loads_project_config(self, tmp_path: Path):
        toml = tmp_path / "hawkeye.toml"
        toml.write_text(textwrap.dedent("""\
            [project]
            name = "MyApp"
            path = "/some/path"
        """), encoding="utf-8")

        config = HawkeyeConfig.from_toml(toml)
        assert config.project_name == "MyApp"
        assert config.project_path == "/some/path"

    def test_loads_analysis_config(self, tmp_path: Path):
        toml = tmp_path / "hawkeye.toml"
        toml.write_text(textwrap.dedent("""\
            [analysis]
            max_depth = 3
            max_hops = 5
            include_external = true
        """), encoding="utf-8")

        config = HawkeyeConfig.from_toml(toml)
        assert config.max_depth == 3
        assert config.max_hops == 5
        assert config.include_external is True

    def test_loads_layer_rules(self, tmp_path: Path):
        toml = tmp_path / "hawkeye.toml"
        toml.write_text(textwrap.dedent("""\
            [rules.layers]
            order = ["domain", "application", "infrastructure"]
            direction = "downward"
        """), encoding="utf-8")

        config = HawkeyeConfig.from_toml(toml)
        assert config.rules.layers is not None
        assert config.rules.layers.order == ["domain", "application", "infrastructure"]
        assert config.rules.layers.direction == "downward"

    def test_loads_forbidden_rules(self, tmp_path: Path):
        toml = tmp_path / "hawkeye.toml"
        toml.write_text(textwrap.dedent("""\
            [[rules.forbidden]]
            from = "api.*"
            to = ["cli.*", "infrastructure.*"]
        """), encoding="utf-8")

        config = HawkeyeConfig.from_toml(toml)
        assert len(config.rules.forbidden) == 1
        assert config.rules.forbidden[0]["from"] == "api.*"

    def test_empty_toml(self, tmp_path: Path):
        toml = tmp_path / "hawkeye.toml"
        toml.write_text("", encoding="utf-8")

        config = HawkeyeConfig.from_toml(toml)
        assert isinstance(config, HawkeyeConfig)


class TestFindAndLoad:
    """Tests for walk-up config file discovery."""

    def test_finds_in_current_dir(self, tmp_path: Path):
        toml = tmp_path / "hawkeye.toml"
        toml.write_text('[project]\nname = "Found"', encoding="utf-8")

        config = HawkeyeConfig.find_and_load(tmp_path)
        assert config.project_name == "Found"

    def test_finds_in_parent_dir(self, tmp_path: Path):
        toml = tmp_path / "hawkeye.toml"
        toml.write_text('[project]\nname = "Parent"', encoding="utf-8")

        subdir = tmp_path / "sub" / "deep"
        subdir.mkdir(parents=True)

        config = HawkeyeConfig.find_and_load(subdir)
        assert config.project_name == "Parent"

    def test_returns_default_if_not_found(self, tmp_path: Path):
        config = HawkeyeConfig.find_and_load(tmp_path)
        assert isinstance(config, HawkeyeConfig)
        assert config.project_name is None
