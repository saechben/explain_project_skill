"""Tests for the businessBrief validation in verify.py.

The business brief is an OPTIONAL top-level object. When present, every
problem/solution/audience claim and every capability must be grounded in facts
under the SAME discipline as nodes (>=1 factRef unless flagged as a written
low-confidence interpretation). techStack[].factRef must name a real external
dependency. capability perspectiveRef/nodeRef must point at a real node.
A narrative WITHOUT businessBrief must behave exactly as before.
"""
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "skills" / "explain-project" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from verify import verify  # noqa: E402


def _facts():
    return {
        "repo": {"headCommit": "abc123"},
        "files": [
            {"id": "f0001", "path": "a.py"},
            {"id": "f0002", "path": "b.py"},
        ],
        "modules": [{"id": "m001", "path": ".", "fileIds": ["f0001", "f0002"]}],
        "edges": [
            {"id": "e0001", "from": "f0001", "to": "f0002", "resolution": "resolved"},
        ],
        "externalDependencies": [
            {"name": "flask"},
            {"name": "pytest"},
        ],
    }


def _node(nid, file_ids, **kw):
    n = {
        "id": nid, "tier": 0, "label": nid, "description": "d",
        "factRefs": {"moduleIds": [], "fileIds": file_ids},
        "children": [], "confidence": "high", "interpretation": False,
    }
    n.update(kw)
    return n


def _perspective(pid, nodes, kind="structural"):
    return {
        "id": pid, "name": pid.title(), "kind": kind, "description": "lens",
        "tiers": [{"level": 0, "name": "System"}],
        "nodes": nodes, "relationships": [],
    }


def _claim(text="t", file_ids=None, module_ids=None, interpretation=False,
           confidence="high"):
    return {
        "text": text,
        "factRefs": {
            "moduleIds": module_ids or [],
            "fileIds": file_ids if file_ids is not None else ["f0001"],
        },
        "confidence": confidence,
        "interpretation": interpretation,
    }


def _narrative(brief=None, perspectives=None, commit="abc123"):
    n = {
        "schemaVersion": "2.0",
        "basedOnFactsCommit": commit,
        "perspectives": perspectives or [
            _perspective("structural", [_node("n1", ["f0001", "f0002"])]),
        ],
        "openQuestions": [],
    }
    if brief is not None:
        n["businessBrief"] = brief
    return n


def _brief(**kw):
    b = {
        "headline": "A grounded project map generator",
        "problem": _claim(text="hard to understand repos"),
        "solution": _claim(text="generate a grounded map"),
    }
    b.update(kw)
    return b


def test_grounded_brief_passes():
    report = verify(_facts(), _narrative(_brief()))
    assert report["status"] == "PASS", report["errors"]


def test_no_business_brief_passes():
    report = verify(_facts(), _narrative())
    assert report["status"] == "PASS", report["errors"]
    assert not any("businessBrief" in e["message"] for e in report["errors"])


def test_ungrounded_claim_fails_empty_grounding():
    brief = _brief(problem=_claim(text="x", file_ids=[], interpretation=False))
    report = verify(_facts(), _narrative(brief))
    assert report["status"] == "FAIL"
    eg = [e for e in report["errors"]
          if e["check"] == "empty-grounding" and "businessBrief" in e["message"]]
    assert eg, report["errors"]


def test_ungrounded_low_confidence_interpretation_passes():
    brief = _brief(problem=_claim(text="a guess", file_ids=[],
                                  interpretation=True, confidence="low"))
    report = verify(_facts(), _narrative(brief))
    assert report["status"] == "PASS", report["errors"]


def test_orphan_fileid_fails_referential_integrity():
    brief = _brief(solution=_claim(text="s", file_ids=["f9999"]))
    report = verify(_facts(), _narrative(brief))
    assert report["status"] == "FAIL"
    ref = [e for e in report["errors"]
           if e["check"] == "referential-integrity" and "businessBrief" in e["message"]]
    assert ref, report["errors"]


def test_techstack_unknown_dep_fails():
    brief = _brief(techStack=[{"name": "Django", "role": "web framework",
                               "factRef": "django"}])
    report = verify(_facts(), _narrative(brief))
    assert report["status"] == "FAIL"
    assert any(e["check"] == "techstack-ref" and "businessBrief" in e["message"]
               for e in report["errors"])


def test_techstack_known_dep_passes():
    brief = _brief(techStack=[{"name": "Flask", "role": "web framework",
                               "factRef": "flask"}])
    report = verify(_facts(), _narrative(brief))
    assert report["status"] == "PASS", report["errors"]


def test_capability_unknown_perspective_ref_fails():
    cap = {"label": "Map", "text": "builds a map", "confidence": "high",
           "interpretation": False, "factRefs": {"fileIds": ["f0001"]},
           "perspectiveRef": "ghost"}
    brief = _brief(capabilities=[cap])
    report = verify(_facts(), _narrative(brief))
    assert report["status"] == "FAIL"
    assert any(e["check"] == "capability-ref" and "businessBrief" in e["message"]
               for e in report["errors"])


def test_capability_noderef_not_a_node_fails():
    cap = {"label": "Map", "text": "builds a map", "confidence": "high",
           "interpretation": False, "factRefs": {"fileIds": ["f0001"]},
           "perspectiveRef": "structural", "nodeRef": "nX"}
    brief = _brief(capabilities=[cap])
    report = verify(_facts(), _narrative(brief))
    assert report["status"] == "FAIL"
    assert any(e["check"] == "capability-ref" and "businessBrief" in e["message"]
               for e in report["errors"])


def test_capability_valid_perspective_and_node_passes():
    cap = {"label": "Map", "text": "builds a map", "confidence": "high",
           "interpretation": False, "factRefs": {"fileIds": ["f0001"]},
           "perspectiveRef": "structural", "nodeRef": "n1"}
    brief = _brief(capabilities=[cap])
    report = verify(_facts(), _narrative(brief))
    assert report["status"] == "PASS", report["errors"]


def test_capability_ungrounded_fails_empty_grounding():
    cap = {"label": "Map", "text": "builds a map", "confidence": "high",
           "interpretation": False, "factRefs": {"fileIds": [], "moduleIds": []}}
    brief = _brief(capabilities=[cap])
    report = verify(_facts(), _narrative(brief))
    assert report["status"] == "FAIL"
    assert any(e["check"] == "empty-grounding" and "businessBrief" in e["message"]
               for e in report["errors"])


def test_audience_claim_validated_when_present():
    brief = _brief(audience=_claim(text="aud", file_ids=["f9999"]))
    report = verify(_facts(), _narrative(brief))
    assert report["status"] == "FAIL"
    assert any(e["check"] == "referential-integrity" and "businessBrief" in e["message"]
               for e in report["errors"])


def test_empty_headline_warns_not_fails():
    brief = _brief(headline="")
    report = verify(_facts(), _narrative(brief))
    # empty headline is a WARN; with otherwise-grounded brief status stays PASS
    assert any(w["check"] == "headline" and "businessBrief" in w["message"]
               for w in report["warnings"]), report["warnings"]
    assert report["status"] == "PASS", report["errors"]


def test_brief_fileid_missing_on_disk_fails_file_existence(tmp_path):
    # f0001 -> a.py exists; f0002 -> b.py missing
    (tmp_path / "a.py").write_text("x")
    brief = _brief(solution=_claim(text="s", file_ids=["f0002"]))
    report = verify(_facts(), _narrative(brief), repo_root=tmp_path)
    assert report["status"] == "FAIL"
    assert any(e["check"] == "file-existence" and "businessBrief" in e["message"]
               for e in report["errors"])
