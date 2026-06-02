"""Tests for build_report's code blob inlining and the --repo CLI path.

The existing test_build_report.py asserts the 3-arg build_report and facts/
narrative inlining; here we cover the optional code blob and main(--repo).
"""
import json
import re
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "skills" / "explain-project" / "scripts"
ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = (ROOT / "skills" / "explain-project" / "templates" / "report.html.tmpl").read_text()
sys.path.insert(0, str(SCRIPTS))

from build_report import build_report, main  # noqa: E402


def _facts():
    return {
        "schemaVersion": "1.0",
        "repo": {"root": ".", "headCommit": "abc", "branch": "main",
                 "generatedAt": "2026-01-01T00:00:00Z", "totalFiles": 1, "totalLoc": 1},
        "files": [{"id": "f0001", "path": "a.py", "lang": "python", "loc": 1, "sizeBytes": 5}],
        "modules": [], "edges": [], "entrypoints": [], "externalDependencies": [],
        "gitCoupling": [],
        "extractionReport": {"languagesDetected": ["python"], "importEdgesResolved": 0,
                             "importEdgesUnresolved": 0, "ecosystemToolsUsed": [],
                             "skipped": [], "warnings": []},
    }


def _narrative():
    return {
        "schemaVersion": "2.0", "basedOnFactsCommit": "abc",
        "perspectives": [{
            "id": "structural", "name": "Structural", "kind": "structural",
            "description": "lens", "tiers": [{"level": 0, "name": "S"}],
            "nodes": [{"id": "n1", "tier": 0, "label": "L", "description": "d",
                       "factRefs": {"moduleIds": [], "fileIds": ["f0001"]},
                       "children": [], "confidence": "high", "interpretation": False}],
            "relationships": [],
        }],
        "openQuestions": [],
    }


def test_code_blob_inlined_and_round_trips():
    code = {"f0001": {"path": "a.py", "lang": "python", "content": "print('hi')\n", "truncated": False}}
    html = build_report(_facts(), _narrative(), TEMPLATE, code=code)
    m = re.search(r'<script id="code"[^>]*>(.*?)</script>', html, re.DOTALL)
    assert m, "expected an inlined code script block"
    recovered = json.loads(m.group(1).replace("<\\/", "</"))
    assert recovered["f0001"]["content"] == "print('hi')\n"


def test_code_blob_neutralizes_script_breakout():
    code = {"f0001": {"path": "a.py", "lang": "python",
                      "content": "x = '</script><b>pwn</b>'\n", "truncated": False}}
    html = build_report(_facts(), _narrative(), TEMPLATE, code=code)
    # the raw breakout sequence must not survive verbatim
    assert "</script><b>pwn</b>" not in html


def test_build_report_without_code_still_works():
    # back-compat: 3-arg form yields an empty code blob, not a crash
    html = build_report(_facts(), _narrative(), TEMPLATE)
    assert "<html" in html and "</html>" in html
    m = re.search(r'<script id="code"[^>]*>(.*?)</script>', html, re.DOTALL)
    assert m and json.loads(m.group(1).replace("<\\/", "</")) == {}


def test_main_builds_code_from_repo(tmp_path):
    (tmp_path / "a.py").write_text("print('from disk')\n")
    facts = _facts()
    facts["repo"]["root"] = str(tmp_path)
    (tmp_path / "facts.json").write_text(json.dumps(facts))
    (tmp_path / "narrative.json").write_text(json.dumps(_narrative()))
    out = tmp_path / "report.html"
    rc = main(["--facts", str(tmp_path / "facts.json"),
               "--narrative", str(tmp_path / "narrative.json"),
               "--out", str(out), "--repo", str(tmp_path)])
    assert rc == 0
    html = out.read_text()
    assert "print('from disk')" in html


def test_main_defaults_repo_to_facts_root(tmp_path):
    (tmp_path / "a.py").write_text("print('default root')\n")
    facts = _facts()
    facts["repo"]["root"] = str(tmp_path)
    (tmp_path / "facts.json").write_text(json.dumps(facts))
    (tmp_path / "narrative.json").write_text(json.dumps(_narrative()))
    out = tmp_path / "report.html"
    rc = main(["--facts", str(tmp_path / "facts.json"),
               "--narrative", str(tmp_path / "narrative.json"),
               "--out", str(out)])  # no --repo
    assert rc == 0
    assert "print('default root')" in out.read_text()
