"""Configuration management for Hawkeye.

Supports TOML config files (hawkeye.toml) with CLI override capability.
Walks up from the project directory to find the nearest config file.
"""

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ImportError:
        tomllib = None  # type: ignore[assignment]

DEFAULT_EXCLUDES = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    "env", ".env", "build", "dist", ".idea", ".vscode",
    ".mypy_cache", ".pytest_cache", ".tox", ".eggs",
    "site-packages", "egg-info",
}


# ── Threshold Configuration ───────────────────────────────────


@dataclass
class ThresholdConfig:
    """Single source of truth for ALL numeric thresholds in Hawkeye.

    Used by: health classification, insight derivation, risk profiles.
    No function should contain hardcoded numeric thresholds — everything
    flows through this dataclass.

    The ``profile`` field labels the output for reproducibility: two runs
    with the same profile produce identical classifications.
    """
    profile: str = "default"

    # ── Instability ──
    instability_high: float = 0.8
    instability_low: float = 0.2

    # ── Coupling ──
    ce_high: int = 8
    ca_high: int = 8

    # ── Cyclomatic complexity ──
    cc_moderate: int = 5
    cc_elevated: int = 10
    cc_high: int = 20
    cc_critical: int = 50

    # ── Cognitive complexity ──
    cog_moderate: int = 8
    cog_elevated: int = 15
    cog_high: int = 25
    cog_critical: int = 50

    # ── Module size ──
    loc_high: int = 300
    loc_critical: int = 500

    # ── Blast radius ──
    dependents_high: int = 5
    dependents_critical: int = 10
    dependencies_high: int = 6

    # ── Cycles ──
    cycle_size_high: int = 4

    # ── Martin zones (abstractness + instability) ──
    distance_high: float = 0.5     # D ≥ this → zone_of_pain / zone_of_uselessness
    distance_low: float = 0.2      # D ≤ this → well_balanced
    abstract_high: float = 0.8     # A ≥ this → highly abstract
    abstract_low: float = 0.2      # A ≤ this → concrete

    @classmethod
    def strict(cls) -> "ThresholdConfig":
        """Lower thresholds — more warnings, catches issues early."""
        return cls(
            profile="strict",
            cc_moderate=3, cc_elevated=7,
            cc_high=10, cc_critical=30,
            cog_moderate=5, cog_elevated=10,
            cog_high=15, cog_critical=30,
            loc_high=200, loc_critical=300,
            dependents_high=3, dependents_critical=5,
            ce_high=5, ca_high=5,
            dependencies_high=4,
        )

    @classmethod
    def relaxed(cls) -> "ThresholdConfig":
        """Higher thresholds — fewer warnings, for large/complex codebases."""
        return cls(
            profile="relaxed",
            cc_moderate=8, cc_elevated=15,
            cc_high=30, cc_critical=80,
            cog_moderate=12, cog_elevated=25,
            cog_high=40, cog_critical=80,
            loc_high=500, loc_critical=1000,
            dependents_high=10, dependents_critical=20,
            ce_high=12, ca_high=12,
            dependencies_high=10,
        )

    @classmethod
    def from_dict(cls, data: dict) -> "ThresholdConfig":
        """Build from a TOML [thresholds] dict, applying a profile first."""
        profile_name = data.get("profile", "default")

        if profile_name == "strict":
            base = cls.strict()
        elif profile_name == "relaxed":
            base = cls.relaxed()
        else:
            base = cls()

        # Override individual keys on top of the profile
        for key, value in data.items():
            if key == "profile":
                continue
            if hasattr(base, key):
                setattr(base, key, value)

        # Mark as custom if individual overrides were applied
        has_overrides = any(k != "profile" and hasattr(base, k) for k in data)
        if has_overrides and profile_name == "default":
            base.profile = "custom"
        elif has_overrides:
            base.profile = f"{profile_name}+custom"

        return base


# ── Architecture Rules ─────────────────────────────────────────


@dataclass
class LayerConfig:
    """Layered architecture rule configuration."""
    order: list[str] = field(default_factory=list)
    direction: str = "downward"
    allow: list[dict[str, str]] = field(default_factory=list)


@dataclass
class ProtectedConfig:
    """Protected module rule — only allowed importers may import these modules."""
    modules: list[str] = field(default_factory=list)
    allowed_importers: list[str] = field(default_factory=list)


@dataclass
class AcyclicSiblingsConfig:
    """Acyclic siblings rule — sibling packages under ancestor must not form cycles."""
    ancestor: str = ""


