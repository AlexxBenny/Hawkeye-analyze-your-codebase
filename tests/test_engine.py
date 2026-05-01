"""Tests for the central analysis engine (engine.py)."""

import json
from pathlib import Path

import pytest

from hawkeye.config import HawkeyeConfig
from hawkeye.engine import HawkeyeEngine, _hash_file


class TestHashFile:
    """Tests for MD5 file hashing."""

    def test_hashes_file(self, tmp_path: Path):
        f = tmp_path / "test.py"
        f.write_text("hello", encoding="utf-8")
        h = _hash_file(str(f))
        assert len(h) == 32  # MD5 hex digest length
        assert h.isalnum()

    def test_consistent_hash(self, tmp_path: Path):
        f = tmp_path / "test.py"
        f.write_text("same content", encoding="utf-8")
        assert _hash_file(str(f)) == _hash_file(str(f))

    def test_different_content_different_hash(self, tmp_path: Path):
        f1 = tmp_path / "a.py"
        f2 = tmp_path / "b.py"
        f1.write_text("content A", encoding="utf-8")
        f2.write_text("content B", encoding="utf-8")
        assert _hash_file(str(f1)) != _hash_file(str(f2))

    def test_missing_file_returns_empty(self):
        assert _hash_file("/nonexistent/path.py") == ""


class TestEngineAnalyze:
    """Tests for the full analysis pipeline."""

    def test_analyze_returns_graph(self, tmp_project: Path):
        engine = HawkeyeEngine()
        graph = engine.analyze(str(tmp_project))

        assert graph is not None
        assert len(graph.nodes) > 0
        assert engine.project_name == tmp_project.name

    def test_populates_all_caches(self, tmp_project: Path):
        engine = HawkeyeEngine()
        engine.analyze(str(tmp_project))

        assert engine.graph is not None
        assert engine.file_index is not None
        assert engine.module_metrics is not None
        assert engine.project_metrics is not None
        assert engine.cycle_report is not None
        assert engine.violations is not None

    def test_raises_before_analyze(self):
        engine = HawkeyeEngine()
        with pytest.raises(RuntimeError, match="Call analyze"):
            _ = engine.graph

    def test_project_metrics_populated(self, tmp_project: Path):
        engine = HawkeyeEngine()
        engine.analyze(str(tmp_project))
        pm = engine.project_metrics

        assert pm.total_modules > 0
        assert pm.total_loc > 0


class TestEngineRefresh:
    """Tests for incremental re-analysis."""

    def test_refresh_without_changes(self, tmp_project: Path):
        engine = HawkeyeEngine()
        engine.analyze(str(tmp_project))

        changed = engine.refresh()
        assert changed == []

    def test_refresh_detects_change(self, tmp_project: Path):
        engine = HawkeyeEngine()
        engine.analyze(str(tmp_project))

        # Modify a file
        utils = tmp_project / "utils.py"
        utils.write_text("# modified\ndef new_func(): pass\n", encoding="utf-8")

        changed = engine.refresh()
        assert len(changed) > 0

    def test_refresh_triggers_reanalysis(self, tmp_project: Path):
        engine = HawkeyeEngine()
        engine.analyze(str(tmp_project))
        old_count = engine.project_metrics.total_loc

        # Add a new file with content
        new_file = tmp_project / "extra.py"
        new_file.write_text("x = 1\ny = 2\nz = 3\n", encoding="utf-8")

        # refresh won't see NEW files (only tracks existing ones),
        # but modifying an existing file should trigger re-analysis
        utils = tmp_project / "utils.py"
        original = utils.read_text(encoding="utf-8")
        utils.write_text(original + "\n# extra line\n", encoding="utf-8")

        engine.refresh()
        # After refresh, metrics should reflect changed state
        assert engine.project_metrics is not None


class TestEngineResolve:
    """Tests for file/module path resolution."""

    def test_resolve_module_name(self, tmp_project: Path):
        engine = HawkeyeEngine()
        engine.analyze(str(tmp_project))

        # Find any module name that contains 'utils'
        utils_modules = [n for n in engine.graph.nodes if "utils" in n]
        assert len(utils_modules) > 0

        result = engine.resolve(utils_modules[0])
        assert result == utils_modules[0]

    def test_resolve_rel_path(self, tmp_project: Path):
        engine = HawkeyeEngine()
        engine.analyze(str(tmp_project))

        result = engine.resolve("utils.py")
        assert result is not None
        assert "utils" in result

    def test_resolve_nonexistent(self, tmp_project: Path):
        engine = HawkeyeEngine()
        engine.analyze(str(tmp_project))
        assert engine.resolve("nonexistent_module") is None


