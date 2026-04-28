"""Python language adapter."""

from __future__ import annotations

from ...core.models import count_lines, path_to_module
from ..base import LanguageAdapter


class PythonAdapter(LanguageAdapter):
    name = "python"
    extensions = (".py",)

    def path_to_module(self, rel_path: str, project_name: str) -> tuple[str, bool]:
        module_name_suffix, is_package = path_to_module(rel_path)
        module_name = (
            f"{project_name}.{module_name_suffix}" if module_name_suffix else project_name
        )
        return module_name, is_package

    def count_lines(self, file_path: str) -> int:
        return count_lines(file_path)

    def analyze_project(self, file_index, project_name: str, project_root: str):
        from ...core.analyzer import analyze_project as _analyze

        python_files = {
            name: info for name, info in file_index.items()
            if info.language == self.name
        }
        return _analyze(python_files, project_name)