@dataclass
class RulesConfig:
    """Architecture rule definitions."""
    layers: Optional[LayerConfig] = None
    forbidden: list[dict[str, list[str]]] = field(default_factory=list)
    independence: list[list[str]] = field(default_factory=list)
    protected: list[ProtectedConfig] = field(default_factory=list)
    acyclic_siblings: list[AcyclicSiblingsConfig] = field(default_factory=list)


# ── Language Configuration ──────────────────────────────────────


@dataclass
class LanguageSettings:
    """Per-language scan settings."""
    extensions: list[str] = field(default_factory=list)
    tsconfig: Optional[str] = None
    package_root: Optional[str] = None


# ── Main Configuration ─────────────────────────────────────────


@dataclass
class HawkeyeConfig:
    """Main configuration container."""
    project_path: str = "."
    project_name: Optional[str] = None
    exclude_dirs: set[str] = field(default_factory=lambda: DEFAULT_EXCLUDES.copy())
    exclude_patterns: list[str] = field(default_factory=list)
    include_patterns: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=lambda: ["python"])
    language_settings: dict[str, LanguageSettings] = field(default_factory=dict)
    max_depth: Optional[int] = None
    max_hops: Optional[int] = None
    include_external: bool = False
    output_format: str = "text"
    output_file: Optional[str] = None
    rules: RulesConfig = field(default_factory=RulesConfig)
    thresholds: ThresholdConfig = field(default_factory=ThresholdConfig)

    @classmethod
    def from_toml(cls, path: Path) -> "HawkeyeConfig":
        """Load configuration from a TOML file."""
        if tomllib is None:
            raise ImportError(
                "TOML parsing requires Python 3.11+ or 'tomli'. "
                "Install with: pip install tomli"
            )

        with open(path, "rb") as f:
            data = tomllib.load(f)

        config = cls()

        project = data.get("project", {})
        config.project_path = project.get("path", config.project_path)
        config.project_name = project.get("name", config.project_name)

        scan = data.get("scan", {})
        if "exclude_dirs" in scan:
            config.exclude_dirs = set(scan["exclude_dirs"])
        if "exclude_patterns" in scan:
            config.exclude_patterns = scan["exclude_patterns"]
        if "include_patterns" in scan:
            config.include_patterns = scan["include_patterns"]
        if "languages" in scan:
            config.languages = list(scan["languages"])
        language_cfg = scan.get("language", {})
        if isinstance(language_cfg, dict):
            for lang, settings in language_cfg.items():
                if not isinstance(settings, dict):
                    continue
                config.language_settings[lang] = LanguageSettings(
                    extensions=list(settings.get("extensions", [])),
                    tsconfig=settings.get("tsconfig"),
                    package_root=settings.get("package_root"),
                )

        analysis = data.get("analysis", {})
        config.max_depth = analysis.get("max_depth")
        config.max_hops = analysis.get("max_hops")
        config.include_external = analysis.get("include_external", False)

        output = data.get("output", {})
        config.output_format = output.get("format", "text")
        config.output_file = output.get("file")

        rules_data = data.get("rules", {})
        if rules_data:
            rules = RulesConfig()
            if "layers" in rules_data:
                ld = rules_data["layers"]
                rules.layers = LayerConfig(
                    order=ld.get("order", []),
                    direction=ld.get("direction", "downward"),
                    allow=ld.get("allow", []),
                )
            rules.forbidden = rules_data.get("forbidden", [])
            rules.independence = rules_data.get("independence", [])
            rules.protected = [
                ProtectedConfig(
                    modules=p.get("modules", []),
                    allowed_importers=p.get("allowed_importers", []),
                )
                for p in rules_data.get("protected", [])
            ]
            rules.acyclic_siblings = [
                AcyclicSiblingsConfig(ancestor=a.get("ancestor", ""))
                for a in rules_data.get("acyclic_siblings", [])
            ]
            config.rules = rules

        thresholds_data = data.get("thresholds", {})
        if thresholds_data:
            config.thresholds = ThresholdConfig.from_dict(thresholds_data)

        return config

    @classmethod
    def find_and_load(cls, start_dir: Path) -> "HawkeyeConfig":
        """Search for hawkeye.toml walking up from start_dir."""
        current = start_dir.resolve()
        while True:
            config_path = current / "hawkeye.toml"
            if config_path.exists():
                return cls.from_toml(config_path)
            parent = current.parent
            if parent == current:
                break
            current = parent
        return cls()
