# Multi-language Expansion Plan (JS/TS First, Mixed-Language, Zero-Dependency)

## 1) Requirements Summary (from request)
- **Languages first**: JavaScript + TypeScript are the first targets.
- **Mixed-language analysis** is required (single project may include multiple languages).
- **Zero dependencies**: keep core install dependency-free; optional extras only if absolutely necessary.
- **Top-tier quality**: must outperform competitors (accuracy, correctness, speed, scalability).
- **No coding now**: deliver only this plan in a Markdown file.
- **Scalable architecture**: introduce a `languages/` folder to independently tune each language.
- **Preserve all existing functionality** (Python analysis, CLI, MCP tools, outputs, tests).

---

## 2) Current Status (as implemented)

### 2.1 Core Pipeline (Python-only)
**File discovery → AST parsing → Graph → Metrics → Insights → Outputs**
- `core/scanner.py`
  - Walks filesystem; **only `.py` files** are considered.
  - `ModuleInfo` is Python-centric (module naming via `__init__.py` and dotted paths).
  - LOC = non-blank, non-comment `#` lines.
- `core/analyzer.py`
  - Uses Python `ast` to parse file once.
  - Extracts imports, classes, functions, methods, and complexities (cyclomatic, cognitive).
  - Resolves imports to internal modules only.
- `core/symbols.py`
  - Builds symbol registry and symbol-level graph (import → symbol link).
- `core/graph.py`
  - Builds directed dependency graph for modules.
- `core/metrics.py`, `core/insights.py`, `core/cycles.py`
  - Computes coupling metrics, health, insights, cycle detection.
- `engine.py`
  - Orchestrates the pipeline; caches results; exposes unified context queries.
- CLI + MCP
  - Documentation and command help are Python-specific.

### 2.2 Coupling Points (Python assumptions)
- Scanner filters only `.py` extensions.
- Module name resolution assumes Python package rules (`__init__.py`).
- Analyzer assumes Python grammar and import syntax.
- Symbol extraction assumes Python classes/functions.
- Config (hawkeye.toml) and CLI descriptions refer to Python.
- Tests use Python-specific fixtures and assumptions.

---

## 3) Target Architecture Overview (Language-Agnostic Core)

### 3.1 New `languages/` Folder (Scalable, Independent Tuning)
Introduce a language adapter layer and keep **core algorithms language-agnostic**:

```
src/hawkeye/languages/
  __init__.py
  registry.py            # Load/register language adapters
  base.py                # LanguageAdapter interface
  python/
    __init__.py
    adapter.py           # Wrap existing Python logic
    parser.py            # Python AST helpers (current analyzer)
    naming.py            # Module naming rules
    metrics.py           # LOC rules (existing)
  javascript/
    __init__.py
    adapter.py
    lexer.py             # Custom JS tokenizer (zero deps)
    parser.py            # JS AST (imports/symbols/complexity)
    resolver.py          # Node/ESM/CJS module resolution
  typescript/
    __init__.py
    adapter.py
    lexer.py             # Shared with JS or TS-specific
    parser.py            # TS AST (interfaces/types)
    resolver.py          # TS resolution (tsconfig paths)
  shared/
    js_ts_common.py      # Shared grammar + utility logic
```

### 3.2 LanguageAdapter Interface (Key Abstraction)
All languages implement the same contract:
- **File discovery**
  - supported extensions
  - language-specific ignore rules
- **Module naming**
  - how to derive stable module IDs from file paths
- **Import extraction**
  - resolve internal dependencies
- **Symbol extraction**
  - classes/functions/methods (+ language-specific kinds)
- **Complexity metrics**
  - cyclomatic & cognitive
- **LOC counting**
  - comment syntax rules (`#`, `//`, `/* */`, etc.)
- **Parse error handling**
  - deterministic fallback when parse fails

This keeps the existing graph, metrics, and insights pipeline unchanged.

---

## 4) Mixed-Language Analysis Strategy

### 4.1 Unified Module Identity
To avoid name collisions, represent module identity as:
- `ModuleId = (language, module_name)`
- **Display name** keeps `module_name` for readability.
- **Graph keys** use a stable string format:
  - `py:project.core.engine`
  - `js:src/components/button`
  - `ts:src/types/user`

### 4.2 Cross-Language Dependencies
Mixed-language projects can have:
- **Same-language edges** (standard import resolution).
- **Cross-language edges** (optional, explicit mapping):
  - Config-driven mapping (e.g., `py:api.users` ↔ `ts:src/api/users.ts`).
  - Useful for full-stack mono-repos.

### 4.3 Output Consistency
All outputs include a `language` field:
- `hawkeye_file_context`
- JSON renderers
- CLI metrics / context outputs

---

## 5) Detailed JS/TS Support Plan (Zero Dependencies, Top Tier)

### 5.1 Module Resolution (Node + TS)
Implement **production-grade resolution** compatible with Node + TS:
- **ESM + CJS**:
  - `import ... from`, `export ... from`, dynamic `import()`, `require()`.
- **Path rules**:
  - `.js`, `.jsx`, `.ts`, `.tsx`, `.mjs`, `.cjs`.
  - directory `index.*` resolution.
