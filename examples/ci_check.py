#!/usr/bin/env python3
"""Example: CI/CD integration with Hawkeye.

Demonstrates how to use Hawkeye as a CI gatekeeper that fails
builds when architecture rules are violated or cycles are detected.

Usage in CI:
    python examples/ci_check.py examples/sample_project
    # Exit code 0 = pass, 1 = violations found
"""

import sys
import io
from pathlib import Path

from hawkeye.engine import HawkeyeEngine
from hawkeye.config import HawkeyeConfig, RulesConfig, LayerConfig


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    project_path = sys.argv[1] if len(sys.argv) > 1 else str(
        Path(__file__).parent / "sample_project"
    )

    # ── Define rules programmatically ──────────────────────
    config = HawkeyeConfig()
    config.rules = RulesConfig(
        # Enforce: models ← services ← api (lower can't import higher)
        layers=LayerConfig(
            order=["models", "services", "api"],
            direction="downward",
        ),
        # Forbid: api must not import utils directly
        forbidden=[
            {"from": "*api*", "to": ["*utils*"]},
        ],
        # Ensure: models and utils are independent
        independence=[
            ["*models*", "*utils*"],
        ],
    )

    # ── Analyze ────────────────────────────────────────────
    engine = HawkeyeEngine(config)
    engine.analyze(project_path)

    violations_found = False

    # ── Check for cycles ───────────────────────────────────
    if engine.cycle_report.has_cycles:
        print("❌ FAIL: Import cycles detected!\n")
        for cycle in engine.cycle_report.cycles:
            print(f"  {cycle}")
        violations_found = True
    else:
        print("✅ No import cycles")

    # ── Check architecture rules ───────────────────────────
    if engine.violations:
        print(f"\n❌ FAIL: {len(engine.violations)} rule violation(s):\n")
        for v in engine.violations:
            print(f"  {v}")
        violations_found = True
    else:
        print("✅ All architecture rules passed")

    # ── Check health thresholds ────────────────────────────
    critical = [
        name for name, m in engine.module_metrics.items()
        if m.health == "critical"
    ]
    if critical:
        print(f"\n⚠️  WARNING: {len(critical)} module(s) with critical health:")
        for name in critical:
            m = engine.module_metrics[name]
            print(f"  {name} (I={m.instability:.2f}, Ce={m.ce})")

    # ── Exit code ──────────────────────────────────────────
    if violations_found:
        print("\n💥 CI check FAILED")
        sys.exit(1)
    else:
        print("\n🎉 CI check PASSED")
        sys.exit(0)


if __name__ == "__main__":
    main()
