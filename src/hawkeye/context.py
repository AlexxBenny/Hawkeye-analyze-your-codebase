"""Context builder — query/presentation layer for file and batch context.

Extracted from HawkeyeEngine to reduce engine complexity.
Converts raw graph/metrics/cycle data into AI-agent-ready dicts.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import HawkeyeConfig, ThresholdConfig
    from .core.analyzer import SymbolTable
    from .core.cycles import CycleReport
    from .core.graph import DependencyGraph
    from .core.insights import classify_risk, derive_module_insights
    from .core.metrics import ModuleMetrics


def build_file_context(
    *,
    module: str,
    graph: DependencyGraph,
    module_metrics: dict[str, ModuleMetrics],
    cycle_report: CycleReport,
    symbol_tables: dict[str, SymbolTable],
    config: HawkeyeConfig,
    compact: bool = True,
) -> dict:
    """Build everything an AI agent needs about a file in ONE call.

    Combines: module info + dependencies + dependents + impact +
    cycle warnings + health metrics + related files + insights + risk.

    Returns:
        Complete context dict.
    """
    from .core.insights import (classify_risk, derive_module_insights,
                                insights_compact, insights_full)

    node = graph.nodes[module]
    m = module_metrics.get(module)

    # Dependencies (what this module imports)
    deps = _build_dependency_list(module, graph, compact)

    # Dependents (what imports this module)
    dependents = _build_dependent_list(module, graph)

    # Transitive impact
    transitive = graph.get_transitive_dependents(module)

    # Cycles involving this module
    cycles = [c for c in cycle_report.cycles if module in c.path[:-1]]

    # Related files: cycle partners + shared-dependency neighbors
    related = compute_related(module, graph, cycle_report)

    result: dict = {
        "module": module,
        "language": node.language,
        "file": node.rel_path,
        "loc": node.loc,
        "package": node.package,
        "threshold_profile": config.thresholds.profile,
        "dependencies": deps,
        "dependency_count": len(deps),
        "dependents": dependents,
        "dependent_count": len(dependents),
        "impact": {
            "direct": len(dependents),
            "transitive": len(transitive),
        },
    }

    if m:
        metrics_dict = {
            "ca": m.ca, "ce": m.ce,
            "instability": m.instability,
            "health": m.health,
            "cyclomatic_complexity": m.cyclomatic_complexity,
            "cognitive_complexity": m.cognitive_complexity,
            "classes": m.class_count,
            "functions": m.function_count,
            "methods": m.method_count,
        }
        if m.parse_error:
            metrics_dict["parse_error"] = True
        result["metrics"] = metrics_dict

    if cycles:
        result["cycles"] = [
            {
                "path": cyc.path,
                "severity": cyc.severity,
                "kind": cyc.kind,
                "break_at": cyc.break_suggestion,
            }
            for cyc in cycles
        ] if not compact else [
            {
                "path": cyc.path,
                "kind": cyc.kind,
            }
            for cyc in cycles
        ]

    # Symbol details (non-compact mode)
    st = symbol_tables.get(module)
    if st and not compact:
        result["symbols"] = {
            "classes": [
                {"name": s.name, "line": s.line,
                 "methods": s.method_count, "complexity": s.complexity}
                for s in st.classes
            ],
            "functions": [
                {"name": s.name, "line": s.line, "complexity": s.complexity}
                for s in st.functions
            ],
        }

    if related:
        result["related_files"] = related

    # ── Layer 2: Deterministic insights ────────────────
    t = config.thresholds
    insights = derive_module_insights(
        instability=m.instability if m else 0.0,
        ca=m.ca if m else 0,
        ce=m.ce if m else 0,
        cyclomatic=m.cyclomatic_complexity if m else 1,
        cognitive=m.cognitive_complexity if m else 0,
        loc=node.loc,
        direct_dependents=len(dependents),
        transitive_dependents=len(transitive),
        cycle_count=len(cycles),
        max_cycle_size=max((len(c.path) - 1 for c in cycles), default=0),
        abstractness=m.abstractness if m else 0.0,
        distance_main_seq=m.distance_main_seq if m else 0.0,
        class_count=m.class_count if m else 0,
        parse_error=m.parse_error if m else False,
        thresholds=t,
    )
    if insights:
        result["insights"] = (
            insights_compact(insights) if compact
            else insights_full(insights)
        )

    # Risk profile: single self-describing label (1 token)
    risk = classify_risk(
        instability=m.instability if m else 0.0,
        ca=m.ca if m else 0,
        ce=m.ce if m else 0,
        cyclomatic=m.cyclomatic_complexity if m else 1,
        cognitive=m.cognitive_complexity if m else 0,
        direct_dependents=len(dependents),
        transitive_dependents=len(transitive),
        cycle_count=len(cycles),
        thresholds=t,
    )
    if risk:
        result["risk"] = risk

    return result


def build_batch_context(
    *,
    files: list[str],
    resolve_fn,
    graph: DependencyGraph,
    cycle_report: CycleReport,
    violations: list,
    module_metrics: dict[str, ModuleMetrics],
    symbol_tables: dict[str, SymbolTable],
    config: HawkeyeConfig,
    compact: bool = True,
) -> dict:
    """Build combined context for multiple files being edited together.

    Returns a unified briefing with shared dependencies, combined
    blast radius, and cross-file warnings.
    """
    modules = []
    not_found = []
    for f in files:
        m = resolve_fn(f)
        if m:
            modules.append(m)
        else:
            not_found.append(f)

    if not modules:
        return {"error": "No matching modules found.", "not_found": not_found}

    # Individual contexts (compact)
    file_contexts = []
    all_deps: set[str] = set()
    all_dependents: set[str] = set()
    all_transitive: set[str] = set()

    for module in modules:
        ctx = build_file_context(
            module=module,
            graph=graph,
            module_metrics=module_metrics,
            cycle_report=cycle_report,
            symbol_tables=symbol_tables,
            config=config,
            compact=compact,
        )
        file_contexts.append({
            "module": ctx["module"],
            "language": ctx.get("language", "python"),
            "file": ctx["file"],
            "health": ctx.get("metrics", {}).get("health", "unknown"),
            "dependency_count": ctx["dependency_count"],
            "dependent_count": ctx["dependent_count"],
        })
        all_deps |= graph.get_dependencies(module)
        all_dependents |= graph.get_dependents(module)
        all_transitive |= graph.get_transitive_dependents(module)

    # Remove the files themselves from impact counts
    module_set = set(modules)
    all_deps -= module_set
    all_dependents -= module_set
    all_transitive -= module_set

    # Shared dependencies (deps imported by 2+ of the files)
    if len(modules) > 1:
        dep_counts: dict[str, int] = {}
        for module in modules:
            for dep in graph.get_dependencies(module):
                dep_counts[dep] = dep_counts.get(dep, 0) + 1
        shared = sorted(d for d, c in dep_counts.items() if c > 1)
    else:
        shared = []

    # Cycle warnings
    cycle_warnings = []
    for c in cycle_report.cycles:
        cycle_modules = set(c.path[:-1])
        if cycle_modules & module_set:
            cycle_warnings.append(c.path)

    # Architecture violations involving these modules
    violation_strs = [
        str(v) for v in violations
        if v.source in module_set or v.target in module_set
    ]

    result: dict = {
        "files": file_contexts,
        "combined_blast_radius": len(all_transitive),
        "shared_dependencies": shared,
        "total_unique_dependencies": len(all_deps),
        "total_unique_dependents": len(all_dependents),
    }

    if cycle_warnings:
        result["cycle_warnings"] = cycle_warnings
    if violation_strs:
        result["violations"] = violation_strs
    if not_found:
        result["not_found"] = not_found

    return result


# ── Internal helpers ────────────────────────────────────────────


def _build_dependency_list(
    module: str, graph: DependencyGraph, compact: bool,
) -> list[dict]:
    """Build the dependency list for a module's context output."""
    deps = []
    for dep in sorted(graph.get_dependencies(module)):
        edge = graph.edges.get((module, dep))
        dep_node = graph.nodes.get(dep)
        entry: dict = {"module": dep}
        if dep_node:
            entry["file"] = dep_node.rel_path
            entry["language"] = dep_node.language
        if edge and edge.is_cycle_member:
            entry["is_cycle"] = True
        if edge and edge.is_type_only:
            entry["is_type_only"] = True
        if edge and edge.is_deferred:
            entry["is_deferred"] = True
        if not compact and edge:
            entry["import_count"] = edge.import_count
            entry["lines"] = edge.lines
        deps.append(entry)
    return deps


