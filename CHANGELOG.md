# Changelog

All notable changes to Hawkeye will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.0] - 2026-04-28

### Added
- **Framework-aware unused symbol detection**: Symbols decorated with known framework entry point decorators are no longer falsely reported as "unused" by `hawkeye impact --unused` or `hawkeye_impact(mode="unused")`. This eliminates false positives for FastAPI routes, pytest fixtures, Celery tasks, Flask endpoints, Django admin, Click commands, and more.
- **Decorator extraction**: `SymbolInfo` now carries a `decorators: list[str]` field populated during AST parsing. Handles `@decorator`, `@module.decorator`, and `@app.get("/path")` call patterns.
- **`DEFAULT_FRAMEWORK_DECORATORS`**: Built-in registry of 30+ decorator patterns covering pytest, FastAPI/Starlette, Flask, Django, Celery, Click, SQLAlchemy, dataclass, and standard library decorators (`property`, `staticmethod`, `classmethod`, `abstractmethod`).
- **Configurable framework decorators**: New `framework_entry_decorators` field on `HawkeyeConfig`. TOML configuration via `[scan.framework_decorators]` with `add` (merge with defaults) and `replace` (override defaults) modes.
- **MCP output enhancements**: `hawkeye_symbols` now includes decorator lists per symbol. `hawkeye_impact(mode="unused")` adds a `framework_filtered` flag indicating whether framework detection is active.
- **22 new tests** in `test_framework_detection.py` covering decorator extraction, framework matching, unused filtering, config loading, and integration with real AST parsing.

### Changed
- **`SymbolGraph.unused_symbols()`**: Now accepts an optional `framework_decorators` parameter. Backward-compatible — `None` preserves original behavior.
- **CLI `impact --unused`**: Passes framework decorator config from engine settings.
- **MCP `hawkeye_impact(mode="unused")`**: Passes framework decorator config from engine settings.

### Performance
- **307 tests** passing (was 285 in v0.3.0, +22 framework detection tests).
- **0 import cycles** in Hawkeye's own codebase (maintained from v0.3.0).
- **60 modules**, 8,744 LOC.

## [0.3.0] - 2026-04-28

### ⚠️ Breaking Changes
- **`ModuleInfo` moved**: Canonical import is now `from hawkeye.core.models import ModuleInfo`. The old import `from hawkeye.core.scanner import ModuleInfo` still works (re-exported) but is deprecated.
- **CLI is now a package**: `hawkeye.cli` changed from a single module to a subpackage (`cli/__init__.py`, `cli/commands.py`, `cli/_helpers.py`). The public entry point `hawkeye.cli:main` is unchanged.

### Added
- **`core/models.py`**: Zero-dependency leaf module containing `ModuleInfo`, `count_lines`, and `path_to_module`. This is the most-depended-on module (Ca=7) with near-zero instability (I=0.125), by design.
- **`context.py`**: Stateless context builder extracted from the engine. Pure functions (`build_file_context`, `build_batch_context`, `compute_related`) that accept explicit data dependencies — independently testable.
- **Import classification**: Imports are now classified as `runtime`, `type_only` (inside `TYPE_CHECKING` blocks), or `deferred` (inside function bodies). Cycle detection uses this to distinguish safe vs dangerous cycles.
- **Cycle kind field**: Each detected cycle now carries a `kind` field (`runtime`, `type_only`, `deferred`). A cycle is "safe" only if **every** edge is non-runtime.
- **`py.typed` marker**: PEP 561 compliance — added to `pyproject.toml` package-data so type checkers recognize Hawkeye as a typed package.
- **`__all__` exports**: Added to `hawkeye/__init__.py` and `core/__init__.py` for clean star-import control.
- **`cli/__main__.py`**: Enables `python -m hawkeye.cli` execution.

### Fixed
- **29 import cycles eliminated → 0**: Root cause was `ModuleInfo` living inside `scanner.py` (the cycle hub, participating in all 29 cycles). Extracting it to `models.py` broke every cycle chain.
- **Python adapter cycle**: Changed `python/adapter.py` from top-level `from ...core import analyzer` to a deferred import inside `analyze_project()`, eliminating the adapter→core→scanner→registry→adapter chain.
- **JS/TS regex masking bug**: Fixed a bug that cleared target imports before analysis in JavaScript/TypeScript files.

