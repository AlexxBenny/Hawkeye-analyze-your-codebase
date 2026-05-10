"""Tests for git history analysis and hotspot detection.

Covers:
- Git log parsing with various formats and edge cases
- Churn category classification
- Hotspot score computation
- Graceful handling of non-git repos and missing git
- Context integration (git data in file context)
- Empty/corrupt git output handling
- Windows path normalization
- Timezone handling in git dates
"""

import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from hawkeye.core.git_history import (FileChurn, GitHistory, HotspotEntry,
                                      _parse_git_log, analyze_git_history,
                                      compute_hotspots)

# ── FileChurn classification ──────────────────────────────────


class TestChurnCategory:
    """Tests for FileChurn.churn_category classification."""

    def test_frozen_zero_commits(self):
        churn = FileChurn(
            rel_path="a.py", commit_count=0,
            lines_changed=0, days_since_last_change=999, contributor_count=0,
            first_seen="2025-01-01", last_changed="2025-01-01",
        )
        assert churn.churn_category == "frozen"

    def test_hot_high_commits(self):
        churn = FileChurn(
            rel_path="a.py", commit_count=10,
            lines_changed=0, days_since_last_change=3, contributor_count=2,
            first_seen="2025-01-01", last_changed="2025-04-25",
        )
        assert churn.churn_category == "hot"

    def test_hot_recent_plus_moderate_commits(self):
        churn = FileChurn(
            rel_path="a.py", commit_count=5,
            lines_changed=0, days_since_last_change=3, contributor_count=1,
            first_seen="2025-01-01", last_changed="2025-04-25",
        )
        assert churn.churn_category == "hot"

    def test_warm_moderate_recent(self):
        churn = FileChurn(
            rel_path="a.py", commit_count=4,
            lines_changed=0, days_since_last_change=15, contributor_count=2,
            first_seen="2025-01-01", last_changed="2025-04-13",
        )
        assert churn.churn_category == "warm"

    def test_cold_low_commits(self):
        churn = FileChurn(
            rel_path="a.py", commit_count=2,
            lines_changed=0, days_since_last_change=10, contributor_count=1,
            first_seen="2025-01-01", last_changed="2025-04-18",
        )
        assert churn.churn_category == "cold"

    def test_cold_old_changes(self):
        churn = FileChurn(
            rel_path="a.py", commit_count=4,
            lines_changed=0, days_since_last_change=45, contributor_count=1,
            first_seen="2025-01-01", last_changed="2025-03-14",
        )
        assert churn.churn_category == "cold"

    def test_boundary_warm_exactly_3_commits_30_days(self):
        """Boundary: exactly 3 commits at exactly 30 days."""
        churn = FileChurn(
            rel_path="a.py", commit_count=3,
            lines_changed=0, days_since_last_change=30, contributor_count=1,
            first_seen="2025-01-01", last_changed="2025-03-29",
        )
        assert churn.churn_category == "warm"

    def test_boundary_cold_3_commits_31_days(self):
        """Boundary: 3 commits but >30 days → cold."""
        churn = FileChurn(
            rel_path="a.py", commit_count=3,
            lines_changed=0, days_since_last_change=31, contributor_count=1,
            first_seen="2025-01-01", last_changed="2025-03-28",
        )
        assert churn.churn_category == "cold"


# ── Git log parsing ───────────────────────────────────────────


