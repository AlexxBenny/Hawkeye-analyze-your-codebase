#!/usr/bin/env python3
"""Example: Basic programmatic analysis with Hawkeye.

Demonstrates how to use HawkeyeEngine directly in Python
to analyze a project and query architectural data.
"""

import sys
import io
from pathlib import Path
from hawkeye.engine import HawkeyeEngine


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    # Point to the sample project bundled with examples
    project_path = str(Path(__file__).parent / "sample_project")

    # ── 1. Analyze ─────────────────────────────────────────
    engine = HawkeyeEngine()
    engine.analyze(project_path)

    print("=" * 60)
    print(f"  Project: {engine.project_name}")
    print(f"  Modules: {engine.project_metrics.total_modules}")
    print(f"  Dependencies: {engine.project_metrics.total_edges}")
    print(f"  Total LOC: {engine.project_metrics.total_loc}")
    print(f"  Has cycles: {engine.cycle_report.has_cycles}")
    print("=" * 60)

    # ── 2. Query module metrics ────────────────────────────
    print("\n── Module Metrics ──\n")
    for name, m in sorted(
        engine.module_metrics.items(),
        key=lambda x: x[1].instability,
        reverse=True,
    ):
        print(f"  {name:40s}  I={m.instability:.2f}  {m.health_emoji}")

    # ── 3. Get context for a specific file ─────────────────
    print("\n── File Context: services.py ──\n")
    ctx = engine.get_file_context("services.py")
    if ctx:
        print(f"  Module: {ctx['module']}")
        print(f"  Dependencies: {ctx['dependency_count']}")
        print(f"  Dependents: {ctx['dependent_count']}")
        print(f"  Health: {ctx['metrics']['health']}")

    # ── 4. Find shortest path between modules ──────────────
    print("\n── Dependency Paths ──\n")
    modules = list(engine.graph.nodes.keys())
    if len(modules) >= 2:
        src, tgt = modules[0], modules[-1]
        path = engine.get_path(src, tgt)
        if path:
            print(f"  {' → '.join(path)}")
        else:
            print(f"  No path from {src} to {tgt}")

    # ── 5. Search for modules ──────────────────────────────
    print("\n── Module Search: 'model' ──\n")
    for match in engine.find_modules("model"):
        print(f"  {match}")


if __name__ == "__main__":
    main()
