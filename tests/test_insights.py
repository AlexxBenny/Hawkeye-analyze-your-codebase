"""Tests for deterministic insight derivation (core/insights.py)."""

import pytest

from hawkeye.core.insights import (
    Insight,
    derive_module_insights,
    insights_compact,
    insights_full,
    classify_risk,
    _THRESHOLDS,
)


# ── Insight dataclass ─────────────────────────────────────────


class TestInsight:
    """Tests for the Insight data type."""

    def test_compact_is_just_code(self):
        i = Insight(
            code="high_instability", severity="warning",
            metric="instability", value=0.9, threshold=0.8,
            detail="I=0.90: high outgoing vs incoming dependencies",
        )
        assert i.to_compact() == "high_instability"

    def test_to_dict_has_three_fields(self):
        i = Insight(
            code="high_instability", severity="warning",
            metric="instability", value=0.9, threshold=0.8,
            detail="I=0.90: high outgoing vs incoming dependencies",
        )
        d = i.to_dict()
        assert set(d.keys()) == {"code", "severity", "detail"}

    def test_frozen(self):
        i = Insight(
            code="test", severity="info", metric="x",
            value=0, threshold=0, detail="test",
        )
        with pytest.raises(AttributeError):
            i.code = "changed"


# ── Instability insights ─────────────────────────────────────


class TestInstabilityInsights:
    """Tests for instability-derived insights."""

    def test_high_instability_triggers(self):
        insights = derive_module_insights(instability=0.92, ce=5, ca=1)
        codes = [i.code for i in insights]
        assert "high_instability" in codes

    def test_moderate_instability_no_trigger(self):
        insights = derive_module_insights(instability=0.5, ce=3, ca=3)
        codes = [i.code for i in insights]
        assert "high_instability" not in codes

    def test_very_high_instability_is_critical(self):
        insights = derive_module_insights(instability=0.98, ce=10, ca=0)
        high = [i for i in insights if i.code == "high_instability"]
        assert len(high) == 1
        assert high[0].severity == "critical"

    def test_highly_stable_triggers(self):
        insights = derive_module_insights(instability=0.1, ca=5, ce=1)
        codes = [i.code for i in insights]
        assert "highly_stable" in codes

    def test_stable_without_dependents_no_trigger(self):
        insights = derive_module_insights(instability=0.1, ca=1, ce=0)
        codes = [i.code for i in insights]
        assert "highly_stable" not in codes


# ── Coupling insights ─────────────────────────────────────────


class TestCouplingInsights:
    """Tests for coupling-derived insights."""

    def test_high_efferent(self):
        insights = derive_module_insights(ce=10, ca=0)
        codes = [i.code for i in insights]
        assert "high_efferent" in codes

    def test_high_afferent(self):
        insights = derive_module_insights(ca=10, ce=0)
        codes = [i.code for i in insights]
        assert "high_afferent" in codes

    def test_isolated(self):
        insights = derive_module_insights(ca=0, ce=0)
        codes = [i.code for i in insights]
        assert "isolated" in codes

    def test_normal_coupling_no_trigger(self):
        insights = derive_module_insights(ca=3, ce=3)
        codes = [i.code for i in insights]
        assert "high_efferent" not in codes
        assert "high_afferent" not in codes
        assert "isolated" not in codes


# ── Complexity insights ───────────────────────────────────────


class TestComplexityInsights:
    """Tests for complexity-derived insights."""

    def test_extreme_cyclomatic(self):
        insights = derive_module_insights(cyclomatic=55)
        codes = [i.code for i in insights]
        assert "extreme_cyclomatic" in codes

    def test_high_cyclomatic(self):
        insights = derive_module_insights(cyclomatic=25)
        codes = [i.code for i in insights]
        assert "high_cyclomatic" in codes

    def test_normal_cyclomatic(self):
        insights = derive_module_insights(cyclomatic=5)
        codes = [i.code for i in insights]
        assert "extreme_cyclomatic" not in codes
        assert "high_cyclomatic" not in codes

    def test_extreme_cognitive(self):
        insights = derive_module_insights(cognitive=60)
        codes = [i.code for i in insights]
        assert "extreme_cognitive" in codes

    def test_high_cognitive(self):
        insights = derive_module_insights(cognitive=30)
        codes = [i.code for i in insights]
        assert "high_cognitive" in codes


# ── Size insights ─────────────────────────────────────────────


class TestSizeInsights:

    def test_very_large_module(self):
        insights = derive_module_insights(loc=600)
        codes = [i.code for i in insights]
        assert "very_large_module" in codes

    def test_large_module(self):
        insights = derive_module_insights(loc=350)
        codes = [i.code for i in insights]
        assert "large_module" in codes

    def test_normal_module(self):
        insights = derive_module_insights(loc=100)
        codes = [i.code for i in insights]
        assert "very_large_module" not in codes
        assert "large_module" not in codes


# ── Blast radius insights ────────────────────────────────────


class TestBlastRadiusInsights:

    def test_critical_blast_radius(self):
        insights = derive_module_insights(direct_dependents=12)
        codes = [i.code for i in insights]
        assert "critical_blast_radius" in codes

    def test_high_blast_radius(self):
        insights = derive_module_insights(direct_dependents=6)
        codes = [i.code for i in insights]
        assert "high_blast_radius" in codes

    def test_wide_transitive_reach(self):
        insights = derive_module_insights(direct_dependents=3, transitive_dependents=10)
        codes = [i.code for i in insights]
        assert "wide_transitive_reach" in codes

    def test_no_transitive_reach_when_close(self):
        insights = derive_module_insights(direct_dependents=3, transitive_dependents=4)
        codes = [i.code for i in insights]
        assert "wide_transitive_reach" not in codes


