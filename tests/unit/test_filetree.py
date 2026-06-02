"""Unit tests for the filetree extractor (collect)."""
from __future__ import annotations

import pathlib

from extractors.filetree import collect


def test_files_found_sorted_with_sequential_ids(py_app):
    files, _ = collect(py_app)
    assert files, "expected files in the py_app fixture"
    paths = [f.path for f in files]
    assert paths == sorted(paths)
    assert [f.id for f in files] == [f"f{i:04d}" for i in range(1, len(files) + 1)]
    assert files[0].id == "f0001"
    # paths are repo-relative POSIX, never absolute
    assert all(not p.startswith("/") for p in paths)
    assert "pkg/sub/helper.py" in paths


def test_detect_lang_applied(py_app):
    files, _ = collect(py_app)
    by_path = {f.path: f for f in files}
    assert by_path["pkg/sub/helper.py"].lang == "python"
    assert by_path["pyproject.toml"].lang == "toml"


def test_loc_counts_newlines(py_app):
    files, _ = collect(py_app)
    by_path = {f.path: f for f in files}
    # helper.py has 6 newlines in the fixture.
    assert by_path["pkg/sub/helper.py"].loc == 6
    assert by_path["pkg/sub/helper.py"].sizeBytes > 0


def test_nested_dir_is_its_own_module(py_app):
    files, modules = collect(py_app)
    by_path_file = {f.path: f for f in files}
    by_path_mod = {m.path: m for m in modules}

    assert "pkg/sub" in by_path_mod
    sub = by_path_mod["pkg/sub"]
    helper_id = by_path_file["pkg/sub/helper.py"].id
    assert sub.fileIds == [helper_id]

    # module IDs are sequential m001.. in path order
    sorted_mods = sorted(modules, key=lambda m: m.path)
    assert [m.id for m in sorted_mods] == [f"m{i:03d}" for i in range(1, len(modules) + 1)]
    assert sorted_mods[0].id == "m001"


def test_module_filelists_are_direct_only(py_app):
    files, modules = collect(py_app)
    by_path_mod = {m.path: m for m in modules}
    by_id = {f.id: f.path for f in files}

    pkg = by_path_mod["pkg"]
    pkg_paths = {by_id[fid] for fid in pkg.fileIds}
    # direct children of pkg, not the nested sub/helper.py
    assert "pkg/__init__.py" in pkg_paths
    assert "pkg/sub/helper.py" not in pkg_paths


def test_js_fixture(js_app):
    files, modules = collect(js_app)
    by_path = {f.path: f for f in files}
    assert by_path["src/index.js"].lang == "javascript"
    mod_paths = {m.path for m in modules}
    assert "src" in mod_paths
    assert "src/lib" in mod_paths


def test_determinism(py_app):
    files_a, mods_a = collect(py_app)
    files_b, mods_b = collect(py_app)
    assert [f.to_dict() for f in files_a] == [f.to_dict() for f in files_b]
    assert [m.to_dict() for m in mods_a] == [m.to_dict() for m in mods_b]


def test_always_skip_dirs(tmp_path):
    (tmp_path / "keep.py").write_text("x = 1\n")
    for d in (".git", ".venv", "node_modules", "__pycache__", "dist", "build"):
        sub = tmp_path / d
        sub.mkdir()
        (sub / "junk.py").write_text("nope = 1\n")

    files, modules = collect(tmp_path)
    paths = [f.path for f in files]
    assert paths == ["keep.py"]
    assert all("/" not in p or not p.startswith((".git", ".venv")) for p in paths)
    mod_paths = {m.path for m in modules}
    assert ".git" not in mod_paths
    assert ".venv" not in mod_paths


def test_root_module_path_is_dot(tmp_path):
    (tmp_path / "top.py").write_text("a = 1\n")
    _, modules = collect(tmp_path)
    by_path = {m.path: m for m in modules}
    assert "." in by_path
    assert len(by_path["."].fileIds) == 1


def test_gitignore_respected(tmp_path):
    (tmp_path / ".gitignore").write_text("ignored/\nsecret.py\n")
    (tmp_path / "keep.py").write_text("k = 1\n")
    (tmp_path / "secret.py").write_text("s = 1\n")
    ign = tmp_path / "ignored"
    ign.mkdir()
    (ign / "x.py").write_text("x = 1\n")

    files, _ = collect(tmp_path)
    paths = {f.path for f in files}
    assert "keep.py" in paths
    assert ".gitignore" in paths
    assert "secret.py" not in paths
    assert "ignored/x.py" not in paths


def test_extra_skip(tmp_path):
    (tmp_path / "keep.py").write_text("k = 1\n")
    skipme = tmp_path / "skipme"
    skipme.mkdir()
    (skipme / "a.py").write_text("a = 1\n")

    files, _ = collect(tmp_path, extra_skip=["skipme"])
    paths = {f.path for f in files}
    assert "keep.py" in paths
    assert "skipme/a.py" not in paths


def test_empty_file_loc_zero(tmp_path):
    (tmp_path / "empty.py").write_text("")
    files, _ = collect(tmp_path)
    by_path = {f.path: f for f in files}
    assert by_path["empty.py"].loc == 0
    assert by_path["empty.py"].sizeBytes == 0


def test_returns_record_types(py_app):
    from contract import FileRecord, ModuleRecord

    files, modules = collect(py_app)
    assert all(isinstance(f, FileRecord) for f in files)
    assert all(isinstance(m, ModuleRecord) for m in modules)
    assert isinstance(py_app, pathlib.Path)
