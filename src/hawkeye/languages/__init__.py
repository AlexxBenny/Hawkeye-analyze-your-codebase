"""Language adapters for multi-language analysis."""

from .base import LanguageAdapter
from .registry import analyze_project, get_language_adapters

__all__ = [
    "LanguageAdapter",
    "get_language_adapters",
    "analyze_project",
]
