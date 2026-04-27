"""Deterministic insight derivation from Hawkeye metrics.

Generates structured, factual insights from computed metrics.
NO prescriptive advice — only mathematically derived conclusions.

Layer 2 in the data hierarchy:
    Layer 1 (Raw Data):    Ca=0, Ce=12, I=1.0
    Layer 2 (Insights):    "high_instability", "high_efferent", "volatile"
    Layer 3 (Advice):      "Refactor this" ← NOT our job

Design for token efficiency:
    Compact mode:  ["high_instability", "high_blast_radius"]     (~30 tokens)
    Full mode:     [{"code": "high_instability", ...}, ...]      (~80 tokens)
    vs current:    {"ca": 0, "ce": 12, "instability": 1.0, ...} (~50 tokens)

The compact mode adds ~5 tokens to existing output. The full mode
replaces the metrics block with self-describing data.
"""

from dataclasses import dataclass
from typing import Optional

# ── Thresholds ────────────────────────────────────────────────
# All thresholds are derived from Robert C. Martin's principles
# and industry-standard static analysis benchmarks.

_THRESHOLDS = {
    "instability_high": 0.8,
    "instability_low": 0.2,
    "ce_high": 8,
    "ca_high": 8,
    "cc_high": 20,
    "cc_critical": 50,
    "cog_high": 25,
    "cog_critical": 50,
    "loc_high": 300,
    "loc_critical": 500,
    "dependents_high": 5,
    "dependents_critical": 10,
    "dependencies_high": 6,
    "cycle_size_high": 4,
}


# ── Insight definition ────────────────────────────────────────


@dataclass(frozen=True)
class Insight:
    """A single deterministic insight derived from metrics.

    Attributes:
        code: Machine-readable identifier (e.g., "high_instability").
        severity: "info", "warning", or "critical".
        metric: The metric that triggered this insight.
        value: Actual value of the metric.
        threshold: Threshold that was exceeded.
        detail: One-line factual description (no advice).
    """
    code: str
    severity: str        # "info" | "warning" | "critical"
    metric: str          # Which metric triggered this
    value: float | int   # Actual value
    threshold: float | int  # Threshold that was crossed
    detail: str          # Factual description

    def to_compact(self) -> str:
        """Token-minimal representation: just the code."""
        return self.code

    def to_dict(self) -> dict:
        """Full structured representation."""
        return {
            "code": self.code,
            "severity": self.severity,
            "detail": self.detail,
        }


# ── Derivation functions ─────────────────────────────────────
# Each function examines ONE metric dimension and returns
# zero or more insights. Pure functions, no side effects.


def _derive_instability(
    instability: float, ca: int, ce: int,
) -> list[Insight]:
    """Derive insights from the instability metric."""
    results = []
    t = _THRESHOLDS

    if instability >= t["instability_high"] and ce > 3:
        results.append(Insight(
            code="high_instability",
            severity="warning" if instability < 0.95 else "critical",
            metric="instability",
            value=instability,
            threshold=t["instability_high"],
            detail=f"I={instability:.2f}: high outgoing vs incoming dependencies",
        ))

    if instability <= t["instability_low"] and ca > 3:
        results.append(Insight(
            code="highly_stable",
            severity="info",
            metric="instability",
            value=instability,
            threshold=t["instability_low"],
            detail=f"I={instability:.2f}: many dependents, changes here propagate widely",
        ))

    return results


def _derive_coupling(ca: int, ce: int) -> list[Insight]:
    """Derive insights from afferent/efferent coupling."""
    results = []
    t = _THRESHOLDS

    if ce >= t["ce_high"]:
        results.append(Insight(
            code="high_efferent",
            severity="warning",
            metric="ce",
            value=ce,
            threshold=t["ce_high"],
            detail=f"Ce={ce}: depends on {ce} modules",
        ))

    if ca >= t["ca_high"]:
        results.append(Insight(
            code="high_afferent",
            severity="warning",
            metric="ca",
            value=ca,
            threshold=t["ca_high"],
            detail=f"Ca={ca}: {ca} modules depend on this",
        ))

    if ca == 0 and ce == 0:
        results.append(Insight(
            code="isolated",
            severity="info",
            metric="coupling",
            value=0,
            threshold=0,
            detail="no internal dependencies or dependents",
        ))

    return results


