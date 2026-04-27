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
        description="Hawkeye — Python dependency analyzer & architecture enforcer",
    )
    parser.add_argument("--version", action="version", version=f"hawkeye {__version__}")
    sub = parser.add_subparsers(dest="command", help="Available commands")

    # ── analyze ──
    p = sub.add_parser("analyze", help="Analyze a project and show summary")
    p.add_argument("project", help="Path to the Python project root")
    p.add_argument("-f", "--format", choices=["text", "json", "dot", "html"], default="text")
    p.add_argument("-o", "--output", help="Write output to file")
    p.add_argument("--max-depth", type=int, help="Collapse modules deeper than N")
    p.add_argument("--exclude", nargs="*", default=[], help="Glob patterns to exclude")
    p.add_argument("--include", nargs="*", default=[], help="Glob patterns to include")

    # ── context (replaces info + impact) ──
    p = sub.add_parser("context", help="Show full context for a file or module")
    p.add_argument("project", help="Path to the Python project root")
    p.add_argument("file", nargs="+", help="File path(s) or module name(s)")

    # ── show ──
    p = sub.add_parser("show", help="Open interactive HTML graph in browser")
    p.add_argument("project", help="Path to the Python project root")
    p.add_argument("-o", "--output", help="Save HTML to file")
    p.add_argument("--max-depth", type=int, help="Collapse modules deeper than N")

    # ── check ──
    p = sub.add_parser("check", help="Check architecture rules (CI/CD)")
    p.add_argument("project", help="Path to the Python project root")
    p.add_argument("--config", help="Path to hawkeye.toml")
    p.add_argument("--no-cycles", action="store_true", help="Fail if cycles exist")

    # ── metrics ──
    p = sub.add_parser("metrics", help="Show coupling metrics")
    p.add_argument("project", help="Path to the Python project root")
    p.add_argument("--sort", choices=["instability", "ca", "ce", "loc"], default="instability")
    p.add_argument("--limit", type=int, default=0, help="Max modules (0=all)")

    # ── impact ──
    p = sub.add_parser("impact", help="Analyze symbol-level impact of changing a file")
    p.add_argument("project", help="Path to the Python project root")
    p.add_argument("file", help="File path or module name to analyze impact for")
    p.add_argument("--symbol", "-s", help="Specific symbol name (e.g., 'Engine')")
    p.add_argument("--hotspots", action="store_true", help="Show most-imported symbols")
    p.add_argument("--unused", action="store_true", help="Show unused symbols")
    p.add_argument("--json", action="store_true", help="Output as JSON")

    # ── serve ──
    p = sub.add_parser("serve", help="Start the MCP server for AI editors")
    p.add_argument("--project", "-p", help="Pre-analyze this project on startup")

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
    from .core import format_metrics_table
    print(format_metrics_table(engine.module_metrics, sort_by=args.sort, limit=args.limit))
    return 0


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
