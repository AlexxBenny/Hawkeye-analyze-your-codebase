"""AST-based import analysis, symbol extraction, and complexity measurement.

Parses Python source files in a single AST pass to extract:
- All import statements (resolved to absolute module paths)
- Symbol definitions (classes, functions, methods)
- Complexity metrics (cyclomatic, cognitive)

This avoids parsing each file multiple times.
"""

import ast
from dataclasses import dataclass, field
from typing import Optional

from .models import ModuleInfo


@dataclass
class ImportDetail:
    """A single imported name with its source location."""
    imported_name: str     # The specific name imported (e.g. "MyClass")
    line: int              # Source line number
    is_from_import: bool   # True for 'from X import Y', False for 'import X'
    is_type_checking: bool = False  # True if inside `if TYPE_CHECKING:` block
    is_deferred: bool = False       # True if inside a function body (lazy import)


@dataclass
class ResolvedImport:
    """A fully resolved import targeting an internal module."""
    raw: str                              # Raw import string as written
    resolved_module: str                  # Fully qualified internal module name
    details: list[ImportDetail] = field(default_factory=list)
    is_internal: bool = True


@dataclass
class SymbolInfo:
    """A symbol (class, function, or method) defined in a module."""
    name: str
    kind: str              # 'class', 'function', 'method', 'interface', 'type', 'enum'
    line: int
    end_line: int = 0
    method_count: int = 0  # Only for classes: number of methods
    complexity: int = 1    # Cyclomatic complexity of this symbol
    is_abstract: bool = False  # ABC, Protocol, or has @abstractmethod
    decorators: list[str] = field(default_factory=list)  # Decorator names on this symbol


@dataclass
class SymbolTable:
    """All symbols and complexity data extracted from a module."""
    classes: list[SymbolInfo] = field(default_factory=list)
    functions: list[SymbolInfo] = field(default_factory=list)
    methods: list[SymbolInfo] = field(default_factory=list)  # ClassName.method
    class_count: int = 0
    function_count: int = 0
    method_count: int = 0
    abstract_class_count: int = 0    # Classes detected as abstract
    cyclomatic_complexity: int = 1   # Module-level cyclomatic complexity
    cognitive_complexity: int = 0    # Cognitive complexity (nesting-weighted)
    parse_error: bool = False        # True if AST parsing failed

    @property
    def total_symbols(self) -> int:
        return self.class_count + self.function_count


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


# ── Complexity helpers ──────────────────────────────────────────

_BRANCHING_NODES = (
    ast.If, ast.IfExp,
    ast.For, ast.AsyncFor,
    ast.While,
    ast.ExceptHandler,
    ast.With, ast.AsyncWith,
    ast.Assert,
)


def _cyclomatic_complexity(node: ast.AST) -> int:
    """Count cyclomatic complexity for an AST subtree.

    CC = 1 + number of branching points (if/elif/for/while/except/
    and/or/assert/with/ternary).
    """
    cc = 1
    for child in ast.walk(node):
        if isinstance(child, _BRANCHING_NODES):
            cc += 1
        elif isinstance(child, ast.BoolOp):
            # Each 'and'/'or' adds a decision point
            cc += len(child.values) - 1
    return cc