class TestGitLogParsing:
    """Tests for _parse_git_log with various git output formats."""

    def test_basic_log(self):
        raw = textwrap.dedent("""\
            abc123|2025-04-28T10:00:00+00:00|Alice
            10	5	src/engine.py
            8	3	src/config.py

            def456|2025-04-27T10:00:00+00:00|Bob
            4	2	src/engine.py
        """)
        churns, total = _parse_git_log(raw)
        assert total == 2  # 2 unique commits
        assert "src/engine.py" in churns
        assert "src/config.py" in churns
        assert churns["src/engine.py"].commit_count == 2
        assert churns["src/config.py"].commit_count == 1
        assert churns["src/engine.py"].contributor_count == 2  # Alice + Bob
        assert churns["src/config.py"].contributor_count == 1  # Alice only

    def test_empty_log(self):
        churns, total = _parse_git_log("")
        assert total == 0
        assert churns == {}

    def test_single_commit_single_file(self):
        raw = "abc123|2025-04-28T10:00:00+00:00|Alice\n10\t5\tsrc/main.py\n"
        churns, total = _parse_git_log(raw)
        assert total == 1
        assert len(churns) == 1
        assert churns["src/main.py"].commit_count == 1

    def test_same_file_multiple_commits(self):
        raw = textwrap.dedent("""\
            aaa|2025-04-28T10:00:00+00:00|Alice
            10	5	core.py

            bbb|2025-04-27T10:00:00+00:00|Alice
            8	3	core.py

            ccc|2025-04-26T10:00:00+00:00|Bob
            6	2	core.py
        """)
        churns, total = _parse_git_log(raw)
        assert total == 3
        assert churns["core.py"].commit_count == 3
        assert churns["core.py"].contributor_count == 2

    def test_backslash_normalization(self):
        raw = "abc|2025-04-28T10:00:00+00:00|Alice\n5\t3\tsrc\\engine.py\n"
        churns, _ = _parse_git_log(raw)
        assert "src/engine.py" in churns

    def test_date_ordering(self):
        """first_seen should be the oldest, last_changed the newest."""
        raw = textwrap.dedent("""\
            aaa|2025-04-28T10:00:00+00:00|Alice
            10	5	app.py

            bbb|2025-01-15T10:00:00+00:00|Alice
            3	1	app.py
        """)
        churns, _ = _parse_git_log(raw)
        assert churns["app.py"].first_seen == "2025-01-15"
        assert churns["app.py"].last_changed == "2025-04-28"

    def test_invalid_date_graceful(self):
        """Invalid ISO date in git output should not crash."""
        raw = "abc|NOT-A-DATE|Alice\n5\t2\tfile.py\n"
        churns, total = _parse_git_log(raw)
        assert total == 1
        assert "file.py" in churns

    def test_timezone_aware_dates(self):
        """Dates with timezone offsets should parse correctly."""
        raw = "abc|2025-04-28T10:00:00+05:30|Alice\n5\t2\tfile.py\n"
        churns, _ = _parse_git_log(raw)
        assert churns["file.py"].commit_count == 1

    def test_blank_lines_between_files(self):
        """Extra blank lines in git output should be ignored."""
        raw = textwrap.dedent("""\
            abc|2025-04-28T10:00:00+00:00|Alice

            10	5	file1.py

            8	3	file2.py

        """)
        churns, _ = _parse_git_log(raw)
        assert "file1.py" in churns
        assert "file2.py" in churns

    def test_pipe_in_author_name(self):
        """Author name with pipe chars — split is limited to 3 parts."""
        raw = "abc|2025-04-28T10:00:00+00:00|Alice|Bob\n5\t2\tfile.py\n"
        churns, _ = _parse_git_log(raw)
        # Split on first 2 pipes: hash=abc, date, author="Alice|Bob"
        assert "file.py" in churns

    def test_deeply_nested_paths(self):
        raw = "abc|2025-04-28T10:00:00+00:00|Alice\n10\t5\tsrc/core/analysis/deep/module.py\n"
        churns, _ = _parse_git_log(raw)
        assert "src/core/analysis/deep/module.py" in churns


# ── Hotspot computation ───────────────────────────────────────


