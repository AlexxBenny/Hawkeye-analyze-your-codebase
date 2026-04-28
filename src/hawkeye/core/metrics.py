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
    health: str         # "healthy", "moderate", "elevated", "high", "critical", "unknown"
    # Symbol counts
    class_count: int = 0
    function_count: int = 0
    method_count: int = 0
    abstract_class_count: int = 0
    # Complexity
    cyclomatic_complexity: int = 1
    cognitive_complexity: int = 0
    # Martin metrics
    abstractness: float = 0.0           # A = Na / Nc (0 if no classes)
    distance_main_seq: float = 0.0      # D = |A + I - 1|
    # Parse status
    parse_error: bool = False

    @property
    def health_emoji(self) -> str:
        return {
            "unknown": "❓", "healthy": "✅", "moderate": "🟡",
            "elevated": "🟠", "high": "🔴", "critical": "🔥",
        }[self.health]

    def to_dict(self) -> dict:
        """Single canonical serialization. ALL renderers use this."""
        d = {
            "module": self.module_name,
            "ca": self.ca,
            "ce": self.ce,
            "instability": self.instability,
            "loc": self.loc,
            "health": self.health,
            "cyclomatic": self.cyclomatic_complexity,
            "cognitive": self.cognitive_complexity,
            "abstractness": self.abstractness,
            "distance": self.distance_main_seq,
            "classes": self.class_count,
            "functions": self.function_count,
            "methods": self.method_count,
            "abstract_classes": self.abstract_class_count,
        }
        if self.parse_error:
            d["parse_error"] = True
        return d


@dataclass
class ProjectMetrics:
    """Aggregate metrics for the entire project."""
    total_modules: int
    total_edges: int
    total_loc: int
    avg_instability: float
    max_instability: float
    modules_critical: int
    modules_high: int
    modules_elevated: int
    modules_moderate: int
    modules_healthy: int
    modules_unknown: int
    density: float          # edge_count / (node_count * (node_count - 1))
    has_cycles: bool


def _assess_health(
    ca: int, ce: int, instability: float,
    cc: int = 1, cog: int = 0,
    *,
    thresholds: "ThresholdConfig | None" = None,
    parse_error: bool = False,
) -> str:
    """Determine module health on a 5-level monotonic severity scale.

    Levels (ascending severity):
        healthy  — no structural issues
        moderate — mild concerns, acceptable
        elevated — noticeable risk
        high     — strong structural problems
        critical — severe / immediate concern
        unknown  — AST parse failed, metrics unreliable

    All thresholds come from ThresholdConfig — no hardcoded numbers.
    """
    if parse_error:
        return "unknown"

    if thresholds is None:
        from ..config import ThresholdConfig
        thresholds = ThresholdConfig()

    t = thresholds

    # Critical: extreme complexity or severe coupling
    if cc >= t.cc_critical or cog >= t.cog_critical:
        return "critical"
    if instability > t.instability_high and ce > t.ce_high:
        return "critical"

    # High: significant structural problems
    if cc >= t.cc_high or cog >= t.cog_high:
        return "high"
    if ca == 0 and ce > t.ce_high:
        return "high"

    # Elevated: noticeable risk
    if cc >= t.cc_elevated or cog >= t.cog_elevated:
        return "elevated"
    if instability > t.instability_high * 0.875 and ce > t.ce_high * 0.625:
        return "elevated"

    # Moderate: mild concerns
    if cc >= t.cc_moderate or cog >= t.cog_moderate:
        return "moderate"

    return "healthy"


