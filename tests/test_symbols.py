"""Tests for cross-file symbol resolution (core/symbols.py)."""

import textwrap
from pathlib import Path

import pytest

from hawkeye.core.analyzer import (ImportDetail, ResolvedImport, SymbolInfo,
                                   SymbolTable)
from hawkeye.core.symbols import (SymbolDefinition, SymbolEdge, SymbolGraph,
                                  SymbolId, SymbolReference, SymbolRegistry,
                                  resolve_references)

# ── SymbolId ──────────────────────────────────────────────────


class TestSymbolId:
    """Tests for the SymbolId identifier."""

    def test_str_format(self):
        sid = SymbolId(module="core.engine", name="Engine", kind="class")
        assert str(sid) == "core.engine::Engine"

    def test_qualified_name(self):
        sid = SymbolId(module="core.engine", name="Engine", kind="class")
        assert sid.qualified_name == "core.engine.Engine"

    def test_hashable(self):
        sid1 = SymbolId(module="a", name="X", kind="class")
        sid2 = SymbolId(module="a", name="X", kind="class")
        assert sid1 == sid2
        assert hash(sid1) == hash(sid2)
        assert len({sid1, sid2}) == 1

    def test_different_kind_different_id(self):
        c = SymbolId(module="a", name="Foo", kind="class")
        f = SymbolId(module="a", name="Foo", kind="function")
        assert c != f


# ── SymbolRegistry ────────────────────────────────────────────


def _make_symbol_tables() -> dict[str, SymbolTable]:
    """Create test symbol tables for two modules."""
    return {
        "proj.models": SymbolTable(
            classes=[
                SymbolInfo(name="User", kind="class", line=5, end_line=20, complexity=3),
                SymbolInfo(name="Admin", kind="class", line=22, end_line=35, complexity=2),
            ],
            functions=[
                SymbolInfo(name="validate", kind="function", line=37, end_line=45, complexity=4),
            ],
            class_count=2, function_count=1, method_count=0,
        ),
        "proj.engine": SymbolTable(
            classes=[
                SymbolInfo(name="Engine", kind="class", line=10, end_line=50, method_count=3, complexity=8),
            ],
            functions=[
                SymbolInfo(name="run", kind="function", line=52, end_line=60, complexity=2),
            ],
            class_count=1, function_count=1, method_count=3,
        ),
        "proj.utils": SymbolTable(
            classes=[], functions=[
                SymbolInfo(name="format_name", kind="function", line=1, end_line=3, complexity=1),
            ],
            class_count=0, function_count=1, method_count=0,
        ),
    }


class TestSymbolRegistryBuild:
    """Tests for building the symbol registry."""

    def test_registers_all_symbols(self):
        tables = _make_symbol_tables()
        registry = SymbolRegistry.build(tables)

        # 2 classes + 1 func from models, 1 class + 1 func from engine, 1 func from utils = 6
        assert registry.total_symbols == 6

    def test_modules_with_symbols(self):
        tables = _make_symbol_tables()
        registry = SymbolRegistry.build(tables)
        assert registry.modules_with_symbols == 3