class TestHotspotComputation:
    """Tests for compute_hotspots ranking."""

    def _make_metrics(self, module, cc=10, health="healthy"):
        m = MagicMock()
        m.cyclomatic_complexity = cc
        m.health = health
        return m

    def _make_info(self, rel_path):
        m = MagicMock()
        m.rel_path = rel_path
        return m

    def test_basic_ranking(self):
        """Higher CC × commits should rank higher."""
        gh = GitHistory(
            available=True, analysis_days=90, total_commits=5,
            files={
                "a.py": FileChurn("a.py", 5, 0, 3, 1, "2025-01-01", "2025-04-25"),
                "b.py": FileChurn("b.py", 2, 0, 10, 1, "2025-01-01", "2025-04-18"),
            },
        )
        metrics = {"mod_a": self._make_metrics("mod_a", cc=20),
                   "mod_b": self._make_metrics("mod_b", cc=30)}
        index = {"mod_a": self._make_info("a.py"),
                 "mod_b": self._make_info("b.py")}

        hotspots = compute_hotspots(gh, metrics, index)
        assert len(hotspots) == 2
        # Ranking accounts for recency decay: exp(-days/30)
        # mod_a: 20 × 5 × exp(-3/30) ≈ 90.5
        # mod_b: 30 × 2 × exp(-10/30) ≈ 43.1
        assert hotspots[0].module == "mod_a"
        assert hotspots[1].module == "mod_b"

    def test_excludes_zero_commit_files(self):
        gh = GitHistory(
            available=True, analysis_days=90, total_commits=3,
            files={
                "a.py": FileChurn("a.py", 3, 0, 5, 1, "2025-01-01", "2025-04-23"),
            },
        )
        # mod_b has no git history
        metrics = {"mod_a": self._make_metrics("mod_a", cc=10),
                   "mod_b": self._make_metrics("mod_b", cc=50)}
        index = {"mod_a": self._make_info("a.py"),
                 "mod_b": self._make_info("b.py")}

        hotspots = compute_hotspots(gh, metrics, index)
        assert len(hotspots) == 1
        assert hotspots[0].module == "mod_a"

    def test_limit(self):
        gh = GitHistory(
            available=True, analysis_days=90, total_commits=10,
            files={f"f{i}.py": FileChurn(f"f{i}.py", 3, 0, 5, 1, "2025-01-01", "2025-04-23")
                   for i in range(10)},
        )
        metrics = {f"mod_{i}": self._make_metrics(f"mod_{i}", cc=10) for i in range(10)}
        index = {f"mod_{i}": self._make_info(f"f{i}.py") for i in range(10)}

        hotspots = compute_hotspots(gh, metrics, index, limit=3)
        assert len(hotspots) == 3

    def test_unavailable_git(self):
        gh = GitHistory(available=False)
        hotspots = compute_hotspots(gh, {}, {})
        assert hotspots == []

    def test_windows_path_matching(self):
        """File index may have backslash paths; git output uses forward slashes."""
        gh = GitHistory(
            available=True, analysis_days=90, total_commits=5,
            files={"src/engine.py": FileChurn("src/engine.py", 5, 0, 3, 1, "2025-01-01", "2025-04-25")},
        )
        metrics = {"mod": self._make_metrics("mod", cc=10)}
        index = {"mod": self._make_info("src\\engine.py")}  # backslash

        hotspots = compute_hotspots(gh, metrics, index)
        assert len(hotspots) == 1

    def test_hotspot_entry_fields(self):
        """Verify all fields are populated correctly."""
        gh = GitHistory(
            available=True, analysis_days=90, total_commits=5,
            files={
                "core.py": FileChurn("core.py", 8, 0, 2, 3, "2025-01-01", "2025-04-26"),
            },
        )
        metrics = {"mod": self._make_metrics("mod", cc=15, health="critical")}
        index = {"mod": self._make_info("core.py")}

        hotspots = compute_hotspots(gh, metrics, index)
        h = hotspots[0]
        assert h.module == "mod"
        assert h.rel_path == "core.py"
        # Score = 15 × 8 × exp(-2/30) ≈ 112.3
        import math
        expected = round(15 * 8 * math.exp(-2 / 30.0), 1)
        assert h.hotspot_score == expected
        assert h.commit_count == 8
        assert h.days_since_last_change == 2
        assert h.contributor_count == 3
        assert h.cyclomatic_complexity == 15
        assert h.health == "critical"
        assert h.churn_category == "hot"


# ── analyze_git_history integration ───────────────────────────


