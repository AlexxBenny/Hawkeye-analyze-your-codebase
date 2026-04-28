"""TypeScript language adapter (zero dependencies)."""

from __future__ import annotations

import json
import os
import posixpath
import re
from pathlib import Path

from ..base import LanguageAdapter
from ..shared.js_ts_common import (
    ARROW_RE,
    CLASS_RE,
    FUNCTION_RE,
    compute_cognitive,
    compute_cyclomatic,
    count_js_loc,
    extract_block,
    extract_imports,
    mask_js_source,
    strip_js_comments,
)
from ...core.analyzer import ImportDetail, ResolvedImport, SymbolInfo, SymbolTable

# TS extends the shared METHOD_RE with `readonly` keyword
_TS_METHOD_RE = re.compile(
    r"(?m)^\s*(?:public|private|protected|static|async|get|set|readonly)?\s*"
    r"([A-Za-z_$][\w$]*)\s*\("
)
_INTERFACE_RE = re.compile(r"\binterface\s+([A-Za-z_$][\w$]*)")
_TYPE_RE = re.compile(r"\btype\s+([A-Za-z_$][\w$]*)\s*=")
_ENUM_RE = re.compile(r"\benum\s+([A-Za-z_$][\w$]*)")


class TypeScriptAdapter(LanguageAdapter):
    name = "typescript"
    extensions = (".ts", ".tsx")
    _prefix = "ts"

    def __init__(self, settings=None) -> None:
        super().__init__(settings)
        self._path_aliases: list[tuple[str, list[str]]] = []
        self._base_url: str | None = None

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
        self._load_tsconfig(project_root)

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
                source, info, path_map, known_exts, project_root
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

    def _load_tsconfig(self, project_root: str) -> None:
        tsconfig_path = self.settings.tsconfig
        if not tsconfig_path:
            tsconfig_path = "tsconfig.json"
        if not os.path.isabs(tsconfig_path):
            tsconfig_path = os.path.join(project_root, tsconfig_path)
        if not os.path.exists(tsconfig_path):
            return
        try:
            raw = Path(tsconfig_path).read_text(encoding="utf-8", errors="replace")
            clean = strip_js_comments(raw)
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

    def _extract_imports(self, source, info, path_map, known_exts, project_root):
        resolved: dict[str, ResolvedImport] = {}
        for imp in extract_imports(source):
            target = self._resolve_specifier(
                imp.specifier, info, path_map, known_exts, project_root
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
        alias_target = self._resolve_alias(spec, path_map, known_exts, project_root)
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

    def _resolve_alias(self, spec, path_map, known_exts, project_root):
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

    def _extract_symbols(self, source: str) -> SymbolTable:
        masked = mask_js_source(source)
        classes: list[SymbolInfo] = []
        functions: list[SymbolInfo] = []
        methods: list[SymbolInfo] = []
        total_methods = 0
        abstract_count = 0

        for match in CLASS_RE.finditer(masked):
            name = match.group(1)
            line = source.count("\n", 0, match.start()) + 1
            body = extract_block(masked, source, match.end())
            method_names = _TS_METHOD_RE.findall(body)
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

        for match in _INTERFACE_RE.finditer(masked):
            name = match.group(1)
            line = source.count("\n", 0, match.start()) + 1
            abstract_count += 1
            classes.append(SymbolInfo(
                name=name,
                kind="interface",
                line=line,
                end_line=line,
                method_count=0,
                complexity=1,
                is_abstract=True,
            ))

        for match in _TYPE_RE.finditer(masked):
            name = match.group(1)
            line = source.count("\n", 0, match.start()) + 1
            abstract_count += 1
            classes.append(SymbolInfo(
                name=name,
                kind="type",
                line=line,
                end_line=line,
                method_count=0,
                complexity=1,
                is_abstract=True,
            ))

        for match in _ENUM_RE.finditer(masked):
            name = match.group(1)
            line = source.count("\n", 0, match.start()) + 1
            classes.append(SymbolInfo(
                name=name,
                kind="enum",
                line=line,
                end_line=line,
                method_count=0,
                complexity=1,
                is_abstract=False,
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
            abstract_class_count=abstract_count,
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

