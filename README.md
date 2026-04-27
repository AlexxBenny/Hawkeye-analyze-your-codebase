# 🦅 Hawkeye

**Python architectural intelligence engine — dependency analysis, symbol-level impact tracking, and MCP server for AI coding agents.**

Hawkeye gives AI editors (Claude Code, Cursor, Windsurf) full architectural awareness before they edit your code — preventing broken imports, hidden coupling, and circular dependencies.

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-195%20passed-brightgreen.svg)]()

---

## Installation

```bash
# From source (recommended during beta)
git clone https://github.com/AlexxBenny/Hawkeye-analyze-your-codebase.git
cd Hawkeye-analyze-your-codebase
pip install -e .

# With MCP server for AI editors
pip install -e ".[mcp]"
```

## Quick Start

```bash
# 1. Analyze any Python project
hawkeye analyze /path/to/project

# 2. Get full architectural context for a file
hawkeye context /path/to/project src/core/engine.py

# 3. Check symbol-level impact before refactoring
hawkeye impact /path/to/project src/core/engine.py -s Engine

# 4. Find coupling hotspots
hawkeye impact /path/to/project src/core/engine.py --hotspots

# 5. Find dead code
hawkeye impact /path/to/project src/core/engine.py --unused

# 6. Open interactive dependency graph
hawkeye show /path/to/project

# 7. Enforce architecture rules in CI
hawkeye check /path/to/project --no-cycles
```

---

## Why Hawkeye?

| Problem | How Hawkeye Solves It |
|---------|-----------------------|
| "I changed a class and 5 tests broke" | `hawkeye impact` shows blast radius **before** you edit |
| "This codebase has spaghetti imports" | `hawkeye analyze` maps the entire dependency graph |
| "Which module is the riskiest?" | `hawkeye metrics` ranks by instability + complexity |
| "Are there circular imports?" | `hawkeye check --no-cycles` detects and suggests fixes |
| "AI editor made a bad import" | MCP server gives the AI full context **before** it writes |

---

## CLI Commands (7)

| Command | Description |
|---------|-------------|
| `hawkeye analyze <path>` | Full project analysis (text/json/dot/html output) |
| `hawkeye context <path> <file...>` | Architectural context for one or more files |
| `hawkeye impact <path> <file>` | Symbol-level impact analysis, hotspots, dead code |
| `hawkeye show <path>` | Open interactive D3.js graph in browser |
| `hawkeye check <path>` | Enforce architecture rules (CI/CD exit codes) |
| `hawkeye metrics <path>` | Coupling + complexity metrics table |
| `hawkeye serve` | Start MCP server for AI editors |

### Example: `hawkeye analyze`

```
=== PROJECT SUMMARY: MyApp ===

  Modules:          20
  Dependencies:     40
  Total LOC:        2696
  Graph density:    0.1053
  Avg instability:  0.444
  Has cycles:       No ✅

  Health breakdown:
    ✅ Healthy:     9
    ⚠️  Warning:    5
    🔴 Critical:    6

── Module Metrics ──
Module                       Ca   Ce       I    LOC   Health
MyApp.core.graph              8    2   0.200    251     🔴
MyApp.core.metrics            5    1   0.167    144     ⚠️
MyApp.core.analyzer           3    1   0.250    328     🔴
MyApp.config                  4    0   0.000    102     ✅
```

### Example: `hawkeye impact --hotspots`

```
🔥 Symbol Hotspots (imported by ≥2 modules):

  DependencyGraph       (core.graph)     → 16 importers
  ModuleMetrics         (core.metrics)   → 10 importers
  HawkeyeEngine         (engine)         →  6 importers
```

### Example: `hawkeye impact --unused`

```
💀 Unused Symbols (5 found):

  EdgeInfo              (core.graph)        ← safe to make private
  analyze_file          (core.analyzer)     ← superseded by analyze_project
```

---

## AI Editor Integration (MCP)

Hawkeye exposes **10 MCP tools** designed for AI coding agents. Add to your editor's MCP config:

```json
{
  "mcpServers": {
    "hawkeye": {
      "command": "hawkeye-mcp",
      "args": ["--project", "/path/to/your/project"]
    }
  }
}
```

### MCP Tools

| Tool | Purpose |
|------|---------|
| `hawkeye_analyze(path)` | Scan project — call this first |
| **`hawkeye_file_context(file)`** | **Everything about a file in one call** — deps, dependents, impact, cycles, health |
| `hawkeye_context(files)` | Combined context for multi-file editing sessions |
| `hawkeye_impact(file, symbol, mode)` | Symbol-level blast radius, hotspots, dead code |
| `hawkeye_symbols(file)` | List all classes/functions with usage counts |
| `hawkeye_find(pattern)` | Search for modules by name |
| `hawkeye_cycles()` | Import cycles with severity and break suggestions |
| `hawkeye_metrics(sort_by)` | Coupling + complexity metrics for all modules |
| `hawkeye_path(source, target)` | Shortest dependency path between modules |
| `hawkeye_graph(max_depth)` | Full graph as structured JSON |

### Example: `hawkeye_file_context`

One call gives the AI agent everything it needs:

