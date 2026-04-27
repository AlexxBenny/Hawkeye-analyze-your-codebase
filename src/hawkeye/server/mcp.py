"""MCP (Model Context Protocol) server for AI coding agents.

Exposes Hawkeye's analysis as MCP tools optimized for AI editors.
The key tool is `hawkeye_file_context` — one call that gives an agent
everything it needs before editing a file.

Usage:
    python -m hawkeye.mcp_server                # stdio transport
    python -m hawkeye.mcp_server --project .    # pre-analyze on startup
"""

import sys
import json
import argparse

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


# ── MCP Server ──────────────────────────────────────────────────

def create_mcp_server():
    """Create the MCP server with 8 consolidated tools."""
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
            "Hawkeye analyzes Python project architecture. Workflow:\n"
            "1. hawkeye_analyze(project_path) — scan the project (do this first)\n"
            "2. hawkeye_file_context(file) — get full context before editing a file\n"
            "3. hawkeye_context(files) — get combined context for multiple files\n"
            "Other tools: hawkeye_find, hawkeye_cycles, hawkeye_metrics, "
            "hawkeye_path, hawkeye_graph"
        ),
    )

    # ── 1. Analyze ─────────────────────────────────────────────

    @mcp.tool(annotations=_TOOL_ANNOTATIONS_READONLY)
    def hawkeye_analyze(project_path: str) -> dict[str, object]:
        """Scan a Python project and build its dependency graph.

        Call this first before using any other tool. Scans all .py files,
        resolves imports, detects cycles, and computes coupling metrics.

        Args:
            project_path: Absolute path to the project root.
        """
        from ..engine import HawkeyeEngine
        engine = HawkeyeEngine()
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
                "warning": pm.modules_warning,
                "critical": pm.modules_critical,
            },
        }

    # ── 2. File Context (THE key tool) ─────────────────────────

    @mcp.tool(annotations=_TOOL_ANNOTATIONS_READONLY)
    def hawkeye_file_context(
        file: str,
        compact: bool = True,
        project_path: str = "",
    ) -> dict[str, object]:
        """Get everything about a file before editing it — in ONE call.

        Accepts a file path OR module name. Returns: dependencies, dependents,
        impact analysis, cycle warnings, health metrics, and related files.

        This replaces the need to call module_info + dependencies + dependents
        + impact separately.

        Args:
            file: File path (e.g. 'cortex/intent_engine.py') or
                  module name (e.g. 'MERLIN.cortex.intent_engine').
            compact: If True (default), trim verbose fields for token efficiency.
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
                {"module": m, "file": engine.graph.nodes[m].rel_path,
                 "loc": engine.graph.nodes[m].loc}
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
        return {
            "has_cycles": cr.has_cycles,
            "count": cr.cycle_count,
            "cycles": [{"path": c.path, "length": c.length} for c in cr.cycles],
            "participation": cr.participation,
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
                {"module": m.module_name, "ca": m.ca, "ce": m.ce,
                 "instability": m.instability, "loc": m.loc, "health": m.health}
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
        return {"source": source, "target": target, "path": path,
                "hops": len(path) - 1}

    # ── 8. Graph ───────────────────────────────────────────────

    @mcp.tool(annotations=_TOOL_ANNOTATIONS_READONLY)
    def hawkeye_graph(
        max_depth: int = 0, project_path: str = "",
    ) -> dict[str, object]:
        """Get the full dependency graph as structured JSON.

        WARNING: Large output. Prefer hawkeye_file_context for targeted queries.

        Args:
            max_depth: If > 0, collapse modules deeper than this.
            project_path: Optional project path.
        """
        engine = _resolve_engine(project_path)
        graph = engine.graph
        if max_depth > 0:
            graph = graph.filtered(max_depth=max_depth)

        from ..visualizer.json_renderer import render_json
        return json.loads(render_json(
            graph, engine.module_metrics,
            engine.project_metrics, engine.cycle_report,
        ))

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