def calculate_module_metrics(
    graph: "DependencyGraph",
    symbol_tables: dict | None = None,
    *,
    thresholds: "ThresholdConfig | None" = None,
) -> dict[str, ModuleMetrics]:
    """Calculate coupling and complexity metrics for every module."""
    if symbol_tables is None:
        symbol_tables = {}

    results: dict[str, ModuleMetrics] = {}

    for module_name, node in graph.nodes.items():
        ca = len(graph.reverse_adj.get(module_name, set()))
        ce = len(graph.adjacency.get(module_name, set()))
        total = ca + ce
        instability = ce / total if total > 0 else 0.0

        import_count = 0
        for (src, _), edge in graph.edges.items():
            if src == module_name:
                import_count += edge.import_count

        # Get symbol data if available
        st = symbol_tables.get(module_name)
        cc = st.cyclomatic_complexity if st else 1
        cog = st.cognitive_complexity if st else 0
        pe = st.parse_error if st else False

        health = _assess_health(
            ca, ce, instability, cc, cog,
            thresholds=thresholds, parse_error=pe,
        )

        # Abstractness (A) and Distance from Main Sequence (D)
        abstract_count = st.abstract_class_count if st else 0
        class_count = st.class_count if st else 0
        abstractness = abstract_count / class_count if class_count > 0 else 0.0
        distance = abs(abstractness + instability - 1.0)

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
            class_count=class_count,
            function_count=st.function_count if st else 0,
            method_count=st.method_count if st else 0,
            abstract_class_count=abstract_count,
            cyclomatic_complexity=cc,
            cognitive_complexity=cog,
            abstractness=round(abstractness, 3),
            distance_main_seq=round(distance, 3),
            parse_error=pe,
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

    def _count(label: str) -> int:
        return sum(1 for m in module_metrics.values() if m.health == label)

    return ProjectMetrics(
        total_modules=n,
        total_edges=e,
        total_loc=total_loc,
        avg_instability=round(avg_instability, 3),
        max_instability=round(max(instabilities, default=0.0), 3),
        modules_critical=_count("critical"),
        modules_high=_count("high"),
        modules_elevated=_count("elevated"),
        modules_moderate=_count("moderate"),
        modules_healthy=_count("healthy"),
        modules_unknown=_count("unknown"),
        density=round(density, 4),
        has_cycles=has_cycles,
    )


_SORT_ALIASES = {
    "cyclomatic": "cyclomatic_complexity",
    "cognitive": "cognitive_complexity",
    "distance": "distance_main_seq",
}

_HEALTH_ORDER = {
    "unknown": -1, "critical": 0, "high": 1,
    "elevated": 2, "moderate": 3, "healthy": 4,
}


def sort_metrics(
    module_metrics: dict[str, ModuleMetrics],
    sort_by: str = "instability",
    limit: int = 0,
) -> list[ModuleMetrics]:
    """Sort and limit module metrics. Used by all output paths."""
    key = _SORT_ALIASES.get(sort_by, sort_by)

    if sort_by == "health":
        result = sorted(
            module_metrics.values(),
            key=lambda m: (_HEALTH_ORDER.get(m.health, 3), -m.cyclomatic_complexity),
        )
    else:
        result = sorted(
            module_metrics.values(),
            key=lambda m: getattr(m, key, 0),
            reverse=True,
        )

    if limit > 0:
        result = result[:limit]
    return result


def format_metrics_table(
    module_metrics: dict[str, ModuleMetrics],
    sort_by: str = "instability",
    limit: int = 0,
) -> str:
    """Format metrics as an ASCII table with all columns."""
    metrics_list = sort_metrics(module_metrics, sort_by, limit)

    header = (f"{'Module':<45} {'Ca':>3} {'Ce':>3} {'I':>6} "
              f"{'CC':>4} {'Cog':>4} {'A':>5} {'D':>5} "
              f"{'LOC':>5} {'Health':>8}")
    sep = "─" * len(header)
    lines = [sep, header, sep]

    for m in metrics_list:
        lines.append(
            f"{m.module_name:<45} {m.ca:>3} {m.ce:>3} {m.instability:>6.3f} "
            f"{m.cyclomatic_complexity:>4} {m.cognitive_complexity:>4} "
            f"{m.abstractness:>5.2f} {m.distance_main_seq:>5.2f} "
            f"{m.loc:>5} {m.health_emoji:>8}"
        )

    lines.append(sep)
    return "\n".join(lines)
