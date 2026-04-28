"""CLI entry point for Hawkeye.

Commands: analyze, context, impact, show, check, metrics, serve.
"""

import argparse
import sys
import webbrowser
from pathlib import Path

from . import __version__


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hawkeye",
        description="Hawkeye — Python architectural intelligence engine.",
        epilog=(
            "examples:\n"
            "  hawkeye analyze ./myproject                Full project analysis\n"
            "  hawkeye context ./myproject src/engine.py  AI-ready context for a file\n"
            "  hawkeye metrics ./myproject --functions    Complexity breakdown per function\n"
            "  hawkeye check ./myproject --no-cycles      CI gate: fail on violations\n"
            "  hawkeye impact ./myproject src/core.py -s Engine  Blast radius of Engine\n"
            "  hawkeye show ./myproject                   Interactive graph in browser\n"
            "  hawkeye serve -p ./myproject               MCP server for AI editors\n"
            "\n"
            "configuration:\n"
            "  Place a hawkeye.toml in your project root to configure architecture\n"
            "  rules, threshold profiles, and scan filters. Run 'hawkeye check' to\n"
            "  enforce rules in CI/CD.\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"hawkeye {__version__}")
    sub = parser.add_subparsers(dest="command", help="Available commands")

    # ── analyze ──
    p = sub.add_parser(
        "analyze",
        help="Full project analysis with metrics and health scoring",
        description=(
            "Scan a Python project and produce a comprehensive report including\n"
            "dependency graph, coupling metrics (Ca/Ce/I), complexity metrics\n"
            "(CC/Cog), abstractness (A), distance from main sequence (D),\n"
            "health classification, and cycle detection."
        ),
        epilog=(
            "examples:\n"
            "  hawkeye analyze ./myproject                    Text summary to stdout\n"
            "  hawkeye analyze ./myproject -f json -o out     JSON report to out.json\n"
            "  hawkeye analyze ./myproject -f html -o graph   Interactive HTML graph\n"
            "  hawkeye analyze ./myproject --max-depth 2      Collapse deep modules\n"
            "  hawkeye analyze ./myproject --exclude 'test*'  Skip test modules\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("project", help="Path to the Python project root")
    p.add_argument("-f", "--format", choices=["text", "json", "dot", "html"],
                   default="text", help="Output format (default: text)")
    p.add_argument("-o", "--output", help="Write output to file (auto-appends extension)")
    p.add_argument("--max-depth", type=int,
                   help="Collapse modules deeper than N levels into their parent")
    p.add_argument("--exclude", nargs="*", default=[],
                   help="Glob patterns to exclude (e.g., 'test*' 'scripts.*')")
    p.add_argument("--include", nargs="*", default=[],
                   help="Glob patterns to include (only matching modules are analyzed)")

    # ── context ──
    p = sub.add_parser(
        "context",
        help="AI-ready architectural context for one or more files",
        description=(
            "Generate a single JSON blob with everything an AI agent needs before\n"
            "editing a file: dependencies, dependents, blast radius, complexity,\n"
            "health, insights, risk classification, cycle involvement, and related\n"
            "files. For multi-file edits, pass multiple files to get combined\n"
            "blast radius and shared dependency analysis."
        ),
        epilog=(
            "examples:\n"
            "  hawkeye context ./myproject src/engine.py\n"
            "  hawkeye context ./myproject engine.py models.py  Combined context\n"
            "  hawkeye context ./myproject myapp.core.engine    Module name works too\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("project", help="Path to the Python project root")
    p.add_argument("file", nargs="+",
                   help="File path(s) or module name(s) to get context for")

    # ── show ──
    p = sub.add_parser(
        "show",
        help="Open interactive D3.js dependency graph in browser",
        description=(
            "Generate a self-contained HTML page with an interactive force-directed\n"
            "dependency graph (D3.js). Includes search, zoom, drag, click-to-inspect,\n"
            "health coloring, and cycle highlighting. Opens automatically in browser."
        ),
        epilog=(
            "examples:\n"
            "  hawkeye show ./myproject                   Opens in default browser\n"
            "  hawkeye show ./myproject -o graph.html     Save to specific path\n"
            "  hawkeye show ./myproject --max-depth 2     Collapse deep packages\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("project", help="Path to the Python project root")
    p.add_argument("-o", "--output", help="Save HTML to file (default: <project>/hawkeye_graph.html)")
    p.add_argument("--max-depth", type=int,
                   help="Collapse modules deeper than N levels into their parent")

    # ── check ──
    p = sub.add_parser(
        "check",
        help="Enforce architecture rules — CI/CD gate with exit codes",
        description=(
            "Evaluate architecture rules defined in hawkeye.toml and exit non-zero\n"
            "on violations. Supports: layer ordering, forbidden imports, module\n"
            "independence (transitive), protected modules, acyclic sibling\n"
            "enforcement, and cycle detection.\n\n"
            "Rule types (in evaluation order):\n"
            "  forbidden          Hard-block specific import patterns\n"
            "  protected          Only allowlisted modules may import protected targets\n"
            "  layers             Enforce directional dependency flow between layers\n"
            "  independence       No transitive paths between independent module groups\n"
            "  acyclic_siblings   Sibling packages under an ancestor must not form cycles"
        ),
        epilog=(
            "examples:\n"
            "  hawkeye check ./myproject                  Check rules from hawkeye.toml\n"
            "  hawkeye check ./myproject --no-cycles      Also fail on import cycles\n"
            "  hawkeye check ./myproject --config ci.toml Use alternate config file\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("project", help="Path to the Python project root")
    p.add_argument("--config", help="Path to hawkeye.toml (default: auto-discover)")
    p.add_argument("--no-cycles", action="store_true",
                   help="Fail if any import cycles exist")

    # ── metrics ──
    p = sub.add_parser(
        "metrics",
        help="Deep-dive coupling, complexity, and Martin metrics",
        description=(
            "Display a sortable metrics table for all modules:\n"
            "  Ca   Afferent coupling (who depends on me)\n"
            "  Ce   Efferent coupling (who I depend on)\n"
            "  I    Instability = Ce/(Ca+Ce). 0=stable, 1=unstable\n"
            "  CC   Cyclomatic complexity (decision branches)\n"
            "  Cog  Cognitive complexity (nesting-weighted, SonarSource spec)\n"
            "  A    Abstractness = abstract classes / total classes\n"
            "  D    Distance from main sequence = |A + I - 1|\n\n"
            "Use --functions to see per-function/method complexity breakdown,\n"
            "revealing the real hotspots hidden inside large classes."
        ),
        epilog=(
            "examples:\n"
            "  hawkeye metrics ./myproject                    Full metrics table\n"
            "  hawkeye metrics ./myproject --sort health      Critical modules first\n"
            "  hawkeye metrics ./myproject --sort distance    Worst architectural fit\n"
            "  hawkeye metrics ./myproject --functions        Per-function breakdown\n"
            "  hawkeye metrics ./myproject --json --limit 10  Top 10 as JSON\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("project", help="Path to the Python project root")
    p.add_argument("--sort", choices=[
        "instability", "ca", "ce", "loc",
        "cyclomatic", "cognitive", "health",
        "abstractness", "distance",
    ], default="instability", help="Sort modules by this metric (default: instability)")
    p.add_argument("--limit", type=int, default=0,
                   help="Max modules to display, 0=all (default: 0)")
    p.add_argument("--functions", action="store_true",
                   help="Show per-function/method complexity breakdown (top 30)")
    p.add_argument("--json", dest="metrics_json", action="store_true",
                   help="Output as JSON (all metrics fields included)")

    # ── impact ──
    p = sub.add_parser(
        "impact",
        help="Symbol-level blast radius, hotspots, and dead code detection",
        description=(
            "Analyze the impact of changing a file or specific symbol.\n\n"
            "Modes:\n"
            "  (default)    Show blast radius for all symbols in a file\n"
            "  --symbol X   Show blast radius for symbol X only\n"
            "  --hotspots   Show most-imported symbols across the project\n"
            "  --unused     Show symbols defined but never imported (dead code)"
        ),
        epilog=(
            "examples:\n"
            "  hawkeye impact ./myproject src/engine.py           All symbols\n"
            "  hawkeye impact ./myproject src/engine.py -s Engine Specific symbol\n"
            "  hawkeye impact ./myproject src/engine.py --hotspots Most-imported\n"
            "  hawkeye impact ./myproject src/engine.py --unused   Dead code\n"
            "  hawkeye impact ./myproject src/engine.py --json     Machine-readable\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("project", help="Path to the Python project root")
    p.add_argument("file", help="File path or module name to analyze impact for")
    p.add_argument("--symbol", "-s",
                   help="Specific symbol name to analyze (e.g., 'Engine', 'process_request')")
    p.add_argument("--hotspots", action="store_true",
                   help="Show most-imported symbols (imported by ≥2 modules)")
    p.add_argument("--unused", action="store_true",
                   help="Show symbols defined but never imported elsewhere")
    p.add_argument("--json", action="store_true", help="Output as JSON")

    # ── serve ──
    p = sub.add_parser(
        "serve",
        help="Start MCP server for AI editors (Claude Code, Cursor, Windsurf)",
        description=(
            "Start a Model Context Protocol (MCP) server that exposes 10 tools\n"
            "for AI coding agents. The server provides architectural context,\n"
            "dependency analysis, and impact tracking that AI editors can query\n"
            "before making code changes.\n\n"
            "MCP tools exposed:\n"
            "  hawkeye_analyze        Scan project (call first)\n"
            "  hawkeye_file_context   Everything about a file in one call\n"
            "  hawkeye_context        Combined context for multi-file edits\n"
            "  hawkeye_impact         Symbol-level blast radius\n"
            "  hawkeye_symbols        List classes/functions with usage counts\n"
            "  hawkeye_find           Search modules by name pattern\n"
            "  hawkeye_cycles         Import cycle report\n"
            "  hawkeye_metrics        Coupling + complexity metrics\n"
            "  hawkeye_path           Shortest dependency path\n"
            "  hawkeye_graph          Full graph as structured JSON"
        ),
        epilog=(
            "editor configuration (add to MCP config):\n"
            '  {"mcpServers": {"hawkeye": {\n'
            '    "command": "hawkeye-mcp",\n'
            '    "args": ["--project", "/path/to/project"]\n'
            "  }}}\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--project", "-p",
                   help="Pre-analyze this project on startup (recommended)")

    return parser


def _ensure_utf8():
    """Reconfigure stdout for UTF-8 on Windows."""
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def _make_engine(args, *, use_config: bool = False):
    """Create and run an engine from CLI args."""
    from .config import HawkeyeConfig
    from .engine import HawkeyeEngine

    if use_config and hasattr(args, "config") and args.config:
        config = HawkeyeConfig.from_toml(Path(args.config))
    elif use_config:
        config = HawkeyeConfig.find_and_load(Path(args.project))
    else:
        config = HawkeyeConfig()
        if hasattr(args, "exclude"):
            config.exclude_patterns = args.exclude or []
        if hasattr(args, "include"):
            config.include_patterns = args.include or []

    engine = HawkeyeEngine(config)
    engine.analyze(args.project)
    return engine


def _run_analyze(args) -> int:
    engine = _make_engine(args)
    graph = engine.graph
    if args.max_depth:
        graph = graph.filtered(max_depth=args.max_depth)

    if args.format == "text":
        from .visualizer.text_renderer import render_project_summary
        output = render_project_summary(graph, engine.project_metrics, engine.module_metrics)
    elif args.format == "json":
        from .visualizer.json_renderer import render_json
        output = render_json(graph, engine.module_metrics, engine.project_metrics, engine.cycle_report)
    elif args.format == "dot":
        from .visualizer.dot_renderer import render_dot
        output = render_dot(graph, engine.module_metrics)
    elif args.format == "html":
        from .visualizer.html_renderer import render_html
        output = render_html(graph, engine.module_metrics, engine.cycle_report.cycle_count)
    else:
        output = ""

    if args.output:
        out_path = Path(args.output)
        # Auto-append extension if missing
        ext_map = {"html": ".html", "json": ".json", "dot": ".dot", "text": ".txt"}
        if not out_path.suffix and args.format in ext_map:
            out_path = out_path.with_suffix(ext_map[args.format])
        out_path.write_text(output, encoding="utf-8")
        print(f"Output written to {out_path}")
    else:
        print(output)
    return 0


def _run_context(args) -> int:
    import json as json_mod
    engine = _make_engine(args)

    if len(args.file) == 1:
        result = engine.get_file_context(args.file[0])
        if result is None:
            matches = engine.find_modules(args.file[0])
            print(f"Not found: '{args.file[0]}'")
            if matches:
                print("Did you mean:")
                for m in matches[:10]:
                    print(f"  {m}")
            return 1
    else:
        result = engine.get_batch_context(args.file)

    print(json_mod.dumps(result, indent=2, ensure_ascii=False))
    return 0


def _run_show(args) -> int:
    engine = _make_engine(args)
    from .visualizer.html_renderer import render_html

    graph = engine.graph
    if args.max_depth:
        graph = graph.filtered(max_depth=args.max_depth)

    html = render_html(graph, engine.module_metrics, engine.cycle_report.cycle_count)
    out_path = Path(args.output) if args.output else Path(args.project) / "hawkeye_graph.html"
    if not out_path.suffix:
        out_path = out_path.with_suffix(".html")
    out_path = out_path.resolve()  # as_uri() requires an absolute path
    out_path.write_text(html, encoding="utf-8")
    print(f"Graph written to {out_path}")
    webbrowser.open(out_path.as_uri())
    return 0


def _run_check(args) -> int:
    engine = _make_engine(args, use_config=True)
    violations = list(engine.violations)

    if args.no_cycles and engine.cycle_report.has_cycles:
        from .visualizer.text_renderer import render_cycle_report
        print(render_cycle_report(engine.cycle_report))
        violations.append(type("V", (), {
            "__str__": lambda self: "❌ [cycle] Import cycles detected"
        })())

    if violations:
        print(f"\n❌ {len(violations)} violation(s) found:\n")
        for v in violations:
            print(f"  {v}")
        return 1

    print("✅ All architecture rules passed!")
    return 0


def _run_metrics(args) -> int:
    engine = _make_engine(args)

    if args.metrics_json:
        import json as json_mod
        data = _metrics_to_json(engine, args)
        print(json_mod.dumps(data, indent=2, ensure_ascii=False))
        return 0

    from .core.metrics import format_metrics_table

    lines: list[str] = []

    # ── Health summary ──
    pm = engine.project_metrics
    lines.append(f"\n📊 Metrics: {engine.project_name}")
    lines.append(f"   {pm.total_modules} modules | {pm.total_loc} LOC | "
                 f"density {pm.density:.4f}")
    lines.append(f"   Health: ✅ {pm.modules_healthy}  ⚠️  {pm.modules_warning}  "
                 f"🔴 {pm.modules_critical}")
    lines.append("")

    # ── Module metrics table (unified renderer — all columns) ──
    lines.append(format_metrics_table(
        engine.module_metrics,
        sort_by=args.sort,
        limit=args.limit,
    ))

    # ── Per-function/method breakdown ──
    if args.functions:
        lines.append("\n🔬 Per-Function Complexity (top 30):")
        lines.append("")
        fn_header = (f"  {'Symbol':<50} {'Module':<30} "
                     f"{'CC':>4} {'Line':>5}")
        fn_sep = "  " + "─" * (len(fn_header) - 2)
        lines.extend([fn_sep, fn_header, fn_sep])

        all_fns: list[tuple[str, str, int, int]] = []
        for mod_name, st in engine._symbol_tables.items():
            for fn in st.functions:
                all_fns.append((fn.name, mod_name, fn.complexity, fn.line))
            for method in st.methods:
                all_fns.append((method.name, mod_name, method.complexity, method.line))

        all_fns.sort(key=lambda x: x[2], reverse=True)
        for name, mod, cc, line in all_fns[:30]:
            lines.append(
                f"  {name:<50} {mod:<30} {cc:>4} {line:>5}"
            )
        lines.append(fn_sep)

    print("\n".join(lines))
    return 0


def _metrics_to_json(engine, args) -> dict:
    """Build JSON output for the metrics command. Uses ModuleMetrics.to_dict()."""
    from .core.metrics import sort_metrics

    metrics_list = sort_metrics(engine.module_metrics, args.sort, args.limit)

    pm = engine.project_metrics
    result: dict = {
        "project": engine.project_name,
        "threshold_profile": engine.config.thresholds.profile,
        "summary": {
            "modules": pm.total_modules,
            "loc": pm.total_loc,
            "density": pm.density,
            "healthy": pm.modules_healthy,
            "warning": pm.modules_warning,
            "critical": pm.modules_critical,
        },
        "modules": [m.to_dict() for m in metrics_list],
    }

    if args.functions:
        all_fns = []
        for mod_name, st in engine._symbol_tables.items():
            for fn in st.functions:
                all_fns.append({
                    "name": fn.name, "kind": "function",
                    "module": mod_name,
                    "complexity": fn.complexity, "line": fn.line,
                })
            for method in st.methods:
                all_fns.append({
                    "name": method.name, "kind": "method",
                    "module": mod_name,
                    "complexity": method.complexity, "line": method.line,
                })
        all_fns.sort(key=lambda x: x["complexity"], reverse=True)
        result["functions"] = all_fns[:50]

    return result


def _run_serve(args) -> int:
    from .server import main as serve_main
    sys.argv = ["hawkeye-mcp"]
    if args.project:
        sys.argv.extend(["--project", args.project])
    serve_main()
    return 0


def _run_impact(args) -> int:
    import json as json_mod
    engine = _make_engine(args, use_config=True)
    sg = engine.symbol_graph
    registry = engine.symbol_registry

    # ── Hotspots mode ──
    if args.hotspots:
        hotspots = sg.hotspots(min_usage=2)
        if args.json:
            print(json_mod.dumps(
                [{"symbol": str(sid), "usage_count": c} for sid, c in hotspots],
                indent=2,
            ))
        else:
            print(f"\n🔥 Symbol Hotspots (imported by ≥2 modules):\n")
            if not hotspots:
                print("  No hotspots found.")
            for sid, count in hotspots:
                print(f"  {sid.name:30s}  ({sid.module})  → {count} importers")
        return 0

    # ── Unused mode ──
    if args.unused:
        unused = sg.unused_symbols(registry)
        if args.json:
            print(json_mod.dumps(
                [{"symbol": str(sid), "module": sid.module} for sid in unused],
                indent=2,
            ))
        else:
            print(f"\n💀 Unused Symbols ({len(unused)} found):\n")
            for sid in unused:
                print(f"  {sid.name:30s}  ({sid.module})")
        return 0

    # ── Symbol impact mode ──
    module = engine.resolve(args.file)
    if module is None:
        print(f"Not found: '{args.file}'")
        return 1

    symbols = registry.get_module_symbols(module)
    if not symbols:
        print(f"No symbols defined in {module}")
        return 0

    if args.symbol:
        # Impact for a specific symbol
        matches = [s for s in symbols if s.id.name == args.symbol]
        if not matches:
            print(f"Symbol '{args.symbol}' not found in {module}")
            print(f"Available: {', '.join(s.id.name for s in symbols)}")
            return 1
        targets = matches
    else:
        targets = symbols

    results = []
    for defn in targets:
        impact = sg.impact_of(defn.id)
        impact["kind"] = defn.id.kind
        results.append(impact)

    if args.json:
        print(json_mod.dumps(results, indent=2))
    else:
        print(f"\n⚡ Impact Analysis: {module}\n")
        for r in results:
            sid_str = r["symbol"].split("::")[-1]
            print(f"  {r.get('kind', '?'):10s} {sid_str}")
            print(f"    Direct users:      {r['direct_users']} module(s)")
            print(f"    Transitive users:  {r['transitive_users']} module(s)")
            if r["direct_modules"]:
                print(f"    Used by: {', '.join(r['direct_modules'])}")
            print()

    return 0


def main() -> int:
    _ensure_utf8()
    parser = _build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    handlers = {
        "analyze": _run_analyze,
        "context": _run_context,
        "impact": _run_impact,
        "show": _run_show,
        "check": _run_check,
        "metrics": _run_metrics,
        "serve": _run_serve,
    }
    handler = handlers.get(args.command)
    return handler(args) if handler else 0


if __name__ == "__main__":
    sys.exit(main())