def _cognitive_complexity(body: list[ast.stmt], nesting: int = 0) -> int:
    """Compute cognitive complexity (nesting-weighted).

    Based on SonarSource's cognitive complexity spec:
    - Each branching statement adds 1
    - Each level of nesting adds a nesting increment
    - Sequences of same-type operators don't add extra
    """
    total = 0
    for node in body:
        if isinstance(node, (ast.If, ast.IfExp)):
            total += 1 + nesting
            if hasattr(node, 'body'):
                total += _cognitive_complexity(node.body, nesting + 1)
            if hasattr(node, 'orelse') and node.orelse:
                # 'else' adds 1, 'elif' is handled as nested If
                if len(node.orelse) == 1 and isinstance(node.orelse[0], ast.If):
                    total += _cognitive_complexity(node.orelse, nesting)
                else:
                    total += 1 + _cognitive_complexity(node.orelse, nesting + 1)
        elif isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
            total += 1 + nesting
            total += _cognitive_complexity(node.body, nesting + 1)
            if node.orelse:
                total += 1 + _cognitive_complexity(node.orelse, nesting + 1)
        elif isinstance(node, ast.Try):
            total += _cognitive_complexity(node.body, nesting)
            for handler in node.handlers:
                total += 1 + nesting
                total += _cognitive_complexity(handler.body, nesting + 1)
            if node.orelse:
                total += _cognitive_complexity(node.orelse, nesting)
            if node.finalbody:
                total += _cognitive_complexity(node.finalbody, nesting)
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            total += 1 + nesting
            total += _cognitive_complexity(node.body, nesting + 1)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            total += _cognitive_complexity(node.body, nesting + 1)
        elif isinstance(node, ast.ClassDef):
            total += _cognitive_complexity(node.body, nesting)
        # BoolOp chains
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.BoolOp):
                total += len(child.values) - 1
    return total


# ── Core Analysis ──────────────────────────────────────────────

def _parse_file(module_info: ModuleInfo) -> ast.Module | None:
    """Parse a Python file into an AST. Returns None on failure."""
    try:
        with open(module_info.full_path, "r", encoding="utf-8", errors="replace") as f:
            source = f.read()
        return ast.parse(source, filename=module_info.full_path)
    except (SyntaxError, OSError):
        return None


def _extract_imports(
    tree: ast.Module,
    module_info: ModuleInfo,
    project_name: str,
    file_index: dict[str, "ModuleInfo"],
) -> list[ResolvedImport]:
    """Extract and resolve all imports from a parsed AST.

    Classifies each import as:
    - type_checking: inside an `if TYPE_CHECKING:` block (safe cycle)
    - deferred: inside a function body (lazy import, safe at import-time)
    - runtime: top-level import (actual runtime dependency)
    """
    raw_imports: dict[str, list[ImportDetail]] = {}

    # Pre-compute which top-level If nodes are TYPE_CHECKING guards
    type_checking_nodes: set[int] = set()
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.If) and _is_type_checking_guard(node):
            type_checking_nodes.add(id(node))

    def _collect_import_nodes(
        nodes: list[ast.AST],
        *,
        is_type_checking: bool = False,
        is_deferred: bool = False,
    ) -> None:
        """Recursively collect imports, tracking context."""
        for node in nodes:
            # Detect TYPE_CHECKING guard
            if isinstance(node, ast.If) and id(node) in type_checking_nodes:
                _collect_import_nodes(
                    node.body, is_type_checking=True, is_deferred=is_deferred,
                )
                continue

            # Detect function body → deferred imports
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                _collect_import_nodes(
                    node.body, is_type_checking=is_type_checking, is_deferred=True,
                )
                continue

            # Detect class body → check for TYPE_CHECKING and nested functions
            if isinstance(node, ast.ClassDef):
                _collect_import_nodes(
                    node.body, is_type_checking=is_type_checking, is_deferred=is_deferred,
                )
                continue

            # Non-top-level If/Try blocks → recurse into body
            if isinstance(node, ast.If):
                _collect_import_nodes(
                    node.body, is_type_checking=is_type_checking, is_deferred=is_deferred,
                )
                if node.orelse:
                    _collect_import_nodes(
                        node.orelse, is_type_checking=is_type_checking, is_deferred=is_deferred,
                    )
                continue

            if isinstance(node, ast.Try):
                _collect_import_nodes(
                    node.body, is_type_checking=is_type_checking, is_deferred=is_deferred,
                )
                for handler in node.handlers:
                    _collect_import_nodes(
                        handler.body, is_type_checking=is_type_checking, is_deferred=is_deferred,
                    )
                continue

            if isinstance(node, ast.Import):
                for alias in node.names:
                    raw_imports.setdefault(alias.name, []).append(
                        ImportDetail(
                            imported_name=alias.name,
                            line=node.lineno,
                            is_from_import=False,
                            is_type_checking=is_type_checking,
                            is_deferred=is_deferred,
                        )
                    )

            elif isinstance(node, ast.ImportFrom):
                level = node.level or 0
                base_module = node.module or ""

                if level > 0:
                    resolved_base = _resolve_relative_import(
                        module_info.module_name,
                        module_info.is_package,
                        level,
                        base_module or None,
                    )
                    if resolved_base is None:
                        continue

                    for alias in node.names:
                        full_candidate = f"{resolved_base}.{alias.name}"
                        raw_imports.setdefault(full_candidate, []).append(
                            ImportDetail(
                                imported_name=alias.name,
                                line=node.lineno,
                                is_from_import=True,
                                is_type_checking=is_type_checking,
                                is_deferred=is_deferred,
                            )
                        )
                        if resolved_base not in raw_imports:
                            raw_imports.setdefault(resolved_base, []).append(
                                ImportDetail(
                                    imported_name=alias.name,
                                    line=node.lineno,
                                    is_from_import=True,
                                    is_type_checking=is_type_checking,
                                    is_deferred=is_deferred,
                                )
                            )
                else:
                    for alias in node.names:
                        full_path = f"{base_module}.{alias.name}" if base_module else alias.name
                        raw_imports.setdefault(full_path, []).append(
                            ImportDetail(
                                imported_name=alias.name,
                                line=node.lineno,
                                is_from_import=True,
                                is_type_checking=is_type_checking,
                                is_deferred=is_deferred,
                            )
                        )
                    if base_module and base_module not in raw_imports:
                        raw_imports.setdefault(base_module, []).append(
                            ImportDetail(
                                imported_name=base_module,
                                line=node.lineno,
                                is_from_import=True,
                                is_type_checking=is_type_checking,
                                is_deferred=is_deferred,
                            )
                        )

    _collect_import_nodes(tree.body)

    # Resolve to internal modules
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


