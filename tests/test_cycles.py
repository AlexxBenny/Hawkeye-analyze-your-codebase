"""Tests for cycle detection (core/cycles.py)."""

from hawkeye.core.cycles import (
    Cycle,
    CycleReport,
    detect_cycles,
    _find_sccs,
)
from hawkeye.core.graph import DependencyGraph, NodeInfo, EdgeInfo


class TestFindSCCs:
    """Tests for Tarjan's SCC algorithm."""

    def test_no_cycles(self, simple_graph):
        sccs = _find_sccs(simple_graph)
        assert len(sccs) == 0

    def test_finds_cycle(self, cyclic_graph):
        sccs = _find_sccs(cyclic_graph)
        assert len(sccs) == 1
        assert set(sccs[0]) == {"X", "Y", "Z"}

    def test_multiple_sccs(self):
        """Two separate cycles: A↔B and C↔D."""
        g = DependencyGraph()
        g.project_name = "test"

        for name in ["A", "B", "C", "D", "E"]:
            g.nodes[name] = NodeInfo(
                module_name=name, package="test",
                rel_path=f"{name.lower()}.py", is_package=False,
                loc=10, depth=0,
            )
            g.adjacency[name] = set()
            g.reverse_adj[name] = set()

        # Cycle 1: A ↔ B
        for src, tgt in [("A", "B"), ("B", "A")]:
            g.adjacency[src].add(tgt)
            g.reverse_adj[tgt].add(src)
            g.edges[(src, tgt)] = EdgeInfo(source=src, target=tgt, import_count=1, lines=[1])

        # Cycle 2: C ↔ D
        for src, tgt in [("C", "D"), ("D", "C")]:
            g.adjacency[src].add(tgt)
            g.reverse_adj[tgt].add(src)
            g.edges[(src, tgt)] = EdgeInfo(source=src, target=tgt, import_count=1, lines=[1])

        sccs = _find_sccs(g)
        assert len(sccs) == 2

    def test_single_node_no_cycle(self):
        """A self-loop-free single node is not an SCC."""
        g = DependencyGraph()
        g.project_name = "test"
        g.nodes["A"] = NodeInfo(
            module_name="A", package="test",
            rel_path="a.py", is_package=False, loc=10, depth=0,
        )
        g.adjacency["A"] = set()
        g.reverse_adj["A"] = set()

        sccs = _find_sccs(g)
        assert len(sccs) == 0


class TestDetectCycles:
    """Tests for the full cycle detection pipeline."""

    def test_no_cycles_report(self, simple_graph):
        report = detect_cycles(simple_graph)
        assert report.has_cycles is False
        assert report.cycle_count == 0
        assert report.cycles == []

    def test_detects_cycles(self, cyclic_graph):
        report = detect_cycles(cyclic_graph)
        assert report.has_cycles is True
        assert report.cycle_count >= 1

    def test_cycle_path_is_closed(self, cyclic_graph):
        report = detect_cycles(cyclic_graph)
        for cycle in report.cycles:
            assert cycle.path[0] == cycle.path[-1]
            assert cycle.length >= 2

    def test_severity_assigned(self, cyclic_graph):
        report = detect_cycles(cyclic_graph)
        for cycle in report.cycles:
            assert cycle.severity in ("low", "medium", "high", "critical")

    def test_break_suggestion_assigned(self, cyclic_graph):
        report = detect_cycles(cyclic_graph)
        for cycle in report.cycles:
            assert cycle.break_suggestion  # Should not be empty

    def test_participation_tracked(self, cyclic_graph):
        report = detect_cycles(cyclic_graph)
        assert len(report.participation) > 0
        for module, count in report.participation.items():
            assert module in cyclic_graph.nodes
            assert count >= 1

    def test_marks_cycle_edges(self, cyclic_graph):
        detect_cycles(cyclic_graph)
        cycle_edges = [e for e in cyclic_graph.edges.values() if e.is_cycle_member]
        assert len(cycle_edges) >= 2

    def test_cycles_sorted_by_severity(self, cyclic_graph):
        report = detect_cycles(cyclic_graph)
        if len(report.cycles) > 1:
            severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
            severities = [severity_order[c.severity] for c in report.cycles]
            assert severities == sorted(severities)


class TestCycleDataclass:
    """Tests for the Cycle dataclass."""

    def test_length_auto_computed(self):
        c = Cycle(path=["A", "B", "C", "A"])
        assert c.length == 3

    def test_str_representation(self):
        c = Cycle(path=["A", "B", "A"])
        assert str(c) == "A → B → A"


class TestDetectCyclesOnRealProject:
    """Integration: detect cycles on the cyclic fixture project."""

    def test_cyclic_project(self, cyclic_project):
        from hawkeye.core.scanner import scan_project
        from hawkeye.core.analyzer import analyze_project
        from hawkeye.core.graph import DependencyGraph

        index = scan_project(str(cyclic_project))
        project_name = cyclic_project.name
        imports, _ = analyze_project(index, project_name)
        graph = DependencyGraph.build(index, imports, project_name)
        report = detect_cycles(graph)

        assert report.has_cycles is True
