"""Entrypoint outside the app package: absolute cross-boundary imports.

These are the imports that stay unresolved under the old resolver because `app`
is rooted under src/ (the file is at src/app/config.py, not app/config.py).
"""
import json  # stdlib -> stays unresolved

from app.config import settings  # cross-boundary -> src/app/config.py
from app.core import run  # cross-boundary -> src/app/core.py


def main() -> None:
    print(json.dumps(settings), run())