def _is_type_checking_guard(node: ast.If) -> bool:
    """Check if an `if` node is a `if TYPE_CHECKING:` guard."""
    test = node.test
    # `if TYPE_CHECKING:`
    if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
        return True
    # `if typing.TYPE_CHECKING:`
    if isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING":
        return True
    return False


# ── Abstract class detection ──────────────────────────────────
# Conservative, high-confidence heuristics only.
# We check base names syntactically — no import resolution needed.

_ABSTRACT_BASE_NAMES = frozenset({"ABC", "ABCMeta", "Protocol"})


def _is_abstract_class(node: ast.ClassDef) -> bool:
    """Detect if a class is abstract using high-confidence patterns.

    High-confidence signals (any one is sufficient):
    - Inherits from ABC, ABCMeta, or Protocol (by name)
    - Uses metaclass=ABCMeta keyword
    - Contains at least one @abstractmethod-decorated method
    """
    # Check base classes by name
    for base in node.bases:
        name = None
        if isinstance(base, ast.Name):
            name = base.id
        elif isinstance(base, ast.Attribute):
            name = base.attr
        if name in _ABSTRACT_BASE_NAMES:
            return True

    # Check metaclass=ABCMeta keyword
    for kw in node.keywords:
        if kw.arg == "metaclass":
            kw_name = None
            if isinstance(kw.value, ast.Name):
                kw_name = kw.value.id
            elif isinstance(kw.value, ast.Attribute):
                kw_name = kw.value.attr
            if kw_name == "ABCMeta":
                return True

    # Check for @abstractmethod on any method
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in child.decorator_list:
                dec_name = None
                if isinstance(dec, ast.Name):
                    dec_name = dec.id
                elif isinstance(dec, ast.Attribute):
                    dec_name = dec.attr
                if dec_name == "abstractmethod":
                    return True

    return False


