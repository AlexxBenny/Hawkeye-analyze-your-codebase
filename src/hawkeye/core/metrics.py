"""Coupling metrics and architectural health scoring.

Computes per-module software engineering metrics including afferent/efferent
coupling, instability, and composite health scores based on Robert C. Martin's
package coupling principles.

v0.6 additions:
  - Percentile-based adaptive thresholds (calibrate to each project)
  - Module role classification (test/init/config/source)
  - Architectural role classification via betweenness centrality
  - Edit cost estimation for AI agents
"""

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .graph import DependencyGraph


# ── Token estimation ratios by language ─────────────────────────
# Approximate LOC-to-token ratio for each language.  Used by edit_cost
# estimation to give AI agents a rough magnitude of work.

_DEFAULT_TOKEN_RATIOS: dict[str, float] = {
    "python": 2.3,
    "javascript": 2.0,
    "typescript": 2.1,
}


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
    health: str         # Effective health (agent-facing, adjusted for arch_role)
    raw_health: str = "unknown"  # Raw health from _assess_health() before adjustment
    # Language (default: python for backward compatibility)
    language: str = "python"
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
    # v0.6: Role and centrality
    role: str = "source"                # "test", "init", "config", "source"
    arch_role: str = ""                 # "core", "orchestrator", "hub-by-design", ""
    centrality: float = 0.0            # Betweenness centrality (normalized)

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
            "language": self.language,
            "ca": self.ca,
            "ce": self.ce,
            "instability": self.instability,
            "loc": self.loc,
            "health": self.health,
            "raw_health": self.raw_health,
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
        if self.role != "source":
            d["role"] = self.role
        if self.arch_role:
            d["arch_role"] = self.arch_role
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


# ── Module role classification ────────────────────────────────────


def _classify_module_role(module_name: str, *, is_package: bool = False) -> str:
    """Classify a module's structural role for threshold scaling.

    Returns: 'test', 'init', 'config', 'source'.

    Test files get relaxed CC thresholds because each test method adds +1
    to CC — a file with 75 test methods has CC=75 which is normal coverage,
    not architectural risk.

    ``is_package`` is True for ``__init__.py`` files — their module name
    uses the package name (e.g. 'core'), not '__init__'.
    """
    basename = module_name.rsplit(".", 1)[-1]

    if basename.startswith("test_") or basename == "conftest":
        return "test"

    if basename == "__init__" or is_package:
        return "init"

    if basename in ("config", "settings", "constants", "defaults"):
        return "config"

    return "source"


# ── Architectural role classification ─────────────────────────────


def _classify_arch_role(
    module_name: str,
    ca: int,
    ce: int,
    centrality_percentile: float,
    ca_percentile: float = 0.0,
) -> str:
    """Classify a module's architectural role using graph centrality + coupling.

    Two signals combined:
      - Betweenness centrality: identifies bridges/orchestrators
      - Ca percentile: identifies foundational modules many depend on

    A module like analyzer.py has low betweenness (it's a leaf, not a bridge)
    but very high Ca (10 modules import it).  Pure betweenness would miss it.

    Returns:
        'core'           — foundational module many depend on (high Ca)
        'orchestrator'   — coordinates many modules (high centrality, high Ce)
        'hub-by-design'  — __init__.py re-export hubs
        ''               — no special role
    """
    basename = module_name.rsplit(".", 1)[-1]

    # Init modules with 3+ re-exports are hubs by design
    if basename == "__init__" and ce >= 3:
        return "hub-by-design"

    # High centrality = structurally central (bridge between subgraphs)
    if centrality_percentile >= 0.90:
        if ca > ce:
            return "core"
        return "orchestrator"

    # High Ca = foundational (many modules depend on it, even if not a bridge)
    if ca_percentile >= 0.90 and ca > ce:
        return "core"

    return ""


# ── Percentile computation ────────────────────────────────────────


def _percentile(sorted_values: list[float], p: float) -> float:
    """Compute the p-th percentile from a pre-sorted list.

    Uses linear interpolation.  p is in [0, 100].
    """
    if not sorted_values:
        return 0.0
    k = (len(sorted_values) - 1) * p / 100.0
    f = int(k)
    c = f + 1
    if c >= len(sorted_values):
        return sorted_values[-1]
    return sorted_values[f] + (k - f) * (sorted_values[c] - sorted_values[f])


