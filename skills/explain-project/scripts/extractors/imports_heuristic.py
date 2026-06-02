"""Heuristic (regex / line-scan) import extractor.

Universal fallback that needs no parser. Scans Python and JS/TS files for
import / from / require statements and emits raw edge dicts (without final IDs;
the combiner owns deterministic ID assignment).

This module also hosts the shared import-resolution helpers used by the
tree-sitter extractor, so resolution logic lives in exactly one place.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from contract import FileIndex

# --- language sets -----------------------------------------------------------
PY_EXT = {".py", ".pyi"}
JS_EXT = {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"}
# Extensions tried (in order) when resolving a JS/TS relative import target.
_JS_RESOLVE_EXT = [".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs"]


# --- resolution helpers (shared with the tree-sitter extractor) --------------
def resolve_python(module: str, level: int, importing_path: str,
                   index: FileIndex) -> Optional[str]:
    """Resolve a Python import to an internal file id, or None.

    module: dotted module text (e.g. "pkg.util"); may be "" for `from . import x`.
    level:  number of leading dots for relative imports (0 = absolute).
    importing_path: repo-relative posix path of the file doing the import.
    """
    parts = [p for p in module.split(".") if p] if module else []

    if level == 0:
        base_parts = parts
    else:
        # Relative: anchor to the importing file's package directory.
        pkg = Path(importing_path).parent
        # Each extra dot beyond the first walks one directory up.
        up = level - 1
        anchor = pkg
        for _ in range(up):
            anchor = anchor.parent
        anchor_parts = [] if anchor == Path(".") else list(anchor.parts)
        base_parts = anchor_parts + parts

    if not base_parts:
        return None

    candidates = [
        "/".join(base_parts) + ".py",
        "/".join(base_parts) + "/__init__.py",
    ]
    for cand in candidates:
        fid = index.id_for_path(cand)
        if fid:
            return fid
    return None


def resolve_js(spec: str, importing_path: str, index: FileIndex) -> Optional[str]:
    """Resolve a JS/TS module specifier to an internal file id, or None.

    Only relative specifiers (./ or ../) are internal; bare specifiers are
    external packages and stay unresolved.
    """
    if not (spec.startswith("./") or spec.startswith("../")):
        return None

    base = (Path(importing_path).parent / spec).as_posix()
    # Normalize away ./ and ../ segments.
    base = _normalize(base)

    # Direct file with given extension already present?
    if index.id_for_path(base):
        return index.id_for_path(base)

    for ext in _JS_RESOLVE_EXT:
        fid = index.id_for_path(base + ext)
        if fid:
            return fid
    for ext in _JS_RESOLVE_EXT:
        fid = index.id_for_path(base + "/index" + ext)
        if fid:
            return fid
    return None


def _normalize(posix_path: str) -> str:
    parts: list[str] = []
    for seg in posix_path.split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":
            if parts:
                parts.pop()
            continue
        parts.append(seg)
    return "/".join(parts)


def make_edge(importing_path: str, line: int, raw: str, target_id: Optional[str],
              from_id: str, extractor: str) -> dict:
    return {
        "id": None,  # combiner assigns final id
        "type": "import",
        "from": from_id,
        "to": target_id,
        "evidence": {"file": importing_path, "line": line, "raw": raw},
        "resolution": "resolved" if target_id else "unresolved",
        "extractor": extractor,
    }


# --- python line scanning ----------------------------------------------------
_PY_FROM = re.compile(r"^\s*from\s+(?P<dots>\.*)(?P<mod>[\w.]*)\s+import\s+")
_PY_IMPORT = re.compile(r"^\s*import\s+(?P<mods>[\w.]+(?:\s*,\s*[\w.]+)*)")


def _scan_python(text: str, importing_path: str, from_id: str, index: FileIndex,
                 extractor: str) -> list[dict]:
    edges: list[dict] = []
    for i, line in enumerate(text.splitlines(), start=1):
        m = _PY_FROM.match(line)
        if m:
            dots = m.group("dots")
            mod = m.group("mod")
            target = resolve_python(mod, len(dots), importing_path, index)
            edges.append(make_edge(importing_path, i, line.rstrip("\n"),
                                   target, from_id, extractor))
            continue
        m = _PY_IMPORT.match(line)
        if m:
            for mod in m.group("mods").split(","):
                mod = mod.strip()
                if not mod:
                    continue
                target = resolve_python(mod, 0, importing_path, index)
                edges.append(make_edge(importing_path, i, line.rstrip("\n"),
                                       target, from_id, extractor))
    return edges


# --- js/ts line scanning -----------------------------------------------------
_JS_IMPORT_FROM = re.compile(r"""\bfrom\s+['"](?P<spec>[^'"]+)['"]""")
_JS_BARE_IMPORT = re.compile(r"""^\s*import\s+['"](?P<spec>[^'"]+)['"]""")
_JS_REQUIRE = re.compile(r"""\brequire\(\s*['"](?P<spec>[^'"]+)['"]\s*\)""")


def _scan_js(text: str, importing_path: str, from_id: str, index: FileIndex,
             extractor: str) -> list[dict]:
    edges: list[dict] = []
    for i, line in enumerate(text.splitlines(), start=1):
        raw = line.rstrip("\n")
        specs: list[str] = []
        stripped = line.lstrip()
        if stripped.startswith("import") or stripped.startswith("export"):
            m = _JS_IMPORT_FROM.search(line)
            if m:
                specs.append(m.group("spec"))
            else:
                m = _JS_BARE_IMPORT.match(line)
                if m:
                    specs.append(m.group("spec"))
        for m in _JS_REQUIRE.finditer(line):
            specs.append(m.group("spec"))

        for spec in specs:
            target = resolve_js(spec, importing_path, index)
            edges.append(make_edge(importing_path, i, raw, target, from_id, extractor))
    return edges


def collect(repo_root, file_index: FileIndex) -> list[dict]:
    """Scan every python/js/ts file in the index for imports via line heuristics."""
    root = Path(repo_root)
    edges: list[dict] = []
    for rec in file_index.records:
        ext = Path(rec.path).suffix.lower()
        if ext not in PY_EXT and ext not in JS_EXT:
            continue
        fpath = root / rec.path
        try:
            text = fpath.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if ext in PY_EXT:
            edges.extend(_scan_python(text, rec.path, rec.id, file_index, "heuristic"))
        else:
            edges.extend(_scan_js(text, rec.path, rec.id, file_index, "heuristic"))
    edges.sort(key=lambda e: (e["evidence"]["file"], e["evidence"]["line"]))
    return edges
