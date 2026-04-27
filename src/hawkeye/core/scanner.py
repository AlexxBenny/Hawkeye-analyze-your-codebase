"""File discovery and module indexing.

Walks a Python project tree, converts file paths to dotted module names,
and builds a structured index of all discoverable modules. Handles
__init__.py packages, namespace packages, and configurable exclusions.
"""

import fnmatch
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class ModuleInfo:
    """Metadata about a discovered Python module."""
    module_name: str       # Dotted module name (e.g. "project.core.engine")
    full_path: str         # Absolute file path
    rel_path: str          # Path relative to project root
    package: str           # Parent package (e.g. "project.core")
    is_package: bool       # True if this is an __init__.py
    loc: int = 0           # Lines of code (populated during analysis)


def _count_lines(file_path: str) -> int:
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


def _path_to_module(rel_path: str) -> tuple[str, bool]:
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


def _should_exclude(name: str, exclude_dirs: set[str]) -> bool:
    """Check if a directory name should be excluded."""
    return name in exclude_dirs or name.startswith(".")


def _matches_patterns(module_name: str, patterns: list[str]) -> bool:
    """Check if a module name matches any of the given glob patterns."""
    for pattern in patterns:
        if fnmatch.fnmatch(module_name, pattern):
            return True
    return False


def scan_project(
    root_path: str,
    exclude_dirs: Optional[set[str]] = None,
    exclude_patterns: Optional[list[str]] = None,
    include_patterns: Optional[list[str]] = None,
) -> dict[str, ModuleInfo]:
    """Scan a Python project and build a module index.

    Args:
        root_path: Absolute path to the project root directory.
        exclude_dirs: Directory names to skip during traversal.
        exclude_patterns: Glob patterns for module names to exclude.
        include_patterns: If set, only modules matching these patterns are included.

    Returns:
        Dictionary mapping dotted module names to ModuleInfo objects.
    """
    from ..config import DEFAULT_EXCLUDES

    if exclude_dirs is None:
        exclude_dirs = DEFAULT_EXCLUDES
    if exclude_patterns is None:
        exclude_patterns = []
    if include_patterns is None:
        include_patterns = []

    root = Path(root_path).resolve()
    project_name = root.name
    file_index: dict[str, ModuleInfo] = {}

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune excluded directories in-place
        dirnames[:] = sorted(
            d for d in dirnames
            if not _should_exclude(d, exclude_dirs)
        )

        for filename in sorted(filenames):
            if not filename.endswith(".py"):
                continue

            full_path = os.path.join(dirpath, filename)
            rel_path = os.path.relpath(full_path, root).replace("\\", "/")

            module_name_suffix, is_package = _path_to_module(rel_path)
            module_name = f"{project_name}.{module_name_suffix}" if module_name_suffix else project_name

            # Apply filters
            if exclude_patterns and _matches_patterns(module_name, exclude_patterns):
                continue
            if include_patterns and not _matches_patterns(module_name, include_patterns):
                continue

            # Determine parent package
            parts = module_name.rsplit(".", 1)
            package = parts[0] if len(parts) > 1 else ""

            file_index[module_name] = ModuleInfo(
                module_name=module_name,
                full_path=full_path,
                rel_path=rel_path,
                package=package,
                is_package=is_package,
                loc=_count_lines(full_path),
            )

    return file_index
