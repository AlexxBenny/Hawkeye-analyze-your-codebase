"""Tree-sitter based JS/TS parsing (replaces regex approach).

Provides AST-accurate import extraction, symbol detection, and complexity
metrics for JavaScript and TypeScript using tree-sitter grammars.

Requires:
    pip install tree-sitter tree-sitter-javascript   # for JS
    pip install tree-sitter tree-sitter-typescript    # for TS
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from tree_sitter import Language, Parser, Query, QueryCursor

if TYPE_CHECKING:
    from tree_sitter import Node, Tree


# ── Lazy language singletons ───────────────────────────────────


def _js_language() -> Language:
    import tree_sitter_javascript as _js
    return Language(_js.language())


def _ts_language() -> Language:
    import tree_sitter_typescript as _ts
    return Language(_ts.language_typescript())


def _tsx_language() -> Language:
    import tree_sitter_typescript as _ts
    return Language(_ts.language_tsx())


# Cache to avoid re-creating Language objects
_LANG_CACHE: dict[str, Language] = {}


def get_language(name: str) -> Language:
    """Get a cached tree-sitter Language by name."""
    if name not in _LANG_CACHE:
        factory = {"javascript": _js_language, "typescript": _ts_language,
                    "tsx": _tsx_language}
        if name not in factory:
            raise ValueError(f"Unsupported language: {name}")
        _LANG_CACHE[name] = factory[name]()
    return _LANG_CACHE[name]


def get_parser(name: str) -> Parser:
    """Create a parser for the given language."""
    lang = get_language(name)
    return Parser(lang)


# ── Data structures ───────────────────────────────────────────


@dataclass(frozen=True)
class JSImport:
    """A resolved import/require/re-export statement."""
    specifier: str
    line: int
    imported_names: list[str]
    is_from_import: bool


# ── Import extraction ─────────────────────────────────────────

# S-expression queries for each import type.
# These run against the full AST — no regex, no masking needed.

_IMPORT_QUERY_SRC = """
(import_statement
  source: (string) @source) @import_stmt

(call_expression
  function: (import)
  arguments: (arguments (string) @dynamic_source)) @dynamic_import