def _derive_complexity(
    cyclomatic: int, cognitive: int,
) -> list[Insight]:
    """Derive insights from complexity metrics."""
    results = []
    t = _THRESHOLDS

    if cyclomatic >= t["cc_critical"]:
        results.append(Insight(
            code="extreme_cyclomatic",
            severity="critical",
            metric="cyclomatic_complexity",
            value=cyclomatic,
            threshold=t["cc_critical"],
            detail=f"CC={cyclomatic}: very high decision branch count",
        ))
    elif cyclomatic >= t["cc_high"]:
        results.append(Insight(
            code="high_cyclomatic",
            severity="warning",
            metric="cyclomatic_complexity",
            value=cyclomatic,
            threshold=t["cc_high"],
            detail=f"CC={cyclomatic}: elevated decision branch count",
        ))

    if cognitive >= t["cog_critical"]:
        results.append(Insight(
            code="extreme_cognitive",
            severity="critical",
            metric="cognitive_complexity",
            value=cognitive,
            threshold=t["cog_critical"],
            detail=f"CogC={cognitive}: deeply nested control flow",
        ))
    elif cognitive >= t["cog_high"]:
        results.append(Insight(
            code="high_cognitive",
            severity="warning",
            metric="cognitive_complexity",
            value=cognitive,
            threshold=t["cog_high"],
            detail=f"CogC={cognitive}: moderately nested control flow",
        ))

    return results


def _derive_size(loc: int) -> list[Insight]:
    """Derive insights from module size."""
    t = _THRESHOLDS

    if loc >= t["loc_critical"]:
        return [Insight(
            code="very_large_module",
            severity="warning",
            metric="loc",
            value=loc,
            threshold=t["loc_critical"],
            detail=f"LOC={loc}: large module",
        )]
    elif loc >= t["loc_high"]:
        return [Insight(
            code="large_module",
            severity="info",
            metric="loc",
            value=loc,
            threshold=t["loc_high"],
            detail=f"LOC={loc}: above-average module size",
        )]
    return []


def _derive_blast_radius(
    direct_dependents: int, transitive_dependents: int,
) -> list[Insight]:
    """Derive insights from impact/blast radius."""
    results = []
    t = _THRESHOLDS

    if direct_dependents >= t["dependents_critical"]:
        results.append(Insight(
            code="critical_blast_radius",
            severity="critical",
            metric="direct_dependents",
            value=direct_dependents,
            threshold=t["dependents_critical"],
            detail=f"{direct_dependents} modules directly depend on this",
        ))
    elif direct_dependents >= t["dependents_high"]:
        results.append(Insight(
            code="high_blast_radius",
            severity="warning",
            metric="direct_dependents",
            value=direct_dependents,
            threshold=t["dependents_high"],
            detail=f"{direct_dependents} modules directly depend on this",
        ))

    if transitive_dependents > direct_dependents + 3:
        results.append(Insight(
            code="wide_transitive_reach",
            severity="info",
            metric="transitive_dependents",
            value=transitive_dependents,
            threshold=direct_dependents,
            detail=f"{transitive_dependents} modules transitively affected (vs {direct_dependents} direct)",
        ))

    return results


def _derive_cycle(
    cycle_count: int, max_cycle_size: int,
) -> list[Insight]:
    """Derive insights from cycle involvement."""
    results = []

    if cycle_count > 0:
        results.append(Insight(
            code="in_cycle",
            severity="critical" if max_cycle_size >= _THRESHOLDS["cycle_size_high"] else "warning",
            metric="cycle_count",
            value=cycle_count,
            threshold=1,
            detail=f"involved in {cycle_count} cycle(s), largest has {max_cycle_size} modules",
        ))

    return results


