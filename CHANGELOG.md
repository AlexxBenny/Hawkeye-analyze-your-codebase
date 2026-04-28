# Changelog

All notable changes to Hawkeye will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.2] - 2026-04-28

### Added
- **Martin Metrics**: Abstractness (A = abstract classes / total classes) and Distance from Main Sequence (D = |A + I - 1|). Conservative high-confidence detection for `ABC`, `Protocol`, `ABCMeta`, and `@abstractmethod` patterns.
- **Zone Insights**: `zone_of_pain` (rigid, concrete), `zone_of_uselessness` (abstract, unstable), and `well_balanced` derived from A/D thresholds.
- **Protected Rules**: Only allowlisted modules may import protected targets (`[[rules.protected]]`).
- **Acyclic Siblings Rules**: Sibling packages under an ancestor must not form cycles (`[[rules.acyclic_siblings]]`). Uses Tarjan's SCC on sibling-level subgraph; intra-sibling cycles are allowed.
- **Threshold Profiles**: `default`, `strict`, and `relaxed` presets with per-key TOML overrides (`[thresholds]`).
- **Per-Method Function Breakdown**: `hawkeye metrics --functions` now shows individual methods (e.g., `Engine.get_file_context`) with per-method cyclomatic complexity. Previously only showed class-level aggregates.
- **Sort Options**: Added `--sort abstractness` and `--sort distance` to the metrics command.
- **Structured Config Types**: `ProtectedConfig` and `AcyclicSiblingsConfig` dataclasses replace raw dicts for type-safe rule configuration.
- **CLI Help Text**: Comprehensive descriptions, usage examples, and epilogs for all 7 commands and the main parser.
- **Threshold Profile in JSON**: `metrics --json` now includes `threshold_profile` field for reproducibility.

### Fixed
- **Independence Rule (transitive)**: Fixed critical correctness bug where independence checks only detected direct edges. Now uses BFS reachability (O(V+E)) to detect transitive paths (e.g., `auth → core → billing`), with `find_path()` for violation explanation.
- **Unified Output Architecture**: Eliminated 3 separate table renderers and 2 JSON serializers. All output paths now use:
  - `ModuleMetrics.to_dict()` — single canonical serialization (14 fields)
  - `format_metrics_table()` — single table renderer (Ca, Ce, I, CC, Cog, A, D, LOC, Health)
  - `sort_metrics()` — single sort function (eliminates duplicated sort logic)
- **Per-Function Breakdown Bug**: Fixed dead `for method_node in []:` loop that prevented class methods from appearing in the function breakdown.
- **JSON Completeness**: `analyze -f json` and `metrics --json` now output all 14 metric fields (was missing 8+ fields including LOC, CC, Cog, A, D, class/function/method counts).
- **Text Renderer**: Module info display now includes CC, Cog, Abstractness, and Distance (was showing only Ca, Ce, I, Health).

### Changed
- **Unified ThresholdConfig**: All 19 numeric thresholds consolidated into a single `ThresholdConfig` dataclass, eliminating inconsistent hardcoded magic numbers across `insights.py`, `metrics.py`, and `engine.py`.
- **Rule Evaluation Order**: Defined explicit precedence: forbidden → protected → layers → independence → acyclic_siblings.
- **Metrics Table**: All output paths (analyze, metrics) now show identical 10-column table.
- **README**: Complete rewrite reflecting current features, 271 tests, 5 rule types, Martin metrics, threshold configuration.
- **Test Suite**: 271 tests (was 240). New coverage for zone detection, transitive independence, protected rules, acyclic siblings.

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
