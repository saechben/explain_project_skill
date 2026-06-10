"""Tests for the webapps extractor: detect ASGI/WSGI app objects as web entrypoints."""
from contract import FileRecord, FileIndex
from extractors.webapps import collect


def _index_with_files(tmp_path, files):
    """files: {relpath: content}. Writes them and returns a FileIndex over them."""
    records = []
    for i, (path, content) in enumerate(files.items()):
        fp = tmp_path / path
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content, encoding="utf-8")
        records.append(
            FileRecord(id=f"f{i:04d}", path=path, lang="python", loc=1, sizeBytes=len(content))
        )
    return FileIndex(records)


def test_detects_fastapi_app(tmp_path):
    idx = _index_with_files(
        tmp_path,
        {"app/main.py": "from fastapi import FastAPI\napp = FastAPI(title='x')\n"},
    )
    eps = collect(tmp_path, idx)
    fid = idx.id_for_path("app/main.py")
    assert any(e["fileId"] == fid and e["kind"] == "web" for e in eps), eps


def test_detects_flask_app(tmp_path):
    idx = _index_with_files(
        tmp_path,
        {"wsgi.py": "from flask import Flask\napplication = Flask(__name__)\n"},
    )
    eps = collect(tmp_path, idx)
    fid = idx.id_for_path("wsgi.py")
    assert any(e["fileId"] == fid and e["kind"] == "web" for e in eps), eps


def test_evidence_recorded(tmp_path):
    idx = _index_with_files(tmp_path, {"app/main.py": "app = FastAPI()\n"})
    eps = collect(tmp_path, idx)
    assert eps and "FastAPI" in eps[0]["evidence"]


def test_detects_factory_pattern_app(tmp_path):
    # Factory pattern: FastAPI() built inside a function, bound module-level via the factory.
    idx = _index_with_files(
        tmp_path,
        {
            "app/main.py": (
                "from fastapi import FastAPI\n\n"
                "def get_application() -> FastAPI:\n"
                "    application = FastAPI()\n"
                "    return application\n\n"
                "app = get_application()\n"
            )
        },
    )
    eps = collect(tmp_path, idx)
    fid = idx.id_for_path("app/main.py")
    assert any(e["fileId"] == fid and e["kind"] == "web" for e in eps), eps


def test_ignores_app_constructed_inside_function_without_module_binding(tmp_path):
    # FastAPI() built in a function but never bound to a module-level app object -> not an entrypoint.
    idx = _index_with_files(
        tmp_path,
        {"app/factory.py": "def create():\n    x = FastAPI()\n    return x\n"},
    )
    assert collect(tmp_path, idx) == []


def test_ignores_files_without_app(tmp_path):
    idx = _index_with_files(tmp_path, {"app/models.py": "class User:\n    pass\n"})
    assert collect(tmp_path, idx) == []


def test_deterministic_and_sorted(tmp_path):
    idx = _index_with_files(
        tmp_path,
        {"b/main.py": "app = FastAPI()\n", "a/main.py": "app = Flask(__name__)\n"},
    )
    a = collect(tmp_path, idx)
    b = collect(tmp_path, idx)
    assert a == b
    assert [e["fileId"] for e in a] == sorted(e["fileId"] for e in a)
