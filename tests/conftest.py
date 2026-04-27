"""Shared test fixtures for Hawkeye test suite.

Provides reusable fixtures for creating temporary Python projects,
pre-built graphs, and common test data.
"""

import os
import textwrap
from pathlib import Path

import pytest

from hawkeye.core.analyzer import (ImportDetail, ResolvedImport, SymbolInfo,
                                   SymbolTable)
from hawkeye.core.graph import DependencyGraph, EdgeInfo, NodeInfo
from hawkeye.core.scanner import ModuleInfo

# ── Temporary project fixtures ─────────────────────────────────


def _write_py(root: Path, rel_path: str, content: str) -> Path:
    """Write a Python file into a temp project tree."""
    full = root / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(textwrap.dedent(content), encoding="utf-8")
    return full


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Create a minimal Python project with known dependencies.

    Structure:
        myproject/
        ├── __init__.py
        ├── core/
        │   ├── __init__.py
        │   ├── models.py       (no deps)
        │   └── engine.py       (imports models)
        ├── api/
        │   ├── __init__.py
        │   └── views.py        (imports core.engine + core.models)
        └── utils.py            (no deps)
    """
    root = tmp_path / "myproject"
    root.mkdir()

    _write_py(root, "__init__.py", "")
    _write_py(root, "utils.py", '''\
        """Utility helpers."""

        def format_name(name: str) -> str:
            return name.strip().title()
    ''')
    _write_py(root, "core/__init__.py", "")
    _write_py(root, "core/models.py", '''\
        """Domain models."""

        class User:
            def __init__(self, name: str):
                self.name = name

            def greet(self) -> str:
                return f"Hello, {self.name}"
    ''')
    _write_py(root, "core/engine.py", '''\
        """Core engine."""

        from . import models

        class Engine:
            def __init__(self):
                self.users: list = []

            def add_user(self, name: str):
                user = models.User(name)
                self.users.append(user)
                return user

            def run(self):
                for u in self.users:
                    if u.name:
                        print(u.greet())
    ''')
    _write_py(root, "api/__init__.py", "")
    _write_py(root, "api/views.py", '''\
        """API views."""

        from ..core.engine import Engine
        from ..core import models

        def create_user(name: str):
            e = Engine()
            user = e.add_user(name)
            return user
    ''')

    return root


@pytest.fixture
def cyclic_project(tmp_path: Path) -> Path:
    """Create a project with intentional circular imports.

    a.py imports b, b.py imports c, c.py imports a.
    """
    root = tmp_path / "cyclic"
    root.mkdir()

    _write_py(root, "__init__.py", "")
    _write_py(root, "a.py", '''\
        """Module A."""
        from . import b

        def func_a():
            return b.func_b()
    ''')
    _write_py(root, "b.py", '''\
        """Module B."""
        from . import c

        def func_b():
            return c.func_c()
    ''')
    _write_py(root, "c.py", '''\
        """Module C."""
        from . import a

        def func_c():
            return a.func_a()
    ''')

    return root


@pytest.fixture
def complex_project(tmp_path: Path) -> Path:
    """Create a project with varied complexity for metrics testing."""
    root = tmp_path / "complex"
    root.mkdir()

    _write_py(root, "__init__.py", "")
    _write_py(root, "simple.py", '''\
        """Simple module — low complexity."""

        def add(a, b):
            return a + b
    ''')
    _write_py(root, "branchy.py", '''\
        """Branchy module — high cyclomatic complexity."""

        def classify(value):
            if value < 0:
                return "negative"
            elif value == 0:
                return "zero"
            elif value < 10:
                return "small"
            elif value < 100:
                return "medium"
            elif value < 1000:
                return "large"
            else:
                return "huge"

        def check(a, b, c):
            if a and b:
                if c or a:
                    return True
            elif b or c:
                return False
            return None
    ''')
    _write_py(root, "nested.py", '''\
        """Nested module — high cognitive complexity."""

        def deep_process(items):
            result = []
            for item in items:
                if item.get("active"):
                    for sub in item.get("children", []):
                        if sub.get("valid"):
                            try:
                                value = int(sub["value"])
                                if value > 0:
                                    result.append(value)
                            except (ValueError, KeyError):
                                pass
            return result
    ''')

    return root


# ── Pre-built graph fixtures ──────────────────────────────────


@pytest.fixture
def simple_graph() -> DependencyGraph:
    """A small hand-built graph: A → B → C, A → C."""
    g = DependencyGraph()
    g.project_name = "test"

    for name, loc, depth in [("A", 50, 0), ("B", 30, 0), ("C", 20, 0)]:
        g.nodes[name] = NodeInfo(
            module_name=name, package="test",
            rel_path=f"{name.lower()}.py", is_package=False,
            loc=loc, depth=depth,
        )
        g.adjacency[name] = set()
        g.reverse_adj[name] = set()

    # A → B
    g.adjacency["A"].add("B")
    g.reverse_adj["B"].add("A")
    g.edges[("A", "B")] = EdgeInfo(source="A", target="B", import_count=1, lines=[1])

    # B → C
    g.adjacency["B"].add("C")
    g.reverse_adj["C"].add("B")
    g.edges[("B", "C")] = EdgeInfo(source="B", target="C", import_count=1, lines=[2])

    # A → C
    g.adjacency["A"].add("C")
    g.reverse_adj["C"].add("A")
    g.edges[("A", "C")] = EdgeInfo(source="A", target="C", import_count=1, lines=[3])

    return g


@pytest.fixture
def cyclic_graph() -> DependencyGraph:
    """A hand-built graph with a cycle: X → Y → Z → X."""
    g = DependencyGraph()
    g.project_name = "test"

    for name in ["X", "Y", "Z"]:
        g.nodes[name] = NodeInfo(
            module_name=name, package="test",
            rel_path=f"{name.lower()}.py", is_package=False,
            loc=25, depth=0,
        )
        g.adjacency[name] = set()
        g.reverse_adj[name] = set()

    for src, tgt in [("X", "Y"), ("Y", "Z"), ("Z", "X")]:
        g.adjacency[src].add(tgt)
        g.reverse_adj[tgt].add(src)
        g.edges[(src, tgt)] = EdgeInfo(
            source=src, target=tgt, import_count=1, lines=[1],
        )

    return g
