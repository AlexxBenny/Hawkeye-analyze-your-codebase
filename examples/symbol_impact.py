#!/usr/bin/env python3
"""Example: Symbol-level impact analysis with Hawkeye.

Demonstrates how to use the symbol resolution engine to understand
the blast radius of changing a specific class or function.

This is the "killer feature" for AI agents — before refactoring,
understand exactly what will break.
"""

import sys
import io
from pathlib import Path
from hawkeye.engine import HawkeyeEngine


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    project_path = str(Path(__file__).parent / "sample_project")

    # ── Analyze ────────────────────────────────────────────
    engine = HawkeyeEngine()
    engine.analyze(project_path)

    registry = engine.symbol_registry
    sg = engine.symbol_graph

    # ── 1. Symbol Registry — what's defined where? ─────────
    print("=" * 60)
    print("  Symbol Registry")
    print("=" * 60)
    print(f"\n  Total symbols: {registry.total_symbols}")
    print(f"  Modules with symbols: {registry.modules_with_symbols}\n")

    for module in sorted(registry._by_module.keys()):
        symbols = registry.get_module_symbols(module)
        print(f"  {module}:")
        for s in symbols:
            usage = sg.usage_count(s.id)
            marker = f"  ← {usage} importers" if usage > 0 else "  (unused)"
            print(f"    {s.id.kind:10s} {s.id.name}{marker}")
        print()

    # ── 2. Hotspots — most-imported symbols ────────────────
    print("=" * 60)
    print("  🔥 Hotspots (most coupled symbols)")
    print("=" * 60)

    hotspots = sg.hotspots(min_usage=1)
    if hotspots:
        for sid, count in hotspots:
            print(f"\n  {sid.name} ({sid.module})")
            print(f"    Imported by {count} module(s)")

            # Show impact
            impact = sg.impact_of(sid)
            print(f"    Direct impact:     {impact['direct_users']} modules")
            print(f"    Transitive impact: {impact['transitive_users']} modules")
            if impact["direct_modules"]:
                print(f"    Affected: {', '.join(impact['direct_modules'])}")
    else:
        print("\n  No hotspots found (no symbols imported by 2+ modules)")

    # ── 3. Unused symbols — dead code candidates ───────────
    print("\n" + "=" * 60)
    print("  💀 Unused Symbols (dead code candidates)")
    print("=" * 60)

    unused = sg.unused_symbols(registry)
    if unused:
        for sid in unused:
            print(f"  {sid.kind:10s} {sid.name:20s} in {sid.module}")
    else:
        print("\n  All symbols are used!")

    # ── 4. Resolved references — who imports what? ─────────
    print("\n" + "=" * 60)
    print("  🔗 Cross-File References")
    print("=" * 60)

    resolved = [r for r in engine.symbol_refs if r.resolved]
    unresolved = [r for r in engine.symbol_refs if not r.resolved]

    print(f"\n  Resolved:   {len(resolved)}")
    print(f"  Unresolved: {len(unresolved)}")

    for ref in resolved:
        print(f"  {ref.source_module}:{ref.line} → {ref.target_symbol}")

    if unresolved:
        print(f"\n  Unresolved references (possible submodules/re-exports):")
        for ref in unresolved:
            print(f"  {ref.source_module}:{ref.line} →? {ref.target_module}.{ref.symbol_name}")


if __name__ == "__main__":
    main()
