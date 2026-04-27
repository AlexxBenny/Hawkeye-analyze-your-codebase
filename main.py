"""Hawkeye entry point.

Usage:
    python main.py analyze <project_path>          # Text analysis
    python main.py show <project_path>             # Interactive HTML graph
    python main.py check <project_path>            # Architecture rule check
    python main.py metrics <project_path>          # Coupling metrics
    python main.py impact <project_path> <module>  # Impact analysis
    python main.py info <project_path> <module>    # Module details
    python main.py serve [--project <path>]        # MCP server for AI editors
"""

import sys
from pathlib import Path

# Add src/ to the import path so 'hawkeye' package is discoverable
_src = str(Path(__file__).resolve().parent / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from hawkeye.cli import main

if __name__ == "__main__":
    sys.exit(main())