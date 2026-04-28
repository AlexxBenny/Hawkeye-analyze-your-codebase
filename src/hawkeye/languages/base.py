"""Language adapter base interfaces."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..config import LanguageSettings

if TYPE_CHECKING:
    from ..core.analyzer import ResolvedImport, SymbolTable
    from ..core.scanner import ModuleInfo


class LanguageAdapter:
    """Base language adapter contract."""

    name: str = ""
    extensions: tuple[str, ...] = ()

    def __init__(self, settings: LanguageSettings | None = None) -> None:
        self.settings = settings or LanguageSettings()
        if self.settings.extensions:
            self.extensions = tuple(self.settings.extensions)

    def path_to_module(self, rel_path: str, project_name: str) -> tuple[str, bool]:
        """Convert a relative path to a module name and package flag."""
        raise NotImplementedError

    def count_lines(self, file_path: str) -> int:
        """Count non-blank, non-comment lines of code."""
        raise NotImplementedError

    def analyze_project(
        self,
        file_index: dict[str, "ModuleInfo"],
        project_name: str,
        project_root: str,
    ) -> tuple[dict[str, list["ResolvedImport"]], dict[str, "SymbolTable"]]:
        """Analyze all modules for this language."""
        raise NotImplementedError
