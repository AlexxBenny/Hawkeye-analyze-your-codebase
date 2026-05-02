"""MCP (Model Context Protocol) server for AI coding agents.

Exposes Hawkeye's analysis as MCP tools optimized for AI editors.
The key tool is `hawkeye_file_context` — one call that gives an agent
everything it needs before editing a file.

Usage:
    python -m hawkeye.mcp_server                # stdio transport
    python -m hawkeye.mcp_server --project .    # pre-analyze on startup
"""

import argparse
import json
import sys

# ── Engine cache ────────────────────────────────────────────────

_engine = None
_analyzed_projects: dict[str, object] = {}

_TOOL_ANNOTATIONS_READONLY = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}


def _get_engine():
    """Lazy-initialize the engine singleton."""
    global _engine
    if _engine is None:
        from ..engine import HawkeyeEngine
        _engine = HawkeyeEngine()
    return _engine


def _resolve_engine(project_path: str = ""):
    """Get the engine for a project, auto-analyzing if needed."""
    if project_path and project_path in _analyzed_projects:
        return _analyzed_projects[project_path]
    engine = _get_engine()
    if engine._graph is None:
        if project_path:
            engine.analyze(project_path)
            _analyzed_projects[project_path] = engine
        else:
            raise RuntimeError(
                "No project analyzed yet. Call hawkeye_analyze(project_path) first."
            )
    return engine



def _to_path(engine: "HawkeyeEngine", module: str) -> str:
    """Convert FQDN module name to file path for consistent MCP output."""
    node = engine.graph.nodes.get(module)
    return node.rel_path if node else module


# ── MCP Server ──────────────────────────────────────────────────