class TestSymbolRegistryLookup:
    """Tests for symbol lookup operations."""

    def test_lookup_by_name(self):
        registry = SymbolRegistry.build(_make_symbol_tables())
        results = registry.lookup("User")
        assert len(results) == 1
        assert results[0].id.module == "proj.models"
        assert results[0].id.kind == "class"

    def test_lookup_nonexistent(self):
        registry = SymbolRegistry.build(_make_symbol_tables())
        assert registry.lookup("Nonexistent") == []

    def test_lookup_in_module(self):
        registry = SymbolRegistry.build(_make_symbol_tables())
        defn = registry.lookup_in_module("proj.engine", "Engine")
        assert defn is not None
        assert defn.id.name == "Engine"

    def test_lookup_in_wrong_module(self):
        registry = SymbolRegistry.build(_make_symbol_tables())
        assert registry.lookup_in_module("proj.utils", "Engine") is None

    def test_get_module_symbols(self):
        registry = SymbolRegistry.build(_make_symbol_tables())
        syms = registry.get_module_symbols("proj.models")
        names = {s.id.name for s in syms}
        assert names == {"User", "Admin", "validate"}

    def test_get_by_id(self):
        registry = SymbolRegistry.build(_make_symbol_tables())
        sid = SymbolId(module="proj.engine", name="Engine", kind="class")
        defn = registry.get_by_id(sid)
        assert defn is not None
        assert defn.info.complexity == 8

    def test_handles_name_collision(self):
        """Same symbol name in different modules."""
        tables = {
            "mod_a": SymbolTable(
                classes=[], functions=[
                    SymbolInfo(name="helper", kind="function", line=1, end_line=5),
                ],
                class_count=0, function_count=1, method_count=0,
            ),
            "mod_b": SymbolTable(
                classes=[], functions=[
                    SymbolInfo(name="helper", kind="function", line=1, end_line=5),
                ],
                class_count=0, function_count=1, method_count=0,
            ),
        }
        registry = SymbolRegistry.build(tables)
        results = registry.lookup("helper")
        assert len(results) == 2
        modules = {r.id.module for r in results}
        assert modules == {"mod_a", "mod_b"}

    def test_lookup_with_module_hint(self):
        """Lookup prioritizes matching module."""
        tables = {
            "mod_a": SymbolTable(
                classes=[], functions=[
                    SymbolInfo(name="helper", kind="function", line=1, end_line=5),
                ],
                class_count=0, function_count=1, method_count=0,
            ),
            "mod_b": SymbolTable(
                classes=[], functions=[
                    SymbolInfo(name="helper", kind="function", line=1, end_line=5),
                ],
                class_count=0, function_count=1, method_count=0,
            ),
        }
        registry = SymbolRegistry.build(tables)
        results = registry.lookup("helper", from_module="mod_b")
        assert len(results) == 1
        assert results[0].id.module == "mod_b"


# ── Reference resolution ─────────────────────────────────────


def _make_imports() -> dict[str, list[ResolvedImport]]:
    """Create test import data: views imports Engine from engine, User from models."""
    return {
        "proj.views": [
            ResolvedImport(
                raw="proj.engine",
                resolved_module="proj.engine",
                details=[
                    ImportDetail(imported_name="Engine", line=1, is_from_import=True),
                ],
            ),
            ResolvedImport(
                raw="proj.models",
                resolved_module="proj.models",
                details=[
                    ImportDetail(imported_name="User", line=2, is_from_import=True),
                    ImportDetail(imported_name="Admin", line=2, is_from_import=True),
                ],
            ),
        ],
        "proj.engine": [
            ResolvedImport(
                raw="proj.models",
                resolved_module="proj.models",
                details=[
                    ImportDetail(imported_name="User", line=3, is_from_import=True),
                ],
            ),
        ],
    }


class TestResolveReferences:
    """Tests for connecting imports to definitions."""

    def test_resolves_known_symbols(self):
        registry = SymbolRegistry.build(_make_symbol_tables())
        refs = resolve_references(_make_imports(), registry)

        resolved = [r for r in refs if r.resolved]
        assert len(resolved) >= 3  # Engine, User (x2), Admin

    def test_marks_unresolved(self):
        """Importing a name not in the symbol table."""
        registry = SymbolRegistry.build(_make_symbol_tables())
        imports = {
            "proj.views": [
                ResolvedImport(
                    raw="proj.models",
                    resolved_module="proj.models",
                    details=[
                        ImportDetail(imported_name="Nonexistent", line=5, is_from_import=True),
                    ],
                ),
            ],
        }
        refs = resolve_references(imports, registry)
        assert len(refs) == 1
        assert refs[0].resolved is False
        assert refs[0].target_symbol is None

    def test_skips_bare_imports(self):
        """'import foo' (not from-import) should be skipped."""
        registry = SymbolRegistry.build(_make_symbol_tables())
        imports = {
            "proj.views": [
                ResolvedImport(
                    raw="proj.models",
                    resolved_module="proj.models",
                    details=[
                        ImportDetail(imported_name="proj.models", line=1, is_from_import=False),
                    ],
                ),
            ],
        }
        refs = resolve_references(imports, registry)
        assert len(refs) == 0

    def test_target_symbol_id_set(self):
        registry = SymbolRegistry.build(_make_symbol_tables())
        refs = resolve_references(_make_imports(), registry)

        engine_ref = [r for r in refs if r.symbol_name == "Engine" and r.resolved]
        assert len(engine_ref) == 1
        assert engine_ref[0].target_symbol == SymbolId(
            module="proj.engine", name="Engine", kind="class",
        )


