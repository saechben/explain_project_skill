"""Detect web-app entrypoints by scanning for module-level ASGI/WSGI app objects.

Many real services declare no console-script and no ``__main__`` — they are launched
out-of-band (``uvicorn app.main:app``, ``gunicorn wsgi``). We recover that entrypoint
deterministically: a module-level assignment of a known web-framework application object
(``app = FastAPI(...)``, ``application = Flask(__name__)``) is a "web" entrypoint.

Returns a list of entrypoint dicts shaped like facts.schema.json items, sorted by fileId.
"""
from __future__ import annotations

import pathlib
import re

from contract import FileIndex

# ASGI/WSGI app constructors worth treating as a web entrypoint.
_FRAMEWORKS = ("FastAPI", "Flask", "Starlette", "Sanic", "Quart", "Litestar", "Bottle")

# A framework application constructor call, anywhere in the file.
_FW_CALL = re.compile(r"\b(" + "|".join(_FRAMEWORKS) + r")\s*\(")

# Module-level (no leading indentation) `<name> = Framework(` — direct construction.
_APP_ASSIGN = re.compile(
    r"^(?P<var>\w+)\s*=\s*(?P<fw>" + "|".join(_FRAMEWORKS) + r")\s*\(",
    re.MULTILINE,
)

# Module-level binding of a conventional ASGI/WSGI callable name — covers the factory
# pattern, where the constructor runs inside a function and is bound here (`app = create()`).
_APP_BIND = re.compile(
    r"^(?P<var>app|application|api|asgi_app|wsgi_app|server)\s*=\s*\w",
    re.MULTILINE,
)


def collect(repo_root: pathlib.Path, file_index: FileIndex) -> list[dict]:
    repo_root = pathlib.Path(repo_root)
    entrypoints: list[dict] = []
    for rec in file_index.records:
        if not rec.path.endswith(".py"):
            continue
        try:
            text = (repo_root / rec.path).read_text(encoding="utf-8")
        except OSError:
            continue
        if _FW_CALL.search(text) is None:
            continue
        direct = _APP_ASSIGN.search(text)
        if direct is not None:
            evidence = f"module-level {direct.group('fw')}() app object: {direct.group('var')}"
        else:
            bind = _APP_BIND.search(text)
            if bind is None:
                continue
            framework = _FW_CALL.search(text).group(1)
            evidence = (
                f"module-level '{bind.group('var')}' bound to a {framework}() "
                "application (factory pattern)"
            )
        entrypoints.append({"fileId": rec.id, "kind": "web", "evidence": evidence})
    entrypoints.sort(key=lambda e: e["fileId"])
    return entrypoints
