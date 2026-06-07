"""Tests for build_report.py: merge facts.json + narrative.json into a single self-contained HTML report.

Placeholder convention (documented): the template uses __FACTS_JSON__ and __NARRATIVE_JSON__
as the two replacement tokens. build_report fills them with the inlined, '</'-neutralized JSON.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills" / "explain-project" / "scripts"
TEMPLATE = ROOT / "skills" / "explain-project" / "templates" / "report.html.tmpl"
sys.path.insert(0, str(SCRIPTS))

from build_report import build_report, main


def make_facts() -> dict:
    return {
        "schemaVersion": "1.0",
        "repo": {
            "root": "/repo",
            "headCommit": "abc123",
            "branch": "main",
            "generatedAt": "2026-06-02T00:00:00Z",
            "totalFiles": 2,
            "totalLoc": 30,
        },
        "files": [
            {"id": "f0001", "path": "src/app/main.py", "lang": "python", "loc": 20, "sizeBytes": 400},
            {"id": "f0002", "path": "src/app/util.py", "lang": "python", "loc": 10, "sizeBytes": 200},
        ],
        "modules": [
            {"id": "m001", "path": "src/app", "fileIds": ["f0001", "f0002"]},
        ],
        "edges": [
            {
                "id": "e0001",
                "type": "import",
                "from": "f0001",
                "to": "f0002",
                "evidence": {"file": "src/app/main.py", "line": 1, "raw": "import util"},
                "resolution": "resolved",
                "extractor": "treesitter",
            },
        ],
        "entrypoints": [{"fileId": "f0001", "kind": "cli", "evidence": "__main__"}],
        "externalDependencies": [],
        "gitCoupling": [],
        "extractionReport": {
            "languagesDetected": ["python"],
            "importEdgesResolved": 1,
            "importEdgesUnresolved": 0,
            "ecosystemToolsUsed": ["pydeps"],
            "skipped": ["node_modules"],
            "warnings": [],
        },
    }


def make_narrative() -> dict:
    return {
        "schemaVersion": "1.0",
        "basedOnFactsCommit": "abc123",
        "tiers": [{"level": 0, "name": "System"}, {"level": 1, "name": "Modules"}],
        "nodes": [
            {
                "id": "n0",
                "tier": 0,
                "label": "Application Core",
                "description": "Top level system. Crafted breakout attempt: </script><b>x</b>",
                "factRefs": {"moduleIds": ["m001"], "fileIds": ["f0001"]},
                "children": ["n1"],
                "confidence": "high",
                "interpretation": False,
            },
            {
                "id": "n1",
                "tier": 1,
                "label": "Utilities",
                "description": "Helper utilities.",
                "factRefs": {"moduleIds": [], "fileIds": ["f0002"]},
                "children": [],
                "confidence": "low",
                "interpretation": True,
            },
        ],
        "relationships": [
            {"from": "n0", "to": "n1", "label": "uses", "factEdgeIds": ["e0001"], "confidence": "high"},
        ],
        "openQuestions": ["Is util.py shared?"],
    }


def make_business_brief() -> dict:
    return {
        "headline": "Ships grounded repo explainers",
        "problem": {
            "text": "Onboarding to a new repo is slow.",
            "factRefs": {"moduleIds": ["m001"], "fileIds": ["f0001"]},
            "confidence": "high",
            "interpretation": False,
        },
        "solution": {
            "text": "Generates an interactive grounded report.",
            "factRefs": {"moduleIds": [], "fileIds": ["f0002"]},
            "confidence": "medium",
            "interpretation": True,
        },
        "audience": {
            "text": "Engineers new to a codebase.",
            "factRefs": {"moduleIds": [], "fileIds": []},
            "confidence": "low",
            "interpretation": True,
        },
        "howItWorks": "Facts are extracted then narrated.",
        "capabilities": [
            {
                "label": "Interactive map",
                "text": "Explore the repo as a graph.",
                "factRefs": {"moduleIds": ["m001"], "fileIds": []},
                "confidence": "high",
                "interpretation": False,
                "perspectiveRef": "structural",
                "nodeRef": "n0",
            }
        ],
        "techStack": [
            {"name": "python", "role": "language", "factRef": "python"},
        ],
    }


def read_template() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


class TestBuildReport:
    def test_returns_complete_html_document(self):
        html = build_report(make_facts(), make_narrative(), read_template())
        assert html
        assert "<html" in html
        assert "</html>" in html

    def test_inlines_node_label_and_file_path(self):
        html = build_report(make_facts(), make_narrative(), read_template())
        assert "Application Core" in html
        assert "src/app/main.py" in html

    def test_neutralizes_script_breakout_in_json(self):
        html = build_report(make_facts(), make_narrative(), read_template())
        # The inlined JSON regions must not contain a raw '</' from any crafted value.
        facts_json = _extract_json(html, "facts")
        narrative_json = _extract_json(html, "narrative")
        assert "</" not in facts_json
        assert "</" not in narrative_json
        # The literal crafted breakout must not survive verbatim.
        assert "</script><b>x</b>" not in html

    def test_cytoscape_cdn_script_present(self):
        html = build_report(make_facts(), make_narrative(), read_template())
        assert "cdnjs.cloudflare.com/ajax/libs/cytoscape" in html

    def test_json_round_trips(self):
        facts = make_facts()
        narrative = make_narrative()
        html = build_report(facts, narrative, read_template())
        assert _unescape_and_load(_extract_json(html, "facts")) == facts
        assert _unescape_and_load(_extract_json(html, "narrative")) == narrative

    def test_extraction_report_values_present(self):
        html = build_report(make_facts(), make_narrative(), read_template())
        # coverage banner data comes from the inlined facts; ensure the JSON carries it
        facts_json = _unescape_and_load(_extract_json(html, "facts"))
        assert facts_json["extractionReport"]["importEdgesResolved"] == 1
        assert "node_modules" in facts_json["extractionReport"]["skipped"]

    def test_business_brief_round_trips(self):
        narrative = make_narrative()
        narrative["businessBrief"] = make_business_brief()
        html = build_report(make_facts(), narrative, read_template())
        # The headline string survives inlining inside the narrative blob.
        assert "Ships grounded repo explainers" in html
        narrative_json = _unescape_and_load(_extract_json(html, "narrative"))
        assert narrative_json["businessBrief"] == make_business_brief()

    def test_business_brief_capability_label_inlined(self):
        narrative = make_narrative()
        narrative["businessBrief"] = make_business_brief()
        html = build_report(make_facts(), narrative, read_template())
        assert "Interactive map" in html


class TestMain:
    def test_main_writes_file(self, tmp_path):
        facts_path = tmp_path / "facts.json"
        narr_path = tmp_path / "narrative.json"
        out_path = tmp_path / "report.html"
        facts_path.write_text(json.dumps(make_facts()), encoding="utf-8")
        narr_path.write_text(json.dumps(make_narrative()), encoding="utf-8")

        rc = main([
            "--facts", str(facts_path),
            "--narrative", str(narr_path),
            "--out", str(out_path),
        ])
        assert rc == 0
        assert out_path.exists()
        content = out_path.read_text(encoding="utf-8")
        assert "<html" in content
        assert "Application Core" in content

    def test_main_accepts_custom_template(self, tmp_path):
        facts_path = tmp_path / "facts.json"
        narr_path = tmp_path / "narrative.json"
        out_path = tmp_path / "report.html"
        facts_path.write_text(json.dumps(make_facts()), encoding="utf-8")
        narr_path.write_text(json.dumps(make_narrative()), encoding="utf-8")

        rc = main([
            "--facts", str(facts_path),
            "--narrative", str(narr_path),
            "--out", str(out_path),
            "--template", str(TEMPLATE),
        ])
        assert rc == 0
        assert out_path.exists()


def _extract_json(html: str, which: str) -> str:
    """Pull the raw text inside <script id="{which}" type="application/json">...</script>."""
    pattern = re.compile(
        r'<script id="' + re.escape(which) + r'" type="application/json">(.*?)</script>',
        re.DOTALL,
    )
    m = pattern.search(html)
    assert m, f"could not find inlined JSON script block for {which}"
    return m.group(1)


def _unescape_and_load(raw: str) -> dict:
    """Reverse the '</' -> '<\\/' neutralization and json.loads."""
    return json.loads(raw.replace("<\\/", "</"))
