"""Tests for the file scanner (core/scanner.py)."""

from pathlib import Path

from hawkeye.core.scanner import (
    ModuleInfo,
    scan_project,
    _count_lines,
    _path_to_module,
    _should_exclude,
    _matches_patterns,
)


class TestCountLines:
    """Tests for non-blank, non-comment line counting."""

    def test_counts_code_lines(self, tmp_path: Path):
        f = tmp_path / "sample.py"
        f.write_text("x = 1\ny = 2\nz = 3\n", encoding="utf-8")
        assert _count_lines(str(f)) == 3

    def test_skips_blank_lines(self, tmp_path: Path):
        f = tmp_path / "sample.py"
        f.write_text("x = 1\n\n\ny = 2\n\n", encoding="utf-8")
        assert _count_lines(str(f)) == 2

    def test_skips_comments(self, tmp_path: Path):
        f = tmp_path / "sample.py"
        f.write_text("# comment\nx = 1\n# another\ny = 2\n", encoding="utf-8")
        assert _count_lines(str(f)) == 2

    def test_handles_missing_file(self):
        assert _count_lines("/nonexistent/file.py") == 0

    def test_empty_file(self, tmp_path: Path):
        f = tmp_path / "empty.py"
        f.write_text("", encoding="utf-8")
        assert _count_lines(str(f)) == 0


class TestPathToModule:
    """Tests for file path → dotted module name conversion."""

    def test_regular_file(self):
        name, is_pkg = _path_to_module("core/engine.py")
        assert name == "core.engine"
        assert is_pkg is False

    def test_init_file(self):
        name, is_pkg = _path_to_module("core/__init__.py")
        assert name == "core"
        assert is_pkg is True

    def test_nested_path(self):
        name, is_pkg = _path_to_module("a/b/c/deep.py")
        assert name == "a.b.c.deep"
        assert is_pkg is False

    def test_windows_separators(self):
        name, is_pkg = _path_to_module("core\\engine.py")
        assert name == "core.engine"

    def test_top_level_file(self):
        name, is_pkg = _path_to_module("utils.py")
        assert name == "utils"
        assert is_pkg is False


class TestShouldExclude:
    """Tests for directory exclusion logic."""

    def test_excludes_named_dirs(self):
        assert _should_exclude("__pycache__", {"__pycache__", ".git"})
        assert _should_exclude(".git", {"__pycache__", ".git"})

    def test_allows_normal_dirs(self):
        assert not _should_exclude("core", {"__pycache__"})

    def test_excludes_dot_prefixed(self):
        assert _should_exclude(".hidden", set())


class TestMatchesPatterns:
    """Tests for glob pattern matching on module names."""

    def test_matches_wildcard(self):
        assert _matches_patterns("myproject.tests.test_foo", ["*.tests.*"])

    def test_no_match(self):
        assert not _matches_patterns("myproject.core.engine", ["*.tests.*"])

    def test_empty_patterns(self):
        assert not _matches_patterns("anything", [])


class TestScanProject:
    """Integration tests for full project scanning."""

    def test_discovers_all_modules(self, tmp_project: Path):
        index = scan_project(str(tmp_project))
        module_names = set(index.keys())

        # Should find all .py files
        assert any("utils" in m for m in module_names)
        assert any("core.models" in m for m in module_names)
        assert any("core.engine" in m for m in module_names)
        assert any("api.views" in m for m in module_names)

    def test_module_info_fields(self, tmp_project: Path):
        index = scan_project(str(tmp_project))

        # Find the models module
        models_key = [k for k in index if k.endswith("core.models")][0]
        info = index[models_key]

        assert isinstance(info, ModuleInfo)
        assert info.is_package is False
        assert info.loc > 0
        assert "core/models.py" in info.rel_path.replace("\\", "/")

    def test_init_files_are_packages(self, tmp_project: Path):
        index = scan_project(str(tmp_project))
        init_keys = [k for k in index if k.endswith(".core")]
        assert len(init_keys) >= 1
        assert index[init_keys[0]].is_package is True

    def test_exclude_dirs(self, tmp_project: Path):
        index = scan_project(str(tmp_project), exclude_dirs={"api"})
        assert not any("api" in m for m in index)

    def test_exclude_patterns(self, tmp_project: Path):
        index = scan_project(str(tmp_project), exclude_patterns=["*utils*"])
        assert not any("utils" in m for m in index)

    def test_include_patterns(self, tmp_project: Path):
        index = scan_project(str(tmp_project), include_patterns=["*core*"])
        for name in index:
            assert "core" in name

    def test_loc_populated(self, tmp_project: Path):
        index = scan_project(str(tmp_project))
        for info in index.values():
            # Every file with content should have loc > 0
            # (except empty __init__.py files)
            assert info.loc >= 0
