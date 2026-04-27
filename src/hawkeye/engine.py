"""Core analysis engine — orchestrates scanning, analysis, graph building, and metrics.

Provides a single HawkeyeEngine class that ties together all subsystems,
caches results for efficient repeated queries, and supports incremental
re-analysis via file content hashing.
"""

import hashlib
from pathlib import Path
from typing import Optional

from .config import HawkeyeConfig
from .core import (
    ModuleInfo, scan_project,
    ResolvedImport, analyze_project,
    DependencyGraph,
    ModuleMetrics, ProjectMetrics,
    calculate_module_metrics, calculate_project_metrics,
    CycleReport, detect_cycles,
    Violation, check_all_rules,
    SymbolRegistry, SymbolGraph, SymbolReference,
    resolve_references,
    derive_module_insights, insights_compact, insights_full,
    classify_risk,
)
from .core.analyzer import SymbolTable


def _hash_file(path: str) -> str:
    """Compute MD5 hash of a file's contents for change detection."""
    try:
        with open(path, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()
    except OSError:
        return ""


class HawkeyeEngine:
    """Central analysis engine with caching and file-path resolution.

    Designed to be instantiated once per project and queried many times
    (by the MCP server, CLI, or programmatically).
    """

    def __init__(self, config: Optional[HawkeyeConfig] = None) -> None:
        self.config = config or HawkeyeConfig()
        self._file_index: dict[str, ModuleInfo] | None = None
        self._analysis: dict[str, list[ResolvedImport]] | None = None
        self._graph: DependencyGraph | None = None
        self._module_metrics: dict[str, ModuleMetrics] | None = None
        self._project_metrics: ProjectMetrics | None = None
        self._cycle_report: CycleReport | None = None
        self._violations: list[Violation] | None = None
        self._symbol_registry: SymbolRegistry | None = None
        self._symbol_graph: SymbolGraph | None = None
        self._symbol_refs: list[SymbolReference] | None = None
        self._project_name: str = ""
        self._project_root: str = ""
        # Reverse lookups: file path → module name
        self._path_index: dict[str, str] = {}
        # File hashes for incremental analysis
        self._file_hashes: dict[str, str] = {}
        self._symbol_tables: dict[str, SymbolTable] = {}

    # ── Analysis Pipeline ──────────────────────────────────────

    def analyze(self, project_path: Optional[str] = None) -> "DependencyGraph":
        """Run the full analysis pipeline. Returns the dependency graph."""
        path = project_path or self.config.project_path
        root = Path(path).resolve()
        self._project_root = str(root)
        self._project_name = self.config.project_name or root.name

        # 1. Scan
        self._file_index = scan_project(
            str(root),
            exclude_dirs=self.config.exclude_dirs,
            exclude_patterns=self.config.exclude_patterns,
            include_patterns=self.config.include_patterns,
        )

        # 2. Build path index (file path → module name)
        self._path_index.clear()
        for name, info in self._file_index.items():
            self._path_index[info.rel_path.replace("\\", "/")] = name
            self._path_index[info.full_path.replace("\\", "/")] = name
            # Also index with backslashes for Windows
            self._path_index[info.rel_path] = name
            self._path_index[info.full_path] = name

        # 3. Compute file hashes for future incremental analysis
        self._file_hashes = {
            name: _hash_file(info.full_path)
            for name, info in self._file_index.items()
        }

        # 4. Analyze imports + symbols in single AST pass
        self._analysis, self._symbol_tables = analyze_project(
            self._file_index, self._project_name
        )

        # 5. Build module-level graph
        self._graph = DependencyGraph.build(
            self._file_index, self._analysis, self._project_name
        )

        # 6. Build symbol registry + resolve cross-file references
        self._symbol_registry = SymbolRegistry.build(self._symbol_tables)
        self._symbol_refs = resolve_references(
            self._analysis, self._symbol_registry
        )
        self._symbol_graph = SymbolGraph.build(
            self._symbol_registry, self._symbol_refs
        )

        # 7. Detect cycles (also marks edges)
        self._cycle_report = detect_cycles(self._graph)

        # 8. Compute metrics (with symbol data for complexity)
        self._module_metrics = calculate_module_metrics(
            self._graph, self._symbol_tables
        )
        self._project_metrics = calculate_project_metrics(
            self._graph, self._module_metrics,
            has_cycles=self._cycle_report.has_cycles,
        )

        # 9. Check architecture rules
        self._violations = check_all_rules(self._graph, self.config.rules)

        return self._graph

    def refresh(self) -> list[str]:
        """Incremental re-analysis: only re-parse files that changed.

        Returns list of module names that were re-analyzed.
        """
        if self._file_index is None:
            self.analyze()
            return list(self._file_index.keys()) if self._file_index else []

        changed: list[str] = []
        for name, info in self._file_index.items():
            new_hash = _hash_file(info.full_path)
            if new_hash != self._file_hashes.get(name, ""):
                changed.append(name)
                self._file_hashes[name] = new_hash

        if changed:
            # Re-run full analysis (incremental graph update is complex;
            # full re-analysis is fast enough for most projects)
            self.analyze(self._project_root)

        return changed

    # ── Properties ─────────────────────────────────────────────

    @property
    def graph(self) -> DependencyGraph:
        if self._graph is None:
            raise RuntimeError("Call analyze() first.")
        return self._graph

    @property
    def file_index(self) -> dict[str, ModuleInfo]:
        if self._file_index is None:
            raise RuntimeError("Call analyze() first.")
        return self._file_index

    @property
    def module_metrics(self) -> dict[str, ModuleMetrics]:
        if self._module_metrics is None:
            raise RuntimeError("Call analyze() first.")
        return self._module_metrics

    @property
    def project_metrics(self) -> ProjectMetrics:
        if self._project_metrics is None:
            raise RuntimeError("Call analyze() first.")
        return self._project_metrics

    @property
    def cycle_report(self) -> CycleReport:
        if self._cycle_report is None:
            raise RuntimeError("Call analyze() first.")
        return self._cycle_report

    @property
    def violations(self) -> list[Violation]:
        if self._violations is None:
            raise RuntimeError("Call analyze() first.")
        return self._violations

    @property
    def symbol_registry(self) -> SymbolRegistry:
        if self._symbol_registry is None:
            raise RuntimeError("Call analyze() first.")
        return self._symbol_registry

    @property
    def symbol_graph(self) -> SymbolGraph:
        if self._symbol_graph is None:
            raise RuntimeError("Call analyze() first.")
        return self._symbol_graph

    @property
    def symbol_refs(self) -> list[SymbolReference]:
        if self._symbol_refs is None:
            raise RuntimeError("Call analyze() first.")
        return self._symbol_refs

    @property
    def project_name(self) -> str:
        return self._project_name

    # ── File/Module Resolution ─────────────────────────────────

    def resolve(self, file_or_module: str) -> str | None:
        """Resolve a file path OR module name to a canonical module name.

        Accepts:
          - Module name: 'MERLIN.cortex.intent_engine'
          - Relative path: 'cortex/intent_engine.py'
          - Absolute path: 'D:/ALEX/CODING/MERLIN/cortex/intent_engine.py'
          - Windows paths: 'cortex\\intent_engine.py'

        Returns the module name, or None if not found.
        """
        # Direct module name match
        if file_or_module in self.graph.nodes:
            return file_or_module

        # Path-based lookup
        normalized = file_or_module.replace("\\", "/")
        if normalized in self._path_index:
            return self._path_index[normalized]

        # Try stripping project root prefix
        if self._project_root:
            root_prefix = self._project_root.replace("\\", "/") + "/"
            if normalized.startswith(root_prefix):
                rel = normalized[len(root_prefix):]
                if rel in self._path_index:
                    return self._path_index[rel]

        # Fuzzy: try adding .py, removing .py, etc.
        for variant in [normalized, normalized + ".py",
                        normalized.removesuffix(".py")]:
            if variant in self._path_index:
                return self._path_index[variant]

        return None

    # ── Unified Context (THE key method) ───────────────────────

    def get_file_context(self, file_or_module: str, compact: bool = True) -> dict | None:
        """Get everything an AI agent needs about a file in ONE call.

        Combines: module info + dependencies + dependents + impact +
        cycle warnings + health metrics + related files.

        Args:
            file_or_module: File path or dotted module name.
            compact: If True, trim verbose fields for token efficiency.

        Returns:
            Complete context dict, or None if not found.
        """
        module = self.resolve(file_or_module)
        if module is None:
            return None

        node = self.graph.nodes[module]
        m = self.module_metrics.get(module)

        # Dependencies (what this module imports)
        deps = []
        for dep in sorted(self.graph.get_dependencies(module)):
            edge = self.graph.edges.get((module, dep))
            dep_node = self.graph.nodes.get(dep)
            entry: dict = {"module": dep}
            if dep_node:
                entry["file"] = dep_node.rel_path
            if edge and edge.is_cycle_member:
                entry["is_cycle"] = True
            if not compact and edge:
                entry["import_count"] = edge.import_count
                entry["lines"] = edge.lines
            deps.append(entry)

        # Dependents (what imports this module)
        dependents = []
        for dep in sorted(self.graph.get_dependents(module)):
            dep_node = self.graph.nodes.get(dep)
            entry = {"module": dep}
            if dep_node:
                entry["file"] = dep_node.rel_path
            dependents.append(entry)

        # Transitive impact
        transitive = self.graph.get_transitive_dependents(module)

        # Cycles involving this module
        cycles = []
        for c in self.cycle_report.cycles:
            if module in c.path[:-1]:  # path repeats first node at end
                cycles.append(c.path)

        # Related files: cycle partners + shared-dependency neighbors
        related = self._compute_related(module)

        result: dict = {
            "module": module,
            "file": node.rel_path,
            "loc": node.loc,
            "package": node.package,
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
            result["metrics"] = {
                "ca": m.ca, "ce": m.ce,
                "instability": m.instability,
                "health": m.health,
                "cyclomatic_complexity": m.cyclomatic_complexity,
                "cognitive_complexity": m.cognitive_complexity,
                "classes": m.class_count,
                "functions": m.function_count,
                "methods": m.method_count,
            }

        if cycles:
            result["cycles"] = [
                {"path": c, "severity": cyc.severity, "break_at": cyc.break_suggestion}
                for c in cycles
                for cyc in self.cycle_report.cycles
                if cyc.path == c
            ] if not compact else cycles

        # Symbol details (non-compact mode)
        st = self._symbol_tables.get(module)
        if st and not compact:
            result["symbols"] = {
                "classes": [{"name": s.name, "line": s.line, "methods": s.method_count, "complexity": s.complexity} for s in st.classes],
                "functions": [{"name": s.name, "line": s.line, "complexity": s.complexity} for s in st.functions],
            }

        if related:
            result["related_files"] = related

        # ── Layer 2: Deterministic insights ────────────────
        transitive = self.graph.get_transitive_dependents(module)
        cycle_modules = [
            c for c in self.cycle_report.cycles
            if module in c.path[:-1]
        ]
        insights = derive_module_insights(
            instability=m.instability if m else 0.0,
            ca=m.ca if m else 0,
            ce=m.ce if m else 0,
            cyclomatic=m.cyclomatic_complexity if m else 1,
            cognitive=m.cognitive_complexity if m else 0,
            loc=node.loc,
            direct_dependents=len(dependents),
            transitive_dependents=len(transitive),
            cycle_count=len(cycle_modules),
            max_cycle_size=max((len(c.path) - 1 for c in cycle_modules), default=0),
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
            cycle_count=len(cycle_modules),
        )
        if risk:
            result["risk"] = risk

        return result

    def get_batch_context(self, files: list[str], compact: bool = True) -> dict:
        """Get combined context for multiple files being edited together.

        Returns a unified briefing with shared dependencies, combined
        blast radius, and cross-file warnings.
        """
        modules = []
        not_found = []
        for f in files:
            m = self.resolve(f)
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
            ctx = self.get_file_context(module, compact=compact)
            if ctx:
                file_contexts.append({
                    "module": ctx["module"],
                    "file": ctx["file"],
                    "health": ctx.get("metrics", {}).get("health", "unknown"),
                    "dependency_count": ctx["dependency_count"],
                    "dependent_count": ctx["dependent_count"],
                })
                all_deps |= self.graph.get_dependencies(module)
                all_dependents |= self.graph.get_dependents(module)
                all_transitive |= self.graph.get_transitive_dependents(module)

        # Remove the files themselves from impact counts
        module_set = set(modules)
        all_deps -= module_set
        all_dependents -= module_set
        all_transitive -= module_set

        # Shared dependencies (deps imported by 2+ of the files)
        if len(modules) > 1:
            dep_counts: dict[str, int] = {}
            for module in modules:
                for dep in self.graph.get_dependencies(module):
                    dep_counts[dep] = dep_counts.get(dep, 0) + 1
            shared = sorted(d for d, c in dep_counts.items() if c > 1)
        else:
            shared = []

        # Cycle warnings
        cycle_warnings = []
        for c in self.cycle_report.cycles:
            cycle_modules = set(c.path[:-1])
            if cycle_modules & module_set:
                cycle_warnings.append(c.path)

        # Architecture violations involving these modules
        violations = [
            str(v) for v in self.violations
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
        if violations:
            result["violations"] = violations
        if not_found:
            result["not_found"] = not_found

        return result

    # ── Query Methods ──────────────────────────────────────────

    def find_modules(self, pattern: str) -> list[str]:
        """Search for modules matching a pattern (case-insensitive)."""
        import fnmatch
        return sorted(
            name for name in self.graph.nodes
            if fnmatch.fnmatch(name, f"*{pattern}*")
            or pattern.lower() in name.lower()
        )

    def get_path(self, source: str, target: str) -> list[str] | None:
        """Find shortest dependency path between two modules."""
        # Accept file paths too
        src = self.resolve(source) or source
        tgt = self.resolve(target) or target
        return self.graph.find_path(src, tgt)

    # ── Internal Helpers ───────────────────────────────────────

    def _compute_related(self, module: str, limit: int = 8) -> list[dict]:
        """Find files related to a module (cycle partners, frequent co-deps)."""
        related: dict[str, str] = {}  # module -> reason

        # Cycle partners
        for c in self.cycle_report.cycles:
            if module in c.path[:-1]:
                for m in c.path[:-1]:
                    if m != module and m not in related:
                        related[m] = "cycle partner"

        # Modules that share many of the same dependents (co-imported)
        my_dependents = self.graph.get_dependents(module)
        if my_dependents:
            for dep in self.graph.get_dependencies(module):
                dep_dependents = self.graph.get_dependents(dep)
                overlap = my_dependents & dep_dependents
                if len(overlap) > 1 and dep not in related:
                    related[dep] = "shared dependency"

        result = []
        for m, reason in list(related.items())[:limit]:
            node = self.graph.nodes.get(m)
            if node:
                result.append({"file": node.rel_path, "module": m, "reason": reason})

        return result