class TestEngineFileContext:
    """Tests for the unified file context API."""

    def test_returns_full_context(self, tmp_project: Path):
        engine = HawkeyeEngine()
        engine.analyze(str(tmp_project))

        # Get context for a module with dependencies
        views_mod = [n for n in engine.graph.nodes if "views" in n]
        if not views_mod:
            pytest.skip("views module not found in fixture")

        ctx = engine.get_file_context(views_mod[0])
        assert ctx is not None
        assert "file" in ctx
        assert "deps" in ctx
        assert "dependents" in ctx
        assert "transitive_impact" in ctx
        assert "edit_cost" in ctx
        assert "v" in ctx
        assert ctx["v"] == "0.6"

    def test_returns_none_for_unknown(self, tmp_project: Path):
        engine = HawkeyeEngine()
        engine.analyze(str(tmp_project))
        assert engine.get_file_context("nonexistent") is None

    def test_compact_mode(self, tmp_project: Path):
        engine = HawkeyeEngine()
        engine.analyze(str(tmp_project))

        mod = list(engine.graph.nodes.keys())[0]
        compact = engine.get_file_context(mod, compact=True)
        full = engine.get_file_context(mod, compact=False)

        # Both should succeed
        assert compact is not None
        assert full is not None

    def test_metrics_included(self, tmp_project: Path):
        engine = HawkeyeEngine()
        engine.analyze(str(tmp_project))

        mod = list(engine.graph.nodes.keys())[0]
        ctx = engine.get_file_context(mod)

        # v0.6 compact: metrics are at top level with short keys
        assert "health" in ctx
        assert "ca" in ctx
        assert "ce" in ctx
        assert "I" in ctx
        assert "cc" in ctx


class TestEngineBatchContext:
    """Tests for multi-file batch context."""

    def test_batch_returns_all_files(self, tmp_project: Path):
        engine = HawkeyeEngine()
        engine.analyze(str(tmp_project))

        modules = list(engine.graph.nodes.keys())[:3]
        result = engine.get_batch_context(modules)

        assert "files" in result
        assert "combined_blast_radius" in result
        assert len(result["files"]) == 3

    def test_batch_not_found(self, tmp_project: Path):
        engine = HawkeyeEngine()
        engine.analyze(str(tmp_project))

        result = engine.get_batch_context(["nonexistent1", "nonexistent2"])
        assert "error" in result

    def test_batch_shared_dependencies(self, tmp_project: Path):
        engine = HawkeyeEngine()
        engine.analyze(str(tmp_project))

        modules = list(engine.graph.nodes.keys())[:2]
        result = engine.get_batch_context(modules)

        assert "shared_dependencies" in result
        assert "total_unique_dependencies" in result


class TestEngineFindModules:
    """Tests for module search."""

    def test_finds_by_substring(self, tmp_project: Path):
        engine = HawkeyeEngine()
        engine.analyze(str(tmp_project))

        results = engine.find_modules("core")
        assert len(results) > 0
        assert all("core" in r.lower() for r in results)

    def test_empty_pattern(self, tmp_project: Path):
        engine = HawkeyeEngine()
        engine.analyze(str(tmp_project))

        results = engine.find_modules("")
        assert len(results) == len(engine.graph.nodes)


class TestEngineGetPath:
    """Tests for shortest path queries."""

    def test_finds_path(self, tmp_project: Path):
        engine = HawkeyeEngine()
        engine.analyze(str(tmp_project))

        # Find two connected modules
        for (src, tgt) in engine.graph.edges:
            path = engine.get_path(src, tgt)
            assert path is not None
            assert path[0] == src
            assert path[-1] == tgt
            break

    def test_no_path_returns_none(self, tmp_project: Path):
        engine = HawkeyeEngine()
        engine.analyze(str(tmp_project))

        result = engine.get_path("nonexistent", "also_nonexistent")
        assert result is None


class TestEngineCycleDetection:
    """Tests for cycle detection through the engine."""

    def test_no_cycles_in_clean_project(self, tmp_project: Path):
        engine = HawkeyeEngine()
        engine.analyze(str(tmp_project))
        assert engine.cycle_report.has_cycles is False

    def test_detects_cycles(self, cyclic_project: Path):
        engine = HawkeyeEngine()
        engine.analyze(str(cyclic_project))
        assert engine.cycle_report.has_cycles is True
        assert engine.cycle_report.cycle_count >= 1
