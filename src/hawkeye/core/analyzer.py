"""AST-based import analysis with full relative import resolution.

Parses Python source files to extract all import statements, resolves
relative imports to absolute module paths, and classifies imports as
internal (within the project) or external (third-party/stdlib).
"""

import ast
from dataclasses import dataclass, field
from typing import Optional

from .scanner import ModuleInfo


@dataclass
class ImportDetail:
    """A single imported name with its source location."""
    imported_name: str     # The specific name imported (e.g. "MyClass")
    line: int              # Source line number
    is_from_import: bool   # True for 'from X import Y', False for 'import X'


@dataclass
class ResolvedImport:
    """A fully resolved import targeting an internal module."""
    raw: str                              # Raw import string as written
    resolved_module: str                  # Fully qualified internal module name
    details: list[ImportDetail] = field(default_factory=list)
    is_internal: bool = True


def _resolve_relative_import(
    importing_module: str,
    is_package: bool,
    level: int,
    module: Optional[str],
) -> Optional[str]:
    """Resolve a relative import to an absolute module path.

    Args:
        importing_module: Dotted name of the module containing the import.
        is_package: Whether the importing module is an __init__.py.
        level: Number of dots in the relative import (1 for '.', 2 for '..').
        module: The module part after the dots (e.g., 'foo' in 'from .foo import bar').

    Returns:
        Resolved absolute module path, or None if resolution fails.
    """
    parts = importing_module.split(".")

    # For a package (__init__.py), the module IS the package.
    # For a regular module, the package is the parent.
    if is_package:
        package_parts = list(parts)
    else:
        package_parts = list(parts[:-1])

    # Go up (level - 1) additional levels from the package
    steps_up = level - 1
    if steps_up > 0:
        if steps_up >= len(package_parts):
            return None  # Can't go above the root
        package_parts = package_parts[:-steps_up]

    if module:
        return ".".join(package_parts + module.split("."))
    else:
        return ".".join(package_parts) if package_parts else None


def _normalize_import(
    raw_import: str,
    project_name: str,
    file_index: dict[str, "ModuleInfo"],
) -> Optional[str]:
    """Try to resolve an absolute import to a known internal module.

    Handles cases like:
        - 'project.core.engine' -> direct match
        - 'core.engine' -> prefixed to 'project.core.engine'
        - 'project.core.engine.MyClass' -> trim to 'project.core.engine'

    Returns:
        The resolved internal module name, or None if external.
    """
    # Direct match (fully qualified)
    if raw_import in file_index:
        return raw_import

    # Try prefixing with project name (handles intra-package imports
    # like 'from brain.core import X' inside project MERLIN)
    prefixed = f"{project_name}.{raw_import}"
    if prefixed in file_index:
        return prefixed

    # Try trimming from the right — the last part might be a class/function
    # rather than a submodule. Check both raw and prefixed forms.
    for base in [raw_import, prefixed]:
        parts = base.split(".")
        for i in range(len(parts) - 1, 0, -1):
            candidate = ".".join(parts[:i])
            if candidate in file_index:
                return candidate

    return None


def analyze_file(
    module_info: ModuleInfo,
    project_name: str,
    file_index: dict[str, "ModuleInfo"],
) -> list[ResolvedImport]:
    """Analyze a Python file and extract all resolved internal imports.

    Args:
        module_info: ModuleInfo for the file to analyze.
        project_name: Top-level project/package name.
        file_index: Complete module index for resolution.

    Returns:
        List of ResolvedImport objects for internal dependencies.
    """
    try:
        with open(module_info.full_path, "r", encoding="utf-8", errors="replace") as f:
            source = f.read()
        tree = ast.parse(source, filename=module_info.full_path)
    except (SyntaxError, OSError):
        return []

    # Collect raw imports with details
    raw_imports: dict[str, list[ImportDetail]] = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                raw_imports.setdefault(alias.name, []).append(
                    ImportDetail(
                        imported_name=alias.name,
                        line=node.lineno,
                        is_from_import=False,
                    )
                )

        elif isinstance(node, ast.ImportFrom):
            level = node.level or 0
            base_module = node.module or ""

            if level > 0:
                # Relative import — resolve to absolute
                resolved_base = _resolve_relative_import(
                    module_info.module_name,
                    module_info.is_package,
                    level,
                    base_module or None,
                )
                if resolved_base is None:
                    continue

                for alias in node.names:
                    # Try resolved_base.name as a module first, then just resolved_base
                    full_candidate = f"{resolved_base}.{alias.name}"
                    raw_imports.setdefault(full_candidate, []).append(
                        ImportDetail(
                            imported_name=alias.name,
                            line=node.lineno,
                            is_from_import=True,
                        )
                    )
                    # Also register the base module as a dependency
                    if resolved_base not in raw_imports:
                        raw_imports.setdefault(resolved_base, []).append(
                            ImportDetail(
                                imported_name=alias.name,
                                line=node.lineno,
                                is_from_import=True,
                            )
                        )
            else:
                # Absolute from-import (e.g., 'from brain.core import Brain')
                for alias in node.names:
                    full_path = f"{base_module}.{alias.name}" if base_module else alias.name
                    raw_imports.setdefault(full_path, []).append(
                        ImportDetail(
                            imported_name=alias.name,
                            line=node.lineno,
                            is_from_import=True,
                        )
                    )
                # Also register the base module itself as a dependency
                if base_module and base_module not in raw_imports:
                    raw_imports.setdefault(base_module, []).append(
                        ImportDetail(
                            imported_name=base_module,
                            line=node.lineno,
                            is_from_import=True,
                        )
                    )

    # Resolve each raw import to internal modules
    resolved: dict[str, ResolvedImport] = {}

    for raw, details in raw_imports.items():
        target = _normalize_import(raw, project_name, file_index)
        if target and target != module_info.module_name:
            if target in resolved:
                resolved[target].details.extend(details)
            else:
                resolved[target] = ResolvedImport(
                    raw=raw,
                    resolved_module=target,
                    details=details,
                    is_internal=True,
                )

    return list(resolved.values())


def analyze_project(
    file_index: dict[str, ModuleInfo],
    project_name: str,
) -> dict[str, list[ResolvedImport]]:
    """Analyze all modules in a project.

    Returns:
        Dictionary mapping module names to their resolved internal imports.
    """
    results: dict[str, list[ResolvedImport]] = {}

    for module_name, module_info in file_index.items():
        results[module_name] = analyze_file(module_info, project_name, file_index)

    return results
