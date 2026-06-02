# explain-project

A Claude Code **plugin** that turns any repository into an **interactive, multi-level
HTML map** — from a system-architect's bird's-eye view down to individual files, with
click-through drill-down.

The hard requirement: **no hallucinated structure.** Deterministic scripts extract the
real skeleton (files, imports, dependencies, entrypoints, git signals) into a
provenance-tagged `facts.json`. Claude groups and labels that skeleton into adaptive
abstraction tiers, writing a `narrative.json` in which **every node and edge references
real facts**. A renderer merges the two into a self-contained `report.html`. A
verification gate fails the run if the narrative references anything absent from the
facts.

## How it works

| Phase | Tool | Output |
|-------|------|--------|
| 1. Extract (deterministic) | `scripts/extract.py` | `facts.json` |
| 2. Narrate (Claude, grounded) | the skill's reasoning | `narrative.json` |
| 3. Render | `scripts/build_report.py` | `report.html` |
| 4. Verify (gate) | `scripts/verify.py` | `verify.report.json` |

The two JSON files are the source of truth; the HTML is a pure projection of them. See
`skills/explain-project/SKILL.md` for the workflow Claude follows and
`IMPLEMENTATION_PLAN.md` / `context.md` for the full design rationale.

## Install / run

Requires **Python 3.11+**.

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

# Phase 1 — extract the real structure of any repo
python skills/explain-project/scripts/extract.py /path/to/repo \
  --out /path/to/repo/.explain-project/facts.json

# Phase 2 — Claude writes narrative.json grounded in facts.json (see SKILL.md)

# Phase 3 — render the interactive report
python skills/explain-project/scripts/build_report.py \
  --facts /path/to/repo/.explain-project/facts.json \
  --narrative /path/to/repo/.explain-project/narrative.json \
  --out /path/to/repo/.explain-project/report.html

# Phase 4 — verify nothing was hallucinated (exit 1 on FAIL)
python skills/explain-project/scripts/verify.py \
  --facts /path/to/repo/.explain-project/facts.json \
  --narrative /path/to/repo/.explain-project/narrative.json \
  --repo /path/to/repo
```

Open `report.html` in a browser:

- **Switch perspectives** — the report carries 2–4 adaptive lenses (Structural,
  Functional, Domain, …), each a separate grounded narrative over the *same* facts.
  Switching changes *what the map is about*, not just the zoom.
- **Floaty graph** — a continuous physics layout; hovering a node makes it react (scale,
  glow, neighbor highlight) and pops a hover-card with quick facts and actions.
- **Ask about a component** — *Ask* composes a fact-grounded prompt (component label, its
  real file/edge IDs, repo) and copies it to your clipboard to paste back into Claude
  Code. The report stays fully offline — no embedded keys, no server.
- **View referenced code** — click a backing file to open a read-only, syntax-highlighted
  viewer. Only referenced files are inlined (size-capped), so the report stays self-contained.
- **Drill down** to real files, inspect provenance/confidence in the side panel, toggle
  **verified-only** to hide all interpretation and see only deterministically-grounded
  structure, and read the coverage banner (overall and per-lens) for the map's limits.

## Anti-hallucination guarantees (verified by `verify.py`)

1. **Referential integrity** — every `factRefs` / `factEdgeIds` ID exists in the facts.
2. **No empty grounding** — every node is grounded, or explicitly flagged low-confidence
   interpretation with a written justification.
3. **File existence** — every referenced file still exists on disk.
4. **Commit match** — the narrative is checked against the facts' commit (warns if stale).
5. **Coverage sanity** — node count and file-coverage % are surfaced, never hidden.

## Development

```bash
pip install -r requirements-dev.txt
python -m pytest          # full suite
```

The codebase is built test-first. Scripts live in `skills/explain-project/scripts/`
(a shared `contract.py`, the `extractors/` package, `extract.py`, `build_report.py`,
`verify.py`); JSON Schemas in `schema/`; the HTML template in `templates/`. Test
fixtures under `tests/fixtures/` are tiny but realistic repos exercising entrypoints,
nested modules, circular imports, and unresolved imports.

## Non-goals (v1)

Runtime/dynamic tracing; editing the target codebase; hosting a live server; deep
call-graph analysis for every language; pulling external context from issue trackers.
