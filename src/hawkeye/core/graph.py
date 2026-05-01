"""Dependency graph construction and traversal algorithms.

Builds a directed graph from analysis results and provides algorithms for
subgraph extraction, filtering, topological sort, transitive closure,
path finding, and impact analysis.
"""

from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from .analyzer import ResolvedImport
from .models import ModuleInfo


@dataclass
class EdgeInfo:
    """Metadata about a dependency edge."""
    source: str
    target: str
    import_count: int = 1
    lines: list[int] = field(default_factory=list)
    is_cycle_member: bool = False
    is_type_only: bool = False   # ALL imports on this edge are TYPE_CHECKING
    is_deferred: bool = False    # ALL imports on this edge are lazy (in function body)


@dataclass
class NodeInfo:
    """Metadata about a module node in the graph."""
    module_name: str
    package: str
    rel_path: str
    is_package: bool
    loc: int
    depth: int  # Nesting depth (number of dots in module name)
    language: str = "python"


class DependencyGraph:
    """Directed dependency graph with traversal and analysis algorithms."""

    def __init__(self) -> None:
        self.nodes: dict[str, NodeInfo] = {}
        self.edges: dict[tuple[str, str], EdgeInfo] = {}
        self.adjacency: dict[str, set[str]] = {}       # forward: module -> deps
        self.reverse_adj: dict[str, set[str]] = {}      # reverse: module -> dependents
        self.project_name: str = ""

    @classmethod
    def build(
        cls,
        file_index: dict[str, ModuleInfo],
        analysis: dict[str, list[ResolvedImport]],
        project_name: str,
    ) -> "DependencyGraph":
        """Build a dependency graph from scan and analysis results."""
        graph = cls()
        graph.project_name = project_name

        # Add all modules as nodes
        for name, info in file_index.items():
            depth = name.count(".")
            graph.nodes[name] = NodeInfo(
                module_name=name,
                package=info.package,
                rel_path=info.rel_path,
                is_package=info.is_package,
                loc=info.loc,
                depth=depth,
                language=info.language,
            )
            graph.adjacency.setdefault(name, set())
            graph.reverse_adj.setdefault(name, set())

        # Add edges from analysis
        for source, imports in analysis.items():
            for imp in imports:
                target = imp.resolved_module
                if target not in graph.nodes:
                    continue

                graph.adjacency[source].add(target)
                graph.reverse_adj[target].add(source)

                edge_key = (source, target)
                lines = [d.line for d in imp.details]
                all_type_checking = all(d.is_type_checking for d in imp.details)
                all_deferred = all(d.is_deferred for d in imp.details)

                if edge_key in graph.edges:
                    edge = graph.edges[edge_key]
                    edge.import_count += len(imp.details)
                    edge.lines.extend(lines)
                    # Edge is type_only only if ALL details so far are type-checking
                    edge.is_type_only = edge.is_type_only and all_type_checking
                    edge.is_deferred = edge.is_deferred and all_deferred
                else:
                    graph.edges[edge_key] = EdgeInfo(
                        source=source,
                        target=target,
                        import_count=len(imp.details),
                        lines=lines,
                        is_type_only=all_type_checking,
                        is_deferred=all_deferred,
                    )

        return graph

    # ── Query methods ──────────────────────────────────────────────

    def get_dependencies(self, module: str) -> set[str]:
        """Direct dependencies of a module (what it imports)."""
        return self.adjacency.get(module, set()).copy()

    def get_dependents(self, module: str) -> set[str]:
        """Direct dependents of a module (what imports it)."""
        return self.reverse_adj.get(module, set()).copy()

    def get_transitive_dependencies(self, module: str) -> set[str]:
        """All modules reachable from the given module (transitive closure)."""
        visited: set[str] = set()
        queue = deque(self.adjacency.get(module, set()))
        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            queue.extend(self.adjacency.get(current, set()) - visited)
        return visited

    def get_transitive_dependents(self, module: str) -> set[str]:
        """All modules that transitively depend on the given module."""
        visited: set[str] = set()
        queue = deque(self.reverse_adj.get(module, set()))
        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            queue.extend(self.reverse_adj.get(current, set()) - visited)
        return visited

    def find_path(self, source: str, target: str) -> Optional[list[str]]:
        """Find shortest dependency path from source to target (BFS)."""
        if source not in self.nodes or target not in self.nodes:
            return None
        if source == target:
            return [source]

        visited: set[str] = {source}
        queue: deque[list[str]] = deque([[source]])

        while queue:
            path = queue.popleft()
            current = path[-1]
            for neighbor in self.adjacency.get(current, set()):
                if neighbor == target:
                    return path + [neighbor]
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(path + [neighbor])
        return None

    def neighborhood(self, module: str, max_hops: int = 1) -> set[str]:
        """Get all nodes within max_hops of the given module (both directions)."""
        result: set[str] = {module}
        frontier = {module}
        for _ in range(max_hops):
            next_frontier: set[str] = set()
            for node in frontier:
                next_frontier |= self.adjacency.get(node, set())
                next_frontier |= self.reverse_adj.get(node, set())
            next_frontier -= result
            result |= next_frontier
            frontier = next_frontier
        return result

    # ── Centrality ─────────────────────────────────────────────────

    def betweenness_centrality(self) -> dict[str, float]:
        """Compute betweenness centrality for all nodes (Brandes' algorithm).

        Measures the fraction of shortest paths that pass through each node.
        High betweenness = structurally central (bridge between subgraphs).
        Returns normalized scores in [0, 1].
        """
        nodes = list(self.nodes)
        centrality: dict[str, float] = {n: 0.0 for n in nodes}

        for source in nodes:
            # BFS from source
            stack: list[str] = []
            predecessors: dict[str, list[str]] = {n: [] for n in nodes}
            sigma: dict[str, int] = {n: 0 for n in nodes}
            dist: dict[str, int] = {n: -1 for n in nodes}
            sigma[source] = 1
            dist[source] = 0
            queue = deque([source])

            while queue:
                v = queue.popleft()
                stack.append(v)
                for w in self.adjacency.get(v, set()):
                    if dist[w] < 0:
                        queue.append(w)
                        dist[w] = dist[v] + 1
                    if dist[w] == dist[v] + 1:
                        sigma[w] += sigma[v]
                        predecessors[w].append(v)

            # Back-propagation of dependencies
            delta: dict[str, float] = {n: 0.0 for n in nodes}
            while stack:
                w = stack.pop()
                for v in predecessors[w]:
                    if sigma[w] > 0:
                        delta[v] += (sigma[v] / sigma[w]) * (1 + delta[w])
                if w != source:
                    centrality[w] += delta[w]

        # Normalize
        n = len(nodes)
        if n > 2:
            scale = 1.0 / ((n - 1) * (n - 2))
            for v in centrality:
                centrality[v] *= scale

        return centrality

    # ── Filtering ──────────────────────────────────────────────────

    def filtered(
        self,
        include: Optional[list[str]] = None,
        exclude: Optional[list[str]] = None,
        max_depth: Optional[int] = None,
    ) -> "DependencyGraph":
        """Create a filtered copy of this graph.

        Args:
            include: If set, only include modules matching these prefixes.
            exclude: Exclude modules matching these prefixes.
            max_depth: Collapse modules deeper than this level.
        """
        import fnmatch

        def should_include(name: str) -> bool:
            if exclude:
                for pat in exclude:
                    if fnmatch.fnmatch(name, pat):
                        return False
            if include:
                return any(fnmatch.fnmatch(name, pat) for pat in include)
            return True

        def collapse_name(name: str) -> str:
            if max_depth is not None:
                parts = name.split(".")
                if len(parts) > max_depth + 1:  # +1 for project name
                    return ".".join(parts[:max_depth + 1])
            return name

        new_graph = DependencyGraph()
        new_graph.project_name = self.project_name

        # Build collapsed node set
        kept_nodes: set[str] = set()
        name_map: dict[str, str] = {}

        for name, node in self.nodes.items():
            if not should_include(name):
                continue
            collapsed = collapse_name(name)
            name_map[name] = collapsed
            kept_nodes.add(collapsed)
            if collapsed not in new_graph.nodes:
                new_graph.nodes[collapsed] = NodeInfo(
                    module_name=collapsed,
                    package=".".join(collapsed.split(".")[:-1]),
                    rel_path=node.rel_path,
                    is_package=node.is_package,
                    loc=node.loc,
                    depth=collapsed.count("."),
                    language=node.language,
                )
                new_graph.adjacency[collapsed] = set()
                new_graph.reverse_adj[collapsed] = set()

        # Rebuild edges with collapsed names
        for (src, tgt), edge in self.edges.items():
            mapped_src = name_map.get(src)
            mapped_tgt = name_map.get(tgt)
            if mapped_src and mapped_tgt and mapped_src != mapped_tgt:
                new_graph.adjacency[mapped_src].add(mapped_tgt)
                new_graph.reverse_adj[mapped_tgt].add(mapped_src)
                edge_key = (mapped_src, mapped_tgt)
                if edge_key not in new_graph.edges:
                    new_graph.edges[edge_key] = EdgeInfo(
                        source=mapped_src,
                        target=mapped_tgt,
                        import_count=edge.import_count,
                        lines=list(edge.lines),
                    )
                else:
                    new_graph.edges[edge_key].import_count += edge.import_count

        return new_graph

    # ── Topological sort ───────────────────────────────────────────

    def topological_sort(self) -> list[str]:
        """Return nodes in topological order (Kahn's algorithm).

        Returns partial order if cycles exist.
        """
        in_degree: dict[str, int] = {n: 0 for n in self.nodes}
        for deps in self.adjacency.values():
            for dep in deps:
                if dep in in_degree:
                    in_degree[dep] += 1

        queue = deque(n for n, d in in_degree.items() if d == 0)
        result: list[str] = []

        while queue:
            node = queue.popleft()
            result.append(node)
            for dep in self.adjacency.get(node, set()):
                if dep in in_degree:
                    in_degree[dep] -= 1
                    if in_degree[dep] == 0:
                        queue.append(dep)

        return result

    # ── Serialization ──────────────────────────────────────────────

    def to_dict(self) -> dict:
        """Serialize the graph to a JSON-compatible dictionary."""
        nodes = []
        for name, node in sorted(self.nodes.items()):
            nodes.append({
                "id": name,
                "language": node.language,
                "package": node.package,
                "rel_path": node.rel_path,
                "is_package": node.is_package,
                "loc": node.loc,
                "depth": node.depth,
                "dependencies": sorted(self.adjacency.get(name, set())),
                "dependents": sorted(self.reverse_adj.get(name, set())),
            })

        edges = []
        for (src, tgt), edge in sorted(self.edges.items()):
            edges.append({
                "source": src,
                "target": tgt,
                "import_count": edge.import_count,
                "lines": edge.lines,
                "is_cycle_member": edge.is_cycle_member,
            })

        return {
            "project_name": self.project_name,
            "node_count": len(self.nodes),
            "edge_count": len(self.edges),
            "nodes": nodes,
            "edges": edges,
        }
