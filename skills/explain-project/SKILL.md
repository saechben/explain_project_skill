---
name: explain-project
description: Use to visualize, understand, explain, or map a codebase or repository — produces an interactive multi-level architecture diagram with drill-down from a system-level view to real files. Triggers on "explain this repo", "map the codebase", "architecture diagram", "how is this project structured", "drill-down code map", "visualize this project".
---

# explain-project

Turn any repository into an **interactive, multi-level HTML map** a reader can drill
through — from a system-architect's bird's-eye view down to individual files. The hard
requirement is **no hallucinated structure**: deterministic scripts extract the real
skeleton; you group and label it; a verifier blocks anything not grounded in facts.

## Core rule (do not violate)

**Deterministic tools decide what exists. You may only group, label, and explain over
the extracted facts.** Never invent a node, edge, component, or dependency that has no
referent in `facts.json`. Every narrative node carries `factRefs`; every relationship
carries `factEdgeIds`. Interpretation is labeled (`confidence`, `interpretation`).

## Setup

Scripts are under `scripts/` in this skill. They need Python 3.11+ and the deps in the
plugin's `requirements.txt` (`pathspec`, `pyyaml`, `tree-sitter`,
`tree-sitter-language-pack`). If imports fail, install them into a venv and use that
interpreter for every script call below. Run scripts with that interpreter.

Outputs land in `<repo>/.explain-project/` (`facts.json`, `narrative.json`,
`report.html`, `verify.report.json`).

## The workflow — four phases

### Phase 1 — Extract (deterministic)

Run the extractor. **Do not hand-write any of this.**

```
python scripts/extract.py <repo> --out <repo>/.explain-project/facts.json
```

Optional: `--focus <subdir>` to restrict to a subtree. This produces `facts.json`:
file inventory, modules (directories), import/dependency edges with evidence,
entrypoints, external dependencies, git signals, and an `extractionReport`.

### Phase 2 — Narrate (grounded)

1. **Read `facts.json` first** — not raw code. Form a structural picture from real data:
   the modules, the edge graph, entrypoints, external deps, the git coupling.
2. **Cluster** modules/files into subsystems. **Decide how many abstraction tiers fit
   THIS repo** and name them. Use the C4 vocabulary (Context → Container → Component →
   Code) as a mental guide, but adapt — a tiny library may need 2 tiers; a large
   monorepo may need 4. Heuristic: tier 0 should have ~3–7 legible nodes a non-author
   can grasp; add a tier whenever a node would otherwise back >~15 files.
3. **Confirm labels with targeted code reading** — READMEs, entrypoint files, one or two
   representative files per cluster. Do NOT read everything.
   - Confirmed by code/docs → `confidence: "high"`, `interpretation: false`.
   - Inferred from names/structure only → `confidence: "medium"|"low"`,
     `interpretation: true`, and say so in the `description`.
4. **Write `narrative.json`** (schema: `schema/narrative.schema.json`) referencing facts
   IDs:
   - Every node's `factRefs` must reference ≥1 real `moduleIds`/`fileIds` from
     `facts.json` — UNLESS it is explicitly `interpretation: true` + `confidence: "low"`
     with a written justification in `description`.
   - Every relationship's `factEdgeIds` must reference real `edges[].id` from
     `facts.json`.
   - `basedOnFactsCommit` must equal `facts.repo.headCommit`.
   - Put genuine unknowns in `openQuestions` rather than guessing.

### Phase 3 — Render

```
python scripts/build_report.py --facts <repo>/.explain-project/facts.json \
  --narrative <repo>/.explain-project/narrative.json \
  --out <repo>/.explain-project/report.html
```

Produces the self-contained interactive report (Cytoscape drill-down, side panel with
provenance + confidence badge, verified-only toggle, coverage banner, legend).

### Phase 4 — Verify (gate)

```
python scripts/verify.py --facts <repo>/.explain-project/facts.json \
  --narrative <repo>/.explain-project/narrative.json \
  --repo <repo>
```

If it reports **FAIL** (orphan references, missing files, empty grounding), **fix
`narrative.json` and re-render before presenting.** Do not show a report that fails the
gate. A `commit-match` warning means the narrative is stale vs. the facts — re-extract.

For large or high-stakes repos, additionally spawn a fresh subagent to spot-check a
sample of nodes against the actual files and flag any label the code doesn't support.

## Presenting

Once the gate passes, present `report.html` and summarize: the tiers you chose and why,
overall confidence/coverage (from `verify.report.json` and the coverage banner), the
external dependencies, and any `openQuestions`. Point out that the **verified-only
toggle** shows the deterministically-grounded structure with all interpretation hidden.

## Anti-patterns (stop and fix)

- Writing `facts.json` yourself, or editing it to fit a story → never. It is extracted.
- A node with no `factRefs` and not flagged as low-confidence interpretation → the gate
  fails; fix the narrative, don't weaken the gate.
- Inventing relationships not backed by `edges` → not allowed. If two subsystems clearly
  relate but no edge exists, say so in `openQuestions` or mark it `interpretation: true`,
  `confidence: "low"` with justification.
- Reading the whole codebase before narrating → read `facts.json` first; read code only
  to confirm specific labels.
