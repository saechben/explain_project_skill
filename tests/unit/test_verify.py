"""Tests for the anti-hallucination verification gate (verify.py)."""
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "skills" / "explain-project" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from verify import verify, main


def make_facts(**overrides):
    facts = {
        "schemaVersion": "1",
        "repo": {
            "root": ".",
            "headCommit": "abc123",
            "branch": "main",
            "generatedAt": "2026-06-02T00:00:00Z",
            "totalFiles": 2,
            "totalLoc": 10,
        },
        "files": [
            {"id": "f0001", "path": "pkg/a.py", "lang": "python", "loc": 5, "sizeBytes": 50},
            {"id": "f0002", "path": "pkg/b.py", "lang": "python", "loc": 5, "sizeBytes": 50},
        ],
        "modules": [
            {"id": "m001", "path": "pkg", "fileIds": ["f0001", "f0002"]},
        ],
        "edges": [
            {
                "id": "e0001",
                "type": "import",
                "from": "f0001",
                "to": "f0002",
                "evidence": {"file": "pkg/a.py", "line": 1, "raw": "import b"},
                "resolution": "resolved",
                "extractor": "treesitter",
            },
        ],
        "entrypoints": [],
        "externalDependencies": [],
        "gitCoupling": [],
        "extractionReport": {
            "languagesDetected": ["python"],
            "importEdgesResolved": 1,
            "importEdgesUnresolved": 0,
            "ecosystemToolsUsed": [],
            "skipped": [],
            "warnings": [],
        },
    }
    facts.update(overrides)
    return facts


def make_narrative(**overrides):
    narrative = {
        "schemaVersion": "1",
        "basedOnFactsCommit": "abc123",
        "tiers": [{"level": 0, "name": "top"}],
        "nodes": [
            {
                "id": "n1",
                "tier": 0,
                "label": "A",
                "description": "module a",
                "factRefs": {"moduleIds": [], "fileIds": ["f0001"]},
                "children": [],
                "confidence": "high",
                "interpretation": False,
            },
            {
                "id": "n2",
                "tier": 0,
                "label": "B",
                "description": "module b",
                "factRefs": {"moduleIds": [], "fileIds": ["f0002"]},
                "children": [],
                "confidence": "high",
                "interpretation": False,
            },
        ],
        "relationships": [
            {
                "from": "n1",
                "to": "n2",
                "label": "imports",
                "factEdgeIds": ["e0001"],
                "confidence": "high",
            },
        ],
        "openQuestions": [],
    }
    narrative.update(overrides)
    return narrative


def test_clean_narrative_passes():
    report = verify(make_facts(), make_narrative())
    assert report["status"] == "PASS"
    assert report["errors"] == []


def test_orphan_file_id_fails_referential_integrity():
    narrative = make_narrative()
    narrative["nodes"][0]["factRefs"]["fileIds"] = ["f9999"]
    report = verify(make_facts(), narrative)
    assert report["status"] == "FAIL"
    assert any(e["check"] == "referential-integrity" for e in report["errors"])


def test_orphan_module_id_fails_referential_integrity():
    narrative = make_narrative()
    narrative["nodes"][0]["factRefs"]["moduleIds"] = ["m999"]
    report = verify(make_facts(), narrative)
    assert report["status"] == "FAIL"
    assert any(e["check"] == "referential-integrity" for e in report["errors"])


def test_orphan_fact_edge_id_fails_referential_integrity():
    narrative = make_narrative()
    narrative["relationships"][0]["factEdgeIds"] = ["e9999"]
    report = verify(make_facts(), narrative)
    assert report["status"] == "FAIL"
    assert any(e["check"] == "referential-integrity" for e in report["errors"])


def test_empty_grounding_non_interpretation_fails():
    narrative = make_narrative()
    narrative["nodes"][0]["factRefs"] = {"moduleIds": [], "fileIds": []}
    narrative["nodes"][0]["interpretation"] = False
    report = verify(make_facts(), narrative)
    assert report["status"] == "FAIL"
    assert any(e["check"] == "empty-grounding" for e in report["errors"])


def test_empty_grounding_low_confidence_interpretation_passes():
    narrative = make_narrative()
    narrative["nodes"][0]["factRefs"] = {"moduleIds": [], "fileIds": []}
    narrative["nodes"][0]["interpretation"] = True
    narrative["nodes"][0]["confidence"] = "low"
    narrative["nodes"][0]["description"] = "an inference about the design"
    report = verify(make_facts(), narrative)
    assert report["status"] == "PASS"
    assert not any(e["check"] == "empty-grounding" for e in report["errors"])