class TestAnalyzeGitHistory:
    """Integration tests for analyze_git_history."""

    @patch("hawkeye.core.git_history._is_git_repo", return_value=False)
    def test_not_a_git_repo(self, mock_is_git):
        result = analyze_git_history("/not/a/repo")
        assert result.available is False
        assert result.files == {}

    @patch("hawkeye.core.git_history._run_git_log", return_value=None)
    @patch("hawkeye.core.git_history._is_git_repo", return_value=True)
    def test_git_log_fails(self, mock_is_git, mock_run):
        result = analyze_git_history("/some/repo")
        assert result.available is False
        assert result.files == {}

    @patch("hawkeye.core.git_history._run_git_log")
    @patch("hawkeye.core.git_history._is_git_repo", return_value=True)
    def test_success(self, mock_is_git, mock_run):
        mock_run.return_value = (
            "abc|2025-04-28T10:00:00+00:00|Alice\n"
            "10\t5\tfile.py\n"
        )
        result = analyze_git_history("/repo")
        assert result.available is True
        assert result.analysis_days == 90  # default
        assert result.total_commits == 1
        assert "file.py" in result.files

    @patch("hawkeye.core.git_history._run_git_log")
    @patch("hawkeye.core.git_history._is_git_repo", return_value=True)
    def test_custom_days(self, mock_is_git, mock_run):
        mock_run.return_value = ""
        result = analyze_git_history("/repo", days=30)
        assert result.analysis_days == 30
        mock_run.assert_called_once()
        # Verify days was passed (can't easily check subprocess args via mock)

    @patch("hawkeye.core.git_history._run_git_log", return_value="")
    @patch("hawkeye.core.git_history._is_git_repo", return_value=True)
    def test_empty_history(self, mock_is_git, mock_run):
        """Git repo with no commits in analysis window."""
        result = analyze_git_history("/repo")
        assert result.available is True
        assert result.total_commits == 0
        assert result.files == {}


# ── Context integration ───────────────────────────────────────


class TestContextIntegration:
    """Test git data integration into build_file_context output."""

    @staticmethod
    def _make_graph():
        """Build a minimal DependencyGraph with one module."""
        from hawkeye.core.graph import DependencyGraph, NodeInfo
        graph = DependencyGraph()
        graph.nodes["proj.core"] = NodeInfo(
            module_name="proj.core", package="proj",
            rel_path="core.py", is_package=False, loc=50, depth=1,
        )
        graph.adjacency["proj.core"] = set()
        graph.reverse_adj["proj.core"] = set()
        return graph

    @staticmethod
    def _make_metrics():
        from hawkeye.core.metrics import ModuleMetrics
        return {
            "proj.core": ModuleMetrics(
                module_name="proj.core", ca=0, ce=0,
                instability=0.0, loc=50, import_count=0,
                fan_in=0, fan_out=0, health="healthy",
                raw_health="healthy",
            ),
        }

    def test_git_data_in_compact_context(self):
        """Git data should appear with minimal fields in compact mode."""
        from hawkeye.config import HawkeyeConfig
        from hawkeye.context import build_file_context
        from hawkeye.core.cycles import CycleReport

        result = build_file_context(
            module="proj.core",
            graph=self._make_graph(),
            module_metrics=self._make_metrics(),
            cycle_report=CycleReport(cycles=[]),
            symbol_tables={},
            config=HawkeyeConfig(),
            compact=True,
            git_history=GitHistory(
                available=True, analysis_days=90, total_commits=10,
                files={"core.py": FileChurn("core.py", 8, 0, 3, 2, "2025-01-01", "2025-04-25")},
            ),
        )

        # v0.6 compact: churn is a top-level key, not nested under 'git'
        assert "churn" in result
        assert result["churn"] == "hot"
        # No nested git dict in compact mode
        assert "git" not in result

    def test_git_data_in_full_context(self):
        """Non-compact mode includes extra git fields."""
        from hawkeye.config import HawkeyeConfig
        from hawkeye.context import build_file_context
        from hawkeye.core.cycles import CycleReport

        result = build_file_context(
            module="proj.core",
            graph=self._make_graph(),
            module_metrics=self._make_metrics(),
            cycle_report=CycleReport(cycles=[]),
            symbol_tables={},
            config=HawkeyeConfig(),
            compact=False,
            git_history=GitHistory(
                available=True, analysis_days=90, total_commits=10,
                files={"core.py": FileChurn("core.py", 5, 0, 10, 3, "2025-01-01", "2025-04-18")},
            ),
        )

        assert "git" in result
        assert result["git"]["contributors"] == 3
        assert result["git"]["last_changed"] == "2025-04-18"

    def test_no_git_data_when_unavailable(self):
        """No git key in output when git_history is None."""
        from hawkeye.config import HawkeyeConfig
        from hawkeye.context import build_file_context
        from hawkeye.core.cycles import CycleReport

        result = build_file_context(
            module="proj.core",
            graph=self._make_graph(),
            module_metrics=self._make_metrics(),
            cycle_report=CycleReport(cycles=[]),
            symbol_tables={},
            config=HawkeyeConfig(),
            compact=True,
            git_history=None,
        )

        assert "churn" not in result
        assert "git" not in result

    def test_no_git_key_when_file_not_in_history(self):
        """No git key when git is available but file has no history."""
        from hawkeye.config import HawkeyeConfig
        from hawkeye.context import build_file_context
        from hawkeye.core.cycles import CycleReport

        result = build_file_context(
            module="proj.core",
            graph=self._make_graph(),
            module_metrics=self._make_metrics(),
            cycle_report=CycleReport(cycles=[]),
            symbol_tables={},
            config=HawkeyeConfig(),
            compact=True,
            git_history=GitHistory(
                available=True, analysis_days=90, total_commits=5,
                files={"other.py": FileChurn("other.py", 3, 0, 5, 1, "2025-01-01", "2025-04-23")},
            ),
        )

        assert "churn" not in result
        assert "git" not in result

    def test_no_git_key_when_git_not_available(self):
        """GitHistory with available=False should not produce git key."""
        from hawkeye.config import HawkeyeConfig
        from hawkeye.context import build_file_context
        from hawkeye.core.cycles import CycleReport

        result = build_file_context(
            module="proj.core",
            graph=self._make_graph(),
            module_metrics=self._make_metrics(),
            cycle_report=CycleReport(cycles=[]),
            symbol_tables={},
            config=HawkeyeConfig(),
            compact=True,
            git_history=GitHistory(available=False),
        )

        assert "churn" not in result
        assert "git" not in result


