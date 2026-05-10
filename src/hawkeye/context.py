"""Context builder — query/presentation layer for file and batch context.

Extracted from HawkeyeEngine to reduce engine complexity.
Converts raw graph/metrics/cycle data into AI-agent-ready dicts.

v0.6: Compact mode rewritten for maximum token efficiency.
  - Flat file paths instead of {module, file, language} objects
  - Redundant keys eliminated (dependency_count, impact.direct, package)
  - Metrics flattened to top level with short keys
  - edit_cost added for AI agent planning
  - Git churn surfaced in compact mode
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
    git_history=None,
) -> dict:
    """Build everything an AI agent needs about a file in ONE call.

    Combines: module info + dependencies + dependents + impact +
    cycle warnings + health metrics + related files + insights + risk +
    git churn (when available) + edit cost estimation.

    Compact mode (default) is optimized for token efficiency — ~200 tokens
    vs ~450 in v0.5.  Non-compact mode retains full detail for CLI/HTML.

    Returns:
        Complete context dict.
    """
    from .core.insights import (classify_risk, derive_module_insights,
                                insights_compact, insights_full,
                                rewrite_insights_for_core)
    from .core.metrics import compute_edit_cost

    node = graph.nodes[module]
    m = module_metrics.get(module)

    # Transitive impact
    transitive = graph.get_transitive_dependents(module)

    # Cycles involving this module
    cycles = [c for c in cycle_report.cycles if module in c.path[:-1]]

    # ── Compact mode: maximum token efficiency ────────────────
    if compact:
        return _build_compact_context(
            module=module,
            node=node,
            m=m,
            graph=graph,
            module_metrics=module_metrics,
            transitive=transitive,
            cycles=cycles,
            cycle_report=cycle_report,
            config=config,
            git_history=git_history,
            insights_compact_fn=insights_compact,
            derive_fn=derive_module_insights,
            classify_fn=classify_risk,
            edit_cost_fn=compute_edit_cost,
            rewrite_core_fn=rewrite_insights_for_core,
        )

    # ── Non-compact mode: full detail for CLI/renderers ───────
    return _build_full_context(
        module=module,
        node=node,
        m=m,
        graph=graph,
        module_metrics=module_metrics,
        transitive=transitive,
        cycles=cycles,
        cycle_report=cycle_report,
        symbol_tables=symbol_tables,
        config=config,
        git_history=git_history,
        insights_full_fn=insights_full,
        derive_fn=derive_module_insights,
        classify_fn=classify_risk,
        rewrite_core_fn=rewrite_insights_for_core,
    )


def _build_compact_context(
    *,
    module, node, m, graph, module_metrics, transitive,
    cycles, cycle_report, config, git_history,
    insights_compact_fn, derive_fn, classify_fn, edit_cost_fn,
    rewrite_core_fn,
) -> dict:
    """Token-efficient compact context for AI agents (~200 tokens).

    Design principles:
      - File path as primary identifier (not FQDN module name)
      - Flat string lists for deps/dependents (not object arrays)
      - Metrics at top level with short keys (not nested)
      - Only include keys that aid editing decisions
    """
    # Flat dependency/dependent lists — just file paths
    deps = sorted(
        graph.nodes[d].rel_path
        for d in graph.get_dependencies(module)
        if d in graph.nodes
    )
    dependents = sorted(
        graph.nodes[d].rel_path
        for d in graph.get_dependents(module)
        if d in graph.nodes
    )

    result: dict = {
        "file": node.rel_path,
        "loc": node.loc,
    }

    if m:
        # Role info (only when non-default)
        if m.role != "source":
            result["role"] = m.role
        if m.arch_role:
            result["arch_role"] = m.arch_role

        # Health + core metrics at top level, short keys
        result["health"] = m.health
        result["cc"] = m.cyclomatic_complexity
        result["cog"] = m.cognitive_complexity
        result["ca"] = m.ca
        result["ce"] = m.ce
        result["I"] = m.instability

        if m.parse_error:
            result["parse_error"] = True

    result["deps"] = deps
    result["dependents"] = dependents
    result["transitive_impact"] = len(transitive)

    # Edit cost estimation — the key AI-agent field
    edit_cost = edit_cost_fn(
        module, graph, module_metrics,
        token_ratios=config.thresholds.token_ratios,
        git_history=git_history,
    )
    result["edit_cost"] = edit_cost

    # Cycles (compact: just paths)
    if cycles:
        result["cycles"] = [
            {"path": cyc.path, "kind": cyc.kind}
            for cyc in cycles
        ]

    # Insights — just codes
    t = config.thresholds
    arch_role = m.arch_role if m else ""
    insights = derive_fn(
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
        arch_role=arch_role,
    )
    if arch_role == "core":
        insights = rewrite_core_fn(insights)
    if insights:
        result["insights"] = insights_compact_fn(insights)[:3]

    # Risk profile (1 token)
    risk = classify_fn(
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

    # Git churn — single category label in compact mode
    if git_history and git_history.available:
        node_path = node.rel_path.replace("\\", "/")
        churn = git_history.files.get(node_path)
        if churn:
            result["churn"] = churn.churn_category

    # Related files — just paths in compact mode
    related = compute_related(module, graph, cycle_report)
    if related:
        result["related"] = [r["file"] for r in related]

    return result


def _build_full_context(
    *,
    module, node, m, graph, module_metrics, transitive,
    cycles, cycle_report, symbol_tables, config, git_history,
    insights_full_fn, derive_fn, classify_fn, rewrite_core_fn,
) -> dict:
    """Full-detail context for CLI, HTML renderers, and debugging.

    Preserves v0.5 format for backward compatibility with non-MCP consumers.
    """
    deps = _build_dependency_list(module, graph, compact=False)
    dependents = _build_dependent_list(module, graph)

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
            "raw_health": m.raw_health,
            "cyclomatic_complexity": m.cyclomatic_complexity,
            "cognitive_complexity": m.cognitive_complexity,
            "classes": m.class_count,
            "functions": m.function_count,
            "methods": m.method_count,
        }
        if m.parse_error:
            metrics_dict["parse_error"] = True
        if m.role != "source":
            metrics_dict["role"] = m.role
        if m.arch_role:
            metrics_dict["arch_role"] = m.arch_role
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
        ]

    # Symbol details (non-compact mode only)
    st = symbol_tables.get(module)
    if st:
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

    related = compute_related(module, graph, cycle_report)
    if related:
        result["related_files"] = related

    # Insights — full detail
    t = config.thresholds
    arch_role = m.arch_role if m else ""
    insights = derive_fn(
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
        arch_role=arch_role,
    )
    if arch_role == "core":
        insights = rewrite_core_fn(insights)
    if insights:
        result["insights"] = insights_full_fn(insights)

    risk = classify_fn(
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

    # Git churn (full detail in non-compact)
    if git_history and git_history.available:
        node_path = node.rel_path.replace("\\", "/")
        churn = git_history.files.get(node_path)
        if churn:
            result["git"] = {
                "commits": churn.commit_count,
                "lines_changed": churn.lines_changed,
                "days_since_change": churn.days_since_last_change,
                "churn": churn.churn_category,
                "contributors": churn.contributor_count,
                "last_changed": churn.last_changed,
            }

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
        if compact:
            file_contexts.append({
                "file": ctx["file"],
                "health": ctx.get("health", "unknown"),
                "cc": ctx.get("cc", 0),
                "risk": ctx.get("risk", ""),
            })
        else:
            file_contexts.append({
                "module": ctx.get("module", module),
                "language": ctx.get("language", "python"),
                "file": ctx["file"],
                "health": ctx.get("metrics", {}).get("health", "unknown"),
                "dependency_count": ctx.get("dependency_count", 0),
                "dependent_count": ctx.get("dependent_count", 0),
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
        shared = sorted(
            graph.nodes[d].rel_path
            for d, c in dep_counts.items()
            if c > 1 and d in graph.nodes
        )
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