# ── SymbolGraph ───────────────────────────────────────────────


class TestSymbolGraph:
    """Tests for the symbol-level dependency graph."""

    def _build_graph(self):
        registry = SymbolRegistry.build(_make_symbol_tables())
        refs = resolve_references(_make_imports(), registry)
        return SymbolGraph.build(registry, refs), registry

    def test_build(self):
        graph, _ = self._build_graph()
        assert len(graph.nodes) > 0
        assert len(graph.edges) > 0

    def test_usage_count(self):
        graph, _ = self._build_graph()
        user_sid = SymbolId(module="proj.models", name="User", kind="class")
        # User is imported by both proj.views and proj.engine
        assert graph.usage_count(user_sid) >= 2

    def test_hotspots(self):
        graph, _ = self._build_graph()
        hotspots = graph.hotspots(min_usage=2)
        # User has >= 2 usages, should appear
        hotspot_names = {str(sid) for sid, _ in hotspots}
        assert any("User" in name for name in hotspot_names)

    def test_unused_symbols(self):
        graph, registry = self._build_graph()
        unused = graph.unused_symbols(registry)
        unused_names = {sid.name for sid in unused}
        # format_name and run are never imported in our test data
        assert "format_name" in unused_names
        assert "run" in unused_names

    def test_impact_of(self):
        graph, _ = self._build_graph()
        user_sid = SymbolId(module="proj.models", name="User", kind="class")
        impact = graph.impact_of(user_sid)
        assert impact["direct_users"] >= 2
        assert impact["total_affected_modules"] >= 2

    def test_to_dict(self):
        graph, _ = self._build_graph()
        d = graph.to_dict()
        assert "total_symbols" in d
        assert "total_references" in d
        assert "hotspots" in d
        assert "edges" in d


# ── Integration with real projects ────────────────────────────


class TestSymbolsIntegration:
    """Integration tests using temp project fixtures."""

    def test_registry_from_real_project(self, tmp_project: Path):
        from hawkeye.core.analyzer import analyze_project
        from hawkeye.core.scanner import scan_project

        index = scan_project(str(tmp_project))
        _, symbols = analyze_project(index, tmp_project.name)
        registry = SymbolRegistry.build(symbols)

        assert registry.total_symbols > 0
        # Should find class User defined in core/models.py
        users = registry.lookup("User")
        assert len(users) >= 1

    def test_full_pipeline(self, tmp_project: Path):
        from hawkeye.engine import HawkeyeEngine

        engine = HawkeyeEngine()
        engine.analyze(str(tmp_project))

        assert engine.symbol_registry.total_symbols > 0
        assert engine.symbol_graph is not None
        assert isinstance(engine.symbol_refs, list)

    def test_engine_symbol_graph_populated(self, tmp_project: Path):
        from hawkeye.engine import HawkeyeEngine

        engine = HawkeyeEngine()
        engine.analyze(str(tmp_project))

        # The fixture has api/views.py importing Engine from core.engine
        # and User/models from core — these should be resolved
        resolved = [r for r in engine.symbol_refs if r.resolved]
        assert len(resolved) >= 1