def _derive_dependency_fan(ce: int) -> list[Insight]:
    """Derive insights from dependency fan-out."""
    t = _THRESHOLDS
    if ce >= t["dependencies_high"]:
        return [Insight(
            code="high_fan_out",
            severity="info",
            metric="ce",
            value=ce,
            threshold=t["dependencies_high"],
            detail=f"imports {ce} modules: high coordination surface",
        )]
    return []


# ── Public API ────────────────────────────────────────────────


def derive_module_insights(
    *,
    instability: float = 0.0,
    ca: int = 0,
    ce: int = 0,
    cyclomatic: int = 1,
    cognitive: int = 0,
    loc: int = 0,
    direct_dependents: int = 0,
    transitive_dependents: int = 0,
    cycle_count: int = 0,
    max_cycle_size: int = 0,
) -> list[Insight]:
    """Derive all deterministic insights for a single module.

    All parameters are keyword-only to prevent argument ordering bugs.
    Returns insights sorted by severity (critical → warning → info).
    """
    insights: list[Insight] = []

    insights.extend(_derive_instability(instability, ca, ce))
    insights.extend(_derive_coupling(ca, ce))
    insights.extend(_derive_complexity(cyclomatic, cognitive))
    insights.extend(_derive_size(loc))
    insights.extend(_derive_blast_radius(direct_dependents, transitive_dependents))
    insights.extend(_derive_cycle(cycle_count, max_cycle_size))
    insights.extend(_derive_dependency_fan(ce))

    # Sort: critical first, then warning, then info
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    insights.sort(key=lambda i: severity_order.get(i.severity, 3))

    return insights


def insights_compact(insights: list[Insight]) -> list[str]:
    """Token-minimal output: just insight codes.

    Example: ["high_instability", "high_blast_radius"]
    Adds ~5-15 tokens to existing output.
    """
    return [i.to_compact() for i in insights]


def insights_full(insights: list[Insight]) -> list[dict]:
    """Structured output with severity and detail.

    Example: [{"code": "high_instability", "severity": "critical",
               "detail": "I=0.92: high outgoing vs incoming dependencies"}]
    """
    return [i.to_dict() for i in insights]


# ── Risk profiles ─────────────────────────────────────────────
# A single self-describing label (1 token) that captures the
# module's architectural role. Deterministic classification
# based on metric combinations.
#
# Labels:
#   "hub"       — high dependents + high complexity (central, fragile)
#   "volatile"  — high instability + many outgoing deps (unstable)
#   "amplifier" — changes cascade widely (transitive >> direct)
#   "tangled"   — involved in import cycles
#   "fragile"   — high complexity + high instability (breakable)
#   None        — no structural risk (healthy module)


def classify_risk(
    *,
    instability: float = 0.0,
    ca: int = 0,
    ce: int = 0,
    cyclomatic: int = 1,
    cognitive: int = 0,
    direct_dependents: int = 0,
    transitive_dependents: int = 0,
    cycle_count: int = 0,
) -> str | None:
    """Classify a module's structural risk as a single label.

    Returns the highest-priority risk label, or None for healthy modules.
    Priority: tangled > hub > fragile > volatile > amplifier.

    Each label is self-describing — no legend or system prompt needed
    for an LLM to interpret it correctly.
    """
    # Tangled: cycles are always highest priority
    if cycle_count > 0:
        return "tangled"

    high_complexity = cyclomatic >= 20 or cognitive >= 25

    # Hub: many dependents + complex (central point of failure)
    if ca >= 5 and high_complexity:
        return "hub"

    # Fragile: complex + unstable (likely to break)
    if high_complexity and instability >= 0.7:
        return "fragile"

    # Volatile: high instability + many outgoing deps
    if instability >= 0.8 and ce >= 5:
        return "volatile"

    # Amplifier: transitive reach much wider than direct
    if direct_dependents >= 3 and transitive_dependents >= direct_dependents * 2:
        return "amplifier"

    return None