# ── Cycle insights ────────────────────────────────────────────


class TestCycleInsights:

    def test_in_cycle(self):
        insights = derive_module_insights(cycle_count=1, max_cycle_size=3)
        codes = [i.code for i in insights]
        assert "in_cycle" in codes

    def test_large_cycle_is_critical(self):
        insights = derive_module_insights(cycle_count=1, max_cycle_size=6)
        cyc = [i for i in insights if i.code == "in_cycle"]
        assert cyc[0].severity == "critical"

    def test_small_cycle_is_warning(self):
        insights = derive_module_insights(cycle_count=1, max_cycle_size=2)
        cyc = [i for i in insights if i.code == "in_cycle"]
        assert cyc[0].severity == "warning"

    def test_no_cycle(self):
        insights = derive_module_insights(cycle_count=0)
        codes = [i.code for i in insights]
        assert "in_cycle" not in codes


# ── Risk profiles ─────────────────────────────────────────────


class TestRiskProfile:
    """Tests for single-label risk classification."""

    def test_tangled_from_cycles(self):
        assert classify_risk(cycle_count=1) == "tangled"

    def test_tangled_overrides_other_risks(self):
        assert classify_risk(
            ca=10, cyclomatic=50, cognitive=100, cycle_count=1,
        ) == "tangled"

    def test_hub(self):
        assert classify_risk(ca=5, cyclomatic=20) == "hub"

    def test_hub_with_cognitive(self):
        assert classify_risk(ca=6, cognitive=30) == "hub"

    def test_fragile(self):
        assert classify_risk(cyclomatic=25, instability=0.8) == "fragile"

    def test_volatile(self):
        assert classify_risk(instability=0.9, ce=6) == "volatile"

    def test_amplifier(self):
        assert classify_risk(
            direct_dependents=4, transitive_dependents=10,
        ) == "amplifier"

    def test_healthy_returns_none(self):
        assert classify_risk(
            ca=2, ce=2, instability=0.5,
            cyclomatic=5, cognitive=3,
        ) is None

    def test_priority_hub_over_volatile(self):
        assert classify_risk(
            ca=8, ce=8, instability=0.9, cyclomatic=25,
        ) == "hub"

    def test_priority_fragile_over_volatile(self):
        assert classify_risk(
            instability=0.85, ce=6, cyclomatic=30,
        ) == "fragile"


# ── Sorting & output formats ─────────────────────────────────


class TestInsightOutput:

    def test_sorted_by_severity(self):
        insights = derive_module_insights(
            instability=0.98, ce=10, ca=10,
            cyclomatic=55, cognitive=60,
            direct_dependents=12,
        )
        severities = [i.severity for i in insights]
        seen_warning = False
        seen_info = False
        for s in severities:
            if s == "warning":
                seen_warning = True
            if s == "info":
                seen_info = True
            if s == "critical":
                assert not seen_warning and not seen_info

    def test_compact_output(self):
        insights = derive_module_insights(instability=0.95, ce=10, ca=0)
        compact = insights_compact(insights)
        assert isinstance(compact, list)
        assert all(isinstance(c, str) for c in compact)

    def test_full_output(self):
        insights = derive_module_insights(instability=0.95, ce=10, ca=0)
        full = insights_full(insights)
        assert isinstance(full, list)
        assert all("code" in d and "severity" in d and "detail" in d for d in full)

    def test_no_insights_for_healthy_module(self):
        insights = derive_module_insights(
            instability=0.5, ca=2, ce=2,
            cyclomatic=5, cognitive=5,
            loc=50, direct_dependents=1,
        )
        assert len(insights) == 0


# ── Integration with engine ──────────────────────────────────


class TestInsightsIntegration:
    """Tests that insights and risk appear in engine file_context output."""

    def test_compact_insights_in_context(self, tmp_project):
        from hawkeye.engine import HawkeyeEngine
        engine = HawkeyeEngine()
        engine.analyze(str(tmp_project))

        modules = list(engine.graph.nodes.keys())
        ctx = engine.get_file_context(modules[0], compact=True)
        if "insights" in ctx:
            assert isinstance(ctx["insights"], list)
            assert all(isinstance(i, str) for i in ctx["insights"])

    def test_full_insights_in_context(self, tmp_project):
        from hawkeye.engine import HawkeyeEngine
        engine = HawkeyeEngine()
        engine.analyze(str(tmp_project))

        modules = list(engine.graph.nodes.keys())
        ctx = engine.get_file_context(modules[0], compact=False)
        if "insights" in ctx:
            assert isinstance(ctx["insights"], list)
            if ctx["insights"]:
                assert "code" in ctx["insights"][0]
                assert "severity" in ctx["insights"][0]

    def test_risk_is_string_or_absent(self, tmp_project):
        from hawkeye.engine import HawkeyeEngine
        engine = HawkeyeEngine()
        engine.analyze(str(tmp_project))

        for module in engine.graph.nodes:
            ctx = engine.get_file_context(module)
            if "risk" in ctx:
                assert isinstance(ctx["risk"], str)
                assert ctx["risk"] in {"hub", "volatile", "amplifier", "tangled", "fragile"}
