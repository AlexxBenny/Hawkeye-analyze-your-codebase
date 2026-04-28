"""JSON renderer for programmatic consumption.

Exports the full dependency graph, metrics, and cycle data as structured
JSON — ideal for piping into other tools, dashboards, or AI agents.
"""

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..core.cycles import CycleReport
    from ..core.graph import DependencyGraph
    from ..core.metrics import ModuleMetrics, ProjectMetrics


def render_json(
    graph: "DependencyGraph",
    module_metrics: dict[str, "ModuleMetrics"] | None = None,
    project_metrics: "ProjectMetrics | None" = None,
    cycle_report: "CycleReport | None" = None,
    indent: int = 2,
) -> str:
    """Render the complete analysis as a JSON string."""
    data: dict[str, Any] = graph.to_dict()

    # Enrich nodes with metrics
    if module_metrics:
        for node in data["nodes"]:
            m = module_metrics.get(node["id"])
            if m:
                node["metrics"] = m.to_dict()

    # Add project-level metrics
    if project_metrics:
        data["project_metrics"] = {
            "total_modules": project_metrics.total_modules,
            "total_edges": project_metrics.total_edges,
            "total_loc": project_metrics.total_loc,
            "avg_instability": project_metrics.avg_instability,
            "max_instability": project_metrics.max_instability,
            "density": project_metrics.density,
            "has_cycles": project_metrics.has_cycles,
            "modules_healthy": project_metrics.modules_healthy,
            "modules_warning": project_metrics.modules_warning,
            "modules_critical": project_metrics.modules_critical,
        }

    # Add cycle information
    if cycle_report:
        data["cycles"] = {
            "has_cycles": cycle_report.has_cycles,
            "count": cycle_report.cycle_count,
            "cycles": [
                {"path": c.path, "length": c.length}
                for c in cycle_report.cycles
            ],
            "participation": cycle_report.participation,
        }

    return json.dumps(data, indent=indent, ensure_ascii=False)
