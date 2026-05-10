# 🦅 Hawkeye

**Architectural intelligence for AI coding agents.** One call gives your AI editor full context about a file — dependencies, blast radius, cycles, health — before it writes a single line.

[![PyPI](https://img.shields.io/pypi/v/hawkeye-analyzer.svg)](https://pypi.org/project/hawkeye-analyzer/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-350%20passed-brightgreen.svg)]()

---

## The Problem

AI coding agents edit files without knowing the architecture. They:
- Break imports they didn't know existed
- Refactor classes used by 20 other modules
- Create circular dependencies
- Miss that a "simple change" cascades through 34 files

**Hawkeye fixes this.** It gives the AI the same architectural awareness a senior engineer has — in one deterministic, token-efficient JSON call.

---

## Setup for AI Editors (MCP)

Hawkeye exposes **12 tools** via [Model Context Protocol](https://modelcontextprotocol.io/). Install and configure in under 60 seconds:

### 1. Install

```bash
pip install hawkeye-analyzer
```

This installs everything: MCP server, Python/JavaScript/TypeScript analysis.

### 2. Add to your editor's MCP config

**Antigravity / Gemini** (`~/.gemini/antigravity/mcp_config.json`):
```json
{
  "mcpServers": {
    "hawkeye": {
      "command": "hawkeye-mcp",
      "args": []
    }
  }
}
```
No `--project` needed — the agent calls `hawkeye_analyze(project_path)` dynamically with whatever workspace is active. Works for any project without config changes.

**Gemini CLI** (`~/.gemini/settings.json`):
```json
{
  "mcpServers": {
    "hawkeye": {
      "command": "hawkeye-mcp",
      "args": []
    }
  }
}
```

**Claude Code** (`~/.claude/claude_desktop_config.json`):
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

**Cursor** (`.cursor/mcp.json` in project root):
```json
{
  "mcpServers": {
    "hawkeye": {
      "command": "hawkeye-mcp",
      "args": ["--project", "."]
    }
  }
}
```

**Windsurf / Other MCP clients** — same pattern. The server uses stdio transport.

> **Two modes:** Pass `--project /path` to pre-analyze on startup (faster first query, locked to one project). Or pass no args and call `hawkeye_analyze()` on demand (works for any project, ~5s on first use). Multi-project caching is supported — switching projects doesn't require re-analysis.

### 3. Done

The AI editor now has access to 12 architectural intelligence tools. The most important one:

```
hawkeye_file_context("src/core/engine.py")
```

Returns everything the agent needs in **one call** (v0.6 compact format):

```json
{
  "file": "core/engine.py",
  "loc": 340,
  "arch_role": "orchestrator",
  "health": "elevated",
  "cc": 36,
  "cog": 66,
  "ca": 2,
  "ce": 6,
  "I": 0.75,
  "deps": [
    "core/scanner.py",
    "core/analyzer.py",
    "core/graph.py"
  ],
  "dependents": [
    "cli.py",
    "server/mcp.py"
  ],
  "transitive_impact": 12,
  "edit_cost": {
    "files": 2,
    "cascade": 12,
    "tokens": 4280,
    "risk": "medium"
  },
  "insights": ["high_cyclomatic", "wide_transitive_reach"],
  "risk": "hub",
  "churn": "hot"
}
```

---

## Design Principles

Hawkeye is built specifically for AI agent consumption:

| Principle | How |
|-----------|-----|
| **Deterministic** | Same code → same output. No randomness, no LLM in the loop. Pure AST + graph algorithms. |
| **Token-efficient** | v0.6 compact format: flat paths, short keys. ~120 tokens for a healthy module, ~200 for a complex one. |
| **One-call context** | `hawkeye_file_context` replaces 5+ separate queries. One tool call = full architectural picture. |
| **Adaptive metrics** | Health thresholds calibrate to each project's percentile distribution. No universal magic numbers. |
| **Architecture-aware** | Betweenness centrality + Ca percentile classify modules as `core`, `orchestrator`, or `hub-by-design`. A core module being complex is expected, not alarming. |
| **Fast** | Single-pass AST parsing. 281 modules analyzed in ~5 seconds. Results cached for the session. |
| **Lightweight** | Pure Python AST for Python, tree-sitter for JS/TS. Minimal dependencies, fast install. |

### Token Budget

| Scenario | Tokens added to context |
|----------|------------------------|
| Healthy module, no issues | ~120 tokens |
| Module with warnings | ~180 tokens |
| Critical module with cycles | ~250 tokens |
| Batch context (3 files) | ~350 tokens |
| Graph summary (62 modules) | ~450 tokens |
| Impact hotspots (15 entries) | ~400 tokens |
| Git churn in compact mode | ~3 tokens |
| Hotspot ranking (5 files) | ~262 tokens |

Compare this to dumping raw `import` statements or `grep` results — Hawkeye gives the AI **structured, pre-analyzed** architectural data at a fraction of the token cost.

---

## MCP Tools Reference

After calling `hawkeye_analyze(project_path)` once, all other tools are available:

| Tool | Purpose | When to use |
|------|---------|-------------|
| **`hawkeye_file_context(file)`** | Everything about a file — deps, dependents, impact, cycles, health, insights, risk. Supports `min_severity` filter. | **Before editing any file** |
| `hawkeye_context(files)` | Combined context for multi-file edits — shared deps, combined blast radius | Before editing 2+ related files |
| `hawkeye_impact(file, symbol)` | Symbol-level blast radius, hotspots, or unused detection (framework-aware) | Before renaming/refactoring a class or function |
| `hawkeye_symbols(file)` | List all classes/functions with usage counts and decorators | Understanding what a module exports |
| `hawkeye_find(pattern)` | Search modules by name | Discovering module names |
| `hawkeye_cycles()` | All import cycles with severity, kind, and break suggestions | Checking for circular dependencies |
| `hawkeye_metrics(sort_by, limit)` | Coupling + complexity table for all modules | Finding the riskiest modules |
| `hawkeye_path(source, target)` | Shortest dependency path between two modules | Understanding how modules are connected |
| `hawkeye_hotspots(limit, days)` | Rank files by complexity × git churn — the real risk | Finding files that are both complex AND actively changing |
| `hawkeye_graph()` | Structural overview — top hubs, edge count, density (~450 tokens) | Understanding project architecture at a glance |

### Recommended Agent Workflow

```
1. hawkeye_analyze("/path/to/project")     — scan once on startup
2. hawkeye_file_context("file_to_edit.py") — before every edit
3. hawkeye_impact("file.py", "ClassName")  — before refactoring a symbol
4. hawkeye_cycles()                         — after creating new imports
```

---

## Interpreting the Output

### Insight Codes

Machine-readable labels derived deterministically from metrics. No natural language, no ambiguity:

| Code | Severity | What it means |
|------|----------|---------------|
| `high_instability` | warning | Many outgoing deps, few incoming — volatile |
| `highly_stable` | info | Many incoming deps — changes here propagate widely |
| `high_efferent` | warning | Depends on too many modules |
| `high_afferent` | warning | Too many modules depend on this |
| `extreme_cyclomatic` | critical | Very high branching complexity (CC ≥ 50) |
| `extreme_cognitive` | critical | Deeply nested control flow (Cog ≥ 50) |
| `high_cyclomatic` | warning | Elevated branching complexity (CC ≥ 20) |
| `high_cognitive` | warning | Moderately nested control flow (Cog ≥ 25) |
| `critical_blast_radius` | critical | ≥10 modules directly depend on this |
| `high_blast_radius` | warning | ≥5 modules directly depend on this |
| `very_large_module` | warning | ≥500 LOC |
| `in_cycle` | critical/warning | Involved in an import cycle |
| `zone_of_pain` | warning | Concrete + stable = rigid, hard to extend (non-core modules only) |
| `core_module` | info | Core architectural component — concrete + stable by design |
| `zone_of_uselessness` | warning | Abstract + unstable = possibly unused abstractions |
| `well_balanced` | info | On the main sequence (good A/I balance) |
| `isolated` | info | No internal dependencies or dependents |
| `high_fan_out` | info | Imports many modules (high coordination surface) |
| `wide_transitive_reach` | info | Transitive impact much wider than direct |
| `core_high_cc` | info | High cyclomatic complexity (structural in `arch_role=core` modules) |
| `core_high_cog` | info | High cognitive complexity (structural in `arch_role=core` modules) |
| `core_wide_reach` | info | Wide blast radius (expected for `arch_role=core` modules) |

### Risk Profiles

Single-token classification of a module's structural role:

| Label | Meaning | Agent should... |
|-------|---------|-----------------|
| `hub` | High dependents + high complexity | Check `arch_role` — if `core`, verify interfaces; if absent, edit with extreme care |
| `tangled` | Involved in import cycles | Fix the cycle before adding more imports |
| `fragile` | High complexity + high instability | Likely to break — add tests first |
| `volatile` | High instability + many outgoing deps | Unstable foundation — minimize changes |
| `amplifier` | Changes cascade widely (transitive >> direct) | Check transitive dependents before editing |
| `null` | No structural risk | Safe to edit freely |

### Health Labels

Five-level composite assessment (monotonic severity):

| Label | Emoji | Meaning |
|-------|-------|---------|
| `healthy` | ✅ | No coupling or complexity concerns |
| `moderate` | 🟡 | Mild elevation in one dimension |
| `elevated` | 🟠 | Notable complexity or coupling. If `arch_role=core`: structural — safe to edit |
| `high` | 🔴 | High risk in multiple dimensions |
| `critical` | 🔥 | Extreme values — needs decomposition |
| `unknown` | ❓ | File could not be parsed (syntax error) |

> **Note:** `health` reflects *effective* health, adjusted for architectural role. Core modules cap at `elevated` (complexity is structural, not pathological). Raw metric-based health is available as `raw_health` in full mode.

---

## CLI for Humans

Hawkeye also works as a standalone CLI:

```bash
pip install hawkeye-analyzer

# Full project analysis
hawkeye analyze ./myproject

# Interactive dependency graph in your browser
hawkeye show ./myproject

# Metrics deep-dive with per-function complexity
hawkeye metrics ./myproject --sort health --functions

# Symbol blast radius
hawkeye impact ./myproject src/engine.py -s Engine

# CI gate — fails on rule violations or import cycles
hawkeye check ./myproject --no-cycles

# AI-ready JSON context
hawkeye context ./myproject src/engine.py

# Git hotspots — complexity × churn
hawkeye hotspots ./myproject
hawkeye hotspots ./myproject --days 30 --limit 10
```

### Output Formats

| Command | Formats |
|---------|---------|
| `hawkeye analyze` | `--format text` (default), `json`, `html`, `dot` |
| `hawkeye metrics` | text (default), `--json`, `--functions` |
| `hawkeye impact` | text (default), `--json`, `--hotspots`, `--unused` (framework-aware) |
| `hawkeye context` | JSON only (designed for machine consumption) |
| `hawkeye hotspots` | text (default), `--json`, `--days N`, `--limit N` |

---

## Configuration

Place a `hawkeye.toml` in your project root. Hawkeye auto-discovers it by walking up from the project directory.

### `.hawkeyeignore`

For quick exclusions without editing TOML, create a `.hawkeyeignore` file in your project root:

```
# Tests and fixtures
*.tests.*
*.test_*
conftest

# Generated code
*.generated.*
*.pb2
```

Each non-blank, non-comment line is treated as a glob exclude pattern. Patterns are merged with any `exclude_patterns` from `hawkeye.toml`.

### Minimal `hawkeye.toml`

```toml
[project]
name = "MyProject"

[scan]
exclude_patterns = ["*.tests.*", "*.test_*"]  # Keep test modules out of coupling analysis
```

### Architecture Rules

```toml
# Enforce layered architecture
[rules.layers]
order = ["models", "services", "api", "cli"]
direction = "downward"

# Block specific imports
[[rules.forbidden]]
from = "api.*"
to = ["cli.*", "scripts.*"]

# Module groups must be independent (transitive — catches indirect paths too)
[[rules.independence]]
modules = ["auth", "billing", "notifications"]

# Only auth may import secrets
[[rules.protected]]
modules = ["core.secrets", "core.tokens"]
allowed_importers = ["auth.*"]

# Sibling services must not form cycles
[[rules.acyclic_siblings]]
ancestor = "services"
```

### Framework Detection

Hawkeye automatically detects framework entry points — symbols decorated with `@app.get()`, `@pytest.fixture`, `@celery_app.task`, etc. These are excluded from unused symbol detection to eliminate false positives.

The built-in registry covers **pytest, FastAPI, Flask, Django, Celery, Click, SQLAlchemy**, and standard library decorators. Add project-specific patterns in your TOML config:

```toml
[scan.framework_decorators]
add = ["my_framework.endpoint", "register_handler"]  # merged with defaults
# replace = true    # set true to fully override defaults
```

### Threshold Tuning

By default, Hawkeye uses **adaptive percentile thresholds** that calibrate to each project's complexity distribution. A module is only `critical` if it's in the top 5% of its project — not by arbitrary universal constants.

To disable percentiles and use fixed thresholds:

```toml
[thresholds]
use_percentiles = false   # Fall back to static thresholds
profile = "strict"         # "default", "strict", or "relaxed"
cc_critical = 40           # Override individual values
loc_critical = 600
```

Percentile floors prevent tiny projects from having meaningless criticals:

```toml
[thresholds]
cc_floor_critical = 30    # Minimum CC for "critical" even if P95 is lower
cc_floor_high = 15
cog_floor_critical = 30
cog_floor_high = 15
```

| Profile | CC warn/crit | Cog warn/crit | LOC warn/crit | Dependents warn/crit |
|---------|-------------|---------------|---------------|---------------------|
| **default** | 20 / 50 | 25 / 50 | 300 / 500 | 5 / 10 |
| **strict** | 10 / 30 | 15 / 30 | 200 / 300 | 3 / 5 |
| **relaxed** | 30 / 80 | 40 / 80 | 500 / 1000 | 10 / 20 |

> **Note:** When `use_percentiles = true` (default), these static values serve as fallback floors. The actual thresholds are computed from your project's CC/Cog distribution.

<details>
<summary>All threshold keys</summary>

| Key | Default | Controls |
|-----|---------|----------|
| `use_percentiles` | true | Enable adaptive percentile-based thresholds |
| `cc_floor_critical` | 30 | Minimum CC for critical (percentile floor) |
| `cc_floor_high` | 15 | Minimum CC for high (percentile floor) |
| `cog_floor_critical` | 30 | Minimum Cog for critical (percentile floor) |
| `cog_floor_high` | 15 | Minimum Cog for high (percentile floor) |
| `instability_high` | 0.8 | `high_instability` insight trigger |
| `instability_low` | 0.2 | `highly_stable` insight trigger |
| `ce_high` | 8 | Efferent coupling warning |
| `ca_high` | 8 | Afferent coupling warning |
| `cc_high` | 20 | Cyclomatic → warning (static fallback) |
| `cc_critical` | 50 | Cyclomatic → critical (static fallback) |
| `cog_high` | 25 | Cognitive → warning (static fallback) |
| `cog_critical` | 50 | Cognitive → critical (static fallback) |
| `loc_high` | 300 | `large_module` insight |
| `loc_critical` | 500 | `very_large_module` insight |
| `dependents_high` | 5 | Blast radius → warning |
| `dependents_critical` | 10 | Blast radius → critical |
| `dependencies_high` | 6 | `high_fan_out` insight |
| `cycle_size_high` | 4 | Cycle → critical severity |
| `distance_high` | 0.5 | Zone of pain / uselessness trigger |
| `distance_low` | 0.2 | `well_balanced` trigger |
| `abstract_high` | 0.8 | Highly abstract classification |
| `abstract_low` | 0.2 | Concrete classification |

</details>

---

## How It Works

```
Source files (Py/JS/TS) → Language-specific parsing → Import resolution → Dependency graph
                                                                      ↓
                    Symbol registry ← Symbol extraction     Graph algorithms
                         ↓                                        ↓
                  Symbol-level impact              Coupling metrics (Ca/Ce/I/A/D)
                  Hotspot detection                Complexity metrics (CC/Cog)
                  Dead code detection (fw-aware)   Cycle detection (Tarjan's SCC)
                                                   Import classification
                                                   Health classification
                                                   Insight derivation
                                                         ↓
                                              Deterministic JSON output
```

- **Single AST pass** per file — no re-parsing, no multiple traversals
- **Tarjan's SCC** for cycle detection — O(V+E), mathematically optimal
- **Import classification** — distinguishes `runtime`, `TYPE_CHECKING`, and `deferred` imports for intelligent cycle triage
- **BFS reachability** for transitive impact — cached per session
- **Brandes' algorithm** for betweenness centrality — O(VE), identifies architectural bridges
- **Robert C. Martin's metrics** — Ca, Ce, Instability, Abstractness, Distance
- **SonarSource spec** for cognitive complexity — nesting-weighted, not just branch counting
- **LOC = code lines only** — blank lines and `#` comment lines are excluded. A file with 1,800 raw lines may report ~1,400 LOC. This is the more useful metric for complexity assessment

### Data Storage

**All analysis data lives in RAM only.** There is no database, no cache file, no `.hawkeye/` directory. The MCP server holds the dependency graph, metrics, and symbol registry in-process for the duration of the session. When the server stops (editor closes), all data is discarded. Next session re-analyzes from scratch — which takes ~5 seconds for a 300-module project.

---

## Performance

| Metric | Value |
|--------|-------|
| 281 modules, 58K LOC | ~5 seconds full analysis |
| Incremental queries after analysis | <10ms per call |
| Memory | Graph + metrics cached in-process |
| Install time | ~5 seconds |
| MCP server startup with pre-analysis | ~6 seconds |

---

## Project Structure

```
src/hawkeye/
├── engine.py           # Central orchestrator (CC=36, 261 LOC)
├── context.py          # AI context builder (stateless, pure functions)
├── config.py           # TOML config with walk-up discovery
├── cli/                # CLI subpackage
│   ├── __init__.py     # Parser + main() entry point
│   ├── commands.py     # 7 command handlers
│   ├── _helpers.py     # Engine creation + UTF-8 setup
│   └── __main__.py     # python -m support
├── core/
│   ├── models.py       # Leaf: ModuleInfo + utilities (I=0.125)
│   ├── scanner.py      # File discovery
│   ├── analyzer.py     # AST imports + symbols + complexity
│   ├── graph.py        # Directed graph + algorithms
│   ├── metrics.py      # Ca/Ce/I/A/D + health scoring
│   ├── cycles.py       # Tarjan's SCC + severity + kind
│   ├── rules.py        # 5 architecture rule types
│   ├── insights.py     # Deterministic insight derivation
│   ├── git_history.py  # Git churn, hotspots, rename tracking
│   └── symbols.py      # Cross-file symbol resolution
├── languages/          # Multi-language support
│   ├── base.py         # Adapter protocol
│   ├── registry.py     # Adapter factory
│   ├── python/         # Python adapter
│   ├── javascript/     # JavaScript adapter
│   ├── typescript/     # TypeScript adapter
│   └── shared/         # Tree-sitter JS/TS parsing engine
├── server/
│   └── mcp.py          # 12 MCP tools
└── visualizer/
    ├── html_renderer.py    # Interactive D3.js graph
    ├── dot_renderer.py     # Graphviz DOT
    ├── text_renderer.py    # Terminal tables
    └── json_renderer.py    # Structured JSON
```

62 modules, 10,302 LOC, 0 import cycles. 350 tests across 12 test files. Python 3.10+.

## License

MIT — see [LICENSE](LICENSE) for details.
