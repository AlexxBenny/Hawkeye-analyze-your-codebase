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
    """A single import cycle.

    The ``kind`` field classifies the cycle:
    - ``runtime``:   At least one edge is a hard, top-level import.
                     These cycles can cause ImportError at startup.
    - ``type_only``: ALL edges live inside ``if TYPE_CHECKING:`` blocks.
                     These are intentional and safe — Python never executes them.
    - ``deferred``:  ALL edges are lazy imports inside function bodies.
                     Safe at import-time but may fail at call-time.
    """
    path: list[str]    # Module names forming the cycle (first == last)
    length: int = 0
    severity: str = "low"          # 'low', 'medium', 'high', 'critical'
    break_suggestion: str = ""     # Which edge to cut
    kind: str = "runtime"          # 'runtime', 'type_only', 'deferred'

    def __post_init__(self) -> None:
        self.length = len(self.path) - 1

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


def tarjan_sccs(
    adj: dict[str, set[str]],
    *,
    min_size: int = 1,
) -> list[list[str]]:
    """Find strongly connected components using Tarjan's algorithm.

    This is the canonical, reusable SCC implementation for the project.
    Both cycle detection and rule enforcement use this function.

    Args:
        adj: Adjacency dict mapping node → set of neighbors.
        min_size: Only return SCCs with at least this many nodes.
                  Use 2 to filter out trivial self-loops.

    Returns:
        List of SCCs, each being a list of node names.
    """
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

        for neighbor in adj.get(node, set()):
            if neighbor not in adj:
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
            if len(scc) >= min_size:
                sccs.append(scc)

    # Increase recursion limit for large projects
    import sys
    old_limit = sys.getrecursionlimit()
    sys.setrecursionlimit(max(old_limit, len(adj) * 2 + 1000))

    try:
        for node in adj:
            if node not in indices:
                strongconnect(node)
    finally:
        sys.setrecursionlimit(old_limit)

    return sccs


def _find_sccs(graph: "DependencyGraph") -> list[list[str]]:
    """Find SCCs in a DependencyGraph (wrapper around tarjan_sccs)."""
    # Build adjacency dict scoped to known nodes
    adj: dict[str, set[str]] = {}
    for node in graph.nodes:
        adj[node] = {
            n for n in graph.adjacency.get(node, set())
            if n in graph.nodes
        }
    return tarjan_sccs(adj, min_size=2)


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


def _score_severity(
    cycle: Cycle,
    graph: "DependencyGraph",
) -> None:
    """Score cycle severity based on blast radius of its members."""
    members = set(cycle.path[:-1])
    total_dependents = 0
    for m in members:
        total_dependents += len(graph.reverse_adj.get(m, set()) - members)

    if total_dependents > 10 or cycle.length > 5:
        cycle.severity = "critical"
    elif total_dependents > 5 or cycle.length > 3:
        cycle.severity = "high"
    elif total_dependents > 2:
        cycle.severity = "medium"
    else:
        cycle.severity = "low"


def _suggest_break(
    cycle: Cycle,
    graph: "DependencyGraph",
) -> None:
    """Suggest which edge to cut to break the cycle.

    Heuristic: cut the edge where the SOURCE has the fewest dependents
    on the TARGET (lowest coupling cost).
    """
    best_edge = ""
    best_score = float("inf")

    for i in range(len(cycle.path) - 1):
        src, tgt = cycle.path[i], cycle.path[i + 1]
        edge = graph.edges.get((src, tgt))
        # Score = import count (fewer imports = easier to break)
        score = edge.import_count if edge else 1
        # Prefer cutting edges where the target has high Ca (many alternatives)
        tgt_ca = len(graph.reverse_adj.get(tgt, set()))
        if tgt_ca > 1:
            score *= 0.5  # Target has other consumers, safer to cut

        if score < best_score:
            best_score = score
            best_edge = f"{src} → {tgt}"

    cycle.break_suggestion = best_edge

def _classify_cycle_kind(
    cycle: Cycle,
    graph: "DependencyGraph",
) -> None:
    """Classify a cycle as runtime, type_only, or deferred.

    A cycle is safe (type_only/deferred) only if EVERY edge in the cycle
    is non-runtime. If even one edge is a hard runtime import, the whole
    cycle is classified as 'runtime'.
    """
    all_type_only = True
    all_deferred = True

    for i in range(len(cycle.path) - 1):
        edge_key = (cycle.path[i], cycle.path[i + 1])
        edge = graph.edges.get(edge_key)
        if edge is None:
            # Unknown edge — treat as runtime (conservative)
            all_type_only = False
            all_deferred = False
            break
        if not edge.is_type_only:
            all_type_only = False
        if not edge.is_deferred:
            all_deferred = False

    if all_type_only:
        cycle.kind = "type_only"
    elif all_deferred:
        cycle.kind = "deferred"
    else:
        cycle.kind = "runtime"


def detect_cycles(graph: "DependencyGraph") -> CycleReport:
    """Detect all import cycles with severity ranking and break suggestions.

    Uses Tarjan's SCC algorithm to find strongly connected components,
    then extracts individual cycles, scores their severity, classifies
    them as runtime/type_only/deferred, and suggests which edge to cut.
    """
    sccs = _find_sccs(graph)

    all_cycles: list[Cycle] = []
    participation: dict[str, int] = {}

    for scc in sccs:
        cycles = _extract_cycles_from_scc(scc, graph)
        for cycle in cycles:
            _score_severity(cycle, graph)
            _suggest_break(cycle, graph)
            _classify_cycle_kind(cycle, graph)
        all_cycles.extend(cycles)

        for cycle in cycles:
            for node in cycle.path[:-1]:
                participation[node] = participation.get(node, 0) + 1

    # Mark cycle edges on the graph
    for cycle in all_cycles:
        for i in range(len(cycle.path) - 1):
            edge_key = (cycle.path[i], cycle.path[i + 1])
            if edge_key in graph.edges:
                graph.edges[edge_key].is_cycle_member = True

    # Sort: runtime first, then by severity (critical first), then length
    kind_order = {"runtime": 0, "deferred": 1, "type_only": 2}
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    all_cycles.sort(key=lambda c: (
        kind_order.get(c.kind, 0),
        severity_order.get(c.severity, 4),
        c.length,
    ))

    return CycleReport(
        cycles=all_cycles,
        participation=participation,
        has_cycles=len(all_cycles) > 0,
    )
