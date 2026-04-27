"""Tests for architecture rule enforcement (core/rules.py)."""

import pytest

from hawkeye.core.rules import (
    Violation,
    check_layer_rules,
    check_forbidden_rules,
    check_independence_rules,
    check_all_rules,
    _module_matches,
    _find_layer,
)
from hawkeye.core.graph import DependencyGraph, NodeInfo, EdgeInfo
from hawkeye.config import RulesConfig, LayerConfig


# ── Helpers ───────────────────────────────────────────────────


def _build_layered_graph(edges: list[tuple[str, str]]) -> DependencyGraph:
    """Build a graph with the given edges for rule testing."""
    g = DependencyGraph()
    g.project_name = "test"

    all_nodes = set()
    for src, tgt in edges:
        all_nodes.add(src)
        all_nodes.add(tgt)

    for name in all_nodes:
        g.nodes[name] = NodeInfo(
            module_name=name, package="test",
            rel_path=f"{name.lower()}.py", is_package=False,
            loc=10, depth=name.count("."),
        )
        g.adjacency.setdefault(name, set())
        g.reverse_adj.setdefault(name, set())

    for src, tgt in edges:
        g.adjacency[src].add(tgt)
        g.reverse_adj[tgt].add(src)
        g.edges[(src, tgt)] = EdgeInfo(
            source=src, target=tgt, import_count=1, lines=[1],
        )

    return g


# ── Pattern matching ──────────────────────────────────────────


class TestModuleMatches:
    """Tests for module name pattern matching."""

    def test_exact_match(self):
        assert _module_matches("core.engine", "core.engine")

    def test_prefix_match(self):
        assert _module_matches("core.engine.sub", "core.engine")

    def test_glob_match(self):
        assert _module_matches("core.engine", "core.*")

    def test_no_match(self):
        assert not _module_matches("api.views", "core.*")

    def test_wildcard_all(self):
        assert _module_matches("anything.here", "*")


class TestFindLayer:
    """Tests for layer index lookup."""

    def test_finds_matching_layer(self):
        layers = ["domain", "application", "infrastructure"]
        assert _find_layer("domain.models", layers) == 0
        assert _find_layer("infrastructure.db", layers) == 2

    def test_returns_negative_for_unknown(self):
        layers = ["domain", "application"]
        assert _find_layer("unknown.module", layers) == -1


# ── Layer rules ───────────────────────────────────────────────


class TestLayerRules:
    """Tests for layered architecture enforcement."""

    def test_valid_downward_dependency(self):
        # application → domain is allowed (higher can import lower)
        graph = _build_layered_graph([("application.service", "domain.models")])
        layers = ["domain", "application"]
        violations = check_layer_rules(graph, layers, direction="downward")
        assert len(violations) == 0

    def test_upward_violation(self):
        # domain → application is NOT allowed (lower cannot import higher)
        graph = _build_layered_graph([("domain.models", "application.service")])
        layers = ["domain", "application"]
        violations = check_layer_rules(graph, layers, direction="downward")
        assert len(violations) == 1
        assert violations[0].rule_type == "layer"

    def test_allowed_exception(self):
        # domain → application normally violates, but allow exception
        graph = _build_layered_graph([("domain.models", "application.service")])
        layers = ["domain", "application"]
        allow = [{"from": "domain.models", "to": "application.service"}]
        violations = check_layer_rules(graph, layers, direction="downward", allow=allow)
        assert len(violations) == 0

    def test_unknown_layer_ignored(self):
        # Modules not in any layer are skipped
        graph = _build_layered_graph([("utils.helper", "random.thing")])
        layers = ["domain", "application"]
        violations = check_layer_rules(graph, layers, direction="downward")
        assert len(violations) == 0


# ── Forbidden rules ───────────────────────────────────────────


class TestForbiddenRules:
    """Tests for forbidden import enforcement."""

    def test_catches_forbidden_import(self):
        graph = _build_layered_graph([("api.views", "infrastructure.db")])
        forbidden = [{"from": "api.*", "to": ["infrastructure.*"]}]
        violations = check_forbidden_rules(graph, forbidden)
        assert len(violations) == 1
        assert violations[0].rule_type == "forbidden"

    def test_allows_non_forbidden(self):
        graph = _build_layered_graph([("api.views", "core.engine")])
        forbidden = [{"from": "api.*", "to": ["infrastructure.*"]}]
        violations = check_forbidden_rules(graph, forbidden)
        assert len(violations) == 0

    def test_multiple_forbidden_targets(self):
        graph = _build_layered_graph([
            ("api.views", "infrastructure.db"),
            ("api.views", "cli.main"),
        ])
        forbidden = [{"from": "api.*", "to": ["infrastructure.*", "cli.*"]}]
        violations = check_forbidden_rules(graph, forbidden)
        assert len(violations) == 2


# ── Independence rules ────────────────────────────────────────


class TestIndependenceRules:
    """Tests for mutual independence enforcement."""

    def test_catches_cross_dependency(self):
        graph = _build_layered_graph([("auth.login", "billing.charge")])
        groups = [["auth.*", "billing.*"]]
        violations = check_independence_rules(graph, groups)
        assert len(violations) == 1
        assert violations[0].rule_type == "independence"

    def test_catches_reverse_direction(self):
        graph = _build_layered_graph([("billing.charge", "auth.login")])
        groups = [["auth.*", "billing.*"]]
        violations = check_independence_rules(graph, groups)
        assert len(violations) == 1

    def test_allows_independent_modules(self):
        graph = _build_layered_graph([("auth.login", "core.utils")])
        groups = [["auth.*", "billing.*"]]
        violations = check_independence_rules(graph, groups)
        assert len(violations) == 0


# ── Combined rules ────────────────────────────────────────────


class TestCheckAllRules:
    """Tests for the combined rule checker."""

    def test_empty_config_no_violations(self, simple_graph):
        config = RulesConfig()
        violations = check_all_rules(simple_graph, config)
        assert violations == []

    def test_combined_violations(self):
        graph = _build_layered_graph([
            ("domain.models", "application.service"),  # layer violation
            ("api.views", "cli.main"),                  # forbidden
        ])
        config = RulesConfig(
            layers=LayerConfig(order=["domain", "application"], direction="downward"),
            forbidden=[{"from": "api.*", "to": ["cli.*"]}],
        )
        violations = check_all_rules(graph, config)
        assert len(violations) == 2


class TestViolationDataclass:
    """Tests for the Violation dataclass."""

    def test_str_error(self):
        v = Violation(
            rule_type="layer", source="a", target="b",
            message="bad import", severity="error",
        )
        s = str(v)
        assert "❌" in s
        assert "layer" in s

    def test_str_warning(self):
        v = Violation(
            rule_type="forbidden", source="a", target="b",
            message="bad import", severity="warning",
        )
        s = str(v)
        assert "⚠️" in s
