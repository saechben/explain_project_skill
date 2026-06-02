"""Merge facts.json + narrative.json into a single self-contained report.html.

The HTML is a pure projection of the two JSON blobs: every rendered element is driven by
the inlined data, so the page can never display something that is absent from the facts or
narrative. Facts and narrative are inlined into <script type="application/json"> blocks and
the template's __FACTS_JSON__ / __NARRATIVE_JSON__ placeholders are replaced.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

FACTS_PLACEHOLDER = "__FACTS_JSON__"
NARRATIVE_PLACEHOLDER = "__NARRATIVE_JSON__"

DEFAULT_TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "report.html.tmpl"


def _inline_json(data: dict) -> str:
    """Serialize ``data`` for safe embedding inside an HTML <script> tag.

    The only sequence that can break out of a <script> element is ``</`` (e.g. ``</script>``),
    so we neutralize it by replacing ``</`` with ``<\\/``. JSON treats ``\\/`` as ``/``, so the
    value round-trips after the inverse replacement. Nothing else is HTML-escaped.
    """
    serialized = json.dumps(data, ensure_ascii=False)
    return serialized.replace("</", "<\\/")


def build_report(facts: dict, narrative: dict, template: str) -> str:
    """Return a complete standalone HTML document with facts and narrative inlined."""
    html = template.replace(FACTS_PLACEHOLDER, _inline_json(facts))
    html = html.replace(NARRATIVE_PLACEHOLDER, _inline_json(narrative))
    return html


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a self-contained explain-project HTML report.",
    )
    parser.add_argument("--facts", required=True, help="Path to facts.json")
    parser.add_argument("--narrative", required=True, help="Path to narrative.json")
    parser.add_argument("--out", required=True, help="Path to write report.html")
    parser.add_argument(
        "--template",
        default=str(DEFAULT_TEMPLATE),
        help="Path to the HTML template (default: bundled report.html.tmpl)",
    )
    args = parser.parse_args(argv)

    facts = json.loads(Path(args.facts).read_text(encoding="utf-8"))
    narrative = json.loads(Path(args.narrative).read_text(encoding="utf-8"))
    template = Path(args.template).read_text(encoding="utf-8")

    html = build_report(facts, narrative, template)
    Path(args.out).write_text(html, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
