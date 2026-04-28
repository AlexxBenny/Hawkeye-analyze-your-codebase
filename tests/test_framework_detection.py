"""Tests for framework-aware symbol tracking.

Covers:
- Decorator name extraction from AST nodes
- Framework entry point detection (substring matching)
- Unused symbol filtering with framework decorators
- Config loading for custom framework decorators
- Integration with real AST parsing
"""

import ast
import textwrap
from pathlib import Path

import pytest

from hawkeye.config import DEFAULT_FRAMEWORK_DECORATORS, HawkeyeConfig
from hawkeye.core.analyzer import (SymbolInfo, SymbolTable,
                                   _extract_decorator_names)

# ── Decorator extraction ──────────────────────────────────────


class TestDecoratorExtraction:
    """Tests for _extract_decorator_names on AST nodes."""

    def _parse_first(self, code: str) -> ast.AST:
        """Parse code and return the first class/function node."""
        tree = ast.parse(textwrap.dedent(code))
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                return node
        raise ValueError("No class or function found")

    def test_simple_decorator(self):
        node = self._parse_first("""
            @staticmethod
            def foo():
                pass
        """)
        assert _extract_decorator_names(node) == ["staticmethod"]

    def test_dotted_decorator(self):
        node = self._parse_first("""
            @pytest.fixture
            def my_fixture():
                pass
        """)
        assert _extract_decorator_names(node) == ["pytest.fixture"]

    def test_call_decorator(self):
        node = self._parse_first("""
            @app.get("/items")
            def get_items():
                pass
        """)
        assert _extract_decorator_names(node) == ["app.get"]

    def test_nested_dotted_call(self):
        node = self._parse_first("""
            @myapp.router.post("/users")
            async def create_user():
                pass
        """)
        assert _extract_decorator_names(node) == ["myapp.router.post"]

    def test_multiple_decorators(self):
        node = self._parse_first("""
            @app.get("/items")
            @require_auth
            def get_items():
                pass
        """)
        names = _extract_decorator_names(node)
        assert names == ["app.get", "require_auth"]

    def test_class_decorator(self):
        node = self._parse_first("""
            @dataclass
            class Config:
                name: str = ""
        """)
        assert _extract_decorator_names(node) == ["dataclass"]

    def test_no_decorators(self):
        node = self._parse_first("""
            def plain_function():
                pass
        """)
        assert _extract_decorator_names(node) == []

    def test_property_decorator(self):
        """Property on a class method."""
        code = textwrap.dedent("""
            class Foo:
                @property
                def bar(self):
                    return 1
        """)
        tree = ast.parse(code)
        cls = next(n for n in ast.iter_child_nodes(tree) if isinstance(n, ast.ClassDef))
        method = next(n for n in ast.iter_child_nodes(cls)
                      if isinstance(n, ast.FunctionDef))
        assert _extract_decorator_names(method) == ["property"]


# ── Framework entry point matching ────────────────────────────


class TestFrameworkEntryMatching:
    """Tests for _is_framework_entry substring matching."""

    def test_exact_match(self):
        from hawkeye.core.symbols import _is_framework_entry
        info = SymbolInfo(name="foo", kind="function", line=1,
                          decorators=["pytest.fixture"])
        assert _is_framework_entry(info, frozenset({"pytest.fixture"}))

    def test_substring_match(self):
        from hawkeye.core.symbols import _is_framework_entry
        info = SymbolInfo(name="bar", kind="function", line=1,
                          decorators=["myapp.router.get"])
        assert _is_framework_entry(info, frozenset({"router.get"}))

    def test_no_match(self):
        from hawkeye.core.symbols import _is_framework_entry
        info = SymbolInfo(name="baz", kind="function", line=1,
                          decorators=["custom_decorator"])
        assert not _is_framework_entry(info, frozenset({"pytest.fixture"}))

    def test_no_decorators(self):
        from hawkeye.core.symbols import _is_framework_entry
        info = SymbolInfo(name="plain", kind="function", line=1)
        assert not _is_framework_entry(info, frozenset({"app.get"}))

    def test_empty_patterns(self):
        from hawkeye.core.symbols import _is_framework_entry
        info = SymbolInfo(name="foo", kind="function", line=1,
                          decorators=["app.get"])
        assert not _is_framework_entry(info, frozenset())

    def test_multiple_decorators_one_matches(self):
        from hawkeye.core.symbols import _is_framework_entry
        info = SymbolInfo(name="foo", kind="function", line=1,
                          decorators=["require_auth", "app.post"])
        assert _is_framework_entry(info, frozenset({"app.post"}))


# ── Unused symbols with framework filtering ───────────────────