(call_expression
  function: (identifier) @_fn
  arguments: (arguments (string) @require_source)
  (#eq? @_fn "require")) @require_call

(export_statement
  source: (string) @reexport_source) @reexport
"""

# Cache compiled queries per language
_IMPORT_QUERIES: dict[str, Query] = {}


def _get_import_query(lang_name: str) -> Query:
    if lang_name not in _IMPORT_QUERIES:
        lang = get_language(lang_name)
        _IMPORT_QUERIES[lang_name] = Query(lang, _IMPORT_QUERY_SRC)
    return _IMPORT_QUERIES[lang_name]


def _strip_quotes(text: str) -> str:
    """Remove surrounding quotes from a string literal."""
    if len(text) >= 2 and text[0] in ("'", '"', "`") and text[-1] == text[0]:
        return text[1:-1]
    return text


def _extract_import_names(node: "Node") -> tuple[list[str], bool]:
    """Extract imported symbol names from an import_statement node.

    Returns (names, is_from_import).
    """
    names: list[str] = []
    is_from = True

    for child in node.children:
        if child.type == "import_clause":
            for sub in child.children:
                if sub.type == "identifier":
                    # Default import: import X from '...'
                    names.append("default")
                elif sub.type == "namespace_import":
                    names.append("*")
                elif sub.type == "named_imports":
                    for spec in sub.named_children:
                        if spec.type == "import_specifier":
                            name_node = spec.child_by_field_name("name")
                            if name_node:
                                names.append(name_node.text.decode("utf-8"))

    # Side-effect import: import './file'
    if not names:
        names = ["*"]
        is_from = False

    return names, is_from


def extract_imports(source: bytes, lang_name: str) -> list[JSImport]:
    """Extract all import/require/re-export statements from source.

    Uses tree-sitter AST queries — accurate across all syntax variants.
    """
    lang = get_language(lang_name)
    parser = Parser(lang)
    tree = parser.parse(source)
    query = _get_import_query(lang_name)
    cursor = QueryCursor(query)
    captures = cursor.captures(tree.root_node)
    imports: list[JSImport] = []
    seen: set[tuple[str, int]] = set()  # (specifier, line) dedup

    # Static imports: import ... from '...'
    for node in captures.get("import_stmt", []):
        source_node = node.child_by_field_name("source")
        if not source_node:
            continue
        spec = _strip_quotes(source_node.text.decode("utf-8"))
        line = node.start_point[0] + 1
        key = (spec, line)
        if key in seen:
            continue
        seen.add(key)
        names, is_from = _extract_import_names(node)
        imports.append(JSImport(spec, line, names, is_from))

    # Dynamic imports: import('...')
    for node in captures.get("dynamic_source", []):
        spec = _strip_quotes(node.text.decode("utf-8"))
        line = node.start_point[0] + 1
        key = (spec, line)
        if key not in seen:
            seen.add(key)
            imports.append(JSImport(spec, line, ["*"], False))

    # require('...')
    for node in captures.get("require_source", []):
        spec = _strip_quotes(node.text.decode("utf-8"))
        line = node.start_point[0] + 1
        key = (spec, line)
        if key not in seen:
            seen.add(key)
            imports.append(JSImport(spec, line, ["*"], False))

    # Re-exports: export ... from '...'
    for node in captures.get("reexport_source", []):
        spec = _strip_quotes(node.text.decode("utf-8"))
        line = node.start_point[0] + 1
        key = (spec, line)
        if key not in seen:
            seen.add(key)
            imports.append(JSImport(spec, line, ["*"], True))

    return imports


# ── Symbol extraction ─────────────────────────────────────────

_JS_SYMBOL_QUERY_SRC = """
(class_declaration name: (identifier) @class_name) @class_decl
(function_declaration name: (identifier) @fn_name) @fn_decl
(lexical_declaration
  (variable_declarator
    name: (identifier) @arrow_name
    value: (arrow_function) @arrow_body))
(method_definition
  name: (property_identifier) @method_name) @method_def
"""

# TS grammar uses type_identifier for class names, not identifier.
# Abstract classes use a separate node type: abstract_class_declaration.
_TS_SYMBOL_QUERY_SRC = """
(class_declaration name: (type_identifier) @class_name) @class_decl
(abstract_class_declaration name: (type_identifier) @class_name) @class_decl
(function_declaration name: (identifier) @fn_name) @fn_decl
(lexical_declaration
  (variable_declarator
    name: (identifier) @arrow_name
    value: (arrow_function) @arrow_body))
(method_definition
  name: (property_identifier) @method_name) @method_def
(interface_declaration name: (type_identifier) @iface_name) @iface_decl
(type_alias_declaration name: (type_identifier) @type_name) @type_decl
(enum_declaration name: (identifier) @enum_name) @enum_decl
"""

_SYMBOL_QUERIES: dict[str, Query] = {}


def _get_symbol_query(lang_name: str) -> Query:
    if lang_name not in _SYMBOL_QUERIES:
        lang = get_language(lang_name)
        src = _TS_SYMBOL_QUERY_SRC if lang_name in ("typescript", "tsx") else _JS_SYMBOL_QUERY_SRC
        _SYMBOL_QUERIES[lang_name] = Query(lang, src)
    return _SYMBOL_QUERIES[lang_name]


@dataclass
class RawSymbol:
    """Intermediate symbol data before conversion to SymbolInfo."""
    name: str
    kind: str  # class, function, method, interface, type, enum
    line: int
    end_line: int
    complexity: int = 1
    method_count: int = 0
    is_abstract: bool = False
    methods: list[str] = field(default_factory=list)


def extract_symbols(source: bytes, lang_name: str) -> list[RawSymbol]:
    """Extract all class/function/interface/type/enum symbols from source."""
    lang = get_language(lang_name)
    parser = Parser(lang)
    tree = parser.parse(source)
    query = _get_symbol_query(lang_name)
    cursor = QueryCursor(query)
    captures = cursor.captures(tree.root_node)
    symbols: list[RawSymbol] = []

    # Classes
    for node in captures.get("class_decl", []):
        name_node = node.child_by_field_name("name")
        name = name_node.text.decode("utf-8") if name_node else "?"
        body = node.child_by_field_name("body")
        methods = _extract_method_names(body) if body else []
        cc = _count_cc(node)
        is_abstract = (node.type == "abstract_class_declaration"
                       or _has_keyword(node, "abstract"))
        symbols.append(RawSymbol(
            name=name, kind="class",
            line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            complexity=cc, method_count=len(methods),
            is_abstract=is_abstract, methods=methods,
        ))

    # Functions
    for node in captures.get("fn_decl", []):
        name_node = node.child_by_field_name("name")
        name = name_node.text.decode("utf-8") if name_node else "?"
        symbols.append(RawSymbol(
            name=name, kind="function",
            line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            complexity=_count_cc(node),
        ))

    # Arrow functions (const x = () => ...)
    for node in captures.get("arrow_name", []):
        name = node.text.decode("utf-8")
        # Find the enclosing lexical_declaration for end_line
        parent = node.parent  # variable_declarator
        if parent and parent.parent:
            parent = parent.parent  # lexical_declaration
        end_line = parent.end_point[0] + 1 if parent else node.end_point[0] + 1
        # Get arrow body for complexity
        arrow_nodes = captures.get("arrow_body", [])
        cc = 1
        for ab in arrow_nodes:
            if ab.start_point[0] == node.start_point[0]:
                cc = _count_cc(ab)
                break
        symbols.append(RawSymbol(
            name=name, kind="function",
            line=node.start_point[0] + 1,
            end_line=end_line,
            complexity=cc,
        ))

    # Interfaces (TS only)
    for node in captures.get("iface_decl", []):
        name_node = node.child_by_field_name("name")
        name = name_node.text.decode("utf-8") if name_node else "?"
        symbols.append(RawSymbol(
            name=name, kind="interface",
            line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            is_abstract=True,
        ))

    # Type aliases (TS only)
    for node in captures.get("type_decl", []):
        name_node = node.child_by_field_name("name")
        name = name_node.text.decode("utf-8") if name_node else "?"
        symbols.append(RawSymbol(
            name=name, kind="type",
            line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            is_abstract=True,
        ))

    # Enums (TS only)
    for node in captures.get("enum_decl", []):
        name_node = node.child_by_field_name("name")
        name = name_node.text.decode("utf-8") if name_node else "?"
        symbols.append(RawSymbol(
            name=name, kind="enum",
            line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
        ))

    return symbols


def _extract_method_names(body_node: "Node") -> list[str]:
    """Extract method names from a class body node."""
    methods = []
    for child in body_node.named_children:
        if child.type == "method_definition":
            name_node = child.child_by_field_name("name")
            if name_node:
                methods.append(name_node.text.decode("utf-8"))
    return methods


def _has_keyword(node: "Node", keyword: str) -> bool:
    """Check if a node has a keyword child (e.g. 'abstract')."""
    for child in node.children:
        if not child.is_named and child.type == keyword:
            return True
    return False


# ── Complexity metrics ────────────────────────────────────────

# Node types that contribute to cyclomatic complexity
_CC_TYPES = frozenset({
    "if_statement", "for_statement", "for_in_statement",
    "while_statement", "do_statement", "switch_case",
    "catch_clause", "ternary_expression",
})

# Logical operators that add to CC
_CC_OPERATORS = frozenset({"&&", "||", "??"})

# Node types that contribute to cognitive complexity nesting
_COG_NESTING_TYPES = frozenset({
    "if_statement", "for_statement", "for_in_statement",
    "while_statement", "do_statement", "switch_statement",
    "catch_clause", "ternary_expression",
})

_COG_INCREMENT_TYPES = frozenset({
    "if_statement", "for_statement", "for_in_statement",
    "while_statement", "do_statement", "switch_statement",
    "catch_clause", "ternary_expression",
})


def _count_cc(node: "Node") -> int:
    """Count cyclomatic complexity for a subtree."""
    count = 1  # base path
    _cc_walk(node, count_ref := [0])
    return 1 + count_ref[0]


def _cc_walk(node: "Node", count_ref: list[int]) -> None:
    """Recursive CC walker."""
    if node.type in _CC_TYPES:
        count_ref[0] += 1
    if node.type == "binary_expression":
        for child in node.children:
            if not child.is_named and child.type in _CC_OPERATORS:
                count_ref[0] += 1
    for child in node.children:
        _cc_walk(child, count_ref)


def compute_cyclomatic(source: bytes, lang_name: str) -> int:
    """Compute module-level cyclomatic complexity."""
    lang = get_language(lang_name)
    parser = Parser(lang)
    tree = parser.parse(source)
    count_ref = [0]
    _cc_walk(tree.root_node, count_ref)
    return 1 + count_ref[0]


def compute_cognitive(source: bytes, lang_name: str) -> int:
    """Compute cognitive complexity using AST nesting depth."""
    lang = get_language(lang_name)
    parser = Parser(lang)
    tree = parser.parse(source)
    return _cog_walk(tree.root_node, 0)


def _cog_walk(node: "Node", nesting: int) -> int:
    """Recursive cognitive complexity walker."""
    total = 0
    if node.type in _COG_INCREMENT_TYPES:
        total += 1 + nesting
    # 'else' clause increments without nesting bonus
    if node.type == "else_clause":
        total += 1
    # Logical operators: increment without nesting
    if node.type == "binary_expression":
        for child in node.children:
            if not child.is_named and child.type in ("&&", "||"):
                total += 1

    child_nesting = nesting + 1 if node.type in _COG_NESTING_TYPES else nesting
    for child in node.children:
        total += _cog_walk(child, child_nesting)
    return total


# ── LOC counting ──────────────────────────────────────────────


def count_loc(source: bytes, lang_name: str) -> int:
    """Count non-blank, non-comment lines using AST.

    Comments are identified as 'comment' nodes in tree-sitter.
    """
    lang = get_language(lang_name)
    parser = Parser(lang)
    tree = parser.parse(source)

    # Collect all comment line ranges
    comment_lines: set[int] = set()
    _collect_comment_lines(tree.root_node, comment_lines)

    lines = source.decode("utf-8", errors="replace").splitlines()
    count = 0
    for i, line in enumerate(lines, 1):
        if line.strip() and i not in comment_lines:
            count += 1
    return count


def _collect_comment_lines(node: "Node", comment_lines: set[int]) -> None:
    """Walk tree and collect line numbers that are pure comments."""
    if node.type == "comment":
        for line_no in range(node.start_point[0] + 1, node.end_point[0] + 2):
            comment_lines.add(line_no)
    for child in node.children:
        _collect_comment_lines(child, comment_lines)
