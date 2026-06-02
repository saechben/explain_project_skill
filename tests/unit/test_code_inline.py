"""Tests for code_inline.collect: gather contents of ONLY referenced files,
bounded by per-file and total caps, with truncation/drop tracking."""
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "skills" / "explain-project" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from code_inline import collect  # noqa: E402


def _facts(files):
    return {"repo": {"root": "."}, "files": files}


def _persp_narrative(file_ids):
    return {
        "schemaVersion": "2.0", "basedOnFactsCommit": None,
        "perspectives": [{
            "id": "p", "name": "P", "kind": "structural", "description": "d",
            "tiers": [{"level": 0, "name": "S"}],
            "nodes": [{
                "id": "n1", "tier": 0, "label": "L", "description": "d",
                "factRefs": {"moduleIds": [], "fileIds": file_ids},
                "children": [], "confidence": "high", "interpretation": False,
            }],
            "relationships": [],
        }],
        "openQuestions": [],
    }


class TestCodeInline:
    def test_only_referenced_files_included(self, tmp_path):
        (tmp_path / "a.py").write_text("print('a')\n")
        (tmp_path / "b.py").write_text("print('b')\n")
        facts = _facts([
            {"id": "f0001", "path": "a.py", "lang": "python"},
            {"id": "f0002", "path": "b.py", "lang": "python"},
        ])
        narrative = _persp_narrative(["f0001"])  # only a.py referenced
        code = collect(facts, narrative, tmp_path)
        assert set(code.keys()) == {"f0001"}
        assert code["f0001"]["content"] == "print('a')\n"
        assert code["f0001"]["path"] == "a.py"
        assert code["f0001"]["lang"] == "python"
        assert code["f0001"]["truncated"] is False

    def test_legacy_v1_narrative_file_refs_collected(self, tmp_path):
        (tmp_path / "a.py").write_text("x = 1\n")
        facts = _facts([{"id": "f0001", "path": "a.py", "lang": "python"}])
        narrative = {
            "schemaVersion": "1.0", "basedOnFactsCommit": None,
            "tiers": [{"level": 0, "name": "S"}],
            "nodes": [{
                "id": "n1", "tier": 0, "label": "L", "description": "d",
                "factRefs": {"moduleIds": [], "fileIds": ["f0001"]},
                "children": [], "confidence": "high", "interpretation": False,
            }],
            "relationships": [], "openQuestions": [],
        }
        code = collect(facts, narrative, tmp_path)
        assert "f0001" in code

    def test_per_file_cap_truncates(self, tmp_path):
        big = "L\n" * 1000  # 2000 bytes
        (tmp_path / "big.py").write_text(big)
        facts = _facts([{"id": "f0001", "path": "big.py", "lang": "python"}])
        code = collect(facts, _persp_narrative(["f0001"]), tmp_path, per_file_cap=100)
        assert code["f0001"]["truncated"] is True
        assert len(code["f0001"]["content"]) <= 100

    def test_total_cap_drops_extra_files(self, tmp_path):
        (tmp_path / "a.py").write_text("a" * 80)
        (tmp_path / "b.py").write_text("b" * 80)
        facts = _facts([
            {"id": "f0001", "path": "a.py", "lang": "python"},
            {"id": "f0002", "path": "b.py", "lang": "python"},
        ])
        # total cap only fits one file
        code = collect(facts, _persp_narrative(["f0001", "f0002"]), tmp_path, total_cap=100)
        present = [fid for fid in ("f0001", "f0002") if fid in code and code[fid].get("content")]
        assert len(present) == 1
        dropped = [fid for fid in ("f0001", "f0002") if code.get(fid, {}).get("dropped")]
        assert len(dropped) == 1

    def test_missing_file_on_disk_is_handled(self, tmp_path):
        facts = _facts([{"id": "f0001", "path": "gone.py", "lang": "python"}])
        code = collect(facts, _persp_narrative(["f0001"]), tmp_path)
        # either omitted or flagged missing, never raises
        assert "f0001" not in code or code["f0001"].get("missing") is True

    def test_unreferenced_file_not_read(self, tmp_path):
        (tmp_path / "a.py").write_text("a\n")
        facts = _facts([{"id": "f0001", "path": "a.py", "lang": "python"}])
        narrative = _persp_narrative([])  # nothing referenced
        code = collect(facts, narrative, tmp_path)
        assert code == {}
