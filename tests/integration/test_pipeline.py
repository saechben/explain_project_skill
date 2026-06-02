"""Integration tests across the full extract -> verify -> render seam.

These exercise the real components together on the py_app fixture: the anti-hallucination
gate is the central guarantee, so we assert it both PASSES a grounded narrative and FAILS
a narrative that references something not in the facts.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills" / "explain-project" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from extract import extract  # noqa: E402
from verify import verify  # noqa: E402
from build_report import build_report  # noqa: E402

TEMPLATE = (ROOT / "skills" / "explain-project" / "templates" / "report.html.tmpl").read_text()


def _grounded_narrative(facts):
    """Build a minimal narrative grounded in whatever facts came out of extraction."""
    file_ids = [f["id"] for f in facts["files"]]
    module_ids = [m["id"] for m in facts["modules"]]
    return {
        "schemaVersion": "1.0",
        "basedOnFactsCommit": facts["repo"]["headCommit"],
        "tiers": [{"level": 0, "name": "System Overview"}],
        "nodes": [
            {
                "id": "n01", "tier": 0, "label": "Package",
                "description": "All code.",
                "factRefs": {"moduleIds": module_ids[:1], "fileIds": file_ids[:2]},
                "children": [], "confidence": "high", "interpretation": False,
            }
        ],
        "relationships": [],
        "openQuestions": [],
    }


class TestPipeline:
    def test_grounded_narrative_passes_gate(self, py_app):
        facts = extract(py_app)
        narrative = _grounded_narrative(facts)
        report = verify(facts, narrative, repo_root=py_app)
        assert report["status"] == "PASS", report["errors"]

    def test_orphan_file_ref_fails_gate(self, py_app):
        facts = extract(py_app)
        narrative = _grounded_narrative(facts)
        # Reference a file id that cannot exist in the facts.
        narrative["nodes"][0]["factRefs"]["fileIds"] = ["f9999"]
        report = verify(facts, narrative, repo_root=py_app)
        assert report["status"] == "FAIL"
        assert any(e["check"] == "referential-integrity" for e in report["errors"])

    def test_orphan_edge_ref_fails_gate(self, py_app):
        facts = extract(py_app)
        narrative = _grounded_narrative(facts)
        narrative["relationships"] = [
            {"from": "n01", "to": "n01", "label": "self", "factEdgeIds": ["e9999"], "confidence": "low"}
        ]
        report = verify(facts, narrative, repo_root=py_app)
        assert report["status"] == "FAIL"
        assert any(e["check"] == "referential-integrity" for e in report["errors"])

    def test_render_projects_real_data(self, py_app):
        facts = extract(py_app)
        narrative = _grounded_narrative(facts)
        html = build_report(facts, narrative, TEMPLATE)
        assert "<html" in html and "</html>" in html
        # the inlined facts must round-trip and contain a real file path
        assert facts["files"][0]["path"] in html

    def test_pipeline_round_trips_inlined_json(self, py_app):
        facts = extract(py_app)
        narrative = _grounded_narrative(facts)
        html = build_report(facts, narrative, TEMPLATE)
        # the facts script block parses back to the same object
        import re
        m = re.search(r'<script id="facts"[^>]*>(.*?)</script>', html, re.DOTALL)
        assert m
        recovered = json.loads(m.group(1).replace("<\\/", "</"))
        assert recovered["repo"]["totalFiles"] == facts["repo"]["totalFiles"]