def _compute_adaptive_thresholds(
    cc_values: list[int],
    cog_values: list[int],
    floors: "dict[str, int]",
) -> dict[str, float]:
    """Compute adaptive thresholds from the project's metric distribution.

    Hybrid approach: use percentiles as primary signal, but apply floor
    values so that tiny/simple projects don't get meaningless criticals.

    Returns dict with keys like 'cc_critical', 'cc_high', etc.
    """
    sorted_cc = sorted(float(v) for v in cc_values)
    sorted_cog = sorted(float(v) for v in cog_values)

    return {
        "cc_critical": max(_percentile(sorted_cc, 95), floors.get("cc_floor_critical", 30)),
        "cc_high": max(_percentile(sorted_cc, 90), floors.get("cc_floor_high", 15)),
        "cc_elevated": max(_percentile(sorted_cc, 80), 8),
        "cc_moderate": max(_percentile(sorted_cc, 60), 4),
        "cog_critical": max(_percentile(sorted_cog, 95), floors.get("cog_floor_critical", 30)),
        "cog_high": max(_percentile(sorted_cog, 90), floors.get("cog_floor_high", 15)),
        "cog_elevated": max(_percentile(sorted_cog, 80), 10),
        "cog_moderate": max(_percentile(sorted_cog, 60), 6),
    }


def _percentile_rank(value: float, sorted_values: list[float]) -> float:
    """What fraction of values are <= this value.  Returns 0.0–1.0."""
    if not sorted_values:
        return 0.0
    count_below = sum(1 for v in sorted_values if v <= value)
    return count_below / len(sorted_values)


# ── Health assessment ─────────────────────────────────────────────


def _assess_health(
    ca: int, ce: int, instability: float,
    cc: int = 1, cog: int = 0,
    *,
    thresholds: "ThresholdConfig | None" = None,
    parse_error: bool = False,
    adaptive: "dict[str, float] | None" = None,
    module_role: str = "source",
    arch_role: str = "",
) -> str:
    """Determine module health on a 5-level monotonic severity scale.

    Levels (ascending severity):
        healthy  — no structural issues
        moderate — mild concerns, acceptable
        elevated — noticeable risk
        high     — strong structural problems
        critical — severe / immediate concern
        unknown  — AST parse failed, metrics unreliable

    When ``adaptive`` thresholds are provided (from percentile computation),
    they override the static thresholds for CC/Cog classification.

    ``module_role`` ('init', 'test', 'config', 'source') and ``arch_role``
    ('hub-by-design', 'core', 'orchestrator', '') control whether coupling-
    based escalation applies.  Hub-by-design init modules have high Ce by
    design (re-exports), so coupling rules are skipped for them.
    """
    if parse_error:
        return "unknown"

    if thresholds is None:
        from ..config import ThresholdConfig
        thresholds = ThresholdConfig()

    t = thresholds

    # Use adaptive thresholds for CC/Cog if available, else static
    if adaptive:
        cc_critical = adaptive["cc_critical"]
        cc_high = adaptive["cc_high"]
        cc_elevated = adaptive["cc_elevated"]
        cc_moderate = adaptive["cc_moderate"]
        cog_critical = adaptive["cog_critical"]
        cog_high = adaptive["cog_high"]
        cog_elevated = adaptive["cog_elevated"]
        cog_moderate = adaptive["cog_moderate"]
    else:
        cc_critical = t.cc_critical
        cc_high = t.cc_high
        cc_elevated = t.cc_elevated
        cc_moderate = t.cc_moderate
        cog_critical = t.cog_critical
        cog_high = t.cog_high
        cog_elevated = t.cog_elevated
        cog_moderate = t.cog_moderate

    # Hub-by-design init modules: skip coupling-based escalation.
    # High Ce in __init__.py is intentional re-exporting, not a problem.
    skip_coupling = (arch_role == "hub-by-design" or module_role == "init")

    # Critical: extreme complexity or severe coupling
    if cc >= cc_critical or cog >= cog_critical:
        return "critical"
    if not skip_coupling and instability > t.instability_high and ce > t.ce_high:
        return "critical"

    # High: significant structural problems
    if cc >= cc_high or cog >= cog_high:
        return "high"
    if not skip_coupling and ca == 0 and ce > t.ce_high:
        return "high"

    # Elevated: noticeable risk
    if cc >= cc_elevated or cog >= cog_elevated:
        return "elevated"
    if not skip_coupling and instability > t.instability_high * 0.875 and ce > t.ce_high * 0.625:
        return "elevated"

    # Moderate: mild concerns
    if cc >= cc_moderate or cog >= cog_moderate:
        return "moderate"

    return "healthy"


