"""Core analysis pipeline — scanner, analyzer, graph, metrics, cycles, rules.

Re-exports key types so other packages can import from hawkeye.core directly.
"""

from .scanner import ModuleInfo, scan_project
from .analyzer import ResolvedImport, analyze_project
from .graph import DependencyGraph
from .metrics import (
    ModuleMetrics, ProjectMetrics,
    calculate_module_metrics, calculate_project_metrics,
    format_metrics_table,
)
from .cycles import CycleReport, detect_cycles
from .rules import Violation, check_all_rules

__all__ = [
    "ModuleInfo", "scan_project",
    "ResolvedImport", "analyze_project",
    "DependencyGraph",
    "ModuleMetrics", "ProjectMetrics",
    "calculate_module_metrics", "calculate_project_metrics",
    "format_metrics_table",
    "CycleReport", "detect_cycles",
    "Violation", "check_all_rules",
]
