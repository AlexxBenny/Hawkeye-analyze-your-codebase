"""Plain-text renderer for terminal and AI agent consumption.

Produces structured, scannable text output including dependency trees,
metrics tables, and cycle reports. Designed to be both human-readable
and parseable by AI coding agents.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.cycles import CycleReport
    from ..core.graph import DependencyGraph
    from ..core.metrics import ModuleMetrics, ProjectMetrics


def render_dependency_tree(graph: "DependencyGraph") -> str:
    """Render the full dependency graph as an indented tree."""
    lines: list[str] = []
    lines.append(f"=== DEPENDENCY GRAPH: {graph.project_name} ===")
    lines.append(f"    Modules: {len(graph.nodes)} | Edges: {len(graph.edges)}")
    lines.append("")

    for module in sorted(graph.nodes):
        deps = sorted(graph.adjacency.get(module, set()))
        dependents = sorted(graph.reverse_adj.get(module, set()))
        node = graph.nodes[module]

        lines.append(f"📦 {module}")
        lines.append(f"   File: {node.rel_path}  |  LOC: {node.loc}  |  Lang: {node.language}")

        if deps:
            lines.append(f"   Imports ({len(deps)}):")
            for dep in deps:
                edge = graph.edges.get((module, dep))
                cycle_mark = " 🔄" if edge and edge.is_cycle_member else ""
                lines.append(f"     → {dep}{cycle_mark}")

        if dependents:
            lines.append(f"   Imported by ({len(dependents)}):")
            for dep in dependents:
                lines.append(f"     ← {dep}")

        lines.append("")

    return "\n".join(lines)


def render_module_info(
    module: str,
    graph: "DependencyGraph",
    metrics: dict[str, "ModuleMetrics"],
) -> str:
    """Render detailed information about a single module."""
    if module not in graph.nodes:
        return f"Module '{module}' not found in the graph."

    node = graph.nodes[module]
    deps = sorted(graph.adjacency.get(module, set()))
    dependents = sorted(graph.reverse_adj.get(module, set()))
    m = metrics.get(module)

    lines = [
        f"=== MODULE: {module} ===",
        f"File:       {node.rel_path}",
        f"Package:    {node.package}",
        f"Is package: {node.is_package}",
        f"LOC:        {node.loc}",
        f"Depth:      {node.depth}",
        f"Language:   {node.language}",
    ]

    if m:
        lines.extend([
            "",
            "── Metrics ──",
            f"Afferent coupling (Ca):  {m.ca}",
            f"Efferent coupling (Ce):  {m.ce}",
            f"Instability:             {m.instability:.3f}",
            f"Cyclomatic complexity:    {m.cyclomatic_complexity}",
            f"Cognitive complexity:     {m.cognitive_complexity}",
            f"Abstractness:            {m.abstractness:.3f}",
            f"Distance (main seq):     {m.distance_main_seq:.3f}",
            f"Health:                  {m.health} {m.health_emoji}",
        ])

    lines.extend(["", f"── Dependencies ({len(deps)}) ──"])
    for dep in deps:
        edge = graph.edges.get((module, dep))
        info = ""
        if edge:
            info = f" (lines: {', '.join(str(l) for l in edge.lines[:5])})"
        lines.append(f"  → {dep}{info}")

    lines.extend(["", f"── Dependents ({len(dependents)}) ──"])
    for dep in dependents:
        lines.append(f"  ← {dep}")

    return "\n".join(lines)


def render_cycle_report(report: "CycleReport") -> str:
    """Render cycle detection results."""
    lines: list[str] = []

    if not report.has_cycles:
        lines.append("✅ No import cycles detected.")
        return "\n".join(lines)

    lines.append(f"🔄 Found {report.cycle_count} import cycle(s):")
    lines.append("")

    for i, cycle in enumerate(report.cycles, 1):
        lines.append(f"  Cycle {i} (length {cycle.length}):")
        lines.append(f"    {cycle}")
        lines.append("")

    if report.participation:
        lines.append("── Cycle participation ──")
        ranked = sorted(report.participation.items(), key=lambda x: x[1], reverse=True)
        for module, count in ranked:
            lines.append(f"  {module}: involved in {count} cycle(s)")

    return "\n".join(lines)


def render_impact_analysis(
    module: str,
    graph: "DependencyGraph",
) -> str:
    """Render impact analysis for a module change."""
    if module not in graph.nodes:
        return f"Module '{module}' not found."

    direct = sorted(graph.get_dependents(module))
    transitive = sorted(graph.get_transitive_dependents(module))
    transitive_only = sorted(set(transitive) - set(direct) - {module})

    lines = [
        f"=== IMPACT ANALYSIS: {module} ===",
        f"If this module changes:",
        "",
        f"── Direct dependents ({len(direct)}) ──",
    ]
    for dep in direct:
        lines.append(f"  ⚡ {dep}")

    lines.extend([
        "",
        f"── Transitive dependents ({len(transitive_only)}) ──",
    ])
    for dep in transitive_only:
        lines.append(f"  ↗ {dep}")

    lines.extend([
        "",
        f"Total affected: {len(transitive)} module(s)",
    ])

    return "\n".join(lines)


def render_project_summary(
    graph: "DependencyGraph",
    project_metrics: "ProjectMetrics",
    module_metrics: dict[str, "ModuleMetrics"],
) -> str:
    """Render a comprehensive project summary."""
    from ..core.metrics import format_metrics_table

    pm = project_metrics
    lines = [
        f"=== PROJECT SUMMARY: {graph.project_name} ===",
        "",
        f"  Modules:          {pm.total_modules}",
        f"  Dependencies:     {pm.total_edges}",
        f"  Total LOC:        {pm.total_loc}",
        f"  Graph density:    {pm.density:.4f}",
        f"  Avg instability:  {pm.avg_instability:.3f}",
        f"  Max instability:  {pm.max_instability:.3f}",
        f"  Has cycles:       {'Yes 🔄' if pm.has_cycles else 'No ✅'}",
        "",
        f"  Health breakdown:",
        f"    ✅ Healthy:     {pm.modules_healthy}",
        f"    🟡 Moderate:    {pm.modules_moderate}",
        f"    🟠 Elevated:    {pm.modules_elevated}",
        f"    🔴 High:        {pm.modules_high}",
        f"    🔥 Critical:    {pm.modules_critical}",
        *([ f"    ❓ Unknown:     {pm.modules_unknown}"] if pm.modules_unknown else []),
        "",
        "── Module Metrics ──",
        format_metrics_table(module_metrics),
    ]

    return "\n".join(lines)
