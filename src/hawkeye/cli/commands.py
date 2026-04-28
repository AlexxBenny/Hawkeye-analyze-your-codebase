"""CLI command handlers for Hawkeye.

Each function handles one CLI subcommand and returns an exit code.
"""

import json as json_mod
from pathlib import Path

from ._helpers import _make_engine


def run_analyze(args) -> int:
    engine = _make_engine(args)
    graph = engine.graph
    if args.max_depth:
        graph = graph.filtered(max_depth=args.max_depth)

    if args.format == "text":
        from ..visualizer.text_renderer import render_project_summary
        output = render_project_summary(graph, engine.project_metrics, engine.module_metrics)
    elif args.format == "json":
        from ..visualizer.json_renderer import render_json
        output = render_json(graph, engine.module_metrics, engine.project_metrics, engine.cycle_report)
    elif args.format == "dot":
        from ..visualizer.dot_renderer import render_dot
        output = render_dot(graph, engine.module_metrics)
    elif args.format == "html":
        from ..visualizer.html_renderer import render_html
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


def run_context(args) -> int:
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


def run_show(args) -> int:
    import webbrowser

    engine = _make_engine(args)
    from ..visualizer.html_renderer import render_html

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


def run_check(args) -> int:
    engine = _make_engine(args, use_config=True)
    violations = list(engine.violations)

    if args.no_cycles and engine.cycle_report.has_cycles:
        from ..visualizer.text_renderer import render_cycle_report
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


def run_metrics(args) -> int:
    engine = _make_engine(args)

    if args.metrics_json:
        data = _metrics_to_json(engine, args)
        print(json_mod.dumps(data, indent=2, ensure_ascii=False))
        return 0

    from ..core.metrics import format_metrics_table

    lines: list[str] = []

    # ── Health summary ──
    pm = engine.project_metrics
    lines.append(f"\n📊 Metrics: {engine.project_name}")
    lines.append(f"   {pm.total_modules} modules | {pm.total_loc} LOC | "
                 f"density {pm.density:.4f}")
    lines.append(f"   Health: ✅ {pm.modules_healthy}  🟡 {pm.modules_moderate}  "
                 f"🟠 {pm.modules_elevated}  🔴 {pm.modules_high}  "
                 f"🔥 {pm.modules_critical}")
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


def run_impact(args) -> int:
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
        fw_decorators = engine.config.framework_entry_decorators
        unused = sg.unused_symbols(registry, framework_decorators=fw_decorators)
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


def run_serve(args) -> int:
    import sys

    from ..server import main as serve_main
    sys.argv = ["hawkeye-mcp"]
    if args.project:
        sys.argv.extend(["--project", args.project])
    serve_main()
    return 0


# ── Internal helpers ────────────────────────────────────────────


def _metrics_to_json(engine, args) -> dict:
    """Build JSON output for the metrics command. Uses ModuleMetrics.to_dict()."""
    from ..core.metrics import sort_metrics

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
            "moderate": pm.modules_moderate,
            "elevated": pm.modules_elevated,
            "high": pm.modules_high,
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
