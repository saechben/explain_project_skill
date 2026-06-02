"""End-to-end test for the extract.py orchestrator: produces schema-valid facts.json."""
import json
import subprocess
import sys
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills" / "explain-project" / "scripts"
SCHEMA = ROOT / "skills" / "explain-project" / "schema" / "facts.schema.json"
sys.path.insert(0, str(SCRIPTS))

from extract import extract  # noqa: E402


def _facts_schema():
    return json.loads(SCHEMA.read_text())


class TestExtract:
    def test_produces_schema_valid_facts(self, py_app):
        facts = extract(py_app)
        jsonschema.validate(facts, _facts_schema())

    def test_files_have_sequential_ids_and_langs(self, py_app):
        facts = extract(py_app)
        assert facts["files"], "expected files"
        assert facts["files"][0]["id"] == "f0001"
        langs = {f["lang"] for f in facts["files"]}
        assert "python" in langs

    def test_internal_import_edges_present_and_grounded(self, py_app):
        facts = extract(py_app)
        # core.py -> util.py should appear as a resolved internal edge
        paths = {f["id"]: f["path"] for f in facts["files"]}
        edges = facts["edges"]
        assert edges, "expected import edges"
        resolved = [e for e in edges if e["resolution"] == "resolved"]
        assert any(
            paths[e["from"]].endswith("core.py") and paths.get(e["to"], "").endswith("util.py")
            for e in resolved
        ), "expected core.py -> util.py resolved edge"
        # every edge carries evidence
        for e in edges:
            assert e["evidence"]["file"] and e["evidence"]["raw"]

    def test_external_dependency_and_entrypoint_detected(self, py_app):
        facts = extract(py_app)
        dep_names = {d["name"] for d in facts["externalDependencies"]}
        assert "requests" in dep_names
        assert facts["entrypoints"], "expected at least one entrypoint"

    def test_extraction_report_counts_match_edges(self, py_app):
        facts = extract(py_app)
        rep = facts["extractionReport"]
        resolved = sum(1 for e in facts["edges"] if e["resolution"] == "resolved")
        unresolved = sum(1 for e in facts["edges"] if e["resolution"] == "unresolved")
        assert rep["importEdgesResolved"] == resolved
        assert rep["importEdgesUnresolved"] == unresolved
        assert "python" in rep["languagesDetected"]

    def test_deterministic(self, py_app):
        a = extract(py_app)
        b = extract(py_app)
        # ignore the volatile generatedAt timestamp
        a["repo"]["generatedAt"] = b["repo"]["generatedAt"] = "X"
        assert a == b

    def test_cli_writes_facts_file(self, py_app, tmp_path):
        out = tmp_path / "facts.json"
        rc = subprocess.run(
            [sys.executable, str(SCRIPTS / "extract.py"), str(py_app), "--out", str(out)],
            capture_output=True, text=True,
        )
        assert rc.returncode == 0, rc.stderr
        assert out.exists()
        jsonschema.validate(json.loads(out.read_text()), _facts_schema())