def _compute_effective_health(raw_health: str, arch_role: str, role: str) -> str:
    """Adjust health for architectural role.

    Core modules cap at 'elevated' — their complexity is structural,
    not pathological.  Test modules cap at 'moderate' — high CC from
    many test methods is normal coverage, not risk.

    Args:
        raw_health: What _assess_health() computed from raw metrics.
        arch_role: 'core', 'orchestrator', 'hub-by-design', or ''.
        role: 'test', 'init', 'config', or 'source'.

    Returns:
        Effective health label for agent consumption.
    """
    if arch_role == "core" and raw_health in ("critical", "high"):
        return "elevated"
    if role == "test" and raw_health in ("critical", "high"):
        return "moderate"
    return raw_health


# ── Edit cost estimation ─────────────────────────────────────────


def compute_edit_cost(
    module: str,
    graph: "DependencyGraph",
    module_metrics: "dict[str, ModuleMetrics]",
    token_ratios: "dict[str, float] | None" = None,
    git_history=None,
) -> dict:
    """Estimate the cost of editing a module — designed for AI agent decisions.

    Returns a compact dict with:
      - files: number of direct dependents (files at risk of breaking)
      - cascade: transitive dependents (full blast radius)
      - tokens: rough token estimate for this file + its direct dependents
      - risk: 'low', 'medium', or 'high' (never 'unknown')
    """
    ratios = token_ratios or _DEFAULT_TOKEN_RATIOS
    node = graph.nodes.get(module)
    if not node:
        return {"files": 0, "cascade": 0, "tokens": 0, "risk": "low"}

    dependents = graph.get_dependents(module)
    transitive = graph.get_transitive_dependents(module)

    # Token estimate: this file + direct dependents
    lang = node.language
    ratio = ratios.get(lang, 2.0)
    own_tokens = int(node.loc * ratio)
    dep_tokens = sum(
        int(graph.nodes[d].loc * ratios.get(graph.nodes[d].language, 2.0))
        for d in dependents if d in graph.nodes
    )

    # Risk: combine git churn (if available) with structural signals.
    # Structural risk is always computable — never emit "unknown".
    files_at_risk = len(dependents)

    if git_history and git_history.available:
        rel = node.rel_path.replace("\\", "/")
        churn = git_history.files.get(rel)
        if churn:
            if churn.churn_category == "hot" and files_at_risk >= 5:
                change_risk = "high"
            elif churn.churn_category in ("hot", "warm") or files_at_risk >= 3:
                change_risk = "medium"
            else:
                change_risk = "low"
        else:
            change_risk = "low"  # No churn data = probably stable
    else:
        # Structural fallback: aligned with dependents_critical (10)
        # and dependents_high (5) from ThresholdConfig defaults.
        if files_at_risk >= 10:
            change_risk = "high"
        elif files_at_risk >= 5:
            change_risk = "medium"
        else:
            change_risk = "low"

    return {
        "files": files_at_risk,
        "cascade": len(transitive),
        "tokens": own_tokens + dep_tokens,
        "risk": change_risk,
    }


# ── Main calculation pipeline ─────────────────────────────────────


