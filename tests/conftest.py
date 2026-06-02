"""Shared pytest fixtures and import-path setup for the explain-project test suite."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "explain-project" / "scripts"
FIXTURES = ROOT / "tests" / "fixtures"

# Make the extractor scripts importable as top-level modules in every test.
sys.path.insert(0, str(SCRIPTS))


@pytest.fixture
def scripts_dir() -> Path:
    return SCRIPTS


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def py_app(fixtures_dir) -> Path:
    return fixtures_dir / "py_app"


@pytest.fixture
def js_app(fixtures_dir) -> Path:
    return fixtures_dir / "js_app"
