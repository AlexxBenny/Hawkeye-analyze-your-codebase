"""Architecture rule enforcement.

Supports layered architecture rules, forbidden import rules, and
independence contracts. Inspired by Tach, import-linter, and Deply.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING
import fnmatch

if TYPE_CHECKING:
    from .graph import DependencyGraph
    from ..config import RulesConfig


@dataclass
class Violation:
    """A single architecture rule violation."""
    rule_type: str       # "layer", "forbidden", "independence"
    source: str          # Module that violates the rule
    target: str          # Module being improperly imported
    message: str         # Human-readable explanation
    severity: str = "error"  # "error" or "warning"

    def __str__(self) -> str:
        icon = "❌" if self.severity == "error" else "⚠️"
        return f"{icon} [{self.rule_type}] {self.source} → {self.target}: {self.message}"


def _module_matches(module: str, pattern: str) -> bool:
    """Check if a module name matches a pattern (supports glob and prefix)."""
    if fnmatch.fnmatch(module, pattern):
        return True
    if module.startswith(pattern + ".") or module == pattern:
        return True
    return False


def _find_layer(module: str, layers: list[str]) -> int:
    """Find the layer index for a module. Returns -1 if not in any layer."""
    for i, layer in enumerate(layers):
        if _module_matches(module, layer):
            return i
    return -1


def check_layer_rules(
    graph: "DependencyGraph",
    layers: list[str],
    direction: str = "downward",
    allow: list[dict[str, str]] | None = None,
) -> list[Violation]:
    """Check that imports respect the defined layer ordering.

    In 'downward' mode, higher layers (later in the list) cannot import
    from lower layers (earlier in the list). In practice, this means a
    module at index i cannot import a module at index j where j > i.

    Wait — convention: layers are ordered from bottom (foundational) to top
    (application). "downward" means dependencies flow downward: higher layers
    can import lower layers, but NOT the reverse.
    """
    if allow is None:
        allow = []

    violations: list[Violation] = []
    allow_set: set[tuple[str, str]] = set()
    for rule in allow:
        allow_set.add((rule.get("from", ""), rule.get("to", "")))

    for (src, tgt) in graph.edges:
        src_layer = _find_layer(src, layers)
        tgt_layer = _find_layer(tgt, layers)

        if src_layer == -1 or tgt_layer == -1:
            continue  # Module not in any defined layer

        # Check if this is an allowed exception
        is_allowed = False
        for from_pat, to_pat in allow_set:
            if _module_matches(src, from_pat) and _module_matches(tgt, to_pat):
                is_allowed = True
                break

        if is_allowed:
            continue

        if direction == "downward" and src_layer < tgt_layer:
            violations.append(Violation(
                rule_type="layer",
                source=src,
                target=tgt,
                message=(
                    f"Layer '{layers[src_layer]}' (index {src_layer}) cannot "
                    f"import from layer '{layers[tgt_layer]}' (index {tgt_layer}). "
                    f"Dependencies must flow downward."
                ),
            ))

    return violations


def check_forbidden_rules(
    graph: "DependencyGraph",
    forbidden: list[dict[str, list[str]]],
) -> list[Violation]:
    """Check that no forbidden imports exist.

    Each rule is a dict: {"from": "pattern", "to": ["pattern1", "pattern2"]}
    """
    violations: list[Violation] = []

    for rule in forbidden:
        from_pattern = rule.get("from", "")
        to_patterns = rule.get("to", [])

        for (src, tgt) in graph.edges:
            if not _module_matches(src, from_pattern):
                continue
            for to_pat in to_patterns:
                if _module_matches(tgt, to_pat):
                    violations.append(Violation(
                        rule_type="forbidden",
                        source=src,
                        target=tgt,
                        message=f"Import from '{to_pat}' is forbidden for modules matching '{from_pattern}'.",
                    ))
                    break

    return violations


def check_independence_rules(
    graph: "DependencyGraph",
    independence_groups: list[list[str]],
) -> list[Violation]:
    """Check that independent module groups don't import each other.

    Each group is a list of patterns that must be mutually independent.
    """
    violations: list[Violation] = []

    for group in independence_groups:
        for i, pat_a in enumerate(group):
            for pat_b in group[i + 1:]:
                # Check edges in both directions
                for (src, tgt) in graph.edges:
                    if _module_matches(src, pat_a) and _module_matches(tgt, pat_b):
                        violations.append(Violation(
                            rule_type="independence",
                            source=src,
                            target=tgt,
                            message=f"Modules matching '{pat_a}' and '{pat_b}' must be independent.",
                        ))
                    elif _module_matches(src, pat_b) and _module_matches(tgt, pat_a):
                        violations.append(Violation(
                            rule_type="independence",
                            source=src,
                            target=tgt,
                            message=f"Modules matching '{pat_b}' and '{pat_a}' must be independent.",
                        ))

    return violations


def check_all_rules(
    graph: "DependencyGraph",
    rules_config: "RulesConfig",
) -> list[Violation]:
    """Run all configured architecture rules and return violations."""
    violations: list[Violation] = []

    if rules_config.layers and rules_config.layers.order:
        violations.extend(check_layer_rules(
            graph,
            rules_config.layers.order,
            rules_config.layers.direction,
            rules_config.layers.allow,
        ))

    if rules_config.forbidden:
        violations.extend(check_forbidden_rules(graph, rules_config.forbidden))

    if rules_config.independence:
        violations.extend(check_independence_rules(graph, rules_config.independence))

    return violations
