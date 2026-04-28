"""Tests for coupling metrics and health scoring (core/metrics.py)."""

from hawkeye.core.analyzer import SymbolTable
from hawkeye.core.metrics import (ModuleMetrics, ProjectMetrics,
                                  _assess_health, calculate_module_metrics,
                                  calculate_project_metrics,
                                  format_metrics_table)


class TestAssessHealth:
    """Tests for module health classification (5-level system)."""

    def test_isolated_module_is_healthy(self):
        assert _assess_health(ca=0, ce=0, instability=0.0) == "healthy"

    def test_high_instability_high_coupling_is_critical(self):
        assert _assess_health(ca=1, ce=10, instability=0.91) == "critical"

    def test_moderate_coupling_is_elevated(self):
        # I=0.75 > 0.8*0.875=0.7, Ce=6 > 8*0.625=5 → elevated
        assert _assess_health(ca=2, ce=6, instability=0.75) == "elevated"

    def test_low_coupling_is_healthy(self):
        assert _assess_health(ca=3, ce=2, instability=0.4) == "healthy"

    def test_extreme_cyclomatic_is_critical(self):
        assert _assess_health(ca=1, ce=1, instability=0.5, cc=55) == "critical"

    def test_extreme_cognitive_is_critical(self):
        assert _assess_health(ca=1, ce=1, instability=0.5, cog=65) == "critical"

    def test_high_complexity_is_high(self):
        assert _assess_health(ca=1, ce=1, instability=0.5, cc=25) == "high"

    def test_elevated_complexity(self):
        assert _assess_health(ca=1, ce=1, instability=0.5, cc=12) == "elevated"

    def test_moderate_complexity(self):
        assert _assess_health(ca=1, ce=1, instability=0.5, cc=6) == "moderate"

    def test_high_outgoing_no_dependents_is_high(self):
        assert _assess_health(ca=0, ce=12, instability=1.0) == "critical"

    def test_parse_error_is_unknown(self):
        assert _assess_health(ca=0, ce=0, instability=0.0, parse_error=True) == "unknown"


class TestCalculateModuleMetrics:
    """Tests for per-module metric computation."""

    def test_metrics_for_all_nodes(self, simple_graph):
        metrics = calculate_module_metrics(simple_graph)
        assert set(metrics.keys()) == {"A", "B", "C"}

    def test_afferent_coupling(self, simple_graph):
        metrics = calculate_module_metrics(simple_graph)
        assert metrics["C"].ca == 2  # A and B depend on C
        assert metrics["A"].ca == 0  # Nothing depends on A

    def test_efferent_coupling(self, simple_graph):
        metrics = calculate_module_metrics(simple_graph)
        assert metrics["A"].ce == 2  # A depends on B and C
        assert metrics["C"].ce == 0  # C depends on nothing

    def test_instability(self, simple_graph):
        metrics = calculate_module_metrics(simple_graph)
        # A: Ce=2, Ca=0 → I = 2/(0+2) = 1.0
        assert metrics["A"].instability == 1.0
        # C: Ce=0, Ca=2 → I = 0/(2+0) = 0.0
        assert metrics["C"].instability == 0.0

    def test_with_symbol_tables(self, simple_graph):
        st = {"A": SymbolTable(
            classes=[], functions=[],
            class_count=2, function_count=3, method_count=5,
            cyclomatic_complexity=15, cognitive_complexity=10,
        )}
        metrics = calculate_module_metrics(simple_graph, symbol_tables=st)
        assert metrics["A"].class_count == 2
        assert metrics["A"].function_count == 3
        assert metrics["A"].cyclomatic_complexity == 15

    def test_health_emoji(self):
        m = ModuleMetrics(
            module_name="x", ca=0, ce=0, instability=0.0,
            loc=10, import_count=0, fan_in=0, fan_out=0,
            health="healthy",
        )
        assert m.health_emoji == "✅"


class TestCalculateProjectMetrics:
    """Tests for aggregate project metrics."""

    def test_project_totals(self, simple_graph):
        mod_metrics = calculate_module_metrics(simple_graph)
        pm = calculate_project_metrics(simple_graph, mod_metrics)

        assert pm.total_modules == 3
        assert pm.total_edges == 3
        assert pm.total_loc == 100  # 50 + 30 + 20

    def test_density(self, simple_graph):
        mod_metrics = calculate_module_metrics(simple_graph)
        pm = calculate_project_metrics(simple_graph, mod_metrics)

        # 3 edges / (3 * 2) = 0.5
        assert pm.density == 0.5

    def test_has_cycles_flag(self, simple_graph):
        mod_metrics = calculate_module_metrics(simple_graph)
        pm = calculate_project_metrics(simple_graph, mod_metrics, has_cycles=True)
        assert pm.has_cycles is True

        pm2 = calculate_project_metrics(simple_graph, mod_metrics, has_cycles=False)
        assert pm2.has_cycles is False

    def test_health_breakdown(self, simple_graph):
        mod_metrics = calculate_module_metrics(simple_graph)
        pm = calculate_project_metrics(simple_graph, mod_metrics)

        total = (pm.modules_healthy + pm.modules_moderate + pm.modules_elevated
                 + pm.modules_high + pm.modules_critical + pm.modules_unknown)
        assert total == 3


class TestFormatMetricsTable:
    """Tests for ASCII table formatting."""

    def test_produces_output(self, simple_graph):
        metrics = calculate_module_metrics(simple_graph)
        table = format_metrics_table(metrics)
        assert len(table) > 0
        assert "Module" in table

    def test_respects_limit(self, simple_graph):
        metrics = calculate_module_metrics(simple_graph)
        table = format_metrics_table(metrics, limit=1)
        # Should contain separator lines + header + 1 data row
        data_lines = [l for l in table.split("\n") if l and "─" not in l and "Module" not in l]
        assert len(data_lines) == 1

    def test_sort_by_ca(self, simple_graph):
        metrics = calculate_module_metrics(simple_graph)
        table = format_metrics_table(metrics, sort_by="ca")
        lines = [l for l in table.split("\n") if l and "─" not in l and "Module" not in l]
        # C has highest Ca (2), should be first
        assert "C" in lines[0]
