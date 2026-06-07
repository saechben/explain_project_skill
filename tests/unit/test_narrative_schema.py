"""The narrative schema must accept both the v1 single-narrative and v2
multi-perspective shapes, and reject a narrative carrying neither."""
import json
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "skills" / "explain-project" / "schema" / "narrative.schema.json").read_text())


def _node(nid="n1"):
    return {
        "id": nid, "tier": 0, "label": "L", "description": "d",
        "factRefs": {"moduleIds": [], "fileIds": ["f0001"]},
        "children": [], "confidence": "high", "interpretation": False,
    }


def test_v1_single_narrative_validates():
    narr = {
        "schemaVersion": "1.0", "basedOnFactsCommit": "abc",
        "tiers": [{"level": 0, "name": "System"}],
        "nodes": [_node()], "relationships": [], "openQuestions": [],
    }
    jsonschema.validate(narr, SCHEMA)


def test_v2_multi_perspective_validates():
    narr = {
        "schemaVersion": "2.0", "basedOnFactsCommit": "abc",
        "perspectives": [
            {"id": "structural", "name": "Structural", "kind": "structural",
             "description": "lens", "tiers": [{"level": 0, "name": "System"}],
             "nodes": [_node()], "relationships": []},
            {"id": "functional", "name": "Functional", "kind": "functional",
             "description": "lens", "tiers": [{"level": 0, "name": "Capabilities"}],
             "nodes": [_node()], "relationships": []},
        ],
        "openQuestions": [],
    }
    jsonschema.validate(narr, SCHEMA)


def test_narrative_with_neither_shape_is_rejected():
    narr = {"schemaVersion": "2.0", "basedOnFactsCommit": "abc", "openQuestions": []}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(narr, SCHEMA)


def test_unknown_perspective_kind_rejected():
    narr = {
        "schemaVersion": "2.0", "basedOnFactsCommit": "abc",
        "perspectives": [
            {"id": "x", "name": "X", "kind": "marketing", "description": "d",
             "tiers": [{"level": 0, "name": "T"}], "nodes": [_node()], "relationships": []},
        ],
        "openQuestions": [],
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(narr, SCHEMA)


def _claim(text="t", interpretation=False, confidence="high", **kw):
    c = {
        "text": text,
        "factRefs": {"moduleIds": [], "fileIds": ["f0001"]},
        "confidence": confidence,
        "interpretation": interpretation,
    }
    c.update(kw)
    return c


def _v2_with_brief(brief):
    return {
        "schemaVersion": "2.0", "basedOnFactsCommit": "abc",
        "perspectives": [
            {"id": "structural", "name": "Structural", "kind": "structural",
             "description": "lens", "tiers": [{"level": 0, "name": "System"}],
             "nodes": [_node()], "relationships": []},
        ],
        "businessBrief": brief,
        "openQuestions": [],
    }


def test_business_brief_minimal_validates():
    narr = _v2_with_brief({
        "headline": "A grounded project map generator",
        "problem": _claim(),
        "solution": _claim(),
    })
    jsonschema.validate(narr, SCHEMA)


def test_business_brief_is_optional():
    narr = {
        "schemaVersion": "2.0", "basedOnFactsCommit": "abc",
        "perspectives": [
            {"id": "structural", "name": "Structural", "kind": "structural",
             "description": "lens", "tiers": [{"level": 0, "name": "System"}],
             "nodes": [_node()], "relationships": []},
        ],
        "openQuestions": [],
    }
    jsonschema.validate(narr, SCHEMA)


def test_business_brief_missing_problem_rejected():
    narr = _v2_with_brief({"headline": "H", "solution": _claim()})
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(narr, SCHEMA)


def test_brief_claim_missing_confidence_rejected():
    bad = {"text": "t", "factRefs": {"fileIds": ["f0001"]}, "interpretation": False}
    narr = _v2_with_brief({"headline": "H", "problem": bad, "solution": _claim()})
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(narr, SCHEMA)


def test_brief_extra_property_rejected():
    narr = _v2_with_brief({
        "headline": "H", "problem": _claim(), "solution": _claim(),
        "tagline": "extra",
    })
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(narr, SCHEMA)


def test_brief_claim_extra_property_rejected():
    narr = _v2_with_brief({
        "headline": "H", "problem": _claim(weight=3), "solution": _claim(),
    })
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(narr, SCHEMA)


def test_techstack_item_missing_factref_rejected():
    narr = _v2_with_brief({
        "headline": "H", "problem": _claim(), "solution": _claim(),
        "techStack": [{"name": "flask", "role": "web framework"}],
    })
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(narr, SCHEMA)


def test_brief_claim_bad_confidence_enum_rejected():
    narr = _v2_with_brief({
        "headline": "H", "problem": _claim(confidence="certain"), "solution": _claim(),
    })
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(narr, SCHEMA)
