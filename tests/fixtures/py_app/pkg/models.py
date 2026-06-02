"""Data models. Imports core back (circular import with core.py)."""
from pkg.core import run  # noqa: F401  (intentional circular import for fixture)


class Item:
    def __init__(self, data):
        self.data = data
