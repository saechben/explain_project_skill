"""Unit tests for package-root detection and src-layout import resolution.

Covers the resolver's ability to map an absolute first-party import whose package
lives under a source dir (e.g. src/) to the real file, at module granularity.
"""
from __future__ import annotations

from pathlib import Path

from contract import FileIndex, FileRecord, detect_lang, file_id
from extractors.imports_heuristic import build_package_roots, resolve_python

_CODE_EXT = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}


def build_index(root: Path) -> FileIndex:
    files = sorted(p for p in root.rglob("*") if p.is_file() and p.suffix in _CODE_EXT)
    records = []
    for i, p in enumerate(files, start=1):
        rel = p.relative_to(root).as_posix()
        text = p.read_text(encoding="utf-8")
        records.append(
            FileRecord(
                id=file_id(i),
                path=rel,
                lang=detect_lang(rel),
                loc=text.count("\n"),
                sizeBytes=len(text.encode("utf-8")),
            )
        )
    return FileIndex(records)


# --- build_package_roots -----------------------------------------------------
def test_package_roots_src_layout(fixtures_dir):
    idx = build_index(fixtures_dir / "py_src_app")
    roots = build_package_roots(idx)
    # `app` lives under src/, `cli` at the repo root.
    assert roots.get("app") == ["src"]
    assert roots.get("cli") == [""]


def test_package_roots_flat_layout(py_app):
    idx = build_index(py_app)
    roots = build_package_roots(idx)
    # Flat layout: `pkg` is rooted at the repo root.
    assert roots.get("pkg") == [""]


def test_package_roots_values_sorted_and_deterministic(fixtures_dir):
    idx = build_index(fixtures_dir / "py_src_app")
    roots = build_package_roots(idx)
    for prefixes in roots.values():
        assert prefixes == sorted(prefixes)


# --- resolve_python with package roots ---------------------------------------
def test_absolute_cross_boundary_resolves_to_src(fixtures_dir):
    idx = build_index(fixtures_dir / "py_src_app")
    roots = build_package_roots(idx)
    fid = resolve_python("app.config", 0, "cli/main.py", idx, roots)
    assert fid is not None
    assert {r.id: r.path for r in idx.records}[fid] == "src/app/config.py"


def test_absolute_package_resolves_to_init(fixtures_dir):
    idx = build_index(fixtures_dir / "py_src_app")
    roots = build_package_roots(idx)
    fid = resolve_python("app", 0, "cli/main.py", idx, roots)
    assert {r.id: r.path for r in idx.records}[fid] == "src/app/__init__.py"


def test_third_party_stays_unresolved(fixtures_dir):
    idx = build_index(fixtures_dir / "py_src_app")
    roots = build_package_roots(idx)
    assert resolve_python("requests", 0, "cli/main.py", idx, roots) is None


def test_relative_import_unchanged_regression(fixtures_dir):
    idx = build_index(fixtures_dir / "py_src_app")
    roots = build_package_roots(idx)
    # from .config import settings inside src/app/core.py (level 1 = same package)
    fid = resolve_python("config", 1, "src/app/core.py", idx, roots)
    assert {r.id: r.path for r in idx.records}[fid] == "src/app/config.py"


def test_flat_layout_absolute_still_resolves_no_double_prefix(py_app):
    idx = build_index(py_app)
    roots = build_package_roots(idx)
    # from pkg.util import fetch — pkg rooted at "", must not become "/pkg/util.py"
    fid = resolve_python("pkg.util", 0, "pkg/core.py", idx, roots)
    assert {r.id: r.path for r in idx.records}[fid] == "pkg/util.py"


def test_resolve_without_roots_is_backward_compatible(py_app):
    idx = build_index(py_app)
    # No package_roots passed -> identical to the old behavior.
    fid = resolve_python("pkg.util", 0, "pkg/core.py", idx)
    assert {r.id: r.path for r in idx.records}[fid] == "pkg/util.py"
