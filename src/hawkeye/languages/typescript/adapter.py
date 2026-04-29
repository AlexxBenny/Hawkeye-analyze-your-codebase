"""TypeScript language adapter (tree-sitter based).

Requires: pip install hawkeye-analyzer[ts]
    (installs tree-sitter + tree-sitter-typescript)
"""

from __future__ import annotations

import json
import os
import posixpath
from pathlib import Path

from ...core.analyzer import (ImportDetail, ResolvedImport, SymbolInfo,
                              SymbolTable)
from ..base import LanguageAdapter
from ..shared.js_ts_treesitter import (compute_cognitive, compute_cyclomatic,
                                       count_loc, extract_imports,
                                       extract_symbols)


class TypeScriptAdapter(LanguageAdapter):
    name = "typescript"
    extensions = (".ts", ".tsx")

    def __init__(self, settings=None) -> None:
        super().__init__(settings)
        self._path_aliases: list[tuple[str, list[str]]] = []
        self._base_url: str | None = None

    def _lang_for_ext(self, ext: str) -> str:
        """Return tree-sitter language name based on file extension."""
        return "tsx" if ext in (".tsx",) else "typescript"

    def path_to_module(self, rel_path: str, project_name: str) -> tuple[str, bool]:
        normalized = rel_path.replace("\\", "/")
        suffix = Path(normalized).suffix
        base = normalized[: -len(suffix)] if suffix else normalized
        parts = [p for p in base.split("/") if p]
        is_package = bool(parts) and parts[-1] == "index"
        if is_package:
            parts = parts[:-1]
        module_name = ".".join(parts) if parts else "index"
        return f"ts:{module_name}", is_package

    def count_lines(self, file_path: str) -> int:
        ext = Path(file_path).suffix
        lang_name = self._lang_for_ext(ext)
        try:
            with open(file_path, "rb") as f:
                return count_loc(f.read(), lang_name)
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
        self._load_tsconfig(project_root)

        for module_name, info in file_index.items():
            if info.language != self.name:
                continue
            ext = Path(info.rel_path).suffix
            lang_name = self._lang_for_ext(ext)
            try:
                with open(info.full_path, "rb") as f:
                    source = f.read()
            except OSError:
                imports[module_name] = []
                symbols[module_name] = SymbolTable(parse_error=True)
                continue

            imports[module_name] = self._extract_imports(
                source, info, path_map, known_exts, project_root, lang_name,
            )
            symbols[module_name] = self._extract_symbols(source, lang_name)

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

    def _load_tsconfig(self, project_root: str) -> None:
        """Load path aliases from tsconfig.json."""
        tsconfig_path = self.settings.tsconfig
        if not tsconfig_path:
            tsconfig_path = "tsconfig.json"
        if not os.path.isabs(tsconfig_path):
            tsconfig_path = os.path.join(project_root, tsconfig_path)
        if not os.path.exists(tsconfig_path):
            return
        try:
            raw = Path(tsconfig_path).read_text(encoding="utf-8", errors="replace")
            # Strip single-line comments for JSON parsing
            import re
            clean = re.sub(r"//.*$", "", raw, flags=re.MULTILINE)
            data = json.loads(clean)
        except (OSError, json.JSONDecodeError):
            return
        compiler = data.get("compilerOptions", {})
        base_url = compiler.get("baseUrl")
        if base_url:
            base_dir = Path(tsconfig_path).parent
            abs_base = (base_dir / base_url).resolve()
            self._base_url = os.path.relpath(abs_base, project_root).replace("\\", "/")
        paths = compiler.get("paths", {})
        aliases: list[tuple[str, list[str]]] = []
        for key, targets in paths.items():
            if isinstance(targets, list):
                aliases.append((key, targets))
        self._path_aliases = aliases

    def _extract_imports(self, source, info, path_map, known_exts,
                         project_root, lang_name):
        resolved: dict[str, ResolvedImport] = {}
        for imp in extract_imports(source, lang_name):
            target = self._resolve_specifier(
                imp.specifier, info, path_map, known_exts, project_root,
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

    def _resolve_specifier(self, spec, info, path_map, known_exts, project_root):
        if spec.startswith(".") or spec.startswith("/"):
            return self._resolve_relative(spec, info, path_map, known_exts)
        alias_target = self._resolve_alias(spec, path_map, known_exts)
        if alias_target:
            return alias_target
        return None

    def _resolve_relative(self, spec, info, path_map, known_exts):
        if spec.startswith("."):
            base = posixpath.dirname(info.rel_path.replace("\\", "/"))
            target = posixpath.normpath(posixpath.join(base, spec))
        else:
            base_root = (self.settings.package_root or "").strip("/")
            target = posixpath.normpath(posixpath.join(base_root, spec.lstrip("/")))

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

    def _resolve_alias(self, spec, path_map, known_exts):
        for key, targets in self._path_aliases:
            prefix, suffix, matched = _match_alias(spec, key)
            if not matched:
                continue
            middle = spec[len(prefix): len(spec) - len(suffix)] if suffix else spec[len(prefix):]
            for target in targets:
                candidate = target
                if "*" in target:
                    candidate = target.replace("*", middle)
                if self._base_url:
                    candidate = posixpath.join(self._base_url, candidate)
                candidate = posixpath.normpath(candidate)
                resolved = self._resolve_candidate(candidate, path_map, known_exts)
                if resolved:
                    return resolved
        return None

    def _resolve_candidate(self, candidate, path_map, known_exts):
        candidates = []
        if os.path.splitext(candidate)[1]:
            candidates.append(candidate)
        else:
            for ext in known_exts:
                candidates.append(f"{candidate}{ext}")
            for ext in known_exts:
                candidates.append(posixpath.join(candidate, f"index{ext}"))
        for item in candidates:
            normalized = item.replace("\\", "/")
            if normalized in path_map:
                return path_map[normalized]
        return None

    def _extract_symbols(self, source: bytes, lang_name: str) -> SymbolTable:
        raw_symbols = extract_symbols(source, lang_name)
        classes: list[SymbolInfo] = []
        functions: list[SymbolInfo] = []
        methods: list[SymbolInfo] = []
        total_methods = 0
        abstract_count = 0

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
            elif sym.kind in ("interface", "type"):
                classes.append(si)
                abstract_count += 1
            elif sym.kind == "enum":
                classes.append(si)
            elif sym.kind == "function":
                functions.append(si)

        module_cc = compute_cyclomatic(source, lang_name)
        module_cog = compute_cognitive(source, lang_name)

        return SymbolTable(
            classes=classes, functions=functions, methods=methods,
            class_count=len(classes), function_count=len(functions),
            method_count=total_methods, abstract_class_count=abstract_count,
            cyclomatic_complexity=module_cc,
            cognitive_complexity=module_cog,
        )


def _match_alias(spec: str, alias: str) -> tuple[str, str, bool]:
    if "*" not in alias:
        return alias, "", spec == alias
    prefix, suffix = alias.split("*", 1)
    if not spec.startswith(prefix):
        return prefix, suffix, False
    if suffix and not spec.endswith(suffix):
        return prefix, suffix, False
    return prefix, suffix, True
