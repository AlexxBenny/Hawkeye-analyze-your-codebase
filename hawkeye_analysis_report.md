# 🦅 Hawkeye — Independent Codebase Audit & Competitive Analysis

> **Methodology**: Every claim below is cross-referenced against the actual source code in `src/hawkeye/`. Competitor data is pulled from GitHub, PyPI, and official documentation as of April 2026.

---

## 1. Codebase Inventory (Verified)

| File | Lines | Role |
|------|------:|------|
| `engine.py` | 457 | Central orchestrator, caching, file resolution |
| `cli.py` | 216 | 6 CLI commands via argparse |
| `config.py` | 123 | TOML config + walk-up discovery |
| `core/scanner.py` | 138 | File discovery, LOC counting |
| `core/analyzer.py` | 406 | AST imports + symbols + complexity |
| `core/graph.py` | 305 | Directed graph + algorithms |
| `core/metrics.py` | 180 | Ca/Ce/Instability + health scoring |
| `core/cycles.py` | 213 | Tarjan SCC + severity + break suggestions |
| `core/rules.py` | 188 | Layer/forbidden/independence rules |
| `server/mcp.py` | 332 | 8 MCP tools for AI editors |
| `visualizer/html_renderer.py` | 383 | D3.js interactive force graph |
| `visualizer/text_renderer.py` | 187 | Terminal summaries |
| `visualizer/dot_renderer.py` | 133 | Graphviz DOT output |
| `visualizer/json_renderer.py` | ~100 | Structured JSON output |
| **Total** | **~3,400** | **15 Python files** |

Zero required dependencies. MCP server optionally requires `pip install mcp`.

---

## 2. ChatGPT Claim Verification — Point by Point

### 2.1 Where ChatGPT Is Correct

