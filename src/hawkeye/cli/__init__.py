"""CLI entry point for Hawkeye.

Commands: analyze, context, impact, show, check, metrics, serve.
"""

import argparse
import sys

from .. import __version__
from ._helpers import ensure_utf8
from .commands import (run_analyze, run_check, run_context, run_impact,
                       run_metrics, run_serve, run_show)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hawkeye",
        description="Hawkeye — multi-language architectural intelligence engine.",
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

    def _add_language_options(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--languages",
            nargs="*",
            help="Languages to analyze (python, javascript, typescript)",
        )
        p.add_argument(
            "--tsconfig",
            help="Path to tsconfig.json (for TypeScript path resolution)",
        )
        p.add_argument(
            "--package-root",
            help="Package root for JS/TS resolution (defaults to project root)",
        )

    # ── analyze ──
    p = sub.add_parser(
        "analyze",
        help="Full project analysis with metrics and health scoring",
        description=(
            "Scan a codebase and produce a comprehensive report including\n"
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
    p.add_argument("project", help="Path to the codebase root")
    p.add_argument("-f", "--format", choices=["text", "json", "dot", "html"],
                   default="text", help="Output format (default: text)")
    p.add_argument("-o", "--output", help="Write output to file (auto-appends extension)")
    p.add_argument("--max-depth", type=int,
                   help="Collapse modules deeper than N levels into their parent")
    p.add_argument("--exclude", nargs="*", default=[],
                   help="Glob patterns to exclude (e.g., 'test*' 'scripts.*')")
    p.add_argument("--include", nargs="*", default=[],
                   help="Glob patterns to include (only matching modules are analyzed)")
    _add_language_options(p)

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
    p.add_argument("project", help="Path to the codebase root")
    p.add_argument("file", nargs="+",
                   help="File path(s) or module name(s) to get context for")
    _add_language_options(p)

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
    p.add_argument("project", help="Path to the codebase root")
    p.add_argument("-o", "--output", help="Save HTML to file (default: <project>/hawkeye_graph.html)")
    p.add_argument("--max-depth", type=int,
                   help="Collapse modules deeper than N levels into their parent")
    _add_language_options(p)

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
    p.add_argument("project", help="Path to the codebase root")
    p.add_argument("--config", help="Path to hawkeye.toml (default: auto-discover)")
    p.add_argument("--no-cycles", action="store_true",
                   help="Fail if any import cycles exist")
    _add_language_options(p)

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
    p.add_argument("project", help="Path to the codebase root")
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
    _add_language_options(p)

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
    p.add_argument("project", help="Path to the codebase root")
    p.add_argument("file", help="File path or module name to analyze impact for")
    p.add_argument("--symbol", "-s",
                   help="Specific symbol name to analyze (e.g., 'Engine', 'process_request')")
    p.add_argument("--hotspots", action="store_true",
                   help="Show most-imported symbols (imported by ≥2 modules)")
    p.add_argument("--unused", action="store_true",
                   help="Show symbols defined but never imported elsewhere")
    p.add_argument("--json", action="store_true", help="Output as JSON")
    _add_language_options(p)

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


def main() -> int:
    ensure_utf8()
    parser = _build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    handlers = {
        "analyze": run_analyze,
        "context": run_context,
        "impact": run_impact,
        "show": run_show,
        "check": run_check,
        "metrics": run_metrics,
        "serve": run_serve,
    }
    handler = handlers.get(args.command)
    return handler(args) if handler else 0


if __name__ == "__main__":
    sys.exit(main())
