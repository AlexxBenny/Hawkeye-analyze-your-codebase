# 🦅 Hawkeye

**Python architectural intelligence engine — dependency analysis, coupling & complexity metrics, architecture enforcement, and MCP server for AI coding agents.**

Hawkeye gives AI editors (Claude Code, Cursor, Windsurf) full architectural awareness before they edit your code — preventing broken imports, hidden coupling, and circular dependencies.

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-271%20passed-brightgreen.svg)]()

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

# 2. Get full architectural context for a file (AI-ready JSON)
hawkeye context /path/to/project src/core/engine.py

# 3. Deep-dive metrics with function-level breakdown
hawkeye metrics /path/to/project --functions

# 4. Check symbol-level blast radius before refactoring
hawkeye impact /path/to/project src/core/engine.py -s Engine

# 5. Enforce architecture rules in CI/CD
hawkeye check /path/to/project --no-cycles

# 6. Open interactive dependency graph
hawkeye show /path/to/project

# 7. Start MCP server for AI editors
hawkeye serve -p /path/to/project
```

---

## Why Hawkeye?

| Problem | How Hawkeye Solves It |
|---------|-----------------------|
| "I changed a class and 5 tests broke" | `hawkeye impact` shows blast radius **before** you edit |
| "This codebase has spaghetti imports" | `hawkeye analyze` maps the entire dependency graph |
| "Which module is the riskiest?" | `hawkeye metrics --sort health` ranks by health status |
| "Are there circular imports?" | `hawkeye check --no-cycles` detects and suggests fixes |
| "Where is the real complexity hiding?" | `hawkeye metrics --functions` shows per-method hotspots |
| "Is this module over-concrete?" | `hawkeye metrics --sort distance` flags zone-of-pain modules |
| "AI editor made a bad import" | MCP server gives the AI full context **before** it writes |

---

## CLI Commands (7)

| Command | Description |
|---------|-------------|
| `hawkeye analyze <path>` | Full project analysis (text/json/dot/html output) |
| `hawkeye context <path> <file...>` | AI-ready architectural context for one or more files |
| `hawkeye metrics <path>` | Coupling + complexity + Martin metrics table |
| `hawkeye impact <path> <file>` | Symbol-level blast radius, hotspots, dead code |
| `hawkeye check <path>` | Enforce architecture rules (CI/CD exit codes) |
| `hawkeye show <path>` | Open interactive D3.js graph in browser |
| `hawkeye serve` | Start MCP server for AI editors |

Every command has detailed help: `hawkeye <command> --help`

### Example: `hawkeye metrics --functions`

```
📊 Metrics: MyApp
   21 modules | 4045 LOC | density 0.1452
   Health: ✅ 6  ⚠️  6  🔴 9

───────────────────────────────────────────────────────────────────────────────────
Module                                Ca  Ce      I   CC  Cog     A     D   LOC   Health
───────────────────────────────────────────────────────────────────────────────────
myapp.engine                          8   5  0.385   45   92  0.00  0.62   340     🔴
myapp.core.analyzer                   4   2  0.333   33   68  0.00  0.67   406     🔴
myapp.config                          7   0  0.000   10   18  0.00  1.00   102     ✅
───────────────────────────────────────────────────────────────────────────────────

🔬 Per-Function Complexity (top 30):

  Symbol                                  Module                   CC  Line
  ──────────────────────────────────────────────────────────────────────────
  Engine.get_file_context                 myapp.engine             34   251
  Analyzer._extract_imports               myapp.core.analyzer      20   229
  Engine.get_batch_context                myapp.engine             15   400
```

### Example: `hawkeye context`

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
    "cognitive_complexity": 32,
    "abstractness": 0.0,
    "distance_main_seq": 0.727
  },
  "insights": ["extreme_cyclomatic", "extreme_cognitive", "wide_transitive_reach"],
  "risk_profile": "amplifier"
}
```

### Example: `hawkeye impact --hotspots`

```
🔥 Symbol Hotspots (imported by ≥2 modules):

  DependencyGraph       (core.graph)     → 16 importers
  ModuleMetrics         (core.metrics)   → 10 importers
  HawkeyeEngine         (engine)         →  6 importers
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

# Ensure module groups are independent (transitive — catches indirect paths)
[[rules.independence]]
modules = ["auth", "billing", "notifications"]

# Only auth modules may import secrets
[[rules.protected]]
modules = ["core.secrets", "core.tokens"]
allowed_importers = ["auth.*"]

# Sibling services must not form cycles
[[rules.acyclic_siblings]]
ancestor = "services"
```