### Changed
- **Engine decomposition**: `engine.py` reduced from 582 → 345 LOC (-41%), CC from 99 → 36 (-64%), Cog from 177 → 66 (-63%). Context-building logic delegated to `context.py`.
- **CLI split**: `cli.py` (623 LOC monolith) → `cli/` subpackage (4 files, 547 LOC total). Parser in `__init__.py`, 7 command handlers in `commands.py`, shared helpers in `_helpers.py`.
- **Scanner slimmed**: `scanner.py` reduced from 173 → 94 LOC. `ModuleInfo`, `count_lines`, and `path_to_module` moved to `models.py`; scanner re-exports for backward compatibility.
- **Canonical Tarjan**: Consolidated two separate SCC implementations into one in `core/cycles.py`. Removed the duplicate from `core/rules.py`.
- **JS/TS shared code**: Consolidated ~120 lines of duplicate regex patterns and `extract_block` logic into `languages/shared/js_ts_common.py`.

### Performance
- **285 tests** passing (was 278 in v0.2.0, +7 import classification tests).
- **0 import cycles** in Hawkeye's own codebase (was 29 in v0.2.0).
- **37 modules**, 5,591 LOC, graph density 0.0833.

## [0.2.0] - 2026-04-28

### ⚠️ Breaking Changes
- **Health labels**: Expanded from 3 (`healthy`/`warning`/`critical`) to 5 monotonic severity levels (`healthy`/`moderate`/`elevated`/`high`/`critical`) plus `unknown` for unparseable files.
- **ProjectMetrics**: `modules_warning` field removed, replaced by `modules_high`, `modules_elevated`, `modules_moderate`, and `modules_unknown`.
- **MCP output**: `hawkeye_analyze` health breakdown now returns all 6 labels instead of 3.

### Fixed
- **Critical: Silent false negatives on corrupted files** — Files that fail AST parsing (syntax errors, encoding issues) were silently reported as `health: "healthy"` with `CC=1, functions=0, classes=0`. Hawkeye now sets `health: "unknown"` and `parse_error: true`, and fires a `parse_failed` critical insight. Corrupted files will never be classified as healthy again.

### Added
- **Parse error detection**: `SymbolTable.parse_error` flag tracks AST parse failures at source. Propagated through `ModuleMetrics`, file context, and MCP output.
- **`parse_failed` insight**: Critical-severity insight fires when a file cannot be parsed, making failures impossible to miss.
- **Intermediate thresholds**: `cc_moderate`/`cc_elevated` and `cog_moderate`/`cog_elevated` in `ThresholdConfig` for finer-grained health classification.
- **All threshold profiles updated**: `strict` and `relaxed` profiles now cover all 5 health levels consistently.
- **274 tests** (was 274, all updated for new health system).

### Changed
- **`_assess_health`**: Rewritten with 5-level monotonic severity scale. Uses combined signals (complexity + coupling + instability) instead of single-metric triggers.
- **Health emojis**: ✅ healthy, 🟡 moderate, 🟠 elevated, 🔴 high, 🔥 critical, ❓ unknown.
- **Text/JSON/MCP renderers**: All output paths updated for 5-level health breakdown.

## [0.1.4] - 2026-04-28

### Changed
- **README**: Complete rewrite with AI-editor-first positioning. Leads with MCP integration, token efficiency, and deterministic output — human CLI is secondary.
- **PyPI description**: Updated to reflect AI agent focus: "Architectural intelligence for AI coding agents — one call gives your editor full context before it edits."
- **Documentation structure**: Added "Interpreting the Output" reference (insight codes, risk profiles, health labels with thresholds), MCP tools reference table, recommended agent workflow, and token budget estimates.

### Added
- **MCP setup examples**: Copy-paste config snippets for Claude Code, Cursor, and Windsurf.
- **Troubleshooting section**: Covers common issues (test module I=1.0, `--functions` output visibility, `--no-cycles` flag, Windows UTF-8).
- **Performance table**: Documented analysis speed (281 modules in ~5s), query latency (<10ms), and install time (<1s).

### Removed
- Internal assessment file (`hawkeye_assessment.md`) — testing artifact, not user-facing.

## [0.1.3] - 2026-04-28

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
  - Health scoring: composite of coupling + complexity → healthy/warning/critical (3-level, replaced in v0.2.0)

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
