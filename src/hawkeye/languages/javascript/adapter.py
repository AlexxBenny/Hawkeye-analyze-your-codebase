"""JavaScript language adapter (tree-sitter based).

Requires: pip install hawkeye-analyzer[js]
    (installs tree-sitter + tree-sitter-javascript)
"""

from __future__ import annotations

import os
import posixpath
from pathlib import Path

from ...core.analyzer import (ImportDetail, ResolvedImport, SymbolInfo,
                              SymbolTable)
from ..base import LanguageAdapter
from ..shared.js_ts_treesitter import (compute_cognitive, compute_cyclomatic,
                                       count_loc, extract_imports,
                                       extract_symbols)


class JavaScriptAdapter(LanguageAdapter):
    name = "javascript"
    extensions = (".js", ".jsx", ".mjs", ".cjs")
    _lang_name = "javascript"

    def path_to_module(self, rel_path: str, project_name: str) -> tuple[str, bool]:
        normalized = rel_path.replace("\\", "/")
        suffix = Path(normalized).suffix
        base = normalized[: -len(suffix)] if suffix else normalized
        parts = [p for p in base.split("/") if p]
        is_package = bool(parts) and parts[-1] == "index"
        if is_package:
            parts = parts[:-1]
        module_name = ".".join(parts) if parts else "index"
        return f"js:{module_name}", is_package

    def count_lines(self, file_path: str) -> int:
        try:
            with open(file_path, "rb") as f:
                return count_loc(f.read(), self._lang_name)
        except OSError:
            return 0

    def analyze_project(self, file_index, project_name: str, project_root: str):
        imports: dict[str, list[ResolvedImport]] = {}
        symbols: dict[str, SymbolTable] = {}
        path_map = {
            info.rel_path.replace("\\", "/"): name
            for name, info in file_index.items()
        }
        known_exts = self._known_extensions(file_index)

        for module_name, info in file_index.items():
            if info.language != self.name:
                continue
            try:
                with open(info.full_path, "rb") as f:
                    source = f.read()
            except OSError:
                imports[module_name] = []
                symbols[module_name] = SymbolTable(parse_error=True)
                continue

            imports[module_name] = self._extract_imports(
                source, info, path_map, known_exts,
            )
            symbols[module_name] = self._extract_symbols(source)

        return imports, symbols

    def _known_extensions(self, file_index) -> tuple[str, ...]:
        supported = {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"}
        exts = {
            Path(info.rel_path).suffix
            for info in file_index.values()
            if Path(info.rel_path).suffix in supported
        }
        exts.discard("")
        return tuple(sorted(exts)) or self.extensions

    def _extract_imports(self, source, info, path_map, known_exts):
        resolved: dict[str, ResolvedImport] = {}
        for imp in extract_imports(source, self._lang_name):
            target = self._resolve_specifier(
                imp.specifier, info, path_map, known_exts,
            )
            if not target or target == info.module_name:
                continue
            details = [
                ImportDetail(
                    imported_name=name,
                    line=imp.line,
                    is_from_import=imp.is_from_import,
                )
                for name in imp.imported_names
            ]
            if target in resolved:
                resolved[target].details.extend(details)
            else:
                resolved[target] = ResolvedImport(
                    raw=imp.specifier,
                    resolved_module=target,
                    details=details,
                    is_internal=True,
                )
        return list(resolved.values())

    def _resolve_specifier(self, spec, info, path_map, known_exts):
        if spec.startswith("."):
            base = posixpath.dirname(info.rel_path.replace("\\", "/"))
            target = posixpath.normpath(posixpath.join(base, spec))
        elif spec.startswith("/"):
            base_root = (self.settings.package_root or "").strip("/")
            target = posixpath.normpath(posixpath.join(base_root, spec.lstrip("/")))
        else:
            return None

        candidates = []
        if os.path.splitext(target)[1]:
            candidates.append(target)
        else:
            for ext in known_exts:
                candidates.append(f"{target}{ext}")
            for ext in known_exts:
                candidates.append(posixpath.join(target, f"index{ext}"))

        for candidate in candidates:
            normalized = candidate.replace("\\", "/")
            if normalized in path_map:
                return path_map[normalized]
        return None

    def _extract_symbols(self, source: bytes) -> SymbolTable:
        raw_symbols = extract_symbols(source, self._lang_name)
        classes: list[SymbolInfo] = []
        functions: list[SymbolInfo] = []
        methods: list[SymbolInfo] = []
        total_methods = 0

        for sym in raw_symbols:
            si = SymbolInfo(
                name=sym.name, kind=sym.kind,
                line=sym.line, end_line=sym.end_line,
                complexity=sym.complexity,
                method_count=sym.method_count,
                is_abstract=sym.is_abstract,
            )
            if sym.kind == "class":
                classes.append(si)
                total_methods += sym.method_count
                for method in sym.methods:
                    methods.append(SymbolInfo(
                        name=f"{sym.name}.{method}", kind="method",
                        line=sym.line, end_line=sym.end_line, complexity=1,
                    ))
            elif sym.kind == "function":
                functions.append(si)

        module_cc = compute_cyclomatic(source, self._lang_name)
        module_cog = compute_cognitive(source, self._lang_name)

        return SymbolTable(
            classes=classes, functions=functions, methods=methods,
            class_count=len(classes), function_count=len(functions),
            method_count=total_methods, abstract_class_count=0,
            cyclomatic_complexity=module_cc,
            cognitive_complexity=module_cog,
        )
