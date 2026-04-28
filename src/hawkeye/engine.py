"""Core analysis engine — orchestrates scanning, analysis, graph building, and metrics.

Provides a single HawkeyeEngine class that ties together all subsystems,
caches results for efficient repeated queries, and supports incremental
re-analysis via file content hashing.
"""

import hashlib
import os
from pathlib import Path
from typing import Optional

from .config import HawkeyeConfig
from .core import (CycleReport, DependencyGraph, ModuleInfo, ModuleMetrics,
                   ProjectMetrics, ResolvedImport, SymbolGraph,
                   SymbolReference, SymbolRegistry, Violation,
                   calculate_module_metrics, calculate_project_metrics,
                   check_all_rules, detect_cycles,
                   resolve_references, scan_project)
from .core.analyzer import SymbolTable
from .languages.registry import analyze_project as analyze_languages
from .languages.registry import get_language_adapters


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
        self._language_adapters: dict[str, object] = {}
        self._known_extensions: set[str] = set()

    # ── Analysis Pipeline ──────────────────────────────────────

    def analyze(self, project_path: Optional[str] = None) -> "DependencyGraph":
        """Run the full analysis pipeline. Returns the dependency graph."""
        path = project_path or self.config.project_path
        root = Path(path).resolve()
        self._project_root = str(root)
        self._project_name = self.config.project_name or root.name

        # 1. Scan
        self._language_adapters = get_language_adapters(
            self.config.languages, self.config.language_settings
        )
        self._file_index = scan_project(
            str(root),
            exclude_dirs=self.config.exclude_dirs,
            exclude_patterns=self.config.exclude_patterns,
            include_patterns=self.config.include_patterns,
            adapters=self._language_adapters,
        )

        # 2. Build path index (file path → module name)
        self._path_index.clear()
        for name, info in self._file_index.items():
            self._path_index[info.rel_path.replace("\\", "/")] = name
            self._path_index[info.full_path.replace("\\", "/")] = name
            rel_no_ext = os.path.splitext(info.rel_path.replace("\\", "/"))[0]
            full_no_ext = os.path.splitext(info.full_path.replace("\\", "/"))[0]
            self._path_index[rel_no_ext] = name
            self._path_index[full_no_ext] = name
            if Path(info.rel_path).stem == "index":
                rel_dir = str(Path(info.rel_path).parent).replace("\\", "/")
                full_dir = str(Path(info.full_path).parent).replace("\\", "/")
                self._path_index[rel_dir] = name
                self._path_index[full_dir] = name
            # Also index with backslashes for Windows
            self._path_index[info.rel_path] = name
            self._path_index[info.full_path] = name

        # 3. Compute file hashes for future incremental analysis
        self._file_hashes = {
            name: _hash_file(info.full_path)
            for name, info in self._file_index.items()
        }
        self._known_extensions = {
            Path(info.rel_path).suffix.lower()
            for info in self._file_index.values()
            if Path(info.rel_path).suffix
        }

        # 4. Analyze imports + symbols in single AST pass
        self._analysis, self._symbol_tables = analyze_languages(
            self._file_index, self._project_name, self._project_root,
            self._language_adapters,
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
            self._graph, self._symbol_tables,
            thresholds=self.config.thresholds,
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

        Accepts (in priority order):
          - Module name: 'MERLIN.cortex.intent_engine'
          - Relative path: 'cortex/intent_engine.py'
          - Full relative: 'src/MERLIN/cortex/intent_engine.py'
          - Absolute path: 'D:/ALEX/CODING/MERLIN/cortex/intent_engine.py'
          - Windows paths: 'cortex\\intent_engine.py'
          - Basename: 'intent_engine.py' (returns first unique match)

        Returns the module name, or None if not found.
        """
        # 1. Direct module name match
        if file_or_module in self.graph.nodes:
            return file_or_module

        # 2. Path-based lookup (exact)
        normalized = file_or_module.replace("\\", "/")
        if normalized in self._path_index:
            return self._path_index[normalized]

        # 3. Try stripping project root prefix
        if self._project_root:
            root_prefix = self._project_root.replace("\\", "/") + "/"
            if normalized.startswith(root_prefix):
                rel = normalized[len(root_prefix):]
                if rel in self._path_index:
                    return self._path_index[rel]

        # 4. Fuzzy extension variants
        variants = [normalized]
        for ext in sorted(self._known_extensions or {".py"}):
            variants.append(normalized + ext)
            if normalized.endswith(ext):
                variants.append(normalized.removesuffix(ext))
        for variant in variants:
            if variant in self._path_index:
                return self._path_index[variant]

        # 5. Suffix match: AI agents often pass workspace-relative paths
        #    like "src/hawkeye/core/analyzer.py" when project root is
        #    "src/hawkeye" — try matching the suffix of each indexed path.
        for indexed_path, module_name in self._path_index.items():
            if normalized.endswith("/" + indexed_path) or normalized.endswith("\\" + indexed_path):
                return module_name

        # 6. Basename match: "analyzer.py" → look for unique match
        basename = normalized.rsplit("/", 1)[-1]
        if basename != normalized:  # only if we actually extracted a basename
            matches = [
                mod for path, mod in self._path_index.items()
                if path.endswith("/" + basename) or path == basename
            ]
            if len(set(matches)) == 1:
                return matches[0]
        else:
            # Input itself is a basename like "analyzer.py"
            matches = [
                mod for path, mod in self._path_index.items()
                if path.endswith("/" + basename) or path == basename
            ]
            if len(set(matches)) == 1:
                return matches[0]

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
        from .context import build_file_context

        module = self.resolve(file_or_module)
        if module is None:
            return None

        return build_file_context(
            module=module,
            graph=self.graph,
            module_metrics=self.module_metrics,
            cycle_report=self.cycle_report,
            symbol_tables=self._symbol_tables,
            config=self.config,
            compact=compact,
        )

    def get_batch_context(self, files: list[str], compact: bool = True) -> dict:
        """Get combined context for multiple files being edited together.

        Returns a unified briefing with shared dependencies, combined
        blast radius, and cross-file warnings.
        """
        from .context import build_batch_context

        return build_batch_context(
            files=files,
            resolve_fn=self.resolve,
            graph=self.graph,
            cycle_report=self.cycle_report,
            violations=self.violations,
            module_metrics=self.module_metrics,
            symbol_tables=self._symbol_tables,
            config=self.config,
            compact=compact,
        )

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

