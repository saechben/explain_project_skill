"""Tests for verify.py under the v2 multi-perspective narrative shape.

The gate must validate each perspective independently against the shared facts,
catch cross-perspective leaks and id collisions, and report coverage both in
aggregate and per perspective. Legacy single-narrative shapes must still verify
(covered by test_verify.py) — here we exercise the perspectives[] form.
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
    }


def _node(nid, file_ids, **kw):
    n = {
        "id": nid, "tier": 0, "label": nid, "description": "d",
        "factRefs": {"moduleIds": [], "fileIds": file_ids},
        "children": [], "confidence": "high", "interpretation": False,
    }
    n.update(kw)
    return n


def _narrative(perspectives, commit="abc123"):
    return {
        "schemaVersion": "2.0",
        "basedOnFactsCommit": commit,
        "perspectives": perspectives,
        "openQuestions": [],
    }


def _perspective(pid, nodes, relationships=None, kind="structural"):
    return {
        "id": pid, "name": pid.title(), "kind": kind, "description": "lens",
        "tiers": [{"level": 0, "name": "System"}],
        "nodes": nodes, "relationships": relationships or [],
    }


class TestMultiPerspectiveGate:
    def test_two_clean_perspectives_pass(self):
        narr = _narrative([
            _perspective("structural", [_node("n1", ["f0001", "f0002"])]),
            _perspective("functional", [_node("n1", ["f0001"], confidence="low", interpretation=True)],
                         kind="functional"),
        ])
        report = verify(_facts(), narr)
        assert report["status"] == "PASS", report["errors"]

    def test_orphan_ref_in_one_perspective_fails_and_names_it(self):
        narr = _narrative([
            _perspective("structural", [_node("n1", ["f0001"])]),
            _perspective("functional", [_node("n1", ["f9999"])], kind="functional"),
        ])
        report = verify(_facts(), narr)
        assert report["status"] == "FAIL"
        ref = [e for e in report["errors"] if e["check"] == "referential-integrity"]
        assert ref, report["errors"]
        assert any("functional" in e["message"] for e in ref)

    def test_duplicate_perspective_ids_fail(self):
        narr = _narrative([
            _perspective("dup", [_node("n1", ["f0001"])]),
            _perspective("dup", [_node("n2", ["f0002"])]),
        ])
        report = verify(_facts(), narr)
        assert report["status"] == "FAIL"
        assert any(e["check"] == "perspective-ids" for e in report["errors"])

    def test_duplicate_node_ids_within_perspective_fail(self):
        narr = _narrative([
            _perspective("structural", [_node("n1", ["f0001"]), _node("n1", ["f0002"])]),
        ])
        report = verify(_facts(), narr)
        assert report["status"] == "FAIL"
        assert any(e["check"] == "node-ids" for e in report["errors"])

    def test_relationship_to_unknown_node_fails(self):
        narr = _narrative([
            _perspective(
                "structural",
                [_node("n1", ["f0001"])],
                relationships=[{"from": "n1", "to": "nX", "label": "x",
                                "factEdgeIds": ["e0001"], "confidence": "high"}],
            ),
        ])
        report = verify(_facts(), narr)
        assert report["status"] == "FAIL"
        assert any(e["check"] == "relationship-endpoints" for e in report["errors"])

    def test_empty_grounding_enforced_per_perspective(self):
        bad = _node("n1", [])  # no refs, interpretation False -> illegal
        narr = _narrative([_perspective("structural", [bad])])
        report = verify(_facts(), narr)
        assert report["status"] == "FAIL"
        assert any(e["check"] == "empty-grounding" for e in report["errors"])

    def test_coverage_aggregate_and_per_perspective(self):
        narr = _narrative([
            _perspective("structural", [_node("n1", ["f0001", "f0002"])]),  # 2/2
            _perspective("functional", [_node("n1", ["f0001"])]),           # 1/2
        ])
        report = verify(_facts(), narr)
        cov = report["coverage"]
        # aggregate = union across perspectives = both files
        assert cov["filesCoveredByNode"] == 2
        assert cov["totalFiles"] == 2
        per = {p["id"]: p for p in cov["perspectives"]}
        assert per["structural"]["fileCoveragePct"] == 100.0
        assert per["functional"]["fileCoveragePct"] == 50.0
        assert per["structural"]["nodeCount"] == 1
