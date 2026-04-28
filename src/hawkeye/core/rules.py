"""Architecture rule enforcement.

Supports layered architecture rules, forbidden import rules, independence
contracts, protected module rules, and acyclic sibling enforcement.
Inspired by Tach, import-linter, and Deply.

Rule evaluation order (precedence):
1. Forbidden   — hard block (explicit deny)
2. Protected   — allowlist (only X may import Y)
3. Layers      — directional constraint
4. Independence — mutual isolation (transitive)
5. Acyclic Siblings — no inter-sibling cycles
"""

import fnmatch
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .cycles import tarjan_sccs

if TYPE_CHECKING:
    from ..config import AcyclicSiblingsConfig, ProtectedConfig, RulesConfig
    from .graph import DependencyGraph


@dataclass
class Violation:
    """A single architecture rule violation."""
    rule_type: str       # "layer", "forbidden", "independence", "protected", "acyclic_siblings"
    source: str          # Module that violates the rule
    target: str          # Module being improperly imported
    message: str         # Human-readable explanation
    severity: str = "error"  # "error" or "warning"
    path: list[str] | None = None  # Transitive path (for independence violations)

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


def _modules_matching(graph: "DependencyGraph", pattern: str) -> list[str]:
    """Return all module names in the graph matching a pattern."""
    return [m for m in graph.nodes if _module_matches(m, pattern)]


def _find_layer(module: str, layers: list[str]) -> int:
    """Find the layer index for a module. Returns -1 if not in any layer."""
    for i, layer in enumerate(layers):
        if _module_matches(module, layer):
            return i
    return -1


# ── Layer Rules ───────────────────────────────────────────────


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


# ── Forbidden Rules ───────────────────────────────────────────


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


# ── Protected Rules ───────────────────────────────────────────


def check_protected_rules(
    graph: "DependencyGraph",
    protected_rules: list["ProtectedConfig"],
) -> list[Violation]:
    """Check that protected modules are only imported by allowed modules.

    This is the inverse of forbidden: instead of "A cannot import B",
    it's "only X can import B".
    """
    violations: list[Violation] = []

    for rule in protected_rules:
        for protected_pattern in rule.modules:
            protected_mods = _modules_matching(graph, protected_pattern)
            for mod in protected_mods:
                # Check all importers via reverse adjacency
                importers = graph.reverse_adj.get(mod, set())
                for importer in importers:
                    is_allowed = any(
                        _module_matches(importer, allowed_pat)
                        for allowed_pat in rule.allowed_importers
                    )
                    if not is_allowed:
                        violations.append(Violation(
                            rule_type="protected",
                            source=importer,
                            target=mod,
                            message=(
                                f"'{mod}' is protected: only modules matching "
                                f"{rule.allowed_importers} may import it."
                            ),
                        ))

    return violations


# ── Independence Rules (transitive) ──────────────────────────


def check_independence_rules(
    graph: "DependencyGraph",
    independence_groups: list[list[str]],
) -> list[Violation]:
    """Check that independent module groups have no transitive paths.

    Uses BFS reachability for detection (O(V+E) per source module),
    then find_path() only for the violation explanation.
    """
    violations: list[Violation] = []
    seen_pairs: set[tuple[str, str]] = set()

    for group in independence_groups:
        for i, pat_a in enumerate(group):
            for pat_b in group[i + 1:]:
                mods_a = _modules_matching(graph, pat_a)
                mods_b_set = set(_modules_matching(graph, pat_b))

                if not mods_a or not mods_b_set:
                    continue

                # Direction A → B: BFS reachability from each mod_a
                for mod_a in mods_a:
                    reachable = graph.get_transitive_dependencies(mod_a)
                    reachable_in_b = reachable & mods_b_set
                    for mod_b in reachable_in_b:
                        pair_key = (mod_a, mod_b)
                        if pair_key not in seen_pairs:
                            seen_pairs.add(pair_key)
                            path = graph.find_path(mod_a, mod_b)
                            violations.append(Violation(
                                rule_type="independence",
                                source=mod_a,
                                target=mod_b,
                                message=(
                                    f"Modules matching '{pat_a}' and '{pat_b}' "
                                    f"must be independent."
                                ),
                                path=path,
                            ))

                # Direction B → A: BFS reachability from each mod_b
                for mod_b in mods_b_set:
                    reachable = graph.get_transitive_dependencies(mod_b)
                    reachable_in_a = reachable & set(mods_a)
                    for mod_a in reachable_in_a:
                        pair_key = (mod_b, mod_a)
                        if pair_key not in seen_pairs:
                            seen_pairs.add(pair_key)
                            path = graph.find_path(mod_b, mod_a)
                            violations.append(Violation(
                                rule_type="independence",
                                source=mod_b,
                                target=mod_a,
                                message=(
                                    f"Modules matching '{pat_b}' and '{pat_a}' "
                                    f"must be independent."
                                ),
                                path=path,
                            ))

    return violations


