"""Tests for the dependency graph (core/graph.py)."""

from hawkeye.core.graph import DependencyGraph, NodeInfo, EdgeInfo


class TestGraphQuery:
    """Tests for graph query methods."""

    def test_get_dependencies(self, simple_graph):
        assert simple_graph.get_dependencies("A") == {"B", "C"}
        assert simple_graph.get_dependencies("B") == {"C"}
        assert simple_graph.get_dependencies("C") == set()

    def test_get_dependents(self, simple_graph):
        assert simple_graph.get_dependents("C") == {"A", "B"}
        assert simple_graph.get_dependents("B") == {"A"}
        assert simple_graph.get_dependents("A") == set()

    def test_transitive_dependencies(self, simple_graph):
        trans = simple_graph.get_transitive_dependencies("A")
        assert trans == {"B", "C"}

    def test_transitive_dependents(self, simple_graph):
        trans = simple_graph.get_transitive_dependents("C")
        assert trans == {"A", "B"}

    def test_transitive_of_leaf(self, simple_graph):
        assert simple_graph.get_transitive_dependencies("C") == set()

    def test_transitive_of_root(self, simple_graph):
        assert simple_graph.get_transitive_dependents("A") == set()


class TestFindPath:
    """Tests for shortest path finding."""

    def test_direct_path(self, simple_graph):
        path = simple_graph.find_path("A", "B")
        assert path == ["A", "B"]

    def test_transitive_path(self, simple_graph):
        path = simple_graph.find_path("A", "C")
        # A → C is direct, so shortest path is length 2
        assert path == ["A", "C"]

    def test_no_path(self, simple_graph):
        path = simple_graph.find_path("C", "A")
        assert path is None

    def test_self_path(self, simple_graph):
        path = simple_graph.find_path("A", "A")
        assert path == ["A"]

    def test_nonexistent_node(self, simple_graph):
        assert simple_graph.find_path("A", "MISSING") is None
        assert simple_graph.find_path("MISSING", "A") is None


class TestNeighborhood:
    """Tests for neighborhood extraction."""

    def test_one_hop(self, simple_graph):
        n = simple_graph.neighborhood("B", max_hops=1)
        assert n == {"A", "B", "C"}  # B's deps + dependents + self

    def test_zero_hops(self, simple_graph):
        n = simple_graph.neighborhood("B", max_hops=0)
        assert n == {"B"}

    def test_full_reach(self, simple_graph):
        n = simple_graph.neighborhood("A", max_hops=2)
        assert n == {"A", "B", "C"}


class TestGraphBuild:
    """Tests for building a graph from scan + analysis results."""

    def test_build_from_data(self, tmp_project):
        from hawkeye.core.scanner import scan_project
        from hawkeye.core.analyzer import analyze_project

        index = scan_project(str(tmp_project))
        project_name = tmp_project.name
        imports, _ = analyze_project(index, project_name)

        graph = DependencyGraph.build(index, imports, project_name)

        assert len(graph.nodes) == len(index)
        assert len(graph.edges) > 0
        assert graph.project_name == project_name

    def test_edges_match_imports(self, tmp_project):
        from hawkeye.core.scanner import scan_project
        from hawkeye.core.analyzer import analyze_project

        index = scan_project(str(tmp_project))
        project_name = tmp_project.name
        imports, _ = analyze_project(index, project_name)

        graph = DependencyGraph.build(index, imports, project_name)

        # Every edge target should be a known node
        for (src, tgt) in graph.edges:
            assert src in graph.nodes
            assert tgt in graph.nodes


class TestGraphFiltered:
    """Tests for graph filtering and depth collapsing."""

    def test_max_depth_collapses(self):
        """Modules deeper than max_depth should be collapsed."""
        g = DependencyGraph()
        g.project_name = "proj"

        for name in ["proj.a", "proj.a.b", "proj.a.b.c"]:
            g.nodes[name] = NodeInfo(
                module_name=name, package=".".join(name.split(".")[:-1]),
                rel_path=f"{name}.py", is_package=False,
                loc=10, depth=name.count("."),
            )
            g.adjacency[name] = set()
            g.reverse_adj[name] = set()

        # proj.a.b.c → proj.a
        g.adjacency["proj.a.b.c"].add("proj.a")
        g.reverse_adj["proj.a"].add("proj.a.b.c")
        g.edges[("proj.a.b.c", "proj.a")] = EdgeInfo(
            source="proj.a.b.c", target="proj.a", import_count=1, lines=[1],
        )

        filtered = g.filtered(max_depth=2)

        # proj.a.b.c should be collapsed to proj.a.b
        assert "proj.a.b.c" not in filtered.nodes
        assert "proj.a.b" in filtered.nodes or "proj.a" in filtered.nodes

    def test_exclude_filter(self, simple_graph):
        filtered = simple_graph.filtered(exclude=["C"])
        assert "C" not in filtered.nodes
        assert "A" in filtered.nodes


class TestTopologicalSort:
    """Tests for topological ordering."""

    def test_acyclic_order(self, simple_graph):
        order = simple_graph.topological_sort()
        # A must come before B, B must come before C
        assert order.index("A") < order.index("B")
        assert order.index("B") < order.index("C")

    def test_cyclic_partial_order(self, cyclic_graph):
        order = cyclic_graph.topological_sort()
        # Should return partial order (some nodes excluded due to cycles)
        assert len(order) <= len(cyclic_graph.nodes)


class TestGraphSerialization:
    """Tests for graph JSON serialization."""

    def test_to_dict_structure(self, simple_graph):
        d = simple_graph.to_dict()
        assert d["project_name"] == "test"
        assert d["node_count"] == 3
        assert d["edge_count"] == 3
        assert len(d["nodes"]) == 3
        assert len(d["edges"]) == 3

    def test_to_dict_node_fields(self, simple_graph):
        d = simple_graph.to_dict()
        node = d["nodes"][0]
        assert "id" in node
        assert "package" in node
        assert "loc" in node
        assert "dependencies" in node
        assert "dependents" in node
