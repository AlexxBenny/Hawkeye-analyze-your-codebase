# 🦅 Hawkeye

**Python dependency graph analyzer, architecture enforcer, and MCP server for AI coding agents.**

Hawkeye provides deep static analysis of Python codebases with interactive visualization, coupling metrics, cycle detection, architecture rule enforcement, and an MCP server interface that lets AI editors (Claude Code, Antigravity, Cursor) fully understand your project's architecture.

## Quick Start

```bash
# Analyze a project (text output)
python main.py analyze /path/to/your/project

# Open interactive graph in browser
python main.py show /path/to/your/project

# Get coupling metrics
python main.py metrics /path/to/your/project

# Check architecture rules
python main.py check /path/to/your/project

# Impact analysis for a module
python main.py impact /path/to/your/project myproject.core.engine

# Module details
python main.py info /path/to/your/project myproject.core.engine

# Start MCP server for AI editors
python main.py serve --project /path/to/your/project
```

## Features

### 📊 Analysis
- **AST-based import analysis** — resolves relative imports, `from X import Y`, and package `__init__.py`
- **Dependency graph** — directed graph with forward/reverse adjacency
- **Cycle detection** — Tarjan's SCC algorithm finds all circular imports
- **Coupling metrics** — Afferent (Ca), Efferent (Ce), Instability (I), Health scoring

### 🎨 Visualization
- **Interactive HTML** — self-contained D3.js force-directed graph with search, click-to-inspect, zoom/pan
- **Graphviz DOT** — package clustering, HSL coloring, cycle highlighting
- **JSON export** — full graph with metrics for programmatic consumption
- **Text output** — structured reports for terminals and AI agents

### 🏗️ Architecture Enforcement
- **Layer rules** — enforce dependency direction (e.g., domain → infrastructure ✗)
- **Forbidden imports** — block specific cross-module dependencies
- **Independence contracts** — ensure module groups stay decoupled
- **CI/CD integration** — `hawkeye check` exits with non-zero code on violations

### 🤖 MCP Server (for AI Editors)
10 tools that give AI agents full architectural understanding:

| Tool | Purpose |
|------|---------|
| `hawkeye_analyze` | Full project analysis with summary |
| `hawkeye_module_info` | Detailed module inspection |
| `hawkeye_dependencies` | What a module imports |
| `hawkeye_dependents` | What imports a module |
| `hawkeye_cycles` | Cycle detection report |
| `hawkeye_metrics` | Coupling metrics table |
| `hawkeye_impact` | Change impact analysis |
| `hawkeye_find` | Search modules by pattern |
| `hawkeye_path` | Find dependency path A → B |
| `hawkeye_graph` | Full graph as JSON |

### MCP Configuration

Add to your AI editor's MCP config:

```json
{
  "mcpServers": {
    "hawkeye": {
      "command": "python",
      "args": ["-m", "hawkeye.mcp_server", "--project", "/path/to/your/project"]
    }
  }
}
```

## Configuration

Create a `hawkeye.toml` in your project root. See the included example for all options.

## Output Formats

```bash
python main.py analyze ./myproject -f text   # Terminal-friendly (default)
python main.py analyze ./myproject -f json   # Machine-readable
python main.py analyze ./myproject -f dot    # Graphviz DOT
python main.py analyze ./myproject -f html   # Interactive browser graph
```

## Project Structure

```
Hawkeye/
├── src/                         # Source root (src layout)
│   └── hawkeye/                 # Importable package
│       ├── __init__.py          # Package metadata
│       ├── __main__.py          # python -m hawkeye support
│       ├── cli.py               # CLI with subcommands
│       ├── config.py            # TOML config loading
│       ├── scanner.py           # File discovery & module indexing
│       ├── analyzer.py          # AST import extraction & resolution
│       ├── graph.py             # Dependency graph & algorithms
│       ├── metrics.py           # Coupling metrics & health scoring
│       ├── cycles.py            # Tarjan's SCC cycle detection
│       ├── rules.py             # Architecture rule enforcement
│       ├── engine.py            # Central analysis orchestrator
│       ├── mcp_server.py        # MCP server (10 tools)
│       └── visualizer/
│           ├── html_renderer.py # Interactive D3.js HTML
│           ├── dot_renderer.py  # Graphviz DOT
│           ├── text_renderer.py # Terminal text
│           └── json_renderer.py # JSON export
├── main.py                      # Entry point
├── pyproject.toml               # Build config (src layout)
├── hawkeye.toml                 # Example analysis config
├── README.md
└── SKILL.md                     # MCP development guide
```