```json
{
  "module": "myapp.core.engine",
  "file": "core/engine.py",
  "loc": 340,
  "dependency_count": 3,
  "dependent_count": 8,
  "dependencies": [
    {"module": "myapp.core.scanner", "file": "core/scanner.py"},
    {"module": "myapp.core.analyzer", "file": "core/analyzer.py"}
  ],
  "dependents": [
    {"module": "myapp.cli", "file": "cli.py"},
    {"module": "myapp.server.mcp", "file": "server/mcp.py"}
  ],
  "impact": {"direct": 8, "transitive": 12},
  "metrics": {
    "ca": 8, "ce": 3, "instability": 0.273,
    "health": "critical",
    "cyclomatic_complexity": 45,
    "cognitive_complexity": 32
  }
}
```

---

## Architecture Rules

Define rules in `hawkeye.toml` and enforce them with `hawkeye check`:

```toml
[project]
name = "MyApp"

[scan]
exclude_dirs = ["venv", "__pycache__", ".git"]

# Enforce layered architecture (lower layers can't import higher ones)
[rules.layers]
order = ["models", "services", "api", "cli"]
direction = "downward"

# Block specific import patterns
[[rules.forbidden]]
from = "api.*"
to = ["cli.*", "scripts.*"]

# Ensure module groups are independent
[[rules.independence]]
modules = ["auth", "billing", "notifications"]
```

```bash
# CI/CD integration — exits non-zero on violations
hawkeye check /path/to/project --no-cycles
```

---

## Core Analysis Features

### Dependency Graph
- AST-based import resolution (relative, absolute, symbol-level)
- Directed graph with transitive closure, shortest path, neighborhood extraction
- Topological sort, depth filtering, subgraph extraction

### Coupling Metrics (Robert C. Martin)
- **Ca** — Afferent coupling (who depends on me)
- **Ce** — Efferent coupling (who do I depend on)
- **I** — Instability (Ce / (Ca + Ce)) — 0.0 = stable, 1.0 = unstable

### Complexity Metrics
- **Cyclomatic complexity** — decision branches per function
- **Cognitive complexity** — nesting-weighted (SonarSource specification)
- Per-function, per-class, and per-module aggregation

### Cycle Detection
- Tarjan's Strongly Connected Components (SCC) algorithm
- Severity scoring (low → critical based on cycle size + coupling)
- Break suggestions with specific edge recommendations

### Symbol Resolution
- Cross-file symbol registry (class X defined in module Y)
- Import → definition matching
- Hotspot detection (most-imported symbols)
- Dead code detection (defined but never imported)
- Symbol-level impact analysis (blast radius per class/function)

### Health Scoring
- Composite of coupling + complexity → **healthy** / **warning** / **critical**
- Per-module and project-level aggregation

---

## Visualization

### Interactive HTML (D3.js)
```bash
hawkeye show /path/to/project           # Opens in browser
hawkeye analyze /path/to/project -f html -o graph.html
```
Force-directed graph with search, zoom, drag, click-to-inspect. Color-coded by health status.

### Graphviz DOT
```bash
hawkeye analyze /path/to/project -f dot -o deps.dot
dot -Tpng deps.dot -o deps.png
```

### JSON
```bash
hawkeye analyze /path/to/project -f json
```

---

## Project Structure

```
Hawkeye/
├── src/hawkeye/
│   ├── engine.py               # Central orchestrator (9-step pipeline)
│   ├── config.py               # TOML config with walk-up discovery
│   ├── cli.py                  # 7 CLI commands
│   ├── core/                   # Analysis pipeline
│   │   ├── scanner.py          #   File discovery + LOC counting
│   │   ├── analyzer.py         #   AST imports + symbols + complexity
│   │   ├── graph.py            #   Directed graph + algorithms
│   │   ├── metrics.py          #   Coupling + complexity metrics
│   │   ├── cycles.py           #   Tarjan's SCC + severity scoring
│   │   ├── rules.py            #   Architecture rule enforcement
│   │   └── symbols.py          #   Cross-file symbol resolution
│   ├── server/                 # AI editor integration
│   │   └── mcp.py              #   10 MCP tools
│   └── visualizer/             # Output renderers
│       ├── html_renderer.py    #   Interactive D3.js graph
│       ├── dot_renderer.py     #   Graphviz DOT format
│       ├── text_renderer.py    #   Terminal tables + summaries
│       └── json_renderer.py    #   Structured JSON
├── tests/                      # 195 tests (pytest)
│   ├── conftest.py             #   Shared fixtures
│   ├── test_scanner.py         #   17 tests
│   ├── test_analyzer.py        #   22 tests
│   ├── test_graph.py           #   16 tests
│   ├── test_metrics.py         #   15 tests
│   ├── test_cycles.py          #   14 tests
│   ├── test_rules.py           #   16 tests
│   ├── test_symbols.py         #   27 tests
│   └── test_engine.py          #   22 tests
├── examples/                   # Usage examples
├── hawkeye.toml                # Example config
├── pyproject.toml              # pip install ready
└── LICENSE                     # MIT
```

**Zero required dependencies.** Core analysis runs on Python stdlib only. MCP server requires `pip install mcp`.

---

## Requirements

- Python 3.10+
- No dependencies for core analysis
- `mcp` package for AI editor integration (optional)

## License

MIT — see [LICENSE](LICENSE) for details.