def test_commit_mismatch_warns_but_passes():
    narrative = make_narrative(basedOnFactsCommit="deadbeef")
    report = verify(make_facts(), narrative)
    assert report["status"] == "PASS"
    assert any(w["check"] == "commit-match" for w in report["warnings"])


def test_file_existence_missing_fails(tmp_path):
    facts = make_facts()
    narrative = make_narrative()
    # only create f0001 on disk, referenced by n1; f0002 missing
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text("import b\n")
    report = verify(facts, narrative, repo_root=tmp_path)
    assert report["status"] == "FAIL"
    assert any(e["check"] == "file-existence" for e in report["errors"])


def test_file_existence_present_passes(tmp_path):
    facts = make_facts()
    narrative = make_narrative()
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text("import b\n")
    (tmp_path / "pkg" / "b.py").write_text("\n")
    report = verify(facts, narrative, repo_root=tmp_path)
    assert not any(e["check"] == "file-existence" for e in report["errors"])
    assert report["status"] == "PASS"


def test_coverage_block_percentage():
    facts = make_facts()
    narrative = make_narrative()
    # cover only f0001 via n1; drop n2
    narrative["nodes"] = [narrative["nodes"][0]]
    narrative["relationships"] = []
    report = verify(facts, narrative)
    cov = report["coverage"]
    assert cov["totalFiles"] == 2
    assert cov["filesCoveredByNode"] == 1
    assert cov["fileCoveragePct"] == 50.0
    assert cov["nodeCount"] == 1


def test_coverage_module_ref_covers_member_files():
    facts = make_facts()
    narrative = make_narrative()
    # single node referencing module m001 which holds both files
    narrative["nodes"] = [
        {
            "id": "n1",
            "tier": 0,
            "label": "pkg",
            "description": "the package",
            "factRefs": {"moduleIds": ["m001"], "fileIds": []},
            "children": [],
            "confidence": "high",
            "interpretation": False,
        }
    ]
    narrative["relationships"] = []
    report = verify(facts, narrative)
    cov = report["coverage"]
    assert cov["filesCoveredByNode"] == 2
    assert cov["fileCoveragePct"] == 100.0


def test_coverage_unresolved_edges_counted():
    facts = make_facts()
    facts["edges"][0]["resolution"] = "unresolved"
    facts["edges"][0]["to"] = None
    narrative = make_narrative()
    narrative["relationships"][0]["factEdgeIds"] = []
    report = verify(facts, narrative)
    assert report["coverage"]["unresolvedEdges"] == 1


def test_main_good_input_returns_zero(tmp_path):
    facts_path = tmp_path / "facts.json"
    narr_path = tmp_path / "narrative.json"
    out_path = tmp_path / "verify.report.json"
    facts_path.write_text(json.dumps(make_facts()))
    narr_path.write_text(json.dumps(make_narrative()))
    rc = main(["--facts", str(facts_path), "--narrative", str(narr_path), "--out", str(out_path)])
    assert rc == 0
    assert out_path.exists()
    report = json.loads(out_path.read_text())
    assert report["status"] == "PASS"


def test_main_orphan_input_returns_one(tmp_path):
    facts_path = tmp_path / "facts.json"
    narr_path = tmp_path / "narrative.json"
    out_path = tmp_path / "verify.report.json"
    narrative = make_narrative()
    narrative["nodes"][0]["factRefs"]["fileIds"] = ["f9999"]
    facts_path.write_text(json.dumps(make_facts()))
    narr_path.write_text(json.dumps(narrative))
    rc = main(["--facts", str(facts_path), "--narrative", str(narr_path), "--out", str(out_path)])
    assert rc == 1
    assert out_path.exists()
    report = json.loads(out_path.read_text())
    assert report["status"] == "FAIL"


def test_main_default_out_next_to_facts(tmp_path):
    facts_path = tmp_path / "facts.json"
    narr_path = tmp_path / "narrative.json"
    facts_path.write_text(json.dumps(make_facts()))
    narr_path.write_text(json.dumps(make_narrative()))
    rc = main(["--facts", str(facts_path), "--narrative", str(narr_path)])
    assert rc == 0
    assert (tmp_path / "verify.report.json").exists()
