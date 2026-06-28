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
`tree-sitter-language-pack`). `requirements.txt` lives at the plugin root (two levels
up from this skill). If imports fail, create an isolated environment from it. Prefer
[`uv`](https://docs.astral.sh/uv/) when it is installed (much faster); otherwise fall
back to the stdlib `venv`. Both create `.venv` in the skill directory:

```bash
# run from this skill directory
REQ=../../requirements.txt
if command -v uv >/dev/null 2>&1; then
  uv venv .venv && uv pip install --python .venv -r "$REQ"
else
  python3 -m venv .venv && .venv/bin/pip install -r "$REQ"
fi
```

Then run **every** script call below with that interpreter, e.g.
`.venv/bin/python scripts/extract.py ...`.

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
2. **Choose 2–4 perspectives (lenses) that fit THIS repo.** The real value is letting a
   reader change *what the map is about*, not just zoom. Pick from this palette only the
   ones the facts can actually support, and name each:
   - **Structural / Code** (`kind: "structural"`) — modules and the import/dependency
     graph. Almost always include this; it is the most grounded lens.
   - **Functional / Capability** (`kind: "functional"`) — group by what the system *does*,
     seeded by entrypoints (each entrypoint roots a capability), call-adjacency via the
     import graph, and git-coupling ("changes together").
   - **Data-flow** (`kind: "dataflow"`) — follow data from entrypoints through modules to
     external deps/IO, using import edges as the flow skeleton.
   - **Runtime / Deployment** (`kind: "runtime"`) — processes/services/CLIs, seeded by
     entrypoint `kind` and manifest scripts.
   - **Domain / Business** (`kind: "domain"`) — domain areas inferred from directory and
     dependency naming. This lens is the *least* grounded; expect mostly interpretation.
   Don't force a lens with no signal (e.g. no Domain lens for a tiny CLI). Skipping a lens
   is better than fabricating one.
3. **Per lens, build the node tree.** Decide how many tiers fit (C4 — Context → Container →
   Component → Code — as a mental guide, adapted). Heuristic: tier 0 should have ~3–7
   legible nodes; add a tier whenever a node would otherwise back >~15 files. Node ids must
   be unique *within* a perspective; relationships connect nodes *within the same* lens.
4. **Confirm labels with targeted code reading** — READMEs, entrypoint files, one or two
   representative files per cluster. Do NOT read everything.
   - Confirmed by code/docs → `confidence: "high"`, `interpretation: false`.
   - Inferred from names/structure only → `confidence: "medium"|"low"`,
     `interpretation: true`, and say so in the `description`.
   - Interpretive lenses (functional/domain) will skew toward `medium`/`low` — that is
     expected and honest. The **Verified-only** toggle hides them, so the Structural lens
     must still stand on its own as a coherent, fully-grounded spine.
5. **Write `narrative.json`** (schema: `schema/narrative.schema.json`), v2 shape:
   ```jsonc
   { "schemaVersion": "2.0", "basedOnFactsCommit": "<facts.repo.headCommit>",
     "perspectives": [ { "id","name","kind","description","tiers","nodes","relationships" } ],
     "businessBrief": { /* optional — see 5b */ },
     "openQuestions": [] }
   ```
   - Every node's `factRefs` must reference ≥1 real `moduleIds`/`fileIds` from
     `facts.json` — UNLESS it is explicitly `interpretation: true` + `confidence: "low"`
     with a written justification in `description`.
   - Every relationship's `factEdgeIds` must reference real `edges[].id`; `from`/`to` must
     be node ids in the same perspective.
   - `basedOnFactsCommit` must equal `facts.repo.headCommit`.
   - Put genuine unknowns in `openQuestions` rather than guessing.

5b. **Write the business brief (optional, grounded).** Add a top-level `businessBrief`
   object — a plain-language brief of *what the project is and what problem it solves*, for
   non-architect readers. The report leads with it as the landing view.
   - **Purpose:** one screen a PM or new hire can read before touching the map. Keep it
     concrete; no marketing fluff.
   - **Source signals:** project name/description are NOT in `facts.json`. Infer `headline`
     from `facts.repo.root` basename + the dominant entrypoint `kind` + the top external
     dependencies. Ground `problem`/`solution`/`audience` claims on real `moduleIds`/`fileIds`
     — e.g. the web/CLI entrypoint file, the core module.
   - **Grounding rules (SAME discipline as nodes, enforced by `verify.py`):**
     - Each of `problem`/`solution`/`audience` and every `capabilities[]` item needs ≥1
       `factRefs` id — UNLESS `interpretation: true` + `confidence: "low"` + written `text`.
     - `techStack[].factRef` must equal a real `externalDependencies[].name`. Infer `role`
       ("web framework", "test runner") freely, but only `name`/`factRef` is grounded.
     - `capabilities[]` should set `perspectiveRef` + `nodeRef` pointing at a real node in
       the **functional** lens so the card can jump into the map.
     - `headline` is the ONE grounding-exempt line — keep it factual and modest; push
       genuine uncertainty into `openQuestions`, not the headline.
   - Keep the **Structural** lens as the grounded spine. Aim for at least one high/medium
     grounded `problem` AND `solution` so the **Verified-only** toggle doesn't blank the brief.
   - Shape:
     ```jsonc
     "businessBrief": {
       "headline": "…",                                  // grounding-exempt, ≥1 char
       "problem":  { "text","factRefs","confidence","interpretation" },   // required
       "solution": { "text","factRefs","confidence","interpretation" },   // required
       "audience": { … },                                // optional briefClaim
       "howItWorks": "…",                                // optional prose
       "capabilities": [ { "label","text","factRefs","confidence","interpretation",
                           "perspectiveRef","nodeRef" } ],
       "techStack": [ { "name","role","factRef" } ]      // factRef == an externalDependencies name
     }
     ```

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

The report now leads with the **Brief** view (the business brief) and offers a **Brief/Map
toggle** — open on the Brief for a plain-language summary, switch to the Map to drill
through the lenses.

## Anti-patterns (stop and fix)

- Writing `facts.json` yourself, or editing it to fit a story → never. It is extracted.
- A node with no `factRefs` and not flagged as low-confidence interpretation → the gate
  fails; fix the narrative, don't weaken the gate.
- Inventing relationships not backed by `edges` → not allowed. If two subsystems clearly
  relate but no edge exists, say so in `openQuestions` or mark it `interpretation: true`,
  `confidence: "low"` with justification.
- Reading the whole codebase before narrating → read `facts.json` first; read code only
  to confirm specific labels.