```bash
# CI/CD integration — exits non-zero on violations
hawkeye check /path/to/project --no-cycles
```

### Rule Types (5)

| Rule | Description |
|------|-------------|
| **forbidden** | Hard-block specific import patterns |
| **protected** | Only allowlisted modules may import protected targets |
| **layers** | Enforce directional dependency flow between layers |
| **independence** | No transitive paths between independent module groups |
| **acyclic_siblings** | Sibling packages under an ancestor must not form cycles |

---

## Threshold Configuration

Tune health and insight sensitivity with profiles:

```toml
[thresholds]
profile = "strict"  # "default", "strict", or "relaxed"

# Override individual thresholds
cyclomatic_high = 15
cognitive_high = 20
```

| Profile | Cyclomatic High | Cognitive High | Instability Critical |
|---------|----------------|----------------|---------------------|
| default | 20 | 30 | 0.8 |
| strict | 10 | 15 | 0.7 |
| relaxed | 30 | 50 | 0.9 |

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
| **`hawkeye_file_context(file)`** | **Everything about a file in one call** — deps, dependents, impact, cycles, health, insights |
| `hawkeye_context(files)` | Combined context for multi-file editing sessions |
| `hawkeye_impact(file, symbol, mode)` | Symbol-level blast radius, hotspots, dead code |
| `hawkeye_symbols(file)` | List all classes/functions with usage counts |
| `hawkeye_find(pattern)` | Search for modules by name |
| `hawkeye_cycles()` | Import cycles with severity and break suggestions |
| `hawkeye_metrics(sort_by)` | Full metrics for all modules |
| `hawkeye_path(source, target)` | Shortest dependency path between modules |
| `hawkeye_graph(max_depth)` | Full graph as structured JSON |

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
- **A** — Abstractness (abstract classes / total classes)
- **D** — Distance from Main Sequence (|A + I - 1|) — 0.0 = ideal

### Complexity Metrics
- **Cyclomatic complexity** — decision branches per function
- **Cognitive complexity** — nesting-weighted (SonarSource specification)
- Per-function, per-method, per-class, and per-module aggregation

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

### Deterministic Insights
- 18 insight codes derived from metrics (no advice, no bias)
- Risk profiles: hub, volatile, amplifier, tangled, fragile
- Zone detection: Zone of Pain (rigid), Zone of Uselessness (abstract)
- Token-efficient encoding: compact mode adds ~5-15 tokens, 0 for healthy modules

### Health Scoring
- Composite of coupling + complexity → **healthy** / **warning** / **critical**
- Configurable thresholds with profiles (default, strict, relaxed)
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
│   ├── cli.py                  # 7 CLI commands with detailed help
│   ├── core/                   # Analysis pipeline
│   │   ├── scanner.py          #   File discovery + LOC counting
│   │   ├── analyzer.py         #   AST imports + symbols + complexity
│   │   ├── graph.py            #   Directed graph + algorithms
│   │   ├── metrics.py          #   Coupling + complexity + Martin metrics
│   │   ├── cycles.py           #   Tarjan's SCC + severity scoring
│   │   ├── rules.py            #   5 architecture rule types
│   │   ├── insights.py         #   Deterministic signal derivation
│   │   └── symbols.py          #   Cross-file symbol resolution
│   ├── server/                 # AI editor integration
│   │   └── mcp.py              #   10 MCP tools
│   └── visualizer/             # Output renderers
│       ├── html_renderer.py    #   Interactive D3.js graph
│       ├── dot_renderer.py     #   Graphviz DOT format
│       ├── text_renderer.py    #   Terminal tables + summaries
│       └── json_renderer.py    #   Structured JSON
├── tests/                      # 271 tests (pytest)
│   ├── conftest.py             #   Shared fixtures
│   ├── test_scanner.py
│   ├── test_analyzer.py
│   ├── test_graph.py
│   ├── test_metrics.py
│   ├── test_cycles.py
│   ├── test_rules.py
│   ├── test_insights.py
│   ├── test_symbols.py
│   └── test_engine.py
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