class TestUnusedWithFramework:
    """Tests for SymbolGraph.unused_symbols with framework decorator filtering."""

    def _build_graph_with_decorated(self):
        """Build a symbol graph where some symbols have framework decorators."""
        from hawkeye.core.analyzer import ImportDetail, ResolvedImport
        from hawkeye.core.symbols import (SymbolGraph, SymbolRegistry,
                                          resolve_references)

        tables = {
            "proj.routes": SymbolTable(
                classes=[],
                functions=[
                    SymbolInfo(name="get_items", kind="function", line=5, end_line=10,
                               decorators=["app.get"]),
                    SymbolInfo(name="create_item", kind="function", line=12, end_line=20,
                               decorators=["app.post"]),
                ],
                class_count=0, function_count=2, method_count=0,
            ),
            "proj.utils": SymbolTable(
                classes=[],
                functions=[
                    SymbolInfo(name="helper", kind="function", line=1, end_line=3),
                    SymbolInfo(name="dead_code", kind="function", line=5, end_line=8),
                ],
                class_count=0, function_count=2, method_count=0,
            ),
            "proj.fixtures": SymbolTable(
                classes=[],
                functions=[
                    SymbolInfo(name="db_session", kind="function", line=1, end_line=5,
                               decorators=["pytest.fixture"]),
                ],
                class_count=0, function_count=1, method_count=0,
            ),
        }

        # Only helper is imported — everything else is "unused"
        imports = {
            "proj.routes": [
                ResolvedImport(
                    raw="proj.utils", resolved_module="proj.utils",
                    details=[
                        ImportDetail(imported_name="helper", line=1, is_from_import=True),
                    ],
                ),
            ],
        }

        registry = SymbolRegistry.build(tables)
        refs = resolve_references(imports, registry)
        graph = SymbolGraph.build(registry, refs)
        return graph, registry

    def test_without_framework_filtering(self):
        """Without framework decorators, all unimported symbols are reported."""
        graph, registry = self._build_graph_with_decorated()
        unused = graph.unused_symbols(registry)
        names = {sid.name for sid in unused}
        # All of these are never imported
        assert "get_items" in names
        assert "create_item" in names
        assert "dead_code" in names
        assert "db_session" in names
        # helper IS imported
        assert "helper" not in names

    def test_with_framework_filtering(self):
        """With framework decorators, decorated symbols are excluded."""
        graph, registry = self._build_graph_with_decorated()
        fw = frozenset({"app.get", "app.post", "pytest.fixture"})
        unused = graph.unused_symbols(registry, framework_decorators=fw)
        names = {sid.name for sid in unused}
        # Framework-decorated → should NOT be reported as unused
        assert "get_items" not in names
        assert "create_item" not in names
        assert "db_session" not in names
        # Truly unused, no framework decorator
        assert "dead_code" in names

    def test_default_decorators_cover_common_frameworks(self):
        """DEFAULT_FRAMEWORK_DECORATORS should cover the main frameworks."""
        graph, registry = self._build_graph_with_decorated()
        unused = graph.unused_symbols(
            registry, framework_decorators=DEFAULT_FRAMEWORK_DECORATORS,
        )
        names = {sid.name for sid in unused}
        assert "get_items" not in names   # app.get is in defaults
        assert "create_item" not in names  # app.post is in defaults
        assert "db_session" not in names   # pytest.fixture is in defaults
        assert "dead_code" in names        # truly unused

    def test_backward_compatibility_no_args(self):
        """Calling without framework_decorators still works (returns all unused)."""
        graph, registry = self._build_graph_with_decorated()
        # Should work fine with no extra args (original behavior)
        unused = graph.unused_symbols(registry, framework_decorators=None)
        names = {sid.name for sid in unused}
        assert "get_items" in names  # No filtering = everything reported


# ── Config loading ────────────────────────────────────────────


class TestFrameworkConfig:
    """Tests for framework decorator configuration."""

    def test_default_config_has_framework_decorators(self):
        config = HawkeyeConfig()
        assert config.framework_entry_decorators
        assert "pytest.fixture" in config.framework_entry_decorators
        assert "app.get" in config.framework_entry_decorators

    def test_default_decorators_immutable(self):
        """frozenset ensures decorators can't be accidentally mutated."""
        config = HawkeyeConfig()
        assert isinstance(config.framework_entry_decorators, frozenset)


# ── Integration: full AST pipeline ────────────────────────────


class TestDecoratorIntegration:
    """Integration tests with real AST parsing."""

    def test_decorators_extracted_in_full_pipeline(self, tmp_path: Path):
        """Decorators flow through analyze_file_full into SymbolTable."""
        code = textwrap.dedent("""\
            import pytest

            @pytest.fixture
            def db():
                return "mock_db"

            def plain():
                return 1
        """)
        (tmp_path / "__init__.py").write_text("", encoding="utf-8")
        (tmp_path / "test_mod.py").write_text(code, encoding="utf-8")

        from hawkeye.core.analyzer import analyze_project
        from hawkeye.core.scanner import scan_project

        index = scan_project(str(tmp_path))
        _, symbols = analyze_project(index, tmp_path.name)

        # Find the test module
        test_mod = None
        for name, st in symbols.items():
            if "test_mod" in name:
                test_mod = st
                break
        assert test_mod is not None

        # db should have pytest.fixture decorator
        db_fn = [f for f in test_mod.functions if f.name == "db"]
        assert len(db_fn) == 1
        assert "pytest.fixture" in db_fn[0].decorators

        # plain should have no decorators
        plain_fn = [f for f in test_mod.functions if f.name == "plain"]
        assert len(plain_fn) == 1
        assert plain_fn[0].decorators == []

    def test_fastapi_style_decorators(self, tmp_path: Path):
        """FastAPI-style route decorators are captured correctly."""
        code = textwrap.dedent("""\
            from fastapi import FastAPI

            app = FastAPI()

            @app.get("/items/{item_id}")
            async def read_item(item_id: int):
                return {"item_id": item_id}

            @app.post("/items/")
            async def create_item(name: str):
                return {"name": name}
        """)
        (tmp_path / "__init__.py").write_text("", encoding="utf-8")
        (tmp_path / "routes.py").write_text(code, encoding="utf-8")

        from hawkeye.core.analyzer import analyze_project
        from hawkeye.core.scanner import scan_project

        index = scan_project(str(tmp_path))
        _, symbols = analyze_project(index, tmp_path.name)

        routes_mod = None
        for name, st in symbols.items():
            if "routes" in name:
                routes_mod = st
                break
        assert routes_mod is not None

        read_fn = [f for f in routes_mod.functions if f.name == "read_item"]
        assert len(read_fn) == 1
        assert "app.get" in read_fn[0].decorators

        create_fn = [f for f in routes_mod.functions if f.name == "create_item"]
        assert len(create_fn) == 1
        assert "app.post" in create_fn[0].decorators
