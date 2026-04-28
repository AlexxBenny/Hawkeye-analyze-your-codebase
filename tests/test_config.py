"""Tests for configuration management (config.py)."""

import textwrap
from pathlib import Path

import pytest

from hawkeye.config import (DEFAULT_EXCLUDES, HawkeyeConfig, LayerConfig,
                            RulesConfig, ThresholdConfig)


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


# ── ThresholdConfig ───────────────────────────────────────────


class TestThresholdDefaults:
    """Tests for default threshold values."""

    def test_default_profile(self):
        t = ThresholdConfig()
        assert t.profile == "default"

    def test_default_complexity_thresholds(self):
        t = ThresholdConfig()
        assert t.cc_high == 20
        assert t.cc_critical == 50
        assert t.cog_high == 25
        assert t.cog_critical == 50

    def test_default_coupling_thresholds(self):
        t = ThresholdConfig()
        assert t.ce_high == 8
        assert t.ca_high == 8
        assert t.instability_high == 0.8
        assert t.instability_low == 0.2

    def test_default_size_thresholds(self):
        t = ThresholdConfig()
        assert t.loc_high == 300
        assert t.loc_critical == 500


class TestThresholdProfiles:
    """Tests for built-in threshold profiles."""

    def test_strict_has_lower_thresholds(self):
        s = ThresholdConfig.strict()
        d = ThresholdConfig()
        assert s.profile == "strict"
        assert s.cc_high < d.cc_high
        assert s.cc_critical < d.cc_critical
        assert s.cog_high < d.cog_high
        assert s.loc_critical < d.loc_critical

    def test_relaxed_has_higher_thresholds(self):
        r = ThresholdConfig.relaxed()
        d = ThresholdConfig()
        assert r.profile == "relaxed"
        assert r.cc_high > d.cc_high
        assert r.cc_critical > d.cc_critical
        assert r.cog_high > d.cog_high
        assert r.loc_critical > d.loc_critical


class TestThresholdFromDict:
    """Tests for ThresholdConfig.from_dict parsing."""

    def test_empty_dict_gives_default(self):
        t = ThresholdConfig.from_dict({})
        assert t.profile == "default"
        assert t.cc_high == 20

    def test_profile_selection(self):
        t = ThresholdConfig.from_dict({"profile": "strict"})
        assert t.profile == "strict"
        assert t.cc_high == 10  # strict default

    def test_individual_override(self):
        t = ThresholdConfig.from_dict({"cc_critical": 80})
        assert t.cc_critical == 80
        assert t.profile == "custom"  # auto-marked

    def test_profile_plus_override(self):
        t = ThresholdConfig.from_dict({
            "profile": "relaxed",
            "cc_critical": 100,
        })
        assert t.cc_critical == 100
        assert t.profile == "relaxed+custom"

    def test_unknown_keys_ignored(self):
        t = ThresholdConfig.from_dict({"nonexistent_key": 999})
        assert t.profile == "default"  # unknown key doesn't count as override


class TestThresholdToml:
    """Tests for loading thresholds from TOML files."""

    def test_loads_thresholds_from_toml(self, tmp_path: Path):
        toml = tmp_path / "hawkeye.toml"
        toml.write_text(textwrap.dedent("""\
            [thresholds]
            cc_critical = 80
            loc_critical = 1000
        """), encoding="utf-8")

        config = HawkeyeConfig.from_toml(toml)
        assert config.thresholds.cc_critical == 80
        assert config.thresholds.loc_critical == 1000
        assert config.thresholds.profile == "custom"

    def test_loads_profile_from_toml(self, tmp_path: Path):
        toml = tmp_path / "hawkeye.toml"
        toml.write_text(textwrap.dedent("""\
            [thresholds]
            profile = "relaxed"
        """), encoding="utf-8")

        config = HawkeyeConfig.from_toml(toml)
        assert config.thresholds.profile == "relaxed"
        assert config.thresholds.cc_critical == 80  # relaxed default

    def test_no_thresholds_section_gives_default(self, tmp_path: Path):
        toml = tmp_path / "hawkeye.toml"
        toml.write_text('[project]\nname = "Test"', encoding="utf-8")

        config = HawkeyeConfig.from_toml(toml)
        assert config.thresholds.profile == "default"
        assert config.thresholds.cc_critical == 50


class TestSemanticConsistency:
    """Verify that health and insights use the same thresholds.

    This is the core correctness guarantee: a module should NEVER
    get health='healthy' while also getting a 'critical' insight.
    """

    def test_critical_complexity_consistent(self):
        """If CC >= cc_critical, both health and insights say 'critical'."""
        from hawkeye.core.insights import derive_module_insights
        from hawkeye.core.metrics import _assess_health

        t = ThresholdConfig()
        cc = t.cc_critical  # exactly at threshold

        health = _assess_health(0, 0, 0.0, cc=cc, cog=0, thresholds=t)
        insights = derive_module_insights(cyclomatic=cc, thresholds=t)
        codes = [i.code for i in insights]

        assert health == "critical"
        assert "extreme_cyclomatic" in codes

    def test_critical_cognitive_consistent(self):
        """If CogC >= cog_critical, both health and insights say 'critical'."""
        from hawkeye.core.insights import derive_module_insights
        from hawkeye.core.metrics import _assess_health

        t = ThresholdConfig()
        cog = t.cog_critical

        health = _assess_health(0, 0, 0.0, cc=1, cog=cog, thresholds=t)
        insights = derive_module_insights(cognitive=cog, thresholds=t)
        codes = [i.code for i in insights]

        assert health == "critical"
        assert "extreme_cognitive" in codes

    def test_high_complexity_consistent(self):
        """If CC >= cc_high, both health and insights say 'high'."""
        from hawkeye.core.insights import derive_module_insights
        from hawkeye.core.metrics import _assess_health

        t = ThresholdConfig()
        cc = t.cc_high  # at high threshold

        health = _assess_health(1, 1, 0.5, cc=cc, cog=0, thresholds=t)
        insights = derive_module_insights(cyclomatic=cc, ca=1, ce=1, thresholds=t)
        codes = [i.code for i in insights]

        assert health == "high"
        assert "high_cyclomatic" in codes

    def test_consistency_across_profiles(self):
        """Consistency holds for ALL profiles, not just default."""
        from hawkeye.core.insights import derive_module_insights
        from hawkeye.core.metrics import _assess_health

        for profile_fn in [ThresholdConfig, ThresholdConfig.strict, ThresholdConfig.relaxed]:
            t = profile_fn()
            cc = t.cc_critical

            health = _assess_health(0, 0, 0.0, cc=cc, cog=0, thresholds=t)
            insights = derive_module_insights(cyclomatic=cc, thresholds=t)
            severities = {i.severity for i in insights}

            assert health == "critical", f"Failed for profile {t.profile}"
            assert "critical" in severities, f"Failed for profile {t.profile}"

