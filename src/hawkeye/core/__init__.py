"""Core analysis pipeline — scanner, analyzer, graph, metrics, cycles, rules, symbols, insights.

Re-exports key types so other packages can import from hawkeye.core directly.
"""

from .analyzer import ResolvedImport, SymbolInfo, SymbolTable, analyze_project
from .cycles import CycleReport, detect_cycles
from .graph import DependencyGraph
from .insights import (Insight, classify_risk, derive_module_insights,
                       insights_compact, insights_full)
from .metrics import (ModuleMetrics, ProjectMetrics, calculate_module_metrics,
                      calculate_project_metrics, format_metrics_table,
                      sort_metrics)
from .models import ModuleInfo
from .rules import Violation, check_all_rules
from .scanner import scan_project
from .symbols import (SymbolGraph, SymbolReference, SymbolRegistry,
                      resolve_references)

__all__ = [
    "ModuleInfo", "scan_project",
    "ResolvedImport", "SymbolInfo", "SymbolTable", "analyze_project",
    "DependencyGraph",
    "ModuleMetrics", "ProjectMetrics",
    "calculate_module_metrics", "calculate_project_metrics",
    "format_metrics_table", "sort_metrics",
    "CycleReport", "detect_cycles",
    "Violation", "check_all_rules",
    "Insight", "classify_risk", "derive_module_insights",
    "insights_compact", "insights_full",
    "SymbolRegistry", "SymbolGraph", "SymbolReference",
    "resolve_references",
]
