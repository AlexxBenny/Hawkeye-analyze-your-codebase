"""CLI shared helpers — engine creation and UTF-8 setup."""

import sys


def ensure_utf8() -> None:
    """Reconfigure stdout for UTF-8 on Windows."""
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def _make_engine(args, *, use_config: bool = False):
    """Create and run an engine from CLI args."""
    from pathlib import Path

    from ..config import HawkeyeConfig, LanguageSettings
    from ..engine import HawkeyeEngine

    if use_config and hasattr(args, "config") and args.config:
        config = HawkeyeConfig.from_toml(Path(args.config))
    elif use_config:
        config = HawkeyeConfig.find_and_load(Path(args.project))
    else:
        config = HawkeyeConfig()
        if hasattr(args, "exclude"):
            config.exclude_patterns = args.exclude or []
        if hasattr(args, "include"):
            config.include_patterns = args.include or []
        if hasattr(args, "languages") and args.languages:
            config.languages = args.languages

    if hasattr(args, "languages") and args.languages:
        config.languages = args.languages
    if hasattr(args, "tsconfig") and args.tsconfig:
        config.language_settings.setdefault(
            "typescript", LanguageSettings()
        ).tsconfig = args.tsconfig
    if hasattr(args, "package_root") and args.package_root:
        for lang in ("javascript", "typescript"):
            config.language_settings.setdefault(
                lang, LanguageSettings()
            ).package_root = args.package_root

    engine = HawkeyeEngine(config)
    engine.analyze(args.project)
    return engine
