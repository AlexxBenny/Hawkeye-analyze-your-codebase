"""Cross-file symbol resolution and reference tracking.

Connects import-side references (what was imported) to definition-side
symbols (what was defined), building a project-wide symbol registry
and a symbol-level reference graph.

This module sits between the analyzer (per-file extraction) and the
graph (module-level edges), adding symbol-level granularity without
modifying either.

Data flow:
    analyzer.SymbolTable  ─┐
                           ├──► SymbolRegistry ──► SymbolGraph
    analyzer.ResolvedImport┘
"""

from dataclasses import dataclass, field
from typing import Optional

from .analyzer import ImportDetail, ResolvedImport, SymbolInfo, SymbolTable

# ── Data types ────────────────────────────────────────────────


@dataclass(frozen=True)
class SymbolId:
    """Globally unique identifier for a symbol.

    Combines module name + symbol name + kind to avoid collisions
    between a class Foo and a function Foo in different modules.
    """
    module: str
    name: str
    kind: str  # 'class', 'function', 'method'

    def __str__(self) -> str:
        return f"{self.module}::{self.name}"

    @property
    def qualified_name(self) -> str:
        return f"{self.module}.{self.name}"


@dataclass
class SymbolDefinition:
    """A symbol definition with its location and metadata."""
    id: SymbolId
    info: SymbolInfo
    line: int
    end_line: int


@dataclass
class SymbolReference:
    """A cross-module reference: module A uses symbol X from module B.

    Tracks the specific import line and whether the reference could
    be resolved to an actual definition.
    """
    source_module: str           # Who is importing
    target_module: str           # Where the symbol lives
    symbol_name: str             # Name of the symbol (e.g., "Engine")
    line: int                    # Import line in source
    resolved: bool = False       # True if matched to a SymbolDefinition
    target_symbol: Optional[SymbolId] = None  # Resolved target (if found)

    def __str__(self) -> str:
        status = "→" if self.resolved else "→?"
        target = self.target_symbol or f"{self.target_module}.{self.symbol_name}"
        return f"{self.source_module}:{self.line} {status} {target}"


@dataclass
class SymbolEdge:
    """A directed edge in the symbol-level graph."""
    source: SymbolId       # The symbol doing the importing (or module-level)
    target: SymbolId       # The symbol being imported
    lines: list[int] = field(default_factory=list)


# ── Registry ─────────────────────────────────────────────────


class SymbolRegistry:
    """Project-wide lookup from symbol names to their definitions.

    Handles name collisions (same symbol name in multiple modules)
    by storing all definitions and disambiguating via module context.
    """

    def __init__(self) -> None:
        # name → list of definitions (handles collisions)
        self._by_name: dict[str, list[SymbolDefinition]] = {}
        # module → list of definitions
        self._by_module: dict[str, list[SymbolDefinition]] = {}
        # SymbolId → SymbolDefinition (unique lookup)
        self._by_id: dict[SymbolId, SymbolDefinition] = {}

    @classmethod
    def build(
        cls,
        symbol_tables: dict[str, SymbolTable],
    ) -> "SymbolRegistry":
        """Build a registry from all modules' symbol tables."""
        registry = cls()

        for module_name, table in symbol_tables.items():
            for sym in table.classes:
                registry._register(module_name, sym)
            for sym in table.functions:
                registry._register(module_name, sym)

        return registry

    def _register(self, module: str, sym: SymbolInfo) -> None:
        """Register a single symbol definition."""
        sid = SymbolId(module=module, name=sym.name, kind=sym.kind)
        defn = SymbolDefinition(
            id=sid,
            info=sym,
            line=sym.line,
            end_line=sym.end_line,
        )

        self._by_name.setdefault(sym.name, []).append(defn)
        self._by_module.setdefault(module, []).append(defn)
        self._by_id[sid] = defn

    def lookup(self, name: str, from_module: Optional[str] = None) -> list[SymbolDefinition]:
        """Find all definitions matching a symbol name.

        If from_module is provided, prioritize definitions from that module.
        """
        candidates = self._by_name.get(name, [])
        if not candidates:
            return []

        if from_module:
            # Exact module match first
            exact = [c for c in candidates if c.id.module == from_module]
            if exact:
                return exact

        return candidates

    def lookup_in_module(self, module: str, name: str) -> Optional[SymbolDefinition]:
        """Find a specific symbol defined in a specific module."""
        for defn in self._by_module.get(module, []):
            if defn.id.name == name:
                return defn
        return None

    def get_module_symbols(self, module: str) -> list[SymbolDefinition]:
        """Get all symbols defined in a module."""
        return self._by_module.get(module, [])

    def get_by_id(self, sid: SymbolId) -> Optional[SymbolDefinition]:
        """Look up a specific symbol by its unique ID."""
        return self._by_id.get(sid)

    @property
    def total_symbols(self) -> int:
        return len(self._by_id)

    @property
    def modules_with_symbols(self) -> int:
        return len(self._by_module)


# ── Reference resolution ─────────────────────────────────────


