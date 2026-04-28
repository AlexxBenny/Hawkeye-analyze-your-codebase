"""Graphviz DOT format renderer.

Generates DOT files for rendering with Graphviz (dot, fdp, neato, etc.).
Supports clustering by package, HSL coloring by source file, and
cycle edge highlighting.
"""

import hashlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.graph import DependencyGraph
    from ..core.metrics import ModuleMetrics


def _module_hue(module_name: str, total_files: int) -> float:
    """Assign a consistent HSL hue based on the top-level package."""
    parts = module_name.split(".")
    # Color by the second-level package (first level is project name)
    key = ".".join(parts[:2]) if len(parts) > 1 else module_name
    h = int(hashlib.md5(key.encode()).hexdigest()[:8], 16)
    return (h % 360) / 360.0


def _health_color(health: str) -> str:
    """Map health status to a fill color."""
    return {
        "healthy": "#2d5a3d",
        "warning": "#7a6a2a",
        "critical": "#7a2a2a",
    }.get(health, "#333333")


def render_dot(
    graph: "DependencyGraph",
    module_metrics: dict[str, "ModuleMetrics"] | None = None,
    cluster: bool = True,
    colored: bool = True,
    rankdir: str = "TB",
    concentrate: bool = True,
) -> str:
    """Render the dependency graph as a Graphviz DOT string.

    Args:
        graph: The dependency graph.
        module_metrics: Optional metrics for node coloring/sizing.
        cluster: Whether to group nodes by package.
        colored: Whether to apply HSL coloring.
        rankdir: Graph direction (TB, BT, LR, RL).
        concentrate: Whether to merge bidirectional edges.
    """
    total = len(graph.nodes)
    lines: list[str] = []
    lines.append("digraph Hawkeye {")
    lines.append(f'    rankdir="{rankdir}";')
    lines.append(f'    concentrate={"true" if concentrate else "false"};')
    lines.append('    bgcolor="#1a1a2e";')
    lines.append('    node [shape=box, style="filled,rounded", fontname="Inter", fontsize=10];')
    lines.append('    edge [color="#555577", fontname="Inter", fontsize=8];')
    lines.append("")

    # Group nodes by package for clustering
    packages: dict[str, list[str]] = {}
    for name, node in graph.nodes.items():
        pkg = node.package or graph.project_name
        packages.setdefault(pkg, []).append(name)

    def render_node(name: str) -> str:
        """Generate a DOT node definition."""
        node = graph.nodes[name]
        label = name.split(".")[-1]  # Short name
        tooltip = f"{name}\\n{node.rel_path}\\nLang: {node.language}\\nLOC: {node.loc}"

        if colored:
            hue = _module_hue(name, total)
            lightness = max(0.3, 0.7 - node.depth * 0.08)
            fill_color = f"{hue:.3f} 0.5 {lightness:.2f}"
            font_color = "white"
        else:
            fill_color = "0.0 0.0 0.95"
            font_color = "black"

        if module_metrics and name in module_metrics:
            m = module_metrics[name]
            label += f"\\n({m.ca}/{m.ce})"
            fill_color_override = _health_color(m.health)
            return (
                f'    "{name}" [label="{label}", tooltip="{tooltip}", '
                f'fillcolor="{fill_color_override}", fontcolor="{font_color}"];'
            )

        return (
            f'    "{name}" [label="{label}", tooltip="{tooltip}", '
            f'fillcolor="{fill_color}", fontcolor="{font_color}"];'
        )

    if cluster:
        for pkg, members in sorted(packages.items()):
            cluster_id = pkg.replace(".", "_")
            pkg_label = pkg.split(".")[-1]
            lines.append(f'    subgraph cluster_{cluster_id} {{')
            lines.append(f'        label="{pkg_label}";')
            lines.append('        style="rounded,dashed";')
            lines.append('        color="#444466";')
            lines.append('        fontcolor="#8888aa";')
            lines.append('        fontname="Inter";')
            for member in sorted(members):
                lines.append(f"    {render_node(member)}")
            lines.append("    }")
            lines.append("")
    else:
        for name in sorted(graph.nodes):
            lines.append(render_node(name))
        lines.append("")

    # Edges
    for (src, tgt), edge in sorted(graph.edges.items()):
        attrs: list[str] = []
        if edge.is_cycle_member:
            attrs.append('color="#ff4444"')
            attrs.append("penwidth=2.0")
        else:
            attrs.append('color="#555577"')

        if edge.import_count > 1:
            attrs.append(f'label="{edge.import_count}"')

        attr_str = f" [{', '.join(attrs)}]" if attrs else ""
        lines.append(f'    "{src}" -> "{tgt}"{attr_str};')

    lines.append("}")
    return "\n".join(lines)
