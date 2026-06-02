"""Nested module. Relative import of util."""
from ..util import fetch


def helper_fetch(url):
    return fetch(url)
