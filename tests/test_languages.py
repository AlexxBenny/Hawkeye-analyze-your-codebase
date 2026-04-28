"""Tests for JS/TS language adapters."""

from hawkeye.core.scanner import scan_project
from hawkeye.languages.registry import analyze_project as analyze_languages
from hawkeye.languages.registry import get_language_adapters


def test_scan_project_js_ts(mixed_project):
    index = scan_project(
        str(mixed_project),
        languages=["javascript", "typescript"],
    )
    assert "js:src" in index
    assert "js:src.utils.math" in index
    assert "ts:src.types.user" in index
    assert "ts:src.components.Button" in index


def test_js_import_resolution(mixed_project):
    index = scan_project(
        str(mixed_project),
        languages=["javascript"],
    )
    adapters = get_language_adapters(["javascript"])
    imports, _ = analyze_languages(
        index, mixed_project.name, str(mixed_project), adapters
    )
    js_root = "js:src"
    math_mod = "js:src.utils.math"
    assert js_root in imports
    assert any(imp.resolved_module == math_mod for imp in imports[js_root])


def test_ts_import_resolution_with_paths(mixed_project):
    index = scan_project(
        str(mixed_project),
        languages=["typescript"],
    )
    adapters = get_language_adapters(["typescript"])
    imports, symbols = analyze_languages(
        index, mixed_project.name, str(mixed_project), adapters
    )
    alias_mod = "ts:src.alias"
    math_mod = "ts:src.utils.math"
    assert alias_mod in imports
    assert any(imp.resolved_module == math_mod for imp in imports[alias_mod])

    user_mod = symbols.get("ts:src.types.user")
    assert user_mod is not None
    assert any(sym.kind == "interface" for sym in user_mod.classes)
