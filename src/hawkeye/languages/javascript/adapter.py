"""JavaScript language adapter (zero dependencies)."""

from __future__ import annotations

import os
import posixpath
from pathlib import Path

from ...core.analyzer import (ImportDetail, ResolvedImport, SymbolInfo,
                              SymbolTable)
from ..base import LanguageAdapter
from ..shared.js_ts_common import (ARROW_RE, CLASS_RE, FUNCTION_RE, METHOD_RE,
                                   compute_cognitive, compute_cyclomatic,
                                   count_js_loc, extract_block,
                                   extract_imports, mask_js_source)


class JavaScriptAdapter(LanguageAdapter):
    name = "javascript"
    extensions = (".js", ".jsx", ".mjs", ".cjs")
    _prefix = "js"

    def path_to_module(self, rel_path: str, project_name: str) -> tuple[str, bool]:
        normalized = rel_path.replace("\\", "/")
        suffix = Path(normalized).suffix
        base = normalized[: -len(suffix)] if suffix else normalized
        parts = [p for p in base.split("/") if p]
        is_package = bool(parts) and parts[-1] == "index"
        if is_package:
            parts = parts[:-1]
        module_name = ".".join(parts) if parts else "index"
        return f"{self._prefix}:{module_name}", is_package

    def count_lines(self, file_path: str) -> int:
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                return count_js_loc(f.read())
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
                with open(info.full_path, "r", encoding="utf-8", errors="replace") as f:
                    source = f.read()
            except OSError:
                imports[module_name] = []
                symbols[module_name] = SymbolTable(parse_error=True)
                continue

            imports[module_name] = self._extract_imports(
                source, info, path_map, known_exts
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
        for imp in extract_imports(source):
            target = self._resolve_specifier(
                imp.specifier, info, path_map, known_exts
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

    def _extract_symbols(self, source: str) -> SymbolTable:
        masked = mask_js_source(source)
        classes: list[SymbolInfo] = []
        functions: list[SymbolInfo] = []
        methods: list[SymbolInfo] = []
        total_methods = 0

        for match in CLASS_RE.finditer(masked):
            name = match.group(1)
            line = source.count("\n", 0, match.start()) + 1
            body = extract_block(masked, source, match.end())
            method_names = METHOD_RE.findall(body)
            method_count = len(method_names)
            total_methods += method_count
            classes.append(SymbolInfo(
                name=name,
                kind="class",
                line=line,
                end_line=line,
                method_count=method_count,
                complexity=compute_cyclomatic(body) if body else 1,
                is_abstract=False,
            ))
            for method in method_names:
                methods.append(SymbolInfo(
                    name=f"{name}.{method}",
                    kind="method",
                    line=line,
                    end_line=line,
                    complexity=1,
                ))

        for match in FUNCTION_RE.finditer(masked):
            name = match.group(1)
            line = source.count("\n", 0, match.start()) + 1
            body = extract_block(masked, source, match.end())
            functions.append(SymbolInfo(
                name=name,
                kind="function",
                line=line,
                end_line=line,
                complexity=compute_cyclomatic(body) if body else 1,
            ))

        for match in ARROW_RE.finditer(masked):
            name = match.group(1)
            line = source.count("\n", 0, match.start()) + 1
            functions.append(SymbolInfo(
                name=name,
                kind="function",
                line=line,
                end_line=line,
                complexity=1,
            ))

        module_cc = compute_cyclomatic(source)
        module_cog = compute_cognitive(source)

        return SymbolTable(
            classes=classes,
            functions=functions,
            methods=methods,
            class_count=len(classes),
            function_count=len(functions),
            method_count=total_methods,
            abstract_class_count=0,
            cyclomatic_complexity=module_cc,
            cognitive_complexity=module_cog,
        )

