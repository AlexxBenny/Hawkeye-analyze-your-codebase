"""Coupling metrics and architectural health scoring.

Computes per-module software engineering metrics including afferent/efferent
coupling, instability, and composite health scores based on Robert C. Martin's
package coupling principles.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .graph import DependencyGraph


@dataclass
class ModuleMetrics:
    """Computed metrics for a single module."""
    module_name: str
    ca: int             # Afferent coupling — modules that depend on this one
    ce: int             # Efferent coupling — modules this one depends on
    instability: float  # I = Ce / (Ca + Ce), 0=stable, 1=unstable
    loc: int            # Lines of code
    import_count: int   # Total import statements
    fan_in: int         # Same as Ca (incoming edges)
    fan_out: int        # Same as Ce (outgoing edges)
    health: str         # "healthy", "warning", "critical"

    @property
    def health_emoji(self) -> str:
        return {"healthy": "✅", "warning": "⚠️", "critical": "🔴"}[self.health]


@dataclass
class ProjectMetrics:
    """Aggregate metrics for the entire project."""
    total_modules: int
    total_edges: int
    total_loc: int
    avg_instability: float
    max_instability: float
    modules_critical: int
    modules_warning: int
    modules_healthy: int
    density: float          # edge_count / (node_count * (node_count - 1))
    has_cycles: bool


def _assess_health(ca: int, ce: int, instability: float) -> str:
    """Determine module health based on coupling metrics."""
    total_coupling = ca + ce
    if total_coupling == 0:
        return "healthy"
    if instability > 0.8 and ce > 8:
        return "critical"
    if instability > 0.7 and ce > 5:
        return "warning"
    if ca == 0 and ce > 10:
        return "warning"  # High outgoing, nothing depends on it — might be god module
    return "healthy"


def calculate_module_metrics(graph: "DependencyGraph") -> dict[str, ModuleMetrics]:
    """Calculate coupling metrics for every module in the graph."""
    results: dict[str, ModuleMetrics] = {}

    for module_name, node in graph.nodes.items():
        ca = len(graph.reverse_adj.get(module_name, set()))
        ce = len(graph.adjacency.get(module_name, set()))
        total = ca + ce
        instability = ce / total if total > 0 else 0.0

        # Count total import lines for this module
        import_count = 0
        for (src, _), edge in graph.edges.items():
            if src == module_name:
                import_count += edge.import_count

        health = _assess_health(ca, ce, instability)

        results[module_name] = ModuleMetrics(
            module_name=module_name,
            ca=ca,
            ce=ce,
            instability=round(instability, 3),
            loc=node.loc,
            import_count=import_count,
            fan_in=ca,
            fan_out=ce,
            health=health,
        )

    return results


def calculate_project_metrics(
    graph: "DependencyGraph",
    module_metrics: dict[str, ModuleMetrics],
    has_cycles: bool = False,
) -> ProjectMetrics:
    """Calculate aggregate project-level metrics."""
    n = len(graph.nodes)
    e = len(graph.edges)
    total_loc = sum(m.loc for m in module_metrics.values())

    instabilities = [m.instability for m in module_metrics.values()]
    avg_instability = sum(instabilities) / len(instabilities) if instabilities else 0.0

    max_possible_edges = n * (n - 1) if n > 1 else 1
    density = e / max_possible_edges

    return ProjectMetrics(
        total_modules=n,
        total_edges=e,
        total_loc=total_loc,
        avg_instability=round(avg_instability, 3),
        max_instability=round(max(instabilities, default=0.0), 3),
        modules_critical=sum(1 for m in module_metrics.values() if m.health == "critical"),
        modules_warning=sum(1 for m in module_metrics.values() if m.health == "warning"),
        modules_healthy=sum(1 for m in module_metrics.values() if m.health == "healthy"),
        density=round(density, 4),
        has_cycles=has_cycles,
    )


def format_metrics_table(
    module_metrics: dict[str, ModuleMetrics],
    sort_by: str = "instability",
    limit: int = 0,
) -> str:
    """Format metrics as an ASCII table sorted by the given field."""
    metrics_list = sorted(
        module_metrics.values(),
        key=lambda m: getattr(m, sort_by, 0),
        reverse=True,
    )

    if limit > 0:
        metrics_list = metrics_list[:limit]

    header = f"{'Module':<50} {'Ca':>4} {'Ce':>4} {'I':>7} {'LOC':>6} {'Health':>8}"
    separator = "─" * len(header)
    lines = [separator, header, separator]

    for m in metrics_list:
        lines.append(
            f"{m.module_name:<50} {m.ca:>4} {m.ce:>4} {m.instability:>7.3f} "
            f"{m.loc:>6} {m.health_emoji:>8}"
        )

    lines.append(separator)
    return "\n".join(lines)