def create_mcp_server():
    """Create the MCP server with 10 consolidated tools."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        print(
            "ERROR: MCP server requires the 'mcp' package.\n"
            "Install with: pip install mcp\n",
            file=sys.stderr,
        )
        sys.exit(1)

    mcp = FastMCP(
        "hawkeye",
        instructions=(
            "Hawkeye provides architectural context for Python/JS/TS codebases.\n"
            "BEFORE editing ANY file, call hawkeye_file_context(file) to check:\n"
            "- How many modules depend on it (blast radius via edit_cost.files)\n"
            "- Its health and risk classification\n"
            "- Whether it participates in import cycles\n"
            "If risk='hub' WITHOUT arch_role: make minimal changes only.\n"
            "If risk='hub' WITH arch_role='core': this is central by design —\n"
            "  changes ARE expected, but verify interfaces with hawkeye_impact().\n"
            "If health='critical' on role='test': normal — test files have high CC.\n"
            "If health='critical' on role='source': prefer surgical changes.\n"
            "Call hawkeye_analyze(project_path) once at session start.\n"
            "For multi-file edits: hawkeye_context(files) gives combined blast radius.\n"
            "Before renaming symbols: hawkeye_impact(file, symbol) shows what breaks.\n"
            "After adding imports: hawkeye_cycles() verifies no circular deps introduced.\n"
            "hawkeye_hotspots ranks files by complexity x git churn (real risk).\n"
            "All tools default to compact=True for token efficiency.\n"
            "Compact schema: v0.6 (flat file paths, top-level metrics, edit_cost)."
        ),
    )

    # ── 1. Analyze ─────────────────────────────────────────────

    @mcp.tool(annotations=_TOOL_ANNOTATIONS_READONLY)
    def hawkeye_analyze(
        project_path: str,
        languages: list[str] | None = None,
        tsconfig: str = "",
    ) -> dict[str, object]:
        """Scan a codebase and build its dependency graph.

        Call this first before using any other tool. Scans Python, JavaScript,
        and TypeScript files, resolves imports, detects cycles, and computes
        coupling metrics.

        Args:
            project_path: Absolute path to the project root.
            languages: Languages to enable (default: ['python']). Options: 'python', 'javascript', 'typescript'.
            tsconfig: Optional path to tsconfig.json for TypeScript path alias resolution.
        """
        from ..config import HawkeyeConfig, LanguageSettings
        from ..engine import HawkeyeEngine
        config = HawkeyeConfig()
        if languages:
            config.languages = languages
        if tsconfig:
            config.language_settings.setdefault(
                "typescript", LanguageSettings()
            ).tsconfig = tsconfig
        engine = HawkeyeEngine(config)
        engine.analyze(project_path)

        _analyzed_projects[project_path] = engine
        global _engine
        _engine = engine

        pm = engine.project_metrics
        return {
            "project_name": engine.project_name,
            "modules": pm.total_modules,
            "dependencies": pm.total_edges,
            "loc": pm.total_loc,
            "density": pm.density,
            "avg_instability": pm.avg_instability,
            "has_cycles": pm.has_cycles,
            "cycle_count": engine.cycle_report.cycle_count,
            "health": {
                "healthy": pm.modules_healthy,
                "moderate": pm.modules_moderate,
                "elevated": pm.modules_elevated,
                "high": pm.modules_high,
                "critical": pm.modules_critical,
                "unknown": pm.modules_unknown,
            },
            "runtime_cycles": len([
                c for c in engine.cycle_report.cycles if c.kind == "runtime"
            ]),
            "safe_cycles": len([
                c for c in engine.cycle_report.cycles if c.kind != "runtime"
            ]),
        }

    # ── 2. File Context (THE key tool) ─────────────────────────

    @mcp.tool(annotations=_TOOL_ANNOTATIONS_READONLY)
    def hawkeye_file_context(
        file: str,
        compact: bool = True,
        min_severity: str = "",
        project_path: str = "",
    ) -> dict[str, object]:
        """Get everything about a file before editing it — in ONE call.

        Accepts a file path OR module name. Returns: dependencies, dependents,
        impact analysis, cycle warnings, health metrics, and related files.

        This replaces the need to call module_info + dependencies + dependents
        + impact separately.

        v0.6 compact format includes:
          - edit_cost: {files, cascade, tokens, risk} for planning
          - role: 'test'/'init'/'config'/'source' for threshold context
          - arch_role: 'core'/'orchestrator'/'hub-by-design' when applicable
          - Flat file paths for deps/dependents (token-efficient)

        If risk='hub' and arch_role is absent: make minimal, surgical changes.
        If risk='hub' and arch_role='core': changes expected, verify interfaces.
        If health='critical' and role='test': normal (test CC is not risk).

        Args:
            file: File path (e.g. 'cortex/intent_engine.py') or
                  module name (e.g. 'MERLIN.cortex.intent_engine').
            compact: If True (default), trim verbose fields for token efficiency.
            min_severity: Filter insights by minimum severity: 'info', 'warning',
                          or 'critical'. Default '' returns all insights.
            project_path: Optional project path if multiple are loaded.
        """
        engine = _resolve_engine(project_path)
        result = engine.get_file_context(file, compact=compact)
        if result is None:
            matches = engine.find_modules(file.replace("/", ".").replace(".py", ""))
            return {
                "error": f"'{file}' not found.",
                "suggestions": matches[:8],
                "hint": "Try a file path relative to project root, or a dotted module name.",
            }

        # Filter insights by severity if requested
        if min_severity and "insights" in result:
            severity_order = {"info": 0, "warning": 1, "critical": 2}
            min_level = severity_order.get(min_severity, 0)
            from ..core.insights import INSIGHT_SEVERITY
            result["insights"] = [
                i for i in result["insights"]
                if severity_order.get(INSIGHT_SEVERITY.get(i, "info"), 0) >= min_level
            ]

        return result

    # ── 3. Batch Context (multi-file) ──────────────────────────

    @mcp.tool(annotations=_TOOL_ANNOTATIONS_READONLY)
    def hawkeye_context(
        files: list[str],
        compact: bool = True,
        project_path: str = "",
    ) -> dict[str, object]:
        """Get combined context for multiple files being edited together.

        Returns shared dependencies, combined blast radius, cycle warnings,
        and architecture violations for the set of files.

        Args:
            files: List of file paths or module names.
            compact: If True, trim verbose fields for token efficiency.
            project_path: Optional project path.
        """
        engine = _resolve_engine(project_path)
        return engine.get_batch_context(files, compact=compact)

    # ── 4. Find ────────────────────────────────────────────────

    @mcp.tool(annotations=_TOOL_ANNOTATIONS_READONLY)
    def hawkeye_find(pattern: str, project_path: str = "") -> dict[str, object]:
        """Search for modules matching a pattern.

        Case-insensitive substring match on module names.
        Use this to discover module names before calling other tools.

        Args:
            pattern: Search string (e.g. 'engine', 'cortex', 'test').
            project_path: Optional project path.
        """
        engine = _resolve_engine(project_path)
        matches = engine.find_modules(pattern)
        return {
            "pattern": pattern,
            "count": len(matches),
            "modules": [
                {"file": engine.graph.nodes[m].rel_path,
                 "loc": engine.graph.nodes[m].loc,
                 "language": engine.graph.nodes[m].language}
                for m in matches[:50]  # Cap for token efficiency
            ],
        }

    # ── 5. Cycles ──────────────────────────────────────────────

    @mcp.tool(annotations=_TOOL_ANNOTATIONS_READONLY)
    def hawkeye_cycles(project_path: str = "") -> dict[str, object]:
        """Detect and report all import cycles in the project.

        Args:
            project_path: Optional project path.
        """
        engine = _resolve_engine(project_path)
        cr = engine.cycle_report
        runtime_cycles = [c for c in cr.cycles if c.kind == "runtime"]
        safe_cycles = [c for c in cr.cycles if c.kind != "runtime"]
        return {
            "has_cycles": cr.has_cycles,
            "count": cr.cycle_count,
            "runtime_count": len(runtime_cycles),
            "safe_count": len(safe_cycles),
            "cycles": [
                {"path": [_to_path(engine, m) for m in c.path],
                 "length": c.length,
                 "severity": c.severity, "kind": c.kind,
                 "break_at": _to_path(engine, c.break_suggestion) if c.break_suggestion else None}
                for c in cr.cycles
            ],
            "participation": {
                _to_path(engine, m): count
                for m, count in cr.participation.items()
            },
        }

    # ── 6. Metrics ─────────────────────────────────────────────

    @mcp.tool(annotations=_TOOL_ANNOTATIONS_READONLY)
    def hawkeye_metrics(
        sort_by: str = "instability",
        limit: int = 20,
        project_path: str = "",
    ) -> dict[str, object]:
        """Get coupling metrics for all modules.

        Ca = afferent coupling (who depends on me).
        Ce = efferent coupling (who I depend on).
        Instability = Ce/(Ca+Ce), 0=stable, 1=unstable.

        Args:
            sort_by: 'instability', 'ca', 'ce', or 'loc'.
            limit: Max modules to return (0 = all).
            project_path: Optional project path.
        """
        engine = _resolve_engine(project_path)
        items = sorted(
            engine.module_metrics.values(),
            key=lambda m: getattr(m, sort_by, 0),
            reverse=True,
        )
        if limit > 0:
            items = items[:limit]
        return {
            "sort_by": sort_by,
            "count": len(items),
            "modules": [
                {"file": _to_path(engine, m.module_name),
                 "language": m.language, "ca": m.ca, "ce": m.ce,
                 "instability": m.instability, "loc": m.loc, "health": m.health,
                 "cc": m.cyclomatic_complexity, "cog": m.cognitive_complexity,
                 "classes": m.class_count, "functions": m.function_count}
                | ({"parse_error": True} if m.parse_error else {})
                for m in items
            ],
        }

    # ── 7. Path ────────────────────────────────────────────────

    @mcp.tool(annotations=_TOOL_ANNOTATIONS_READONLY)
    def hawkeye_path(
        source: str, target: str, project_path: str = "",
    ) -> dict[str, object]:
        """Find shortest dependency path between two modules.

        Accepts file paths or module names for both source and target.

        Args:
            source: Starting file/module.
            target: Target file/module.
            project_path: Optional project path.
        """
        engine = _resolve_engine(project_path)
        path = engine.get_path(source, target)
        if path is None:
            return {"source": source, "target": target, "path": None,
                    "message": f"No dependency path from '{source}' to '{target}'."}
        return {"source": source, "target": target,
                "path": [_to_path(engine, m) for m in path],
                "hops": len(path) - 1}

    # ── 8. Graph ───────────────────────────────────────────────

    @mcp.tool(annotations=_TOOL_ANNOTATIONS_READONLY)
    def hawkeye_graph(
        max_depth: int = 0, project_path: str = "",
    ) -> dict[str, object]:
        """Get the full dependency graph as structured JSON.

        WARNING: Large output — can overwhelm AI context windows.
        Prefer hawkeye_file_context for targeted queries.
        On projects with 50+ modules, set max_depth=2 to limit output.

        Args:
            max_depth: If > 0, collapse modules deeper than this. Recommended: 2.
            project_path: Optional project path.
        """
        engine = _resolve_engine(project_path)
        graph = engine.graph

        node_count = len(graph.nodes)
        edge_count = sum(len(deps) for deps in graph.adjacency.values())

        # Summary mode for MCP: always return a bounded overview.
        # Full graph is only useful for CLI/HTML visualization.
        # Top hubs by afferent coupling = most depended-on modules.
        metrics_list = sorted(
            engine.module_metrics.values(),
            key=lambda m: m.ca,
            reverse=True,
        )
        top_hubs = [
            {"file": _to_path(engine, m.module_name),
             "ca": m.ca, "ce": m.ce, "health": m.health}
            for m in metrics_list[:15]
            if m.ca > 0
        ]

        # Package-level edge summary
        pkg_edges: dict[str, set[str]] = {}
        for src, deps in graph.adjacency.items():
            src_pkg = src.rsplit(".", 1)[0] if "." in src else src
            for dst in deps:
                dst_pkg = dst.rsplit(".", 1)[0] if "." in dst else dst
                if src_pkg != dst_pkg:
                    pkg_edges.setdefault(src_pkg, set()).add(dst_pkg)

        result: dict[str, object] = {
            "modules": node_count,
            "edges": edge_count,
            "density": round(edge_count / (node_count * (node_count - 1))
                             if node_count > 1 else 0.0, 4),
            "packages": len(pkg_edges),
            "top_hubs": top_hubs,
            "hint": "Use hawkeye_file_context(file) for targeted queries. "
                    "Use hawkeye_metrics(sort_by, limit) for rankings.",
        }

        return result

    # ── 9. Symbol Impact ──────────────────────────────────────

    @mcp.tool(annotations=_TOOL_ANNOTATIONS_READONLY)
    def hawkeye_impact(
        file: str,
        symbol: str = "",
        mode: str = "impact",
        limit: int = 15,
        project_path: str = "",
    ) -> dict[str, object]:
        """Analyze symbol-level impact of changing a file or specific symbol.

        Three modes:
        - 'impact' (default): Show which modules break if you change a symbol.
        - 'hotspots': Show the most-imported symbols (coupling risk).
        - 'unused': Show symbols that are defined but never imported.

        Results are capped at ``limit`` entries (default 15) for token
        efficiency.  The response includes ``total`` so you know if data
        was truncated.

        Args:
            file: File path or module name to analyze.
            symbol: Specific symbol name (e.g., 'Engine'). If empty, all symbols.
            mode: 'impact', 'hotspots', or 'unused'.
            limit: Max entries to return (default: 15).
            project_path: Optional project path.
        """
        engine = _resolve_engine(project_path)
        sg = engine.symbol_graph
        registry = engine.symbol_registry
        cap = max(limit, 1)

        if mode == "hotspots":
            hotspots = sg.hotspots(min_usage=2)
            total = len(hotspots)
            return {
                "mode": "hotspots",
                "total": total,
                "showing": min(cap, total),
                "hotspots": [
                    {"file": _to_path(engine, sid.module),
                     "name": sid.name, "kind": sid.kind,
                     "usage_count": count}
                    for sid, count in hotspots[:cap]
                ],
            }

        if mode == "unused":
            fw_decorators = engine.config.framework_entry_decorators
            unused = sg.unused_symbols(registry, framework_decorators=fw_decorators)
            total = len(unused)
            return {
                "mode": "unused",
                "total": total,
                "showing": min(cap, total),
                "framework_filtered": bool(fw_decorators),
                "symbols": [
                    {"file": _to_path(engine, sid.module),
                     "name": sid.name, "kind": sid.kind}
                    for sid in unused[:cap]
                ],
            }

        # Impact mode
        module = engine.resolve(file)
        if module is None:
            return {"error": f"Module not found: '{file}'",
                    "suggestions": engine.find_modules(file)[:10]}

        symbols = registry.get_module_symbols(module)
        if not symbols:
            return {
                "file": _to_path(engine, module),
                "language": engine.graph.nodes[module].language,
                "symbols": [],
                "message": "No symbols defined in this module.",
            }

        if symbol:
            symbols = [s for s in symbols if s.id.name == symbol]
            if not symbols:
                available = registry.get_module_symbols(module)
                return {"error": f"Symbol '{symbol}' not found in {module}",
                        "available": [s.id.name for s in available]}

        # Sort by usage count descending — most-imported symbols first
        symbols_with_usage = [
            (s, sg.usage_count(s.id)) for s in symbols
        ]
        symbols_with_usage.sort(key=lambda x: x[1], reverse=True)

        total = len(symbols_with_usage)
        results = []
        for defn, _ in symbols_with_usage[:cap]:
            impact = sg.impact_of(defn.id)
            impact["kind"] = defn.id.kind
            results.append(impact)

        return {
            "mode": "impact",
            "file": _to_path(engine, module),
            "language": engine.graph.nodes[module].language,
            "total": total,
            "showing": min(cap, total),
            "impacts": results,
        }

    # ── 10. Symbols ───────────────────────────────────────────

    @mcp.tool(annotations=_TOOL_ANNOTATIONS_READONLY)
    def hawkeye_symbols(
        file: str,
        project_path: str = "",
    ) -> dict[str, object]:
        """List all symbols (classes, functions) defined in a module.

        Use this to understand what a module exports before analyzing impact.

        Args:
            file: File path or module name.
            project_path: Optional project path.
        """
        engine = _resolve_engine(project_path)
        registry = engine.symbol_registry
        sg = engine.symbol_graph

        module = engine.resolve(file)
        if module is None:
            return {"error": f"Module not found: '{file}'",
                    "suggestions": engine.find_modules(file)[:10]}

        symbols = registry.get_module_symbols(module)
        return {
            "file": _to_path(engine, module),
            "language": engine.graph.nodes[module].language,
            "total_symbols": len(symbols),
            "symbols": [
                {
                    "name": s.id.name,
                    "kind": s.id.kind,
                    "line": s.line,
                    "end_line": s.end_line,
                    "complexity": s.info.complexity,
                    "usage_count": sg.usage_count(s.id),
                }
                | ({"decorators": s.info.decorators} if s.info.decorators else {})
                for s in symbols
            ],
        }

    # ── 11. Git Hotspots ──────────────────────────────────────

    @mcp.tool(annotations=_TOOL_ANNOTATIONS_READONLY)
    async def hawkeye_hotspots(
        limit: int = 20,
        days: int = 90,
        project_path: str = "",
    ) -> dict[str, object]:
        """Rank files by hotspot score = complexity × git churn.

        A file with CC=10 changing daily is more dangerous than CC=50
        unchanged for 6 months. This tool surfaces the files that are
        both complex AND actively changing — the real risk.

        Requires git. Returns empty results if not a git repository.

        Args:
            limit: Max entries to return (default: 20).
            days: Git history window in days (default: 90). Use 30 for
                recent activity or 180 for long-term trends.
            project_path: Optional project path.
        """
        import anyio

        engine = _resolve_engine(project_path)

        # Git subprocess calls block — run in a thread to avoid
        # freezing the MCP stdio event loop.
        def _compute():
            return engine.git_hotspots(limit=limit, days=days)

        hotspots, gh = await anyio.to_thread.run_sync(_compute)

        if not gh.available:
            return {
                "available": False,
                "message": "Git history not available (not a git repo or git not installed).",
            }
        return {
            "available": True,
            "analysis_days": gh.analysis_days,
            "total_commits": gh.total_commits,
            "count": len(hotspots),
            "hotspots": [
                {
                    "file": h.rel_path,
                    "hotspot_score": h.hotspot_score,
                    "cc": h.cyclomatic_complexity,
                    "commits": h.commit_count,
                    "lines_changed": h.lines_changed,
                    "days_since_change": h.days_since_last_change,
                    "contributors": h.contributor_count,
                    "churn": h.churn_category,
                    "health": h.health,
                }
                for h in hotspots
            ],
        }

    return mcp


# ── Entry Point ─────────────────────────────────────────────────

def main():
    """Entry point for the MCP server."""
    parser = argparse.ArgumentParser(description="Hawkeye MCP Server")
    parser.add_argument("--project", "-p", help="Pre-analyze this project on startup")
    args = parser.parse_args()

    mcp = create_mcp_server()

    if args.project:
        from ..engine import HawkeyeEngine
        engine = HawkeyeEngine()
        engine.analyze(args.project)
        global _engine
        _engine = engine
        _analyzed_projects[args.project] = engine
        print(f"[hawkeye] Pre-analyzed: {args.project}", file=sys.stderr)

    mcp.run()


if __name__ == "__main__":
    main()
