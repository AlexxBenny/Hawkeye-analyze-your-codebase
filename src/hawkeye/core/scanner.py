"""File discovery and module indexing.

Walks a project tree, converts file paths to dotted module names,
and builds a structured index of all discoverable modules. Handles
language-specific module conventions and configurable exclusions.
"""

import fnmatch
import os
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from .models import ModuleInfo, count_lines, path_to_module  # canonical; re-exported

if TYPE_CHECKING:
    from ..languages.base import LanguageAdapter


# Backward-compatible aliases (deprecated — use the public names)
_count_lines = count_lines
_path_to_module = path_to_module


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
    languages: Optional[list[str]] = None,
    language_settings: Optional[dict] = None,
    *,
    adapters: Optional[dict[str, "LanguageAdapter"]] = None,
) -> dict[str, ModuleInfo]:
    """Scan a project and build a module index.

    Args:
        root_path: Absolute path to the project root directory.
        exclude_dirs: Directory names to skip during traversal.
        exclude_patterns: Glob patterns for module names to exclude.
        include_patterns: If set, only modules matching these patterns are included.
        languages: Language names to enable (default: Python only).
        language_settings: Per-language configuration.
        adapters: Pre-built adapter dict (avoids import cycle when
                  called from engine). If not provided, falls back to
                  lazy import of the registry for backward compatibility.

    Returns:
        Dictionary mapping dotted module names to ModuleInfo objects.
    """
    from ..config import DEFAULT_EXCLUDES

    if adapters is None:
        # Backward-compatible fallback — only used by tests and CLI
        from ..languages.registry import get_language_adapters
        adapters = get_language_adapters(languages, language_settings or {})

    if exclude_dirs is None:
        exclude_dirs = DEFAULT_EXCLUDES
    if exclude_patterns is None:
        exclude_patterns = []
    if include_patterns is None:
        include_patterns = []

    root = Path(root_path).resolve()
    project_name = root.name
    file_index: dict[str, ModuleInfo] = {}
    extension_map = {
        ext.lower(): adapter
        for adapter in adapters.values()
        for ext in adapter.extensions
    }

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune excluded directories in-place
        dirnames[:] = sorted(
            d for d in dirnames
            if not _should_exclude(d, exclude_dirs)
        )

        for filename in sorted(filenames):
            ext = Path(filename).suffix.lower()
            adapter = extension_map.get(ext)
            if not adapter:
                continue

            full_path = os.path.join(dirpath, filename)
            rel_path = os.path.relpath(full_path, root).replace("\\", "/")

            module_name, is_package = adapter.path_to_module(rel_path, project_name)

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
                loc=adapter.count_lines(full_path),
                language=adapter.name,
            )

    return file_index

