"""Unit tests for the heuristic (regex/line-scan) import extractor."""
from __future__ import annotations

from pathlib import Path

from contract import FileIndex, FileRecord, detect_lang, file_id
from extractors.imports_heuristic import collect

# Languages we expect import-graph extractors to scan.
_CODE_EXT = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}


def build_index(root: Path) -> FileIndex:
    """Local helper: scan a fixture dir into a FileIndex of code FileRecords."""
    files = sorted(
        p for p in root.rglob("*")
        if p.is_file() and p.suffix in _CODE_EXT
    )
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


def edges_for(edges, from_path):
    return [e for e in edges if e["evidence"]["file"] == from_path]


def test_python_resolved_internal_edges(py_app):
    idx = build_index(py_app)
    edges = collect(py_app, idx)
    by_id = {r.id: r.path for r in idx.records}

    core_edges = edges_for(edges, "pkg/core.py")
    targets = {by_id[e["to"]] for e in core_edges if e["to"] is not None}
    assert "pkg/util.py" in targets
    assert "pkg/models.py" in targets
    for e in core_edges:
        if e["to"] is not None:
            assert e["resolution"] == "resolved"
    assert all(e["extractor"] == "heuristic" for e in edges)


def test_python_external_unresolved(py_app):
    idx = build_index(py_app)
    edges = collect(py_app, idx)
    util_edges = edges_for(edges, "pkg/util.py")
    assert util_edges, "expected an import edge from util.py"
    req = [e for e in util_edges if "requests" in e["evidence"]["raw"]]
    assert req, "expected the requests import edge"
    assert all(e["to"] is None for e in req)
    assert all(e["resolution"] == "unresolved" for e in req)


def test_python_circular_edge_captured(py_app):
    idx = build_index(py_app)
    edges = collect(py_app, idx)
    by_id = {r.id: r.path for r in idx.records}
    models_edges = edges_for(edges, "pkg/models.py")
    targets = {by_id[e["to"]] for e in models_edges if e["to"] is not None}
    assert "pkg/core.py" in targets


def test_python_relative_import_resolves(py_app):
    idx = build_index(py_app)
    edges = collect(py_app, idx)
    by_id = {r.id: r.path for r in idx.records}
    helper_edges = edges_for(edges, "pkg/sub/helper.py")
    targets = {by_id[e["to"]] for e in helper_edges if e["to"] is not None}
    assert "pkg/util.py" in targets


def test_evidence_shape(py_app):
    idx = build_index(py_app)
    edges = collect(py_app, idx)
    core_edges = edges_for(edges, "pkg/core.py")
    e = core_edges[0]
    assert e["type"] == "import"
    assert isinstance(e["evidence"]["line"], int) and e["evidence"]["line"] >= 1
    assert "import" in e["evidence"]["raw"]
    assert e["evidence"]["file"] == "pkg/core.py"
    # from is the importing file id
    assert idx.record_for_id(e["from"]).path == "pkg/core.py"


def test_js_relative_resolved_and_external_unresolved(js_app):
    idx = build_index(js_app)
    edges = collect(js_app, idx)
    by_id = {r.id: r.path for r in idx.records}

    app_edges = edges_for(edges, "src/app.js")
    resolved = {by_id[e["to"]] for e in app_edges if e["to"] is not None}
    assert "src/lib/util.js" in resolved

    react = [e for e in app_edges if "react" in e["evidence"]["raw"]]
    assert react and all(e["to"] is None for e in react)
    assert all(e["resolution"] == "unresolved" for e in react)


def test_js_missing_relative_unresolved(js_app):
    idx = build_index(js_app)
    edges = collect(js_app, idx)
    util_edges = edges_for(edges, "src/lib/util.js")
    missing = [e for e in util_edges if "does-not-exist" in e["evidence"]["raw"]]
    assert missing, "expected the ./does-not-exist import edge"
    assert all(e["to"] is None for e in missing)
    assert all(e["resolution"] == "unresolved" for e in missing)


def test_determinism(py_app):
    idx = build_index(py_app)
    a = collect(py_app, idx)
    b = collect(py_app, idx)
    assert a == b
