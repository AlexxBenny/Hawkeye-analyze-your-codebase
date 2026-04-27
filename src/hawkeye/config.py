"""Configuration management for Hawkeye.

Supports TOML config files (hawkeye.toml) with CLI override capability.
Walks up from the project directory to find the nearest config file.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import sys

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


@dataclass
class LayerConfig:
    """Layered architecture rule configuration."""
    order: list[str] = field(default_factory=list)
    direction: str = "downward"
    allow: list[dict[str, str]] = field(default_factory=list)


@dataclass
class RulesConfig:
    """Architecture rule definitions."""
    layers: Optional[LayerConfig] = None
    forbidden: list[dict[str, list[str]]] = field(default_factory=list)
    independence: list[list[str]] = field(default_factory=list)


@dataclass
class HawkeyeConfig:
    """Main configuration container."""
    project_path: str = "."
    project_name: Optional[str] = None
    exclude_dirs: set[str] = field(default_factory=lambda: DEFAULT_EXCLUDES.copy())
    exclude_patterns: list[str] = field(default_factory=list)
    include_patterns: list[str] = field(default_factory=list)
    max_depth: Optional[int] = None
    max_hops: Optional[int] = None
    include_external: bool = False
    output_format: str = "text"
    output_file: Optional[str] = None
    rules: RulesConfig = field(default_factory=RulesConfig)

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
            config.rules = rules

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
