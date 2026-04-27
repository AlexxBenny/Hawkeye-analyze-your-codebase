# Changelog

All notable changes to Hawkeye will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1] - 2026-04-28

### Fixed
- `--output` flag now auto-appends file extension based on `--format` (e.g., `--output graph` + `--format html` → `graph.html`)
- `hawkeye show --output` also auto-appends `.html` when missing
- Removed deprecated `License :: OSI Approved :: MIT License` classifier for Python 3.13 compatibility
- Sorted all imports with isort for consistent code style

## [0.1.0] - 2026-04-28

### Added
- **Core Analysis Pipeline**
  - AST-based import resolution (relative, absolute, symbol-level)
  - Directed dependency graph with BFS/DFS, transitive closure, shortest path
  - Coupling metrics: Ca (afferent), Ce (efferent), Instability (I = Ce/(Ca+Ce))
  - Cyclomatic complexity and cognitive complexity (SonarSource specification)
  - Symbol extraction: classes, functions, methods per module
  - Health scoring: composite of coupling + complexity → healthy/warning/critical

- **Cycle Detection**
  - Tarjan's SCC algorithm
  - Severity scoring (low → critical based on cycle size + coupling)
  - Break-edge suggestions with specific recommendations

- **Architecture Rules** (`hawkeye.toml`)
  - Layer ordering enforcement
  - Forbidden import patterns
  - Independence contracts
  - CI/CD-compatible exit codes

- **Symbol Resolution**
  - Cross-file symbol registry with globally unique IDs
  - Import → definition matching (`resolve_references()`)
  - Symbol-level dependency graph with forward/reverse edges
  - Hotspot detection (most-imported symbols)
  - Dead code detection (defined but never imported)
  - Symbol-level blast radius analysis

- **Deterministic Insights**
  - 15 insight codes derived from metrics (no advice, no bias)
  - Risk profile classification: hub, volatile, amplifier, tangled, fragile
  - Token-efficient encoding: compact mode adds ~5-15 tokens, 0 for healthy modules

- **CLI Commands** (7)
  - `hawkeye analyze` — full project analysis (text/json/dot/html)
  - `hawkeye context` — architectural context for files
  - `hawkeye impact` — symbol-level impact analysis, hotspots, dead code
  - `hawkeye show` — interactive D3.js graph in browser
  - `hawkeye check` — architecture rule enforcement
  - `hawkeye metrics` — coupling + complexity table
  - `hawkeye serve` — MCP server for AI editors

- **MCP Server** (10 tools)
  - `hawkeye_analyze` — scan project
  - `hawkeye_file_context` — everything about a file in one call
  - `hawkeye_context` — batch multi-file context
  - `hawkeye_impact` — symbol-level blast radius
  - `hawkeye_symbols` — list symbols with usage counts
  - `hawkeye_find` — module search
  - `hawkeye_cycles` — cycle reporting
  - `hawkeye_metrics` — coupling metrics
  - `hawkeye_path` — shortest dependency path
  - `hawkeye_graph` — full graph JSON

- **Visualization**
  - Interactive D3.js force-directed graph (HTML)
  - Graphviz DOT output
  - Structured JSON output
  - Terminal text summaries and tables

- **Test Suite**
  - 240 tests across 10 test files
  - Full coverage of scanner, analyzer, graph, metrics, cycles, rules, symbols, insights, engine

- **Documentation**
  - Comprehensive README with installation, quickstart, feature docs
  - 3 runnable examples with sample project
  - GitHub Actions CI pipeline

### Technical Details
- Zero required dependencies (Python stdlib only)
- MCP server requires optional `mcp` package
- Python 3.10+ required
- MIT License