def _build_dependent_list(module: str, graph: DependencyGraph) -> list[dict]:
    """Build the dependent list for a module's context output."""
    dependents = []
    for dep in sorted(graph.get_dependents(module)):
        dep_node = graph.nodes.get(dep)
        entry: dict = {"module": dep}
        if dep_node:
            entry["file"] = dep_node.rel_path
            entry["language"] = dep_node.language
        dependents.append(entry)
    return dependents


def compute_related(
    module: str,
    graph: DependencyGraph,
    cycle_report: CycleReport,
    limit: int = 8,
) -> list[dict]:
    """Find files related to a module (cycle partners, frequent co-deps)."""
    related: dict[str, str] = {}  # module -> reason

    # Cycle partners
    for c in cycle_report.cycles:
        if module in c.path[:-1]:
            for m in c.path[:-1]:
                if m != module and m not in related:
                    related[m] = "cycle partner"

    # Modules that share many of the same dependents (co-imported)
    my_dependents = graph.get_dependents(module)
    if my_dependents:
        for dep in graph.get_dependencies(module):
            dep_dependents = graph.get_dependents(dep)
            overlap = my_dependents & dep_dependents
            if len(overlap) > 1 and dep not in related:
                related[dep] = "shared dependency"

    result = []
    for m, reason in list(related.items())[:limit]:
        node = graph.nodes.get(m)
        if node:
            result.append({"file": node.rel_path, "module": m, "reason": reason})

    return result
