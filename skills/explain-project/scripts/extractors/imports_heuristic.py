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
def build_package_roots(index: FileIndex) -> dict[str, list[str]]:
    """Map each top-level Python package name to the source-dir prefix(es) it lives under.

    A *top-level package* is a directory containing ``__init__.py`` whose parent
    directory does NOT itself contain ``__init__.py``. Its source-dir prefix is that
    parent (the repo root is ``""``). This lets the resolver follow absolute
    cross-boundary imports under a ``src/`` layout (e.g. ``app`` -> ``src``), where
    the import path (``app.config``) differs from the on-disk path
    (``src/app/config.py``).

    Returns ``{pkg_name: [sorted source-dir prefixes]}``. Module granularity only;
    no symbol-level resolution and no PEP-420 namespace packages (which have no
    ``__init__.py`` to detect).
    """
    init_dirs = {
        str(Path(p).parent.as_posix())
        for p in index.paths()
        if Path(p).name == "__init__.py"
    }

    def has_init(dir_posix: str) -> bool:
        # "" denotes the repo root, which never holds a package __init__.py.
        return dir_posix in init_dirs

    roots: dict[str, set[str]] = {}
    for d in init_dirs:
        parent = str(Path(d).parent.as_posix())
        parent = "" if parent == "." else parent
        if has_init(parent):
            continue  # nested package; not a top-level one
        name = Path(d).name
        roots.setdefault(name, set()).add(parent)
    return {name: sorted(prefixes) for name, prefixes in roots.items()}


def resolve_python(module: str, level: int, importing_path: str,
                   index: FileIndex,
                   package_roots: Optional[dict[str, list[str]]] = None) -> Optional[str]:
    """Resolve a Python import to an internal file id, or None.

    module: dotted module text (e.g. "pkg.util"); may be "" for `from . import x`.
    level:  number of leading dots for relative imports (0 = absolute).
    importing_path: repo-relative posix path of the file doing the import.
    package_roots: optional ``{pkg: [source-dir prefixes]}`` from
        :func:`build_package_roots`; enables src-layout resolution for absolute
        imports. When omitted, behavior is identical to the pre-existing resolver.
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

    fid = _lookup_module(base_parts, index)
    if fid:
        return fid

    # src-layout retry: absolute import whose first segment is a known package
    # rooted under a source dir (e.g. app -> src/app). Module granularity.
    if level == 0 and package_roots and parts:
        for prefix in package_roots.get(parts[0], []):
            if not prefix:
                continue  # root-level prefix already tried above
            fid = _lookup_module(prefix.split("/") + base_parts, index)
            if fid:
                return fid
    return None


def _lookup_module(base_parts: list[str], index: FileIndex) -> Optional[str]:
    """Try the ``<parts>.py`` then ``<parts>/__init__.py`` candidates for a module path."""
    joined = "/".join(base_parts)
    for cand in (joined + ".py", joined + "/__init__.py"):
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
                 extractor: str,
                 package_roots: Optional[dict[str, list[str]]] = None) -> list[dict]:
    edges: list[dict] = []
    for i, line in enumerate(text.splitlines(), start=1):
        m = _PY_FROM.match(line)
        if m:
            dots = m.group("dots")
            mod = m.group("mod")
            target = resolve_python(mod, len(dots), importing_path, index, package_roots)
            edges.append(make_edge(importing_path, i, line.rstrip("\n"),
                                   target, from_id, extractor))
            continue
        m = _PY_IMPORT.match(line)
        if m:
            for mod in m.group("mods").split(","):
                mod = mod.strip()
                if not mod:
                    continue
                target = resolve_python(mod, 0, importing_path, index, package_roots)
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
    package_roots = build_package_roots(file_index)
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
            edges.extend(_scan_python(text, rec.path, rec.id, file_index, "heuristic",
                                      package_roots))
        else:
            edges.extend(_scan_js(text, rec.path, rec.id, file_index, "heuristic"))
    edges.sort(key=lambda e: (e["evidence"]["file"], e["evidence"]["line"]))
    return edges