# ── Acyclic Siblings Rules ───────────────────────────────────


def check_acyclic_siblings_rules(
    graph: "DependencyGraph",
    acyclic_rules: list["AcyclicSiblingsConfig"],
) -> list[Violation]:
    """Check that sibling packages under an ancestor don't form cycles.

    Only detects cycles spanning multiple sibling groups.
    Cycles within a single sibling package are allowed.

    Uses Tarjan's SCC on the sibling-level subgraph:
    1. Collect all modules under ancestor
    2. Group by first-level child (the "sibling")
    3. Build a sibling-level adjacency graph
    4. Find SCCs — any SCC with >1 sibling is a violation
    """
    violations: list[Violation] = []

    for rule in acyclic_rules:
        ancestor = rule.ancestor
        if not ancestor:
            continue

        prefix = ancestor + "."

        # Collect sibling groups: "services.auth" → ["services.auth.login", ...]
        sibling_map: dict[str, list[str]] = {}  # sibling_name → [modules]
        for mod in graph.nodes:
            if not mod.startswith(prefix):
                continue
            remainder = mod[len(prefix):]
            sibling_name = prefix + remainder.split(".")[0]
            sibling_map.setdefault(sibling_name, []).append(mod)

        if len(sibling_map) < 2:
            continue  # Need at least 2 siblings to have a cycle

        # Build sibling-level adjacency (edges between different siblings)
        sibling_adj: dict[str, set[str]] = {s: set() for s in sibling_map}
        for sibling, modules in sibling_map.items():
            for mod in modules:
                for dep in graph.adjacency.get(mod, set()):
                    # Find which sibling this dep belongs to
                    if not dep.startswith(prefix):
                        continue
                    dep_remainder = dep[len(prefix):]
                    dep_sibling = prefix + dep_remainder.split(".")[0]
                    if dep_sibling != sibling and dep_sibling in sibling_map:
                        sibling_adj[sibling].add(dep_sibling)

        # Find SCCs using canonical Tarjan's from cycles module
        sccs = tarjan_sccs(sibling_adj, min_size=2)
        for scc in sccs:
            if len(scc) > 1:
                cycle_str = " → ".join(sorted(scc))
                for sib in scc:
                    for dep_sib in sibling_adj.get(sib, set()):
                        if dep_sib in scc:
                            violations.append(Violation(
                                rule_type="acyclic_siblings",
                                source=sib,
                                target=dep_sib,
                                message=(
                                    f"Sibling packages under '{ancestor}' must be acyclic. "
                                    f"Cycle: {cycle_str}"
                                ),
                                severity="error",
                            ))

    return violations



# ── Orchestrator ──────────────────────────────────────────────


def check_all_rules(
    graph: "DependencyGraph",
    rules_config: "RulesConfig",
) -> list[Violation]:
    """Run all configured architecture rules and return violations.

    Evaluation order: forbidden → protected → layers → independence → acyclic_siblings
    """
    violations: list[Violation] = []

    # 1. Forbidden (highest precedence — explicit deny)
    if rules_config.forbidden:
        violations.extend(check_forbidden_rules(graph, rules_config.forbidden))

    # 2. Protected (allowlist)
    if rules_config.protected:
        violations.extend(check_protected_rules(graph, rules_config.protected))

    # 3. Layers (directional constraint)
    if rules_config.layers and rules_config.layers.order:
        violations.extend(check_layer_rules(
            graph,
            rules_config.layers.order,
            rules_config.layers.direction,
            rules_config.layers.allow,
        ))

    # 4. Independence (transitive isolation)
    if rules_config.independence:
        violations.extend(check_independence_rules(graph, rules_config.independence))

    # 5. Acyclic siblings (no inter-sibling cycles)
    if rules_config.acyclic_siblings:
        violations.extend(check_acyclic_siblings_rules(graph, rules_config.acyclic_siblings))

    return violations