# ── Edge cases ────────────────────────────────────────────────


class TestEdgeCases:
    """Edge cases and defensive behavior."""

    def test_file_churn_is_frozen(self):
        """FileChurn is a frozen dataclass — should be immutable."""
        churn = FileChurn("a.py", 5, 0, 3, 1, "2025-01-01", "2025-04-25")
        with pytest.raises(AttributeError):
            churn.commit_count = 10  # type: ignore

    def test_git_history_default_values(self):
        """Default GitHistory should indicate unavailability."""
        gh = GitHistory()
        assert gh.available is False
        assert gh.files == {}
        assert gh.analysis_days == 0

    def test_hotspot_entry_fields_complete(self):
        """HotspotEntry should carry all necessary context."""
        entry = HotspotEntry(
            module="mod", rel_path="mod.py", hotspot_score=100.0,
            commit_count=5, lines_changed=0, days_since_last_change=3,
            contributor_count=2, churn_category="hot",
            cyclomatic_complexity=20, health="high",
        )
        assert entry.module == "mod"
        assert entry.hotspot_score == 100.0

    @patch("hawkeye.core.git_history._is_git_repo", return_value=True)
    @patch("hawkeye.core.git_history._run_git_log", return_value=None)
    def test_git_command_timeout(self, mock_run, mock_is_git):
        """If git log returns None (timeout), result is unavailable."""
        result = analyze_git_history("/project")
        assert result.available is False

    def test_parse_log_only_blank_lines(self):
        """Git log with only blank lines should produce empty result."""
        churns, total = _parse_git_log("\n\n\n\n")
        assert total == 0
        assert churns == {}

    def test_parse_log_commit_header_but_no_files(self):
        """A commit with no file changes."""
        raw = "abc|2025-04-28T10:00:00+00:00|Alice\n\n"
        churns, total = _parse_git_log(raw)
        assert total == 1  # commit is counted
        assert churns == {}  # but no files

    def test_compute_hotspots_module_not_in_index(self):
        """Module in metrics but not in file_index → skipped."""
        gh = GitHistory(
            available=True, analysis_days=90, total_commits=5,
            files={"a.py": FileChurn("a.py", 5, 0, 3, 1, "2025-01-01", "2025-04-25")},
        )
        metrics = {"ghost_module": MagicMock(cyclomatic_complexity=10, health="healthy")}
        hotspots = compute_hotspots(gh, metrics, {})  # empty index
        assert hotspots == []

    def test_renamed_file_appears_twice(self):
        """A file renamed during the window might appear under both names."""
        raw = textwrap.dedent("""\
            aaa|2025-04-28T10:00:00+00:00|Alice
            5	3	old_name.py

            bbb|2025-04-27T10:00:00+00:00|Alice
            8	2	new_name.py
        """)
        churns, total = _parse_git_log(raw)
        assert total == 2
        assert "old_name.py" in churns
        assert "new_name.py" in churns
        assert churns["old_name.py"].commit_count == 1
        assert churns["new_name.py"].commit_count == 1