def _extract_decorator_names(node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """Extract human-readable decorator names from a decorated node.

    Handles common patterns:
      - @decorator           → 'decorator'
      - @module.decorator     → 'module.decorator'
      - @app.get("/path")    → 'app.get'
      - @router.post("/x")   → 'router.post'
    """
    names: list[str] = []
    for dec in node.decorator_list:
        name = _decorator_name(dec)
        if name:
            names.append(name)
    return names


def _decorator_name(node: ast.expr) -> str | None:
    """Resolve a single decorator AST node to a dotted name string."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _decorator_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    if isinstance(node, ast.Call):
        return _decorator_name(node.func)
    return None


def _extract_symbols(tree: ast.Module) -> SymbolTable:
    """Extract class/function definitions and complexity from a parsed AST."""
    classes: list[SymbolInfo] = []
    functions: list[SymbolInfo] = []
    all_methods: list[SymbolInfo] = []
    total_methods = 0
    abstract_count = 0

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            methods = [
                n for n in ast.iter_child_nodes(node)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            total_methods += len(methods)
            is_abstract = _is_abstract_class(node)
            if is_abstract:
                abstract_count += 1
            classes.append(SymbolInfo(
                name=node.name,
                kind="class",
                line=node.lineno,
                end_line=getattr(node, 'end_lineno', node.lineno),
                method_count=len(methods),
                complexity=_cyclomatic_complexity(node),
                is_abstract=is_abstract,
                decorators=_extract_decorator_names(node),
            ))
            # Extract per-method entries for function breakdown
            for method_node in methods:
                all_methods.append(SymbolInfo(
                    name=f"{node.name}.{method_node.name}",
                    kind="method",
                    line=method_node.lineno,
                    end_line=getattr(method_node, 'end_lineno', method_node.lineno),
                    complexity=_cyclomatic_complexity(method_node),
                    decorators=_extract_decorator_names(method_node),
                ))

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(SymbolInfo(
                name=node.name,
                kind="function",
                line=node.lineno,
                end_line=getattr(node, 'end_lineno', node.lineno),
                complexity=_cyclomatic_complexity(node),
                decorators=_extract_decorator_names(node),
            ))

    # Module-level complexity
    module_cc = _cyclomatic_complexity(tree)
    module_cog = _cognitive_complexity(tree.body)

    return SymbolTable(
        classes=classes,
        functions=functions,
        methods=all_methods,
        class_count=len(classes),
        function_count=len(functions),
        method_count=total_methods,
        abstract_class_count=abstract_count,
        cyclomatic_complexity=module_cc,
        cognitive_complexity=module_cog,
    )


def analyze_file(
    module_info: ModuleInfo,
    project_name: str,
    file_index: dict[str, "ModuleInfo"],
) -> list[ResolvedImport]:
    """Analyze a Python file and extract all resolved internal imports."""
    tree = _parse_file(module_info)
    if tree is None:
        return []
    return _extract_imports(tree, module_info, project_name, file_index)


def analyze_file_full(
    module_info: ModuleInfo,
    project_name: str,
    file_index: dict[str, "ModuleInfo"],
) -> tuple[list[ResolvedImport], SymbolTable]:
    """Analyze a file for imports AND symbols in a single AST parse."""
    tree = _parse_file(module_info)
    if tree is None:
        return [], SymbolTable(parse_error=True)
    imports = _extract_imports(tree, module_info, project_name, file_index)
    symbols = _extract_symbols(tree)
    return imports, symbols


def analyze_project(
    file_index: dict[str, ModuleInfo],
    project_name: str,
) -> tuple[dict[str, list[ResolvedImport]], dict[str, SymbolTable]]:
    """Analyze all modules for imports and symbols in a single pass.

    Returns:
        Tuple of (imports_by_module, symbols_by_module).
    """
    imports: dict[str, list[ResolvedImport]] = {}
    symbols: dict[str, SymbolTable] = {}

    for module_name, module_info in file_index.items():
        mod_imports, mod_symbols = analyze_file_full(
            module_info, project_name, file_index
        )
        imports[module_name] = mod_imports
        symbols[module_name] = mod_symbols

    return imports, symbols
