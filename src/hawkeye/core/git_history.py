"""Git history analysis — churn, hotspots, and temporal intelligence.

Extracts file-level change history from git log to compute:
- Change frequency (commits in analysis window)
- Lines changed (total added + removed across all commits)
- Recency (days since last change)
- Contributor count (unique authors)
- Hotspot score (complexity × churn)

Uses subprocess calls to git — zero external dependencies.
All data is derived from `git log` in a single batch call per project.

Design:
    - Lazy: only computed when requested, not during standard analyze()
    - Cached: results persist for the session lifetime
    - Graceful: returns empty data if not a git repo or git unavailable
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class FileChurn:
    """Git churn data for a single file."""
    rel_path: str
    commit_count: int          # Total commits in analysis window
    lines_changed: int         # Total lines added + removed
    days_since_last_change: int  # Days since most recent commit
    contributor_count: int     # Unique authors
    first_seen: str            # ISO date of first commit in window
    last_changed: str          # ISO date of most recent commit

    @property
    def churn_category(self) -> str:
        """Classify churn as hot/warm/cold/frozen.

        hot:    ≥10 commits or changed in last 7 days with ≥5 commits
        warm:   ≥3 commits and changed in last 30 days
        cold:   1-2 commits or not changed in 30+ days
        frozen: 0 commits in analysis window
        """
        if self.commit_count == 0:
            return "frozen"
        if self.commit_count >= 10 or (
            self.days_since_last_change <= 7 and self.commit_count >= 5
        ):
            return "hot"
        if self.commit_count >= 3 and self.days_since_last_change <= 30:
            return "warm"
        return "cold"


@dataclass
class HotspotEntry:
    """A file ranked by hotspot score = complexity × churn."""
    module: str
    rel_path: str
    hotspot_score: float
    commit_count: int
    lines_changed: int
    days_since_last_change: int
    contributor_count: int
    churn_category: str
    cyclomatic_complexity: int
    health: str


@dataclass
class GitHistory:
    """Complete git history analysis for a project."""
    available: bool = False            # False if not a git repo or git missing
    analysis_days: int = 0             # Window size used for analysis
    total_commits: int = 0             # Total commits in window
    files: dict[str, FileChurn] = field(default_factory=dict)  # rel_path → churn


def analyze_git_history(
    project_root: str,
    days: int = 90,
) -> GitHistory:
    """Extract git history for all tracked files.

    Runs a single `git log --numstat` command to get per-file commit
    and line-change data for the last N days. Gracefully returns empty
    GitHistory if git is unavailable or the directory is not a git repo.

    Args:
        project_root: Absolute path to the project root.
        days: Number of days to look back (default: 90).
    """
    root = Path(project_root).resolve()

    if not _is_git_repo(root):
        return GitHistory()

    raw_log = _run_git_log(root, days)
    if raw_log is None:
        return GitHistory()

    files, total_commits = _parse_git_log(raw_log)

    return GitHistory(
        available=True,
        analysis_days=days,
        total_commits=total_commits,
        files=files,
    )


def compute_hotspots(
    git_history: GitHistory,
    module_metrics: dict,
    file_index: dict,
    limit: int = 20,
) -> list[HotspotEntry]:
    """Compute hotspot ranking: complexity × churn × recency.

    The insight: CC=38 on a file that hasn't changed in 6 months is
    low priority. CC=10 on a file changing daily is dangerous.

    Hotspot score = cyclomatic_complexity × commit_count × recency_decay.
    Recency decay = exp(-days_since_last_change / 30), so recent changes
    dominate and old hotspots fade.  This prevents stale files from
    permanently ranking high.

    Args:
        git_history: Output from analyze_git_history().
        module_metrics: Dict of module_name → ModuleMetrics.
        file_index: Dict of module_name → ModuleInfo.
        limit: Maximum entries to return.
    """
    import math

    if not git_history.available:
        return []

    entries: list[HotspotEntry] = []

    for module_name, metrics in module_metrics.items():
        info = file_index.get(module_name)
        if not info:
            continue

        rel = info.rel_path.replace("\\", "/")
        churn = git_history.files.get(rel)
        if not churn or churn.commit_count == 0:
            continue

        recency_factor = math.exp(-churn.days_since_last_change / 30.0)
        score = metrics.cyclomatic_complexity * churn.commit_count * recency_factor
        entries.append(HotspotEntry(
            module=module_name,
            rel_path=rel,
            hotspot_score=round(score, 1),
            commit_count=churn.commit_count,
            lines_changed=churn.lines_changed,
            days_since_last_change=churn.days_since_last_change,
            contributor_count=churn.contributor_count,
            churn_category=churn.churn_category,
            cyclomatic_complexity=metrics.cyclomatic_complexity,
            health=metrics.health,
        ))

    entries.sort(key=lambda e: e.hotspot_score, reverse=True)
    return entries[:limit]


# ── Internal helpers ────────────────────────────────────────────


def _is_git_repo(root: Path) -> bool:
    """Check if directory is inside a git repository."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=str(root),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _run_git_log(root: Path, days: int) -> str | None:
    """Run git log with --numstat and return raw output.

    Uses --numstat for lines-added/removed per file per commit,
    with a custom format separator to parse commits efficiently.
    """
    try:
        result = subprocess.run(
            [
                "git", "log",
                f"--since={days} days ago",
                "--format=%H|%aI|%aN",
                "--numstat",
                "--diff-filter=ACDMR",
                "--no-merges",
            ],
            cwd=str(root),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return None
        return result.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None


def _parse_git_log(
    raw: str,
) -> tuple[dict[str, FileChurn], int]:
    """Parse git log --numstat output into per-file churn data.

    Lines from --numstat have the format: <added>\\t<removed>\\t<file>
    Binary files show as: -\\t-\\t<file>

    Returns (file_churns, total_commit_count).
    """
    now = datetime.now(timezone.utc)

    # Accumulate per-file stats
    file_commits: dict[str, int] = {}
    file_lines: dict[str, int] = {}
    file_authors: dict[str, set[str]] = {}
    file_first: dict[str, datetime] = {}
    file_last: dict[str, datetime] = {}

    commit_hashes: set[str] = set()
    current_date: datetime | None = None
    current_author: str = ""

    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue

        # Commit header: hash|date|author
        if "|" in line and len(line.split("|")) == 3:
            parts = line.split("|", 2)
            commit_hashes.add(parts[0])
            try:
                current_date = datetime.fromisoformat(parts[1])
            except ValueError:
                current_date = None
            current_author = parts[2]
            continue

        # Numstat line: <added>\t<removed>\t<file>
        tab_parts = line.split("\t")
        if len(tab_parts) != 3:
            continue

        added_str, removed_str, rel_path = tab_parts
        rel_path = rel_path.replace("\\", "/")

        # Skip rename arrows like "old => new"
        if " => " in rel_path:
            # Extract the new name from rename syntax: {old => new}/rest
            rel_path = _extract_rename_target(rel_path)

        # Parse line counts (binary files show as "-")
        added = int(added_str) if added_str != "-" else 0
        removed = int(removed_str) if removed_str != "-" else 0

        file_commits[rel_path] = file_commits.get(rel_path, 0) + 1
        file_lines[rel_path] = file_lines.get(rel_path, 0) + added + removed
        file_authors.setdefault(rel_path, set()).add(current_author)

        if current_date:
            if rel_path not in file_first or current_date < file_first[rel_path]:
                file_first[rel_path] = current_date
            if rel_path not in file_last or current_date > file_last[rel_path]:
                file_last[rel_path] = current_date

    # Build FileChurn entries
    churns: dict[str, FileChurn] = {}
    for rel_path, count in file_commits.items():
        last_dt = file_last.get(rel_path, now)
        first_dt = file_first.get(rel_path, now)
        days_since = max(0, (now - last_dt).days)

        churns[rel_path] = FileChurn(
            rel_path=rel_path,
            commit_count=count,
            lines_changed=file_lines.get(rel_path, 0),
            days_since_last_change=days_since,
            contributor_count=len(file_authors.get(rel_path, set())),
            first_seen=first_dt.strftime("%Y-%m-%d"),
            last_changed=last_dt.strftime("%Y-%m-%d"),
        )

    return churns, len(commit_hashes)


def _extract_rename_target(path: str) -> str:
    """Extract the target file path from git rename syntax.

    Git --numstat shows renames as:
        {old_dir => new_dir}/file.py
        old_name.py => new_name.py
    We want the new (target) path.
    """
    if "{" in path and "}" in path:
        # {old => new}/rest  →  new/rest
        pre = path[:path.index("{")]
        inner = path[path.index("{") + 1:path.index("}")]
        post = path[path.index("}") + 1:]
        _, new_part = inner.split(" => ", 1)
        return (pre + new_part + post).replace("//", "/")
    if " => " in path:
        # simple rename: old.py => new.py
        return path.split(" => ", 1)[1]
    return path
