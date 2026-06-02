"""Tree-sitter based import extractor (precise).

Uses tree-sitter grammars (python, javascript, typescript) to find import nodes
exactly. Files whose language has no available grammar are skipped; the combiner
covers them with the heuristic extractor.

Resolution logic is shared with the heuristic extractor (imported from there) so
the two never diverge on what counts as an internal target.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from contract import FileIndex

from extractors.imports_heuristic import (
    JS_EXT,
    PY_EXT,
    make_edge,
    resolve_js,
    resolve_python,
)

# Map file extension -> tree-sitter grammar name.
_EXT_GRAMMAR = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
}


def _node_text(node, src: bytes) -> str:
    return src[node.start_byte():node.end_byte()].decode("utf-8", "replace")


def _line_of(node) -> int:
    pos = node.start_position()
    row = pos.row if hasattr(pos, "row") else pos[0]
    return row + 1


def _children(node):
    return [node.child(i) for i in range(node.child_count())]


def _raw_line(src_lines: list[str], line_no: int) -> str:
    idx = line_no - 1
    return src_lines[idx] if 0 <= idx < len(src_lines) else ""


# --- python ------------------------------------------------------------------
def _walk_python_imports(root, src: bytes, src_lines, importing_path, from_id,
                         index) -> list[dict]:
    edges: list[dict] = []

    def visit(node):
        kind = node.kind()
        if kind == "import_statement":
            line = _line_of(node)
            raw = _raw_line(src_lines, line)
            for child in _children(node):
                ck = child.kind()
                if ck == "dotted_name":
                    mod = _node_text(child, src)
                    target = resolve_python(mod, 0, importing_path, index)
                    edges.append(make_edge(importing_path, line, raw, target,
                                           from_id, "treesitter"))
                elif ck == "aliased_import":
                    dn = next((c for c in _children(child)
                               if c.kind() == "dotted_name"), None)
                    if dn is not None:
                        mod = _node_text(dn, src)
                        target = resolve_python(mod, 0, importing_path, index)
                        edges.append(make_edge(importing_path, line, raw, target,
                                               from_id, "treesitter"))
        elif kind == "import_from_statement":
            line = _line_of(node)
            raw = _raw_line(src_lines, line)
            level = 0
            mod = ""
            for child in _children(node):
                ck = child.kind()
                if ck == "relative_import":
                    for sub in _children(child):
                        sk = sub.kind()
                        if sk == "import_prefix":
                            level = _node_text(sub, src).count(".")
                        elif sk == "dotted_name":
                            mod = _node_text(sub, src)
                    break
                if ck == "dotted_name":
                    # absolute `from pkg.util import x`; first dotted_name is module
                    mod = _node_text(child, src)
                    break
            target = resolve_python(mod, level, importing_path, index)
            edges.append(make_edge(importing_path, line, raw, target,
                                   from_id, "treesitter"))
            return  # don't descend into the import body
        for c in _children(node):
            visit(c)

    visit(root)
    return edges


# --- js / ts -----------------------------------------------------------------
def _js_string_spec(node, src: bytes) -> Optional[str]:
    """Extract the specifier from a `string` node (its string_fragment)."""
    for c in _children(node):
        if c.kind() == "string_fragment":
            return _node_text(c, src)
    # Fallback: strip quotes off the raw string.
    raw = _node_text(node, src)
    return raw.strip("'\"`") or None


def _walk_js_imports(root, src: bytes, src_lines, importing_path, from_id,
                     index) -> list[dict]:
    edges: list[dict] = []

    def add(spec, line):
        raw = _raw_line(src_lines, line)
        target = resolve_js(spec, importing_path, index)
        edges.append(make_edge(importing_path, line, raw, target, from_id,
                               "treesitter"))

    def visit(node):
        kind = node.kind()
        if kind in ("import_statement", "export_statement"):
            # specifier is a direct `string` child (import ... from 'x')
            str_child = next((c for c in _children(node) if c.kind() == "string"),
                             None)
            if str_child is not None:
                spec = _js_string_spec(str_child, src)
                if spec is not None:
                    add(spec, _line_of(str_child))
        elif kind == "call_expression":
            fn = node.child(0) if node.child_count() > 0 else None
            if fn is not None and fn.kind() == "identifier" and \
                    _node_text(fn, src) == "require":
                args = next((c for c in _children(node) if c.kind() == "arguments"),
                            None)
                if args is not None:
                    str_child = next((c for c in _children(args)
                                      if c.kind() == "string"), None)
                    if str_child is not None:
                        spec = _js_string_spec(str_child, src)
                        if spec is not None:
                            add(spec, _line_of(node))
        for c in _children(node):
            visit(c)

    visit(root)
    return edges


def _grammar_for(ext: str) -> Optional[str]:
    return _EXT_GRAMMAR.get(ext)


def collect(repo_root, file_index: FileIndex) -> list[dict]:
    """Extract import edges via tree-sitter; skip files with no grammar."""
    from tree_sitter_language_pack import get_parser

    root = Path(repo_root)
    edges: list[dict] = []
    parsers: dict[str, object] = {}

    for rec in file_index.records:
        ext = Path(rec.path).suffix.lower()
        grammar = _grammar_for(ext)
        if grammar is None:
            continue
        fpath = root / rec.path
        try:
            text = fpath.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        if grammar not in parsers:
            try:
                parsers[grammar] = get_parser(grammar)
            except Exception:
                parsers[grammar] = None
        parser = parsers[grammar]
        if parser is None:
            continue

        src = text.encode("utf-8")
        src_lines = text.splitlines()
        tree = parser.parse(text)
        rootnode = tree.root_node()

        if ext in PY_EXT:
            edges.extend(_walk_python_imports(rootnode, src, src_lines, rec.path,
                                              rec.id, file_index))
        elif ext in JS_EXT:
            edges.extend(_walk_js_imports(rootnode, src, src_lines, rec.path,
                                          rec.id, file_index))

    edges.sort(key=lambda e: (e["evidence"]["file"], e["evidence"]["line"]))
    return edges
