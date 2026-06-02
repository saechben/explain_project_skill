"""Tests for the shared extractor contract: ID helpers, language detection, FileIndex."""
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "skills" / "explain-project" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from contract import file_id, module_id, edge_id, detect_lang, FileIndex, FileRecord


class TestIdHelpers:
    def test_file_id_is_zero_padded_and_prefixed(self):
        assert file_id(1) == "f0001"
        assert file_id(42) == "f0042"

    def test_module_id_is_zero_padded_and_prefixed(self):
        assert module_id(1) == "m001"

    def test_edge_id_is_zero_padded_and_prefixed(self):
        assert edge_id(1) == "e0001"


class TestDetectLang:
    def test_detects_python(self):
        assert detect_lang("src/app/main.py") == "python"

    def test_detects_typescript(self):
        assert detect_lang("src/login.ts") == "typescript"

    def test_detects_javascript(self):
        assert detect_lang("index.js") == "javascript"

    def test_unknown_extension_returns_unknown(self):
        assert detect_lang("data/blob.xyzzy") == "unknown"

    def test_detection_is_case_insensitive(self):
        assert detect_lang("README.MD") == "markdown"


class TestFileIndex:
    def test_resolves_path_to_id(self):
        records = [
            FileRecord(id="f0001", path="src/a.py", lang="python", loc=1, sizeBytes=10),
            FileRecord(id="f0002", path="src/b.py", lang="python", loc=2, sizeBytes=20),
        ]
        idx = FileIndex(records)
        assert idx.id_for_path("src/a.py") == "f0001"
        assert idx.id_for_path("src/b.py") == "f0002"

    def test_returns_none_for_unknown_path(self):
        idx = FileIndex([])
        assert idx.id_for_path("nope.py") is None

    def test_record_for_id_round_trips(self):
        rec = FileRecord(id="f0001", path="src/a.py", lang="python", loc=1, sizeBytes=10)
        idx = FileIndex([rec])
        assert idx.record_for_id("f0001").path == "src/a.py"