def resolve_references(
    imports: dict[str, list[ResolvedImport]],
    registry: SymbolRegistry,
) -> list[SymbolReference]:
    """Resolve import references to symbol definitions.

    For each import like `from module_b import ClassName`, try to
    match `ClassName` against the symbols defined in `module_b`.

    Returns a list of all cross-module symbol references, both
    resolved (matched a definition) and unresolved (imported name
    not found in target's symbol table — could be a submodule,
    re-export, or dynamic attribute).
    """
    refs: list[SymbolReference] = []

    for source_module, mod_imports in imports.items():
        for imp in mod_imports:
            target_module = imp.resolved_module

            for detail in imp.details:
                if not detail.is_from_import:
                    # `import foo` — module-level, no specific symbol
                    continue

                name = detail.imported_name
                defn = registry.lookup_in_module(target_module, name)

                ref = SymbolReference(
                    source_module=source_module,
                    target_module=target_module,
                    symbol_name=name,
                    line=detail.line,
                    resolved=defn is not None,
                    target_symbol=defn.id if defn else None,
                )
                refs.append(ref)

    return refs


# ── Symbol graph ──────────────────────────────────────────────


class SymbolGraph:
    """Directed graph of symbol-level dependencies.

    Nodes are SymbolIds, edges represent "module A uses symbol X
    from module B". This is a finer-grained view than the module
    dependency graph.
    """

    def __init__(self) -> None:
        self.nodes: dict[SymbolId, SymbolDefinition] = {}
        self.edges: list[SymbolEdge] = []
        self.forward: dict[SymbolId, set[SymbolId]] = {}   # who does X use?
        self.reverse: dict[SymbolId, set[SymbolId]] = {}   # who uses X?

        # Aggregated module-level stats
        self._incoming_by_module: dict[str, set[str]] = {}  # target_mod → set of source_mods
        self._symbol_usage_count: dict[SymbolId, int] = {}

    @classmethod
    def build(
        cls,
        registry: SymbolRegistry,
        references: list[SymbolReference],
    ) -> "SymbolGraph":
        """Build a symbol graph from the registry and resolved references."""
        graph = cls()

        # Add all defined symbols as nodes
        for sid, defn in registry._by_id.items():
            graph.nodes[sid] = defn
            graph.forward.setdefault(sid, set())
            graph.reverse.setdefault(sid, set())

        # Add edges from resolved references
        for ref in references:
            if not ref.resolved or ref.target_symbol is None:
                continue

            target_sid = ref.target_symbol

            # Create a pseudo-node for the source (module-level importer)
            # This represents "something in source_module uses target symbol"
            source_sid = SymbolId(
                module=ref.source_module,
                name="<module>",
                kind="module",
            )

            if source_sid not in graph.forward:
                graph.forward[source_sid] = set()
            if source_sid not in graph.reverse:
                graph.reverse[source_sid] = set()

            graph.forward[source_sid].add(target_sid)
            graph.reverse.setdefault(target_sid, set()).add(source_sid)
            graph.edges.append(SymbolEdge(
                source=source_sid, target=target_sid, lines=[ref.line],
            ))

            # Track usage stats
            graph._symbol_usage_count[target_sid] = (
                graph._symbol_usage_count.get(target_sid, 0) + 1
            )
            graph._incoming_by_module.setdefault(ref.target_module, set()).add(
                ref.source_module,
            )

        return graph

    # ── Queries ───────────────────────────────────────────────

    def get_usages(self, symbol: SymbolId) -> set[SymbolId]:
        """Who uses this symbol? Returns source SymbolIds."""
        return self.reverse.get(symbol, set())

    def get_dependencies(self, symbol: SymbolId) -> set[SymbolId]:
        """What symbols does this one depend on?"""
        return self.forward.get(symbol, set())

    def usage_count(self, symbol: SymbolId) -> int:
        """How many modules import this symbol?"""
        return self._symbol_usage_count.get(symbol, 0)

    def hotspots(self, min_usage: int = 3) -> list[tuple[SymbolId, int]]:
        """Find heavily-used symbols (potential coupling hotspots).

        Returns (SymbolId, usage_count) sorted by count descending.
        """
        return sorted(
            [(sid, count) for sid, count in self._symbol_usage_count.items()
             if count >= min_usage],
            key=lambda x: x[1],
            reverse=True,
        )

    def unused_symbols(self, registry: SymbolRegistry) -> list[SymbolId]:
        """Find symbols that are defined but never imported.

        Excludes __init__.py module-level code and private names.
        """
        unused = []
        for sid in registry._by_id:
            if sid.name.startswith("_"):
                continue
            if self.usage_count(sid) == 0:
                unused.append(sid)
        return unused

    def impact_of(self, symbol: SymbolId) -> dict:
        """Analyze the impact of changing a specific symbol.

        Returns dict with direct users, transitive users, and
        affected modules.
        """
        direct = self.get_usages(symbol)
        direct_modules = {s.module for s in direct}

        # BFS for transitive impact
        visited: set[SymbolId] = set()
        queue = list(direct)
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            for user in self.get_usages(current):
                if user not in visited:
                    queue.append(user)

        all_modules = {s.module for s in visited}

        return {
            "symbol": str(symbol),
            "direct_users": len(direct),
            "direct_modules": sorted(direct_modules),
            "transitive_users": len(visited),
            "transitive_modules": sorted(all_modules),
            "total_affected_modules": len(all_modules),
        }

    # ── Serialization ─────────────────────────────────────────

    def to_dict(self) -> dict:
        """Serialize the symbol graph for JSON output."""
        return {
            "total_symbols": len(self.nodes),
            "total_references": len(self.edges),
            "hotspots": [
                {"symbol": str(sid), "usage_count": count}
                for sid, count in self.hotspots(min_usage=2)
            ],
            "edges": [
                {
                    "from": str(e.source),
                    "to": str(e.target),
                    "lines": e.lines,
                }
                for e in self.edges
            ],
        }
