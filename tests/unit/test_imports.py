"""Unit tests for the imports combiner (primary entry point)."""
from __future__ import annotations

from pathlib import Path

from contract import FileIndex, FileRecord, detect_lang, file_id
from extractors.imports import collect

_CODE_EXT = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}


def build_index(root: Path) -> FileIndex:
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


def test_edge_ids_unique_sequential(py_app):
    idx = build_index(py_app)
    edges = collect(py_app, idx)
    ids = [e["id"] for e in edges]
    assert ids == [f"e{i:04d}" for i in range(1, len(edges) + 1)]
    assert len(set(ids)) == len(ids)
    assert edges[0]["id"] == "e0001"


def test_deterministic_order(py_app):
    idx = build_index(py_app)
    edges = collect(py_app, idx)
    keys = [(e["evidence"]["file"], e["evidence"]["line"]) for e in edges]
    assert keys == sorted(keys)
    assert collect(py_app, idx) == collect(py_app, idx)


def test_no_duplicate_imports(py_app):
    """Same from+line+raw must not appear twice (heuristic vs treesitter merge)."""
    idx = build_index(py_app)
    edges = collect(py_app, idx)
    sigs = [(e["from"], e["evidence"]["line"], e["evidence"]["raw"]) for e in edges]
    assert len(sigs) == len(set(sigs))


def test_prefers_treesitter(py_app):
    """Files tree-sitter can parse should be attributed to treesitter."""
    idx = build_index(py_app)
    edges = collect(py_app, idx)
    py_edges = [e for e in edges if e["evidence"]["file"].endswith(".py")]
    assert py_edges
    assert all(e["extractor"] == "treesitter" for e in py_edges)


def test_python_resolution(py_app):
    idx = build_index(py_app)
    edges = collect(py_app, idx)
    by_id = {r.id: r.path for r in idx.records}

    core_targets = {by_id[e["to"]] for e in edges_for(edges, "pkg/core.py")
                    if e["to"] is not None}
    assert {"pkg/util.py", "pkg/models.py"} <= core_targets

    models_targets = {by_id[e["to"]] for e in edges_for(edges, "pkg/models.py")
                      if e["to"] is not None}
    assert "pkg/core.py" in models_targets

    helper_targets = {by_id[e["to"]] for e in edges_for(edges, "pkg/sub/helper.py")
                      if e["to"] is not None}
    assert "pkg/util.py" in helper_targets

    util_req = [e for e in edges_for(edges, "pkg/util.py")
                if "requests" in e["evidence"]["raw"]]
    assert util_req and all(e["to"] is None for e in util_req)


def test_js_resolution(js_app):
    idx = build_index(js_app)
    edges = collect(js_app, idx)
    by_id = {r.id: r.path for r in idx.records}

    app_resolved = {by_id[e["to"]] for e in edges_for(edges, "src/app.js")
                    if e["to"] is not None}
    assert "src/lib/util.js" in app_resolved

    react = [e for e in edges_for(edges, "src/app.js")
             if "react" in e["evidence"]["raw"]]
    assert react and all(e["to"] is None for e in react)

    missing = [e for e in edges_for(edges, "src/lib/util.js")
               if "does-not-exist" in e["evidence"]["raw"]]
    assert missing and all(e["to"] is None for e in missing)


def test_schema_fields(py_app):
    idx = build_index(py_app)
    edges = collect(py_app, idx)
    for e in edges:
        assert set(e.keys()) == {"id", "type", "from", "to", "evidence",
                                 "resolution", "extractor"}
        assert e["type"] == "import"
        assert e["resolution"] in ("resolved", "unresolved")
        assert e["extractor"] in ("treesitter", "heuristic")
        assert (e["to"] is None) == (e["resolution"] == "unresolved")
