"""Hawkeye - Python dependency graph analyzer, architecture enforcer, and MCP server.

Provides deep static analysis of Python codebases with interactive visualization,
coupling metrics, cycle detection, architecture rule enforcement, and an MCP
server interface for AI coding agents.
"""

try:
    from importlib.metadata import version
    __version__ = version("hawkeye-analyzer")
except Exception:
    __version__ = "0.0.0-dev"

__author__ = "Alex"
__all__ = ["__version__", "__author__"]
