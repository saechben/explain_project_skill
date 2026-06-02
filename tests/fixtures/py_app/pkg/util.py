"""Utility helpers. Imports requests (external, unresolved internally)."""
import requests


def fetch(url):
    return requests.get(url).text
