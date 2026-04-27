"""Cycle detection using Tarjan's strongly connected components.

Finds all import cycles in the dependency graph and reports detailed
cycle paths with participation counts per module.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .graph import DependencyGraph


@dataclass
class Cycle:
    """A single import cycle."""
    path: list[str]    # Module names forming the cycle (first == last)
    length: int = 0

    def __post_init__(self) -> None:
        self.length = len(self.path) - 1  # Don't count the repeated node

    def __str__(self) -> str:
        return " → ".join(self.path)


@dataclass
class CycleReport:
    """Complete cycle analysis results."""
    cycles: list[Cycle] = field(default_factory=list)
    participation: dict[str, int] = field(default_factory=dict)
    has_cycles: bool = False

    @property
    def cycle_count(self) -> int:
        return len(self.cycles)


def _find_sccs(graph: "DependencyGraph") -> list[list[str]]:
    """Find all strongly connected components using Tarjan's algorithm."""
    index_counter = [0]
    stack: list[str] = []
    on_stack: set[str] = set()
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    sccs: list[list[str]] = []

    def strongconnect(node: str) -> None:
        indices[node] = index_counter[0]
        lowlinks[node] = index_counter[0]
        index_counter[0] += 1
        stack.append(node)
        on_stack.add(node)

        for neighbor in graph.adjacency.get(node, set()):
            if neighbor not in graph.nodes:
                continue
            if neighbor not in indices:
                strongconnect(neighbor)
                lowlinks[node] = min(lowlinks[node], lowlinks[neighbor])
            elif neighbor in on_stack:
                lowlinks[node] = min(lowlinks[node], indices[neighbor])

        if lowlinks[node] == indices[node]:
            scc: list[str] = []
            while True:
                w = stack.pop()
                on_stack.remove(w)
                scc.append(w)
                if w == node:
                    break
            if len(scc) > 1:
                sccs.append(scc)

    # Increase recursion limit for large projects
    import sys
    old_limit = sys.getrecursionlimit()
    sys.setrecursionlimit(max(old_limit, len(graph.nodes) * 2 + 1000))

    try:
        for node in graph.nodes:
            if node not in indices:
                strongconnect(node)
    finally:
        sys.setrecursionlimit(old_limit)

    return sccs


def _extract_cycles_from_scc(
    scc: list[str],
    graph: "DependencyGraph",
) -> list[Cycle]:
    """Extract individual cycles from a strongly connected component using DFS."""
    scc_set = set(scc)
    cycles: list[Cycle] = []
    seen_cycles: set[tuple[str, ...]] = set()

    def dfs(start: str, current: str, path: list[str], visited: set[str]) -> None:
        if len(cycles) > 50:  # Cap to avoid explosion in large SCCs
            return
        for neighbor in graph.adjacency.get(current, set()):
            if neighbor not in scc_set:
                continue
            if neighbor == start and len(path) > 1:
                # Normalize cycle for deduplication
                min_idx = path.index(min(path))
                normalized = tuple(path[min_idx:] + path[:min_idx])
                if normalized not in seen_cycles:
                    seen_cycles.add(normalized)
                    cycles.append(Cycle(path=path + [start]))
            elif neighbor not in visited and len(path) < 10:  # Max cycle length
                visited.add(neighbor)
                dfs(start, neighbor, path + [neighbor], visited)
                visited.discard(neighbor)

    for node in scc:
        dfs(node, node, [node], {node})

    return cycles


def detect_cycles(graph: "DependencyGraph") -> CycleReport:
    """Detect all import cycles in the dependency graph.

    Uses Tarjan's SCC algorithm to find strongly connected components,
    then extracts individual cycles from each SCC.
    """
    sccs = _find_sccs(graph)

    all_cycles: list[Cycle] = []
    participation: dict[str, int] = {}

    for scc in sccs:
        cycles = _extract_cycles_from_scc(scc, graph)
        all_cycles.extend(cycles)

        for cycle in cycles:
            for node in cycle.path[:-1]:  # Exclude repeated last node
                participation[node] = participation.get(node, 0) + 1

    # Mark cycle edges on the graph
    for cycle in all_cycles:
        for i in range(len(cycle.path) - 1):
            edge_key = (cycle.path[i], cycle.path[i + 1])
            if edge_key in graph.edges:
                graph.edges[edge_key].is_cycle_member = True

    # Sort by length (shortest cycles first)
    all_cycles.sort(key=lambda c: c.length)

    return CycleReport(
        cycles=all_cycles,
        participation=participation,
        has_cycles=len(all_cycles) > 0,
    )
