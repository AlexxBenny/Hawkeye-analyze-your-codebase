"""Language adapter registry and multi-language analysis helpers."""

from __future__ import annotations

from typing import Iterable

from ..config import LanguageSettings
from .base import LanguageAdapter


def _normalize_languages(languages: Iterable[str] | None) -> list[str]:
    if not languages:
        return ["python"]
    normalized: list[str] = []
    for lang in languages:
        key = lang.strip().lower()
        if key in {"py"}:
            key = "python"
        elif key in {"js"}:
            key = "javascript"
        elif key in {"ts"}:
            key = "typescript"
        if key not in normalized:
            normalized.append(key)
    return normalized or ["python"]


def get_language_adapters(
    languages: Iterable[str] | None = None,
    settings_map: dict[str, LanguageSettings] | None = None,
) -> dict[str, LanguageAdapter]:
    """Instantiate adapters for the requested languages."""
    from .javascript.adapter import JavaScriptAdapter
    from .python.adapter import PythonAdapter
    from .typescript.adapter import TypeScriptAdapter

    settings_map = settings_map or {}
    adapters: dict[str, LanguageAdapter] = {}

    for lang in _normalize_languages(languages):
        settings = settings_map.get(lang, LanguageSettings())
        if lang == "python":
            adapters[lang] = PythonAdapter(settings)
        elif lang == "javascript":
            adapters[lang] = JavaScriptAdapter(settings)
        elif lang == "typescript":
            adapters[lang] = TypeScriptAdapter(settings)
        else:
            continue

    return adapters


def analyze_project(
    file_index: dict[str, "ModuleInfo"],
    project_name: str,
    project_root: str,
    adapters: dict[str, LanguageAdapter],
) -> tuple[dict[str, list["ResolvedImport"]], dict[str, "SymbolTable"]]:
    """Analyze a mixed-language project by delegating per language."""
    from typing import TYPE_CHECKING

    if TYPE_CHECKING:  # pragma: no cover - typing only
        from ..core.analyzer import ResolvedImport, SymbolTable
        from ..core.models import ModuleInfo

    imports: dict[str, list["ResolvedImport"]] = {}
    symbols: dict[str, "SymbolTable"] = {}

    for adapter in adapters.values():
        lang_imports, lang_symbols = adapter.analyze_project(
            file_index, project_name, project_root
        )
        imports.update(lang_imports)
        symbols.update(lang_symbols)

    return imports, symbols
