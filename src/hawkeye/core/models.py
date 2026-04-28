"""Shared data models for Hawkeye's analysis pipeline.

This module is a **leaf** — it has ZERO internal hawkeye imports.
All other modules should import data types from here, not from the
modules that use them. This breaks import cycles by design.
"""

from dataclasses import dataclass


@dataclass
class ModuleInfo:
    """Metadata about a discovered module."""
    module_name: str       # Dotted module name (e.g. "project.core.engine")
    full_path: str         # Absolute file path
    rel_path: str          # Path relative to project root
    package: str           # Parent package (e.g. "project.core")
    is_package: bool       # True if this is an __init__.py
    loc: int = 0           # Lines of code (populated during analysis)
    language: str = "python"


# ── Pure utility functions ───────────────────────────────────────
# These have ZERO internal imports, keeping models.py a true leaf.


def count_lines(file_path: str) -> int:
    """Count non-blank, non-comment lines in a Python file."""
    count = 0
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    count += 1
    except (OSError, UnicodeDecodeError):
        pass
    return count


def path_to_module(rel_path: str) -> tuple[str, bool]:
    """Convert a relative file path to a dotted module name.

    Returns:
        Tuple of (module_name, is_package).
    """
    rel_path = rel_path.replace("\\", "/")
    parts = rel_path.split("/")

    is_package = parts[-1] == "__init__.py"
    if is_package:
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1].removesuffix(".py")

    return ".".join(parts), is_package