#### ✅ "Coupling metrics (Ca, Ce, Instability) — real software architecture analysis"
**CONFIRMED.** [metrics.py L75-120](file:///d:/ALEX/CODING/Hawkeye/src/hawkeye/core/metrics.py#L75-L120) computes:
- `Ca` = `len(graph.reverse_adj.get(module))` — afferent coupling
- `Ce` = `len(graph.adjacency.get(module))` — efferent coupling  
- `I = Ce / (Ca + Ce)` — instability per Robert C. Martin

Health scoring factors in both coupling AND complexity thresholds. This is genuine.

#### ✅ "Tarjan SCC — not beginner-level"
**CONFIRMED.** [cycles.py L41-89](file:///d:/ALEX/CODING/Hawkeye/src/hawkeye/core/cycles.py#L41-L89) implements textbook Tarjan's with:
- `lowlinks`, `indices`, `on_stack` tracking
- Recursion limit auto-scaling for large projects
- Post-SCC cycle extraction via DFS with deduplication (normalized tuple comparison)
- Cycle cap at 50 per SCC and max length 10 to prevent explosion
- Severity scoring and break-edge heuristics

This is non-trivial. The break suggestion heuristic ([cycles.py L145-171](file:///d:/ALEX/CODING/Hawkeye/src/hawkeye/core/cycles.py#L145-L171)) that considers import count and target Ca is a genuine algorithmic contribution.

#### ✅ "Config-driven rules (TOML)"
**CONFIRMED.** [config.py L59-108](file:///d:/ALEX/CODING/Hawkeye/src/hawkeye/config.py#L59-L108) loads TOML with:
- Walk-up directory search for `hawkeye.toml`
- Python 3.10 compatibility via `tomli` fallback
- Three rule types: `LayerConfig`, `RulesConfig.forbidden`, `RulesConfig.independence`

#### ⚠️ "MD5 caching + refresh() → qualifies as incremental"
**OVERSTATED.** The [refresh() method](file:///d:/ALEX/CODING/Hawkeye/src/hawkeye/engine.py#L117-L138) does detect changes via MD5 hashing, but look at lines 133-136:
```python
if changed:
    # Re-run full analysis (incremental graph update is complex;
    # full re-analysis is fast enough for most projects)
    self.analyze(self._project_root)
```
This is **change detection**, not incremental analysis. If ANY file changes, it re-runs the ENTIRE pipeline. The code's own comment admits this. ChatGPT calling this "incremental" is technically defensible but misleading — it's more accurate to say "change-aware full re-analysis."

#### ✅ "D3 interactive graph — real interactivity"
**CONFIRMED.** [html_renderer.py](file:///d:/ALEX/CODING/Hawkeye/src/hawkeye/visualizer/html_renderer.py) is 383 lines generating a self-contained HTML file with:
- Force-directed simulation with collision detection
- Zoom/pan via D3 zoom behavior
- Click-to-highlight neighborhood (dims non-neighbors)
- Search box with live filtering
- Details sidebar showing Ca/Ce/Instability/Health
- Cycle edges highlighted in red with arrow markers
- Node radius scaled by coupling
- Health-based stroke coloring (green/yellow/red)
- Drag-to-reposition nodes

This is genuinely interactive, not a static SVG dump.

#### ✅ "MCP tooling — suggests system thinking"
**CONFIRMED.** [server/mcp.py](file:///d:/ALEX/CODING/Hawkeye/src/hawkeye/server/mcp.py) exposes 8 tools:
1. `hawkeye_analyze` — project scanning
2. `hawkeye_file_context` — **the key tool** — everything about a file in one call
3. `hawkeye_context` — batch multi-file context
4. `hawkeye_find` — module search
5. `hawkeye_cycles` — cycle reporting
6. `hawkeye_metrics` — coupling metrics
7. `hawkeye_path` — shortest dependency path
8. `hawkeye_graph` — full graph JSON

All tools have proper `annotations` (`readOnlyHint`, `idempotentHint`, etc.). The `hawkeye_file_context` tool's design — combining deps, dependents, impact, cycles, complexity, and related files in ONE call — is genuinely well-thought-out for AI agent consumption.

### 2.2 What ChatGPT Missed That Hawkeye Actually Has

ChatGPT didn't acknowledge several non-trivial features:

1. **Cyclomatic + Cognitive Complexity** ([analyzer.py L140-211](file:///d:/ALEX/CODING/Hawkeye/src/hawkeye/core/analyzer.py#L140-L211)) — Full SonarSource-spec cognitive complexity with nesting weights, plus standard cyclomatic complexity. This is integrated into health scoring.

2. **Topological Sort** ([graph.py L246-269](file:///d:/ALEX/CODING/Hawkeye/src/hawkeye/core/graph.py#L246-L269)) — Kahn's algorithm implementation for build ordering.

3. **Graph Filtering with Depth Collapsing** ([graph.py L168-242](file:///d:/ALEX/CODING/Hawkeye/src/hawkeye/core/graph.py#L168-L242)) — Creates filtered subgraphs with module collapsing at configurable depth. Supports include/exclude patterns.

4. **Related Files Computation** ([engine.py L430-456](file:///d:/ALEX/CODING/Hawkeye/src/hawkeye/engine.py#L430-L456)) — Finds cycle partners + shared-dependency neighbors. This is useful context for AI agents.

5. **Batch Context with Cross-File Analysis** ([engine.py L326-408](file:///d:/ALEX/CODING/Hawkeye/src/hawkeye/engine.py#L326-L408)) — Combined blast radius, shared dependencies, cycle warnings, and architecture violations across multiple files. No competitor offers this.

---

## 3. ChatGPT Gap Analysis — Verification

### 3.1 "No Semantic Resolution" — ✅ CORRECT

**Verified.** [analyzer.py L314-357](file:///d:/ALEX/CODING/Hawkeye/src/hawkeye/core/analyzer.py#L314-L357) extracts symbol definitions (classes, functions, methods) but **only within each module independently**. There is no cross-module symbol resolution.

What this means concretely:
- Hawkeye knows `class IntentEngine` exists in `cortex/intent_engine.py`
- But does NOT know that `main.py` calls `IntentEngine.run()`
- The dependency graph tracks `main → cortex.intent_engine` at import level, but not which specific symbols are used

**Impact:** Call graphs are impossible without this. "If I rename method X, what breaks?" cannot be answered.

### 3.2 "No Architectural Constraint Language" — ⚠️ PARTIALLY WRONG

ChatGPT overstates this gap. Looking at [rules.py](file:///d:/ALEX/CODING/Hawkeye/src/hawkeye/core/rules.py), Hawkeye supports **exactly the same 3 contract types** as import-linter:

| Contract Type | import-linter | Hawkeye | Notes |
|--------------|:---:|:---:|-------|
| Layer ordering | ✅ | ✅ | Both enforce directional layer deps |
| Forbidden imports | ✅ | ✅ | Both use pattern matching |
| Independence | ✅ | ✅ | Both enforce mutual isolation |
| Custom contracts | ✅ | ❌ | import-linter supports plugins |
| Composability | ✅ | ❌ | import-linter allows multiple contracts |

The gap is real but **not critical** — it's about extensibility, not missing core contracts. Hawkeye's rules cover 90% of real-world use cases. The missing piece is plugin-based custom contract types.

### 3.3 "No Temporal Intelligence" — ✅ CORRECT

No snapshot storage, no comparison over time, no drift detection. Every run is a fresh point-in-time analysis. The MD5 hashes are ephemeral (in-memory only, lost when the process exits).

### 3.4 "No Developer Workflow Integration" — ⚠️ PARTIALLY WRONG

ChatGPT ignores that the **MCP server IS developer workflow integration** — and arguably a more advanced form of it than PR comments. When an AI editor has Hawkeye connected:
- It gets full architectural context BEFORE editing
- It sees blast radius for changes
- It gets cycle warnings in real-time

What IS missing:
- ❌ GitHub PR annotations
- ❌ Pre-commit hooks
- ❌ VS Code extension  
- ❌ Inline diff comments

But calling this "no developer workflow integration" when MCP integration exists is inaccurate.

### 3.5 "No Scale Validation" — ✅ CORRECT

No benchmarks exist. Additionally, the recursive Tarjan implementation ([cycles.py L61](file:///d:/ALEX/CODING/Hawkeye/src/hawkeye/core/cycles.py#L61)) could hit Python's stack limit on very deep graphs despite the recursion limit increase. The `_extract_cycles_from_scc` DFS ([cycles.py L101-117](file:///d:/ALEX/CODING/Hawkeye/src/hawkeye/core/cycles.py#L101-L117)) is also recursive and capped at depth 10, which is pragmatic but means some cycles might be missed.

### 3.6 "No Competitive Moat" — ⚠️ PARTIALLY WRONG

ChatGPT says "everything you built can be replicated in ~2–4 weeks." This undersells two things:

1. **MCP integration is a real differentiator** — No Python architecture tool (import-linter, pydeps, Tach) currently ships an MCP server. This is genuinely novel.

2. **The unified analysis-to-AI pipeline** — The `get_file_context()` and `get_batch_context()` methods that combine deps + dependents + impact + cycles + complexity + related files in one token-efficient call don't exist anywhere else.

However, ChatGPT is right that these are **thin moats** — they could be replicated. The question is whether Hawkeye can establish adoption before others add MCP support.

---

## 4. Competitor Deep-Dive (Real Data)

### 4.1 import-linter (seddonym/import-linter)

| Metric | Value |
|--------|-------|
| GitHub Stars | ~1,000 |
| Forks | 79 |
| Commits | 517 |
| Releases | 47 |
| License | BSD-2-Clause |
| Language | Python 95.2% |
| Dependencies | `grimp` (import graph engine), `click`, `typing-extensions` |

**What it does:**
- Defines **contracts** in `.importlinter` config or `setup.cfg`
- Three contract types: `layers`, `independence`, `forbidden`
- Uses `grimp` library for import graph building (separate mature library)
- Has a **browser-based UI** for architecture exploration
- Supports **custom contract types** via plugin system
- Pre-commit hooks support
- Comprehensive docs on ReadTheDocs

**What it does NOT do:**
- ❌ No coupling metrics (Ca/Ce/Instability)
- ❌ No complexity metrics
- ❌ No interactive D3 visualization
- ❌ No MCP / AI editor integration
- ❌ No impact analysis
- ❌ No cycle break suggestions
- ❌ No symbol extraction

**Key insight:** import-linter is a **rule enforcement tool**, not an analysis engine. It answers "does my code follow the rules?" but not "what is the health of my architecture?"

### 4.2 pydeps (thebjorn/pydeps)

| Metric | Value |
|--------|-------|
| GitHub Stars | ~2,100 |
| Dependencies | `Graphviz` (external system dependency) |
| Focus | Visualization only |

**What it does:**
- Generates SVG/PNG dependency graphs via Graphviz
- "Bacon number" filtering (hop distance from target)
- Basic cycle detection (highlight only, no analysis)
- Configuration via `.pydeps`, `pyproject.toml`, or `setup.cfg`
- Can show external dependencies

**What it does NOT do:**
- ❌ No coupling metrics
- ❌ No complexity metrics
- ❌ No architecture rule enforcement
- ❌ No MCP / AI integration
- ❌ No impact analysis
- ❌ No cycle severity/break suggestions
- ❌ No interactive visualization (static image output)
- ❌ No symbol extraction

**Key insight:** pydeps is a **visualization tool**. Period. Hawkeye is categorically more advanced.

### 4.3 Tach (tach-org/tach)

| Metric | Value |
|--------|-------|
| GitHub Stars | ~2,700 |
| Core Language | **Rust** (Python wrapper) |
| License | MIT |
| VS Code Extension | Yes (`gauge-sh/tach-vscode`) |

**What it does:**
- Defines **module boundaries** with explicit dependency declarations
- **Public interface enforcement** — flag imports that bypass declared interfaces
- `tach init` — interactive boundary definition
- `tach check` — boundary validation (CI-compatible)
- `tach sync` — auto-update constraints to match actual code
- `tach show` — dependency graph visualization
- **Deprecation tracking** — mark dependencies as deprecated, surface usage without errors
- **Caching** for fast re-checks
- **VS Code extension** with inline feedback
- Layer enforcement
- `tach-ignore` for gradual adoption

**What it does NOT do:**
- ❌ No coupling metrics (Ca/Ce/Instability)
- ❌ No complexity metrics (cyclomatic/cognitive)
- ❌ No MCP / AI editor integration
- ❌ No cycle break suggestions (detects but doesn't advise)
- ❌ No impact analysis (transitive blast radius)
- ❌ No interactive D3 visualization
- ❌ No batch file context for AI agents

**Key insight:** Tach is the **most mature product** in this space. Its Rust core gives genuine performance advantage. Its VS Code extension and `tach sync` are killer features for adoption. But it's focused on **boundary enforcement**, not architectural analysis.

### 4.4 snakefood

**DEAD.** Not maintained. Does not support Python 3.x. The project docs state a significant rewrite would be required. ChatGPT listing this as a current competitor is incorrect — it's historical only.

### 4.5 CodeSee

**Acquired by GitKraken (May 2024).** Technology being integrated into GitKraken platform. No longer an independent tool. Not a relevant competitor.

### 4.6 Sourcegraph

Enterprise-grade, multi-language, cross-repository intelligence platform. Different tier entirely. Not a direct competitor for a Python-specific architecture tool. However, Sourcegraph now offers **MCP support**, which means it's a potential threat in the AI-context-for-editors space.

---

## 5. Competitive Feature Matrix

| Feature | Hawkeye | import-linter | pydeps | Tach |
|---------|:---:|:---:|:---:|:---:|
| **Import Graph** | ✅ | ✅ (via grimp) | ✅ | ✅ |
| **Ca/Ce/Instability** | ✅ | ❌ | ❌ | ❌ |
| **Cyclomatic Complexity** | ✅ | ❌ | ❌ | ❌ |
| **Cognitive Complexity** | ✅ | ❌ | ❌ | ❌ |
| **Symbol Extraction** | ✅ | ❌ | ❌ | ❌ |
| **Health Scoring** | ✅ | ❌ | ❌ | ❌ |
| **Layer Rules** | ✅ | ✅ | ❌ | ✅ |
| **Forbidden Rules** | ✅ | ✅ | ❌ | ❌ |
| **Independence Rules** | ✅ | ✅ | ❌ | ❌ |
| **Custom Contracts** | ❌ | ✅ | ❌ | ❌ |
| **Public Interfaces** | ❌ | ❌ | ❌ | ✅ |
| **Deprecation Tracking** | ❌ | ❌ | ❌ | ✅ |
| **Cycle Detection** | ✅ (Tarjan) | ❌ | ⚠️ basic | ✅ |
| **Cycle Break Suggestions** | ✅ | ❌ | ❌ | ❌ |
| **Cycle Severity Ranking** | ✅ | ❌ | ❌ | ❌ |
| **Impact Analysis** | ✅ | ❌ | ❌ | ❌ |
| **Interactive D3 Graph** | ✅ | ❌ | ❌ | ❌ |
| **Graphviz DOT** | ✅ | ❌ | ✅ | ❌ |
| **MCP Server** | ✅ (8 tools) | ❌ | ❌ | ❌ |
| **AI Agent Optimization** | ✅ | ❌ | ❌ | ❌ |
| **Batch File Context** | ✅ | ❌ | ❌ | ❌ |
| **VS Code Extension** | ❌ | ❌ | ❌ | ✅ |
| **Pre-commit Hooks** | ❌ | ✅ | ❌ | ✅ |
| **Rust Performance** | ❌ | ❌ | ❌ | ✅ |
| **Zero Dependencies** | ✅ | ❌ | ❌ | ❌ |
| **Incremental Sync** | ❌ | ❌ | ❌ | ✅ (`tach sync`) |
| **Browser UI** | ✅ (D3) | ✅ | ❌ | ❌ |
| **Test Suite** | ❌ | ✅ | ✅ | ✅ |
| **Published on PyPI** | ❌ | ✅ | ✅ | ✅ |
| **Documentation Site** | ❌ | ✅ | ✅ | ✅ |

### Key Takeaway

Hawkeye has the **widest feature breadth** of any tool in this space. No single competitor matches its combination of metrics + rules + visualization + AI integration. But Hawkeye has the **lowest product maturity** — no tests, no PyPI, no docs site, no extensions.

---

## 6. Corrected Scoring (vs ChatGPT's Assessment)

| Dimension | ChatGPT Score | My Score | Rationale |
|-----------|:---:|:---:|-----------|
| Engineering Quality | 8.2/10 | **7.5/10** | Clean architecture, good separation, non-trivial algorithms. But: zero tests, recursive Tarjan could stack overflow, refresh() isn't truly incremental, no error recovery in AST parsing. |
| Analytical Depth | 6.5/10 | **6.0/10** | Import graph + coupling + complexity + symbols is solid. But: no cross-module symbol resolution, no call graph, symbols are isolated per-module. Impact analysis is at module level only. |
| Product Maturity | 5/10 | **3.5/10** | ChatGPT was generous. No test suite. No CI/CD. Not on PyPI. No changelog. No documentation site. No examples directory. No benchmarks. No pre-commit hooks. These are table stakes for any "product." |
| Differentiation | 4/10 | **5.5/10** | ChatGPT undersold this. MCP integration is genuinely unique — zero competitors have it. AI-optimized output design (compact mode, batch context, file resolution) is novel. Zero-dependency architecture is unusual. |

### Composite Assessment

**Hawkeye is a strong analysis ENGINE with a weak product SHELL.**

The core algorithms and architecture are legitimate. The AI integration angle is genuinely novel. But everything around the core — testing, packaging, documentation, developer experience — is missing.

---

## 7. What ChatGPT Got Wrong (Summary)

| Claim | Verdict | Reality |
|-------|---------|---------|
| "refresh() is incremental" | ⚠️ Overstated | Change detection only; re-runs full pipeline |
| "No architectural constraint language (Critical)" | ⚠️ Overstated | Has same 3 contract types as import-linter |
| "No developer workflow integration" | ⚠️ Wrong | MCP server IS workflow integration |
| "No competitive moat" (4/10) | ⚠️ Undersold | MCP + AI-optimized output is genuinely unique |
| "Product maturity 5/10" | ⚠️ Oversold | No tests/PyPI/docs = 3.5/10 at best |
| "snakefood" as competitor | ❌ Wrong | Dead project, no Python 3 support |
| "CodeSee" as competitor | ❌ Wrong | Acquired by GitKraken, no longer independent |
| "more advanced than pydeps" | ✅ Correct | Categorically more advanced |
| "approaching import-linter territory" | ✅ Correct | Similar rules, plus metrics + viz + MCP |

---

## 8. Strategic Roadmap (Corrected Priorities)

ChatGPT's priorities are partially right but miss the most critical gaps.

### 🔴 Priority 0: Product Foundation (ChatGPT MISSED this entirely)
**Before ANY new features, fix the product shell:**

1. **Test suite** — Even 50% coverage transforms credibility
2. **Publish to PyPI** — `pip install hawkeye-analyzer` must work
3. **CI/CD pipeline** — GitHub Actions for tests + linting
4. **Documentation site** — Even a simple MkDocs deployment
5. **Changelog** — Track what changes between versions

> Without these, nothing else matters. No one adopts a tool without tests or pip install.

### 🟠 Priority 1: Symbol Resolution → Call Graph
**ChatGPT is right here.** This is the foundation for everything else.
- Cross-file resolution: know that `main.py` uses `IntentEngine.run()`
- Method-level edges in the dependency graph
- Enables: "If I change X, what breaks at symbol level?"

### 🟡 Priority 2: Impact Analysis Engine
**ChatGPT is right.** High value, low competition.
- "If I change function X → what breaks?"
- Reverse dependency graph at symbol level
- Propagation analysis with confidence scores

### 🟢 Priority 3: Developer Experience Polish
**ChatGPT's Priority 5 should be higher:**
- **Pre-commit hook** — trivial to add, huge for adoption
- `hawkeye init` command (like `tach init`) — interactive setup
- `hawkeye sync` command (like `tach sync`) — auto-update rules
- GitHub Actions template in README

### 🔵 Priority 4: Architectural Drift Detection
**ChatGPT is right but this comes AFTER product foundation.**
- Save snapshots to `.hawkeye/` directory
- Compare: "coupling increased by 23%"
- Detect: "new cycle introduced in this PR"

### 🟣 Priority 5: AI Layer
**ChatGPT is right that this is your unfair advantage.**
- Explain cycles in plain English
- Suggest refactors based on coupling patterns
- Detect architectural anti-patterns
- This leverages your MERLIN system knowledge

### ❌ Agree With ChatGPT — Do NOT Do:
- ❌ Multi-language support (too early, too complex)
- ❌ More renderers (zero adoption leverage)
- ❌ Fancy UI upgrades (the D3 graph is already good enough)
- ❌ More metrics for the sake of metrics

---

## 9. The Real Competitive Position

```
                    Analysis Depth
                         ▲
                         │
           Sourcegraph   │
           (enterprise)  │
                         │
                         │    ┌─────────┐
                         │    │ HAWKEYE │ ← widest breadth, weakest product
                         │    │ (HERE)  │
                         │    └─────────┘
          import-linter  │         Tach
          (rules-deep)   │    (product-mature)
                         │
              pydeps     │
           (viz-only)    │
                         │
    ─────────────────────┼──────────────────────► Product Maturity
                         │
```

### Where Hawkeye Wins
1. **Only tool with MCP integration** — no competitor has this
2. **Widest feature breadth** — metrics + rules + viz + AI in one package
3. **Zero dependencies** — easiest to install and embed
4. **AI-first design** — compact mode, batch context, file resolution

### Where Hawkeye Loses
1. **No tests** — immediate credibility gap
2. **Not on PyPI** — friction kills adoption
3. **No VS Code extension** — Tach has one
4. **No Rust performance** — Tach is faster at scale
5. **No pre-commit hooks** — import-linter and Tach have them
6. **No documentation site** — all competitors have one

### The Bottom Line

> **Hawkeye has built the most feature-complete Python architecture analysis engine that nobody can install.**
>
> The core is genuinely strong. The AI angle is genuinely novel. But without test coverage, PyPI publishing, and basic documentation, it's an impressive engineering exercise, not a product.
>
> Fix the product shell first. Then the AI + MCP angle becomes a real competitive advantage that could leapfrog established tools.