def calculate_module_metrics(
    graph: "DependencyGraph",
    symbol_tables: dict | None = None,
    *,
    thresholds: "ThresholdConfig | None" = None,
) -> dict[str, ModuleMetrics]:
    """Calculate coupling and complexity metrics for every module.

    When ``thresholds.use_percentiles`` is True (default), computes
    project-relative percentile thresholds for CC/Cog instead of using
    hardcoded values.  This prevents alarm fatigue on projects where
    35%+ of modules would be labeled 'critical' under static thresholds.
    """
    if symbol_tables is None:
        symbol_tables = {}

    if thresholds is None:
        from ..config import ThresholdConfig
        thresholds = ThresholdConfig()

    # ── Pass 1: collect raw data ──────────────────────────────────
    raw_data: list[dict] = []
    for module_name, node in graph.nodes.items():
        ca = len(graph.reverse_adj.get(module_name, set()))
        ce = len(graph.adjacency.get(module_name, set()))
        total = ca + ce
        instability = ce / total if total > 0 else 0.0

        import_count = 0
        for (src, _), edge in graph.edges.items():
            if src == module_name:
                import_count += edge.import_count

        st = symbol_tables.get(module_name)
        cc = st.cyclomatic_complexity if st else 1
        cog = st.cognitive_complexity if st else 0
        pe = st.parse_error if st else False

        abstract_count = st.abstract_class_count if st else 0
        class_count = st.class_count if st else 0
        abstractness = abstract_count / class_count if class_count > 0 else 0.0
        distance = abs(abstractness + instability - 1.0)

        role = _classify_module_role(module_name, is_package=node.is_package)

        raw_data.append({
            "module_name": module_name,
            "node": node,
            "ca": ca, "ce": ce,
            "instability": instability,
            "import_count": import_count,
            "cc": cc, "cog": cog, "pe": pe,
            "abstract_count": abstract_count,
            "class_count": class_count,
            "abstractness": abstractness,
            "distance": distance,
            "role": role,
            "function_count": st.function_count if st else 0,
            "method_count": st.method_count if st else 0,
        })

    # ── Pass 2: compute adaptive thresholds (if enabled) ──────────
    # Key insight: compute percentiles from SOURCE files only.
    # Test files (CC=75 just means 75 test methods) would inflate the
    # distribution and make the thresholds useless.
    adaptive_source = None
    adaptive_test = None
    adaptive_init = None
    if thresholds.use_percentiles and raw_data:
        source_data = [d for d in raw_data if d["role"] == "source"]
        if source_data:
            cc_values = [d["cc"] for d in source_data]
            cog_values = [d["cog"] for d in source_data]
            floors = {
                "cc_floor_critical": thresholds.cc_floor_critical,
                "cc_floor_high": thresholds.cc_floor_high,
                "cog_floor_critical": thresholds.cog_floor_critical,
                "cog_floor_high": thresholds.cog_floor_high,
            }
            adaptive_source = _compute_adaptive_thresholds(
                cc_values, cog_values, floors,
            )
            # Test files: 3x relaxed thresholds (CC=75 is just 75 tests)
            adaptive_test = {
                k: v * 3.0 for k, v in adaptive_source.items()
            }
            # Init/config: 1.5x relaxed
            adaptive_init = {
                k: v * 1.5 for k, v in adaptive_source.items()
            }

    # Role → adaptive thresholds mapping
    _role_adaptive = {
        "source": adaptive_source,
        "test": adaptive_test,
        "init": adaptive_init,
        "config": adaptive_init,  # config uses same relaxation as init
    }

    # ── Pass 3: compute betweenness centrality ────────────────────
    centrality = graph.betweenness_centrality()
    sorted_centrality = sorted(centrality.values())
    sorted_ca = sorted(float(d["ca"]) for d in raw_data)

    # ── Pass 4: build ModuleMetrics with role-aware health ────────
    results: dict[str, ModuleMetrics] = {}
    for d in raw_data:
        module_name = d["module_name"]
        node = d["node"]

        # Compute arch_role FIRST — health scoring needs it
        cent = centrality.get(module_name, 0.0)
        cent_pct = _percentile_rank(cent, sorted_centrality)
        ca_pct = _percentile_rank(float(d["ca"]), sorted_ca)

        arch_role = _classify_arch_role(
            module_name, d["ca"], d["ce"], cent_pct,
            ca_percentile=ca_pct,
        )

        # Pick adaptive thresholds for this module's role
        role_adaptive = _role_adaptive.get(d["role"], adaptive_source)

        health = _assess_health(
            d["ca"], d["ce"], d["instability"], d["cc"], d["cog"],
            thresholds=thresholds, parse_error=d["pe"],
            adaptive=role_adaptive,
            module_role=d["role"], arch_role=arch_role,
        )
        effective = _compute_effective_health(health, arch_role, d["role"])

        results[module_name] = ModuleMetrics(
            module_name=module_name,
            language=node.language,
            ca=d["ca"],
            ce=d["ce"],
            instability=round(d["instability"], 3),
            loc=node.loc,
            import_count=d["import_count"],
            fan_in=d["ca"],
            fan_out=d["ce"],
            health=effective,
            raw_health=health,
            class_count=d["class_count"],
            function_count=d["function_count"],
            method_count=d["method_count"],
            abstract_class_count=d["abstract_count"],
            cyclomatic_complexity=d["cc"],
            cognitive_complexity=d["cog"],
            abstractness=round(d["abstractness"], 3),
            distance_main_seq=round(d["distance"], 3),
            parse_error=d["pe"],
            role=d["role"],
            arch_role=arch_role,
            centrality=round(cent, 6),
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
