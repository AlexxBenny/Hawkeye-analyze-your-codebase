"""Shared JS/TS parsing utilities (zero dependencies)."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class JSImport:
    specifier: str
    line: int
    imported_names: list[str]
    is_from_import: bool


_IMPORT_FROM_RE = re.compile(
    r"\bimport\s+(?:type\s+)?(?P<clause>[^;]+?)\s+from\s+"
    r"['\"](?P<spec>[^'\"]+)['\"]",
    re.MULTILINE,
)
_IMPORT_SIDE_RE = re.compile(
    r"\bimport\s+['\"](?P<spec>[^'\"]+)['\"]",
    re.MULTILINE,
)
_EXPORT_FROM_RE = re.compile(
    r"\bexport\s+(?:type\s+)?(?P<clause>[^;]+?)\s+from\s+"
    r"['\"](?P<spec>[^'\"]+)['\"]",
    re.MULTILINE,
)
_DYNAMIC_IMPORT_RE = re.compile(
    r"\bimport\s*\(\s*['\"](?P<spec>[^'\"]+)['\"]\s*\)"
)
_REQUIRE_RE = re.compile(
    r"\brequire\s*\(\s*['\"](?P<spec>[^'\"]+)['\"]\s*\)"
)


def _line_for_index(source: str, index: int) -> int:
    return source.count("\n", 0, index) + 1


def strip_js_comments(source: str) -> str:
    """Strip JS/TS comments while preserving string literals."""
    result: list[str] = []
    i = 0
    state = "code"
    quote = ""
    while i < len(source):
        ch = source[i]
        nxt = source[i + 1] if i + 1 < len(source) else ""
        if state == "code":
            if ch == "/" and nxt == "/":
                result.append(" ")
                result.append(" ")
                i += 2
                state = "line"
                continue
            if ch == "/" and nxt == "*":
                result.append(" ")
                result.append(" ")
                i += 2
                state = "block"
                continue
            if ch in {"'", '"', "`"}:
                quote = ch
                result.append(ch)
                i += 1
                state = "string"
                continue
            result.append(ch)
            i += 1
        elif state == "line":
            if ch == "\n":
                result.append("\n")
                i += 1
                state = "code"
            else:
                result.append(" ")
                i += 1
        elif state == "block":
            if ch == "*" and nxt == "/":
                result.append(" ")
                result.append(" ")
                i += 2
                state = "code"
            else:
                result.append("\n" if ch == "\n" else " ")
                i += 1
        elif state == "string":
            result.append(ch)
            if ch == "\\":
                if i + 1 < len(source):
                    result.append(source[i + 1])
                    i += 2
                else:
                    i += 1
                continue
            if ch == quote:
                state = "code"
            i += 1
    return "".join(result)


def mask_js_source(source: str) -> str:
    """Replace comments and strings with spaces while preserving newlines."""
    result: list[str] = []
    i = 0
    state = "code"
    quote = ""
    while i < len(source):
        ch = source[i]
        nxt = source[i + 1] if i + 1 < len(source) else ""
        if state == "code":
            if ch == "/" and nxt == "/":
                result.append(" ")
                result.append(" ")
                i += 2
                state = "line"
                continue
            if ch == "/" and nxt == "*":
                result.append(" ")
                result.append(" ")
                i += 2
                state = "block"
                continue
            if ch in {"'", '"', "`"}:
                quote = ch
                result.append(" ")
                i += 1
                state = "string"
                continue
            result.append(ch)
            i += 1
        elif state == "line":
            if ch == "\n":
                result.append("\n")
                i += 1
                state = "code"
            else:
                result.append(" ")
                i += 1
        elif state == "block":
            if ch == "*" and nxt == "/":
                result.append(" ")
                result.append(" ")
                i += 2
                state = "code"
            else:
                result.append("\n" if ch == "\n" else " ")
                i += 1
        elif state == "string":
            if ch == "\\":
                result.append(" ")
                if i + 1 < len(source):
                    result.append("\n" if source[i + 1] == "\n" else " ")
                    i += 2
                else:
                    i += 1
                continue
            if ch == quote:
                result.append(" ")
                i += 1
                state = "code"
            else:
                result.append("\n" if ch == "\n" else " ")
                i += 1
    return "".join(result)


def count_js_loc(source: str) -> int:
    """Count non-blank, non-comment lines for JS/TS."""
    stripped = strip_js_comments(source)
    return sum(1 for line in stripped.splitlines() if line.strip())


def extract_imports(source: str) -> list[JSImport]:
    """Extract import/export/require statements from masked source."""
    masked = mask_js_source(source)
    imports: list[JSImport] = []

    def add_match(spec: str, idx: int, names: list[str], is_from_import: bool) -> None:
        imports.append(
            JSImport(
                specifier=spec,
                line=_line_for_index(masked, idx),
                imported_names=names,
                is_from_import=is_from_import,
            )
        )

    for match in _IMPORT_FROM_RE.finditer(masked):
        spec = match.group("spec")
        clause = match.group("clause")
        names = _parse_import_clause(clause)
        add_match(spec, match.start(), names, True)

    for match in _EXPORT_FROM_RE.finditer(masked):
        spec = match.group("spec")
        clause = match.group("clause")
        names = _parse_import_clause(clause)
        add_match(spec, match.start(), names, True)

    for match in _IMPORT_SIDE_RE.finditer(masked):
        spec = match.group("spec")
        add_match(spec, match.start(), ["*"], False)

    for match in _DYNAMIC_IMPORT_RE.finditer(masked):
        spec = match.group("spec")
        add_match(spec, match.start(), ["*"], False)

    for match in _REQUIRE_RE.finditer(masked):
        spec = match.group("spec")
        add_match(spec, match.start(), ["*"], False)

    return imports


def _parse_import_clause(clause: str) -> list[str]:
    """Parse import clause to extract imported symbol names."""
    cleaned = clause.strip()
    cleaned = re.sub(r"^\s*type\s+", "", cleaned)
    names: list[str] = []

    if "{" in cleaned and "}" in cleaned:
        brace_content = cleaned.split("{", 1)[1].rsplit("}", 1)[0]
        for part in brace_content.split(","):
            part = part.strip()
            if not part:
                continue
            if " as " in part:
                part = part.split(" as ", 1)[0].strip()
            names.append(part)

    if cleaned.startswith("*"):
        names.append("*")

    # Default import (before comma)
    if "," in cleaned:
        default_part = cleaned.split(",", 1)[0].strip()
        if default_part and not default_part.startswith("{") and not default_part.startswith("*"):
            names.append("default")
    elif cleaned and not cleaned.startswith("{") and not cleaned.startswith("*"):
        names.append("default")

    return names or ["*"]


def compute_cyclomatic(source: str) -> int:
    """Rudimentary cyclomatic complexity for JS/TS."""
    masked = mask_js_source(source)
    cc = 1
    cc += len(re.findall(r"\b(if|for|while|catch|case|switch)\b", masked))
    cc += len(re.findall(r"&&|\|\|", masked))
    for i, ch in enumerate(masked):
        if ch == "?":
            nxt = masked[i + 1] if i + 1 < len(masked) else ""
            if nxt not in {".", "?"}:
                cc += 1
    return cc


def compute_cognitive(source: str) -> int:
    """Approximate cognitive complexity using brace-based nesting."""
    masked = mask_js_source(source)
    tokens = re.finditer(r"\b(if|for|while|catch|case|switch)\b|[{}?]", masked)
    total = 0
    nesting = 0
    for match in tokens:
        token = match.group(0)
        if token == "{":
            nesting += 1
            continue
        if token == "}":
            nesting = max(0, nesting - 1)
            continue
        if token == "?":
            total += 1 + nesting
            continue
        total += 1 + nesting
    return total