- **`package.json`**:
  - `main`, `module`, `exports`, `types`.
  - `package.json` boundaries for package root.
- **`tsconfig.json`**:
  - `baseUrl`, `paths`, `rootDirs`, `references`.
- **Monorepo support**:
  - multiple `package.json` + `tsconfig.json`.

### 5.2 Parsing & AST (Zero Dependencies)
Implement a **custom tokenizer + parser**:
- Tokenizer covers:
  - identifiers, keywords, literals, template strings
  - punctuation, operators, comments
  - JSX/TSX tokens
- Parser extracts only what we need:
  - imports/exports
  - class/function declarations
  - method declarations
  - arrow functions, function expressions
  - `interface`, `type`, `enum` (TS)
- Complexity:
  - cyclomatic: count control-flow nodes
  - cognitive: nesting + branching

### 5.3 Symbol Semantics for JS/TS
Symbols tracked:
- **Functions**
  - `function foo()`
  - `const foo = () =>`
  - `export default function`
- **Classes**
  - `class Foo`, `export class Foo`
  - methods, constructors
- **TS-only**
  - `interface`, `type`, `enum`
  - abstract classes

Mapping to Hawkeye:
- `class` → class symbol
- `function` / `arrow` → function symbol
- `interface` / `type` → **abstractness contribution**

### 5.4 LOC Counting
Language-specific LOC rules:
- JS/TS: ignore `//` and `/* */` comments.
- Template strings and JSX handled as code, not comments.

### 5.5 Parse Failover
If the parser fails:
- Mark module `parse_error = True`.
- Return imports via regex fallback (best-effort).
- Preserve deterministic output.

---

## 6) Core System Changes Required

### 6.1 Scanner (`core/scanner.py`)
Changes:
- Scan by registered language extensions.
- `ModuleInfo` adds:
  - `language`
  - `module_id`
- Module naming delegated to adapter.
- LOC counting delegated to adapter.

### 6.2 Analyzer (`core/analyzer.py`)
Changes:
- Becomes language-neutral orchestrator.
- Delegates parsing to adapter.
- Aggregates results from multiple adapters.

### 6.3 Symbol Resolution (`core/symbols.py`)
Changes:
- SymbolId includes language.
- Allow new symbol kinds: `interface`, `type`, `namespace`.
- Preserve existing Python behavior.

### 6.4 Graph & Metrics
Minimal changes:
- Graph nodes keyed by `module_id`.
- Metrics unaffected, but include `language`.
- Insights/risk remain deterministic.

---

## 7) CLI, MCP, Config, Output Updates

### 7.1 Config (`hawkeye.toml`)
Add language settings:
```
[scan]
languages = ["python", "javascript", "typescript"]

[scan.language.javascript]
extensions = [".js", ".jsx", ".mjs", ".cjs"]

[scan.language.typescript]
extensions = [".ts", ".tsx"]
tsconfig = "tsconfig.json"
```

### 7.2 CLI
Updates:
- Change wording from “Python project” → “codebase”.
- Add `--languages` flag.
- Add JS/TS options: `--tsconfig`, `--package-root`.

### 7.3 MCP
Update tool descriptions:
- Language-agnostic.
- Allow `language` filter in queries.

### 7.4 Outputs
All renderers add `language` fields:
- text, json, dot, html.

---

## 8) Testing Strategy (High Coverage, Mixed Languages)

### 8.1 New Fixtures
Add:
- JS project fixture
- TS project fixture
- Mixed-language monorepo fixture

### 8.2 Test Categories
- Scanner tests per language.
- Analyzer import resolution (JS/TS).
- Symbol extraction accuracy.
- Complexity metrics (known cases).
- Mixed-language graph correctness.

### 8.3 Regression
Ensure all existing Python tests pass unchanged.

---

## 9) Performance & Scalability

- Cache per-language parse results.
- Reuse shared parser logic (JS/TS).
- Parallelize analysis by language (safe once adapters exist).
- Ensure deterministic outputs regardless of language order.

---

## 10) Quality & “Top-Tier” Goals

Define competitive benchmarks:
- Import resolution accuracy ≥ 95% (Node/TS spec).
- Complexity metrics match SonarSource equivalents.
- Mixed-language graphs with zero false edges.
- Large codebases (10k+ files) analyzed within seconds.

---

## 11) Rollout Phases

1. **Phase 1**: Language adapter scaffolding + Python adapter migration.
2. **Phase 2**: JS/TS scanning + imports only.
3. **Phase 3**: Full JS/TS symbols + complexity.
4. **Phase 4**: Mixed-language graph + config support.
5. **Phase 5**: Quality hardening + benchmarks.

---

## 12) Open Questions / Clarifications Needed
- Do we treat JS/TS monorepo workspaces as separate projects or unified?
- Should `node_modules` ever be partially analyzed?
- Should `@types` definitions be parsed for symbol extraction?
- Are cross-language dependencies explicitly provided or inferred?

---

## 13) Summary
This plan keeps Hawkeye **zero-dependency**, introduces a **languages adapter layer**, and preserves all existing Python functionality while enabling **JS/TS-first mixed-language analysis** with production-grade module resolution, symbol extraction, complexity metrics, and scalable architecture.
