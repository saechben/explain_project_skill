"""Structural presence tests for the v2 report template features.

JS behavior is verified manually in a browser; here we lock in that the wiring
exists in the rendered HTML so it can't silently regress: perspective switcher,
floaty physics layout with fallback, hover reactions, the copy-prompt Ask bridge,
and the read-only code viewer.
"""
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "skills" / "explain-project" / "scripts"
ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = (ROOT / "skills" / "explain-project" / "templates" / "report.html.tmpl").read_text()
sys.path.insert(0, str(SCRIPTS))

from build_report import build_report  # noqa: E402


def _facts():
    return {
        "schemaVersion": "1.0",
        "repo": {"root": ".", "headCommit": "abc", "branch": "main",
                 "generatedAt": "t", "totalFiles": 1, "totalLoc": 1},
        "files": [{"id": "f0001", "path": "a.py", "lang": "python", "loc": 1, "sizeBytes": 5}],
        "modules": [], "edges": [], "entrypoints": [], "externalDependencies": [],
        "gitCoupling": [],
        "extractionReport": {"languagesDetected": ["python"], "importEdgesResolved": 0,
                             "importEdgesUnresolved": 0, "ecosystemToolsUsed": [],
                             "skipped": [], "warnings": []},
    }


def _narrative():
    def persp(pid, kind):
        return {"id": pid, "name": pid.title(), "kind": kind, "description": "lens",
                "tiers": [{"level": 0, "name": "S"}],
                "nodes": [{"id": "n1", "tier": 0, "label": "L", "description": "d",
                           "factRefs": {"moduleIds": [], "fileIds": ["f0001"]},
                           "children": [], "confidence": "high", "interpretation": False}],
                "relationships": []}
    return {"schemaVersion": "2.0", "basedOnFactsCommit": "abc",
            "perspectives": [persp("structural", "structural"), persp("functional", "functional")],
            "openQuestions": []}


def _html(code=None):
    return build_report(_facts(), _narrative(), TEMPLATE, code=code or {})


class TestTemplateFeatures:
    def test_perspective_switcher_present(self):
        html = _html()
        assert 'id="perspectives"' in html
        assert "currentPerspective" in html

    def test_floaty_physics_layout_with_fallback(self):
        html = _html()
        # cola physics layout requested, cose named as the fallback
        assert "cola" in html
        assert "cose" in html

    def test_hover_handlers_wired(self):
        html = _html()
        assert 'cy.on("mouseover"' in html or "cy.on('mouseover'" in html
        assert 'cy.on("mouseout"' in html or "cy.on('mouseout'" in html
        assert 'id="hovercard"' in html

    def test_ask_copy_prompt_bridge_present(self):
        html = _html()
        assert "composeAskPrompt" in html
        assert "clipboard" in html  # navigator.clipboard with manual fallback

    def test_code_viewer_present_with_highlight_fallback(self):
        html = _html()
        assert "openCodeViewer" in html
        assert "highlight.js" in html or "hljs" in html
        assert 'id="codeviewer"' in html

    def test_renders_code_blob_content(self):
        code = {"f0001": {"path": "a.py", "lang": "python", "content": "print('x')\n", "truncated": False}}
        html = _html(code=code)
        assert "print('x')" in html


class TestBusinessBriefFeatures:
    def test_briefview_and_viewtabs_present(self):
        html = _html()
        assert 'id="briefview"' in html
        assert 'id="viewtabs"' in html

    def test_view_toggle_buttons_present(self):
        html = _html()
        assert 'id="vt-brief"' in html
        assert 'id="vt-map"' in html
        assert "showMap" in html
        assert "showBrief" in html

    def test_mapview_wrapper_present(self):
        html = _html()
        assert 'id="mapview"' in html

    def test_render_brief_function_present(self):
        html = _html()
        assert "renderBrief" in html

    def test_capability_cards_classes_and_link_present(self):
        html = _html()
        assert "cap-card" in html
        assert "cap-grid" in html
        # capability cards link into the graph via setPerspective
        assert "setPerspective" in html

    def test_stat_tiles_classes_and_facts_source(self):
        html = _html()
        assert "stat-grid" in html
        assert "stat" in html
        # stats are computed purely from facts
        assert "totalFiles" in html

    def test_tech_chips_group_class_present(self):
        html = _html()
        assert "tech-group" in html

    def test_brief_respects_verified_only(self):
        html = _html()
        # the brief render path consults the verified-only predicate
        assert "hidden(" in html

    def test_vtab_css_class_present(self):
        html = _html()
        assert ".vtab" in html

    def test_lazy_init_flag_present(self):
        html = _html()
        assert "cyInited" in html

    def test_ask_about_brief_present(self):
        html = _html()
        assert "askAboutBrief" in html
