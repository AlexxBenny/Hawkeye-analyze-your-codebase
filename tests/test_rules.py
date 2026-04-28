"""Tests for architecture rule enforcement (core/rules.py)."""

import pytest

from hawkeye.config import (AcyclicSiblingsConfig, LayerConfig,
                            ProtectedConfig, RulesConfig)
from hawkeye.core.graph import DependencyGraph, EdgeInfo, NodeInfo
from hawkeye.core.rules import (Violation, _find_layer, _module_matches,
                                check_acyclic_siblings_rules, check_all_rules,
                                check_forbidden_rules,
                                check_independence_rules, check_layer_rules,
                                check_protected_rules)

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


# ── Independence rules (transitive) ──────────────────────────


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

    def test_catches_transitive_dependency(self):
        """The critical fix: A → B → C where A and C must be independent."""
        graph = _build_layered_graph([
            ("auth.login", "core.shared"),
            ("core.shared", "billing.charge"),
        ])
        groups = [["auth.*", "billing.*"]]
        violations = check_independence_rules(graph, groups)
        assert len(violations) == 1
        assert violations[0].source == "auth.login"
        assert violations[0].target == "billing.charge"

    def test_transitive_path_included(self):
        """Violation should include the full transitive path."""
        graph = _build_layered_graph([
            ("auth.login", "core.shared"),
            ("core.shared", "billing.charge"),
        ])
        groups = [["auth.*", "billing.*"]]
        violations = check_independence_rules(graph, groups)
        assert violations[0].path is not None
        assert violations[0].path == ["auth.login", "core.shared", "billing.charge"]

    def test_no_duplicate_violations(self):
        """Same pair should only be reported once."""
        graph = _build_layered_graph([
            ("auth.login", "billing.charge"),
        ])
        groups = [["auth.*", "billing.*"]]
        violations = check_independence_rules(graph, groups)
        # Only one direction reported (auth → billing)
        assert len(violations) == 1


# ── Protected rules ──────────────────────────────────────────


class TestProtectedRules:
    """Tests for protected module enforcement."""

    def test_blocks_unauthorized_importer(self):
        graph = _build_layered_graph([("api.views", "core.secrets")])
        rules = [ProtectedConfig(
            modules=["core.secrets"],
            allowed_importers=["auth.*"],
        )]
        violations = check_protected_rules(graph, rules)
        assert len(violations) == 1
        assert violations[0].rule_type == "protected"
        assert violations[0].source == "api.views"
        assert violations[0].target == "core.secrets"

    def test_allows_authorized_importer(self):
        graph = _build_layered_graph([("auth.service", "core.secrets")])
        rules = [ProtectedConfig(
            modules=["core.secrets"],
            allowed_importers=["auth.*"],
        )]
        violations = check_protected_rules(graph, rules)
        assert len(violations) == 0

    def test_multiple_protected_modules(self):
        graph = _build_layered_graph([
            ("api.views", "core.secrets"),
            ("api.views", "core.tokens"),
        ])
        rules = [ProtectedConfig(
            modules=["core.secrets", "core.tokens"],
            allowed_importers=["auth.*"],
        )]
        violations = check_protected_rules(graph, rules)
        assert len(violations) == 2

    def test_multiple_allowed_importers(self):
        graph = _build_layered_graph([
            ("auth.service", "core.secrets"),
            ("admin.panel", "core.secrets"),
        ])
        rules = [ProtectedConfig(
            modules=["core.secrets"],
            allowed_importers=["auth.*", "admin.*"],
        )]
        violations = check_protected_rules(graph, rules)
        assert len(violations) == 0


# ── Acyclic siblings rules ───────────────────────────────────


class TestAcyclicSiblingsRules:
    """Tests for acyclic sibling package enforcement."""

    def test_catches_sibling_cycle(self):
        graph = _build_layered_graph([
            ("services.auth.login", "services.billing.charge"),
            ("services.billing.charge", "services.auth.verify"),
        ])
        rules = [AcyclicSiblingsConfig(ancestor="services")]
        violations = check_acyclic_siblings_rules(graph, rules)
        assert len(violations) > 0
        assert all(v.rule_type == "acyclic_siblings" for v in violations)

    def test_allows_intra_sibling_cycle(self):
        """Cycles within a single sibling package are allowed."""
        graph = _build_layered_graph([
            ("services.auth.login", "services.auth.verify"),
            ("services.auth.verify", "services.auth.login"),
        ])
        rules = [AcyclicSiblingsConfig(ancestor="services")]
        violations = check_acyclic_siblings_rules(graph, rules)
        assert len(violations) == 0

    def test_allows_acyclic_siblings(self):
        """One-directional dependency between siblings is fine."""
        graph = _build_layered_graph([
            ("services.auth.login", "services.billing.charge"),
        ])
        rules = [AcyclicSiblingsConfig(ancestor="services")]
        violations = check_acyclic_siblings_rules(graph, rules)
        assert len(violations) == 0

    def test_ignores_modules_outside_ancestor(self):
        graph = _build_layered_graph([
            ("utils.helper", "services.auth.login"),
        ])
        rules = [AcyclicSiblingsConfig(ancestor="services")]
        violations = check_acyclic_siblings_rules(graph, rules)
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

    def test_all_rule_types_together(self):
        graph = _build_layered_graph([
            ("domain.models", "application.service"),      # layer violation
            ("api.views", "cli.main"),                      # forbidden
            ("api.views", "core.secrets"),                  # protected violation
            ("auth.login", "billing.charge"),               # independence violation
        ])
        config = RulesConfig(
            layers=LayerConfig(order=["domain", "application"], direction="downward"),
            forbidden=[{"from": "api.*", "to": ["cli.*"]}],
            protected=[ProtectedConfig(
                modules=["core.secrets"],
                allowed_importers=["auth.*"],
            )],
            independence=[["auth.*", "billing.*"]],
        )
        violations = check_all_rules(graph, config)
        types = {v.rule_type for v in violations}
        assert "layer" in types
        assert "forbidden" in types
        assert "protected" in types
        assert "independence" in types


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

    def test_path_field(self):
        v = Violation(
            rule_type="independence", source="a", target="c",
            message="test", path=["a", "b", "c"],
        )
        assert v.path == ["a", "b", "c"]

