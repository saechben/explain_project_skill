"""Core logic. Imports util (resolved) and models (circular with models.py)."""
from pkg.util import fetch
from pkg.models import Item


def run():
    data = fetch("https://example.com")
    return Item(data)
