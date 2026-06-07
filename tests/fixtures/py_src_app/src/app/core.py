"""Intra-package module: uses a relative import (regression guard)."""
from .config import settings


def run() -> str:
    return settings["name"]
