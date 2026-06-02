"""Tests for the manifests extractor: dependency parsing + declared entrypoints."""
from contract import FileRecord, FileIndex
from extractors.manifests import collect


def _index(paths):
    return FileIndex(
        [
            FileRecord(id=f"f{i:04d}", path=p, lang="x", loc=1, sizeBytes=1)
            for i, p in enumerate(paths)
        ]
    )


def test_py_app_deps_and_entrypoint(py_app):
    idx = _index(["pkg/__main__.py", "pkg/__init__.py", "pkg/core.py"])
    deps, entrypoints = collect(py_app, idx)

    names = {d["name"] for d in deps}
    assert "requests" in names
    req = next(d for d in deps if d["name"] == "requests")
    assert req["ecosystem"] == "pypi"
    assert req["manifest"] == "pyproject.toml"
    assert req["usedByFileIds"] == []

    main_id = idx.id_for_path("pkg/__main__.py")
    cli = [e for e in entrypoints if e["fileId"] == main_id and e["kind"] == "cli"]
    assert cli, f"expected cli entrypoint for {main_id}, got {entrypoints}"


def test_js_app_deps_and_entrypoint(js_app):
    idx = _index(["src/index.js", "src/app.js", "src/lib/util.js"])
    deps, entrypoints = collect(js_app, idx)

    names = {d["name"] for d in deps}
    assert "react" in names
    react = next(d for d in deps if d["name"] == "react")
    assert react["ecosystem"] == "npm"
    assert react["manifest"] == "package.json"

    idx_id = idx.id_for_path("src/index.js")
    assert any(e["fileId"] == idx_id for e in entrypoints), entrypoints


def test_version_parsed_for_some_dep(js_app):
    idx = _index(["src/index.js"])
    deps, _ = collect(js_app, idx)
    react = next(d for d in deps if d["name"] == "react")
    assert react["version"] == "18.2.0"


def test_requirements_txt(tmp_path):
    (tmp_path / "requirements.txt").write_text(
        "# a comment\nflask>=2.0\n\nrequests==2.28.1\n"
    )
    idx = _index([])
    deps, _ = collect(tmp_path, idx)
    names = {d["name"] for d in deps}
    assert {"flask", "requests"} <= names
    for d in deps:
        assert d["ecosystem"] == "pypi"
        assert d["manifest"] == "requirements.txt"


def test_skip_entrypoint_not_in_index(py_app):
    # __main__.py not in index -> no entrypoint for it
    idx = _index(["pkg/core.py"])
    _, entrypoints = collect(py_app, idx)
    assert entrypoints == []


def test_determinism(py_app):
    idx = _index(["pkg/__main__.py", "pkg/core.py"])
    a = collect(py_app, idx)
    b = collect(py_app, idx)
    assert a == b


def test_deps_sorted_by_name(js_app):
    idx = _index(["src/index.js"])
    deps, _ = collect(js_app, idx)
    names = [d["name"] for d in deps]
    assert names == sorted(names)
