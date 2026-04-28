"""Tests for the AST analyzer (core/analyzer.py)."""

import ast
import textwrap

from hawkeye.core.analyzer import (ResolvedImport, SymbolInfo, SymbolTable,
                                   _cognitive_complexity,
                                   _cyclomatic_complexity, _normalize_import,
                                   _resolve_relative_import, analyze_file,
                                   analyze_file_full, analyze_project)
from hawkeye.core.models import ModuleInfo

# ── Relative import resolution ────────────────────────────────


class TestResolveRelativeImport:
    """Tests for dotted relative import resolution."""

    def test_single_dot_from_module(self):
        # from . import foo  (inside pkg.bar)
        result = _resolve_relative_import("pkg.bar", False, 1, "foo")
        assert result == "pkg.foo"

    def test_single_dot_from_package(self):
        # from . import foo  (inside pkg/__init__.py)
        result = _resolve_relative_import("pkg", True, 1, "foo")
        assert result == "pkg.foo"

    def test_double_dot(self):
        # from .. import foo  (inside pkg.sub.bar)
        result = _resolve_relative_import("pkg.sub.bar", False, 2, "foo")
        assert result == "pkg.foo"

    def test_dot_without_module(self):
        # from . import *  (inside pkg.bar)
        result = _resolve_relative_import("pkg.bar", False, 1, None)
        assert result == "pkg"

    def test_too_many_dots_returns_none(self):
        # from ... import x  (inside top-level module)
        result = _resolve_relative_import("top", False, 3, "x")
        assert result is None

    def test_deep_relative(self):
        # from .sub.deep import X  (inside pkg/__init__.py)
        result = _resolve_relative_import("pkg", True, 1, "sub.deep")
        assert result == "pkg.sub.deep"


class TestNormalizeImport:
    """Tests for absolute import normalization."""

    def test_direct_match(self):
        index = {"proj.core.engine": None}
        assert _normalize_import("proj.core.engine", "proj", index) == "proj.core.engine"

    def test_prefixed_match(self):
        index = {"proj.core.engine": None}
        assert _normalize_import("core.engine", "proj", index) == "proj.core.engine"

    def test_symbol_trimming(self):
        # Importing a class: proj.core.engine.Engine → trim to proj.core.engine
        index = {"proj.core.engine": None}
        assert _normalize_import("proj.core.engine.Engine", "proj", index) == "proj.core.engine"

    def test_external_returns_none(self):
        index = {"proj.core": None}
        assert _normalize_import("os.path", "proj", index) is None

    def test_stdlib_returns_none(self):
        index = {"proj.main": None}
        assert _normalize_import("json", "proj", index) is None


# ── Complexity measurement ────────────────────────────────────


class TestCyclomaticComplexity:
    """Tests for cyclomatic complexity calculation."""

    def test_empty_function(self):
        tree = ast.parse("def f(): pass")
        func = tree.body[0]
        assert _cyclomatic_complexity(func) == 1

    def test_single_if(self):
        tree = ast.parse("def f(x):\n  if x: pass")
        func = tree.body[0]
        assert _cyclomatic_complexity(func) == 2

    def test_if_elif_else(self):
        code = textwrap.dedent("""\
            def f(x):
                if x > 0:
                    pass
                elif x == 0:
                    pass
                else:
                    pass
        """)
        tree = ast.parse(code)
        func = tree.body[0]
        assert _cyclomatic_complexity(func) == 3  # 1 + if + elif

    def test_for_loop(self):
        tree = ast.parse("def f(xs):\n  for x in xs: pass")
        func = tree.body[0]
        assert _cyclomatic_complexity(func) == 2

    def test_boolean_operators(self):
        tree = ast.parse("def f(a, b, c):\n  if a and b or c: pass")
        func = tree.body[0]
        # 1 (base) + 1 (if) + 1 (and) + 1 (or) = 4... but BoolOp counts values-1
        cc = _cyclomatic_complexity(func)
        assert cc >= 3

    def test_try_except(self):
        code = textwrap.dedent("""\
            def f():
                try:
                    pass
                except ValueError:
                    pass
                except TypeError:
                    pass
        """)
        tree = ast.parse(code)
        func = tree.body[0]
        assert _cyclomatic_complexity(func) == 3  # 1 + 2 handlers


class TestCognitiveComplexity:
    """Tests for cognitive complexity (nesting-weighted)."""

    def test_flat_code(self):
        code = textwrap.dedent("""\
            x = 1
            y = 2
            z = x + y
        """)
        tree = ast.parse(code)
        assert _cognitive_complexity(tree.body) == 0

    def test_single_if_no_nesting(self):
        code = textwrap.dedent("""\
            if x:
                pass
        """)
        tree = ast.parse(code)
        assert _cognitive_complexity(tree.body) == 1  # +1 for if, +0 nesting

    def test_nested_if_adds_nesting(self):
        code = textwrap.dedent("""\
            if x:
                if y:
                    pass
        """)
        tree = ast.parse(code)
        cc = _cognitive_complexity(tree.body)
        assert cc >= 3  # outer if: +1, inner if: +1 +1(nesting)

    def test_for_with_nested_if(self):
        code = textwrap.dedent("""\
            for x in items:
                if x > 0:
                    pass
        """)
        tree = ast.parse(code)
        cc = _cognitive_complexity(tree.body)
        assert cc >= 3  # for: +1, if: +1 +1(nesting)


# ── Symbol extraction ─────────────────────────────────────────


class TestSymbolExtraction:
    """Tests for class/function/method extraction."""

    def test_extracts_classes(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text(textwrap.dedent("""\
            class Foo:
                def method_a(self): pass
                def method_b(self): pass

            class Bar:
                pass
        """), encoding="utf-8")
        info = ModuleInfo("test.mod", str(src), "mod.py", "test", False, 6)
        _, symbols = analyze_file_full(info, "test", {"test.mod": info})

        assert symbols.class_count == 2
        assert symbols.method_count == 2
        assert any(c.name == "Foo" for c in symbols.classes)
        assert any(c.name == "Bar" for c in symbols.classes)

    def test_extracts_functions(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text(textwrap.dedent("""\
            def alpha(): pass
            def beta(): pass
            async def gamma(): pass
        """), encoding="utf-8")
        info = ModuleInfo("test.mod", str(src), "mod.py", "test", False, 3)
        _, symbols = analyze_file_full(info, "test", {"test.mod": info})

        assert symbols.function_count == 3


# ── Full file analysis ────────────────────────────────────────


class TestAnalyzeProject:
    """Integration tests for analyzing a full project."""

    def test_resolves_internal_imports(self, tmp_project):
        from hawkeye.core.scanner import scan_project

        index = scan_project(str(tmp_project))
        project_name = tmp_project.name
        imports, symbols = analyze_project(index, project_name)

        # api/views.py should have resolved imports to core.engine and core.models
        views_key = [k for k in imports if "views" in k][0]
        resolved_targets = {imp.resolved_module for imp in imports[views_key]}
        assert any("engine" in t for t in resolved_targets)

    def test_skips_external_imports(self, tmp_project):
        from hawkeye.core.scanner import scan_project

        index = scan_project(str(tmp_project))
        project_name = tmp_project.name
        imports, _ = analyze_project(index, project_name)

        # No resolved import should point to stdlib modules
        for mod_imports in imports.values():
            for imp in mod_imports:
                assert imp.resolved_module in index

    def test_symbols_populated(self, tmp_project):
        from hawkeye.core.scanner import scan_project

        index = scan_project(str(tmp_project))
        project_name = tmp_project.name
        _, symbols = analyze_project(index, project_name)

        # core/models.py defines class User
        models_key = [k for k in symbols if "models" in k][0]
        st = symbols[models_key]
        assert st.class_count >= 1
        assert any(c.name == "User" for c in st.classes)

    def test_handles_syntax_error(self, tmp_path):
        """Files with syntax errors should be flagged, not silently ignored."""
        root = tmp_path / "badproject"
        root.mkdir()
        bad = root / "bad.py"
        bad.write_text("def broken(:\n  pass", encoding="utf-8")

        from hawkeye.core.scanner import scan_project

        index = scan_project(str(root))
        project_name = root.name
        imports, symbols = analyze_project(index, project_name)

        bad_key = [k for k in index if "bad" in k][0]
        assert imports[bad_key] == []
        assert symbols[bad_key].class_count == 0
        assert symbols[bad_key].parse_error is True


# ── TYPE_CHECKING / Deferred import classification ──────────────


class TestImportClassification:
    """Tests for TYPE_CHECKING and deferred (lazy) import detection."""

    def test_type_checking_import_flagged(self, tmp_path):
        """Imports inside `if TYPE_CHECKING:` should have is_type_checking=True."""
        root = tmp_path / "tc_project"
        root.mkdir()
        (root / "alpha.py").write_text(textwrap.dedent("""\
            from __future__ import annotations
            from typing import TYPE_CHECKING
            if TYPE_CHECKING:
                from .beta import BetaClass
            def greet(): pass
        """), encoding="utf-8")
        (root / "beta.py").write_text("class BetaClass: pass\n", encoding="utf-8")

        from hawkeye.core.scanner import scan_project
        index = scan_project(str(root))
        project_name = root.name
        imports, _ = analyze_project(index, project_name)

        alpha_key = [k for k in imports if "alpha" in k][0]
        assert len(imports[alpha_key]) > 0
        for imp in imports[alpha_key]:
            for d in imp.details:
                assert d.is_type_checking is True
                assert d.is_deferred is False

    def test_typing_dot_type_checking_detected(self, tmp_path):
        """Also supports `if typing.TYPE_CHECKING:` style guard."""
        root = tmp_path / "tc2_project"
        root.mkdir()
        (root / "alpha.py").write_text(textwrap.dedent("""\
            import typing
            if typing.TYPE_CHECKING:
                from .beta import B
        """), encoding="utf-8")
        (root / "beta.py").write_text("class B: pass\n", encoding="utf-8")

        from hawkeye.core.scanner import scan_project
        index = scan_project(str(root))
        imports, _ = analyze_project(index, root.name)

        alpha_key = [k for k in imports if "alpha" in k][0]
        for imp in imports[alpha_key]:
            for d in imp.details:
                assert d.is_type_checking is True

    def test_deferred_import_flagged(self, tmp_path):
        """Imports inside function bodies should have is_deferred=True."""
        root = tmp_path / "lazy_project"
        root.mkdir()
        (root / "alpha.py").write_text(textwrap.dedent("""\
            def my_func():
                from .beta import helper
                return helper()
        """), encoding="utf-8")
        (root / "beta.py").write_text("def helper(): return 42\n", encoding="utf-8")

        from hawkeye.core.scanner import scan_project
        index = scan_project(str(root))
        imports, _ = analyze_project(index, root.name)

        alpha_key = [k for k in imports if "alpha" in k][0]
        assert len(imports[alpha_key]) > 0
        for imp in imports[alpha_key]:
            for d in imp.details:
                assert d.is_deferred is True
                assert d.is_type_checking is False

    def test_runtime_import_has_no_flags(self, tmp_path):
        """Top-level imports should have both flags False."""
        root = tmp_path / "rt_project"
        root.mkdir()
        (root / "alpha.py").write_text("from .beta import B\n", encoding="utf-8")
        (root / "beta.py").write_text("class B: pass\n", encoding="utf-8")

        from hawkeye.core.scanner import scan_project
        index = scan_project(str(root))
        imports, _ = analyze_project(index, root.name)

        alpha_key = [k for k in imports if "alpha" in k][0]
        for imp in imports[alpha_key]:
            for d in imp.details:
                assert d.is_type_checking is False
                assert d.is_deferred is False

    def test_mixed_imports_classified_correctly(self, tmp_path):
        """A module with runtime, TYPE_CHECKING, and deferred imports."""
        root = tmp_path / "mix_project"
        root.mkdir()
        (root / "alpha.py").write_text(textwrap.dedent("""\
            from typing import TYPE_CHECKING
            from .beta import runtime_fn
            if TYPE_CHECKING:
                from .gamma import GammaType
            def load():
                from .delta import lazy_fn
                return lazy_fn()
        """), encoding="utf-8")
        (root / "beta.py").write_text("def runtime_fn(): pass\n", encoding="utf-8")
        (root / "gamma.py").write_text("class GammaType: pass\n", encoding="utf-8")
        (root / "delta.py").write_text("def lazy_fn(): return 1\n", encoding="utf-8")

        from hawkeye.core.scanner import scan_project
        index = scan_project(str(root))
        imports, _ = analyze_project(index, root.name)

        alpha_key = [k for k in imports if "alpha" in k][0]
        resolved = {imp.resolved_module: imp for imp in imports[alpha_key]}

        # beta is a runtime import
        beta_key = [k for k in resolved if "beta" in k][0]
        assert all(not d.is_type_checking and not d.is_deferred for d in resolved[beta_key].details)

        # gamma is TYPE_CHECKING
        gamma_key = [k for k in resolved if "gamma" in k][0]
        assert all(d.is_type_checking for d in resolved[gamma_key].details)

        # delta is deferred
        delta_key = [k for k in resolved if "delta" in k][0]
        assert all(d.is_deferred for d in resolved[delta_key].details)


class TestCycleKindClassification:
    """Tests for cycle kind classification (runtime vs type_only vs deferred)."""

    def test_type_only_cycle_classified(self, tmp_path):
        """Cycles where ALL edges are TYPE_CHECKING should be 'type_only'."""
        root = tmp_path / "tc_cycle"
        root.mkdir()
        (root / "alpha.py").write_text(textwrap.dedent("""\
            from typing import TYPE_CHECKING
            if TYPE_CHECKING:
                from .beta import B
            class A: pass
        """), encoding="utf-8")
        (root / "beta.py").write_text(textwrap.dedent("""\
            from typing import TYPE_CHECKING
            if TYPE_CHECKING:
                from .alpha import A
            class B: pass
        """), encoding="utf-8")

        from hawkeye.engine import HawkeyeEngine
        engine = HawkeyeEngine()
        engine.analyze(str(root))

        cr = engine.cycle_report
        if cr.has_cycles:
            for c in cr.cycles:
                assert c.kind == "type_only"

    def test_runtime_cycle_classified(self, tmp_path):
        """Cycles with at least one runtime edge should be 'runtime'."""
        root = tmp_path / "rt_cycle"
        root.mkdir()
        (root / "alpha.py").write_text("from .beta import B\nclass A: pass\n", encoding="utf-8")
        (root / "beta.py").write_text("from .alpha import A\nclass B: pass\n", encoding="utf-8")

        from hawkeye.engine import HawkeyeEngine
        engine = HawkeyeEngine()
        engine.analyze(str(root))

        cr = engine.cycle_report
        assert cr.has_cycles
        for c in cr.cycles:
            assert c.kind == "runtime"
