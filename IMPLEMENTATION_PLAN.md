# Implementation Plan — Codebase Visualizer Plugin ("explain-project")

> Build-ready spec for handoff to Claude Code. Read `context.md` first for the
> rationale and research behind these decisions; this document is the *how*.
> Audience: a coding agent implementing the plugin end to end.

## 0. One-paragraph summary

Build a Claude Code **plugin** that turns any repository into an **interactive,
multi-level HTML map** a reader can drill down through — from a system-architect's
bird's-eye view down to individual files. The hard requirement is **no hallucinated
structure**: deterministic scripts extract the real skeleton (files, dependencies,
imports, entrypoints, git signals) into a provenance-tagged `facts.json`; Claude then
groups and labels that skeleton into adaptive abstraction tiers, writing a
`narrative.json` in which **every node and edge references real facts**. A renderer
merges the two into a self-contained `report.html`. A verification gate fails the run
if the narrative references anything that doesn't exist in the facts.

## 1. Core design principles (do not violate)

1. **Deterministic tools decide what exists.** Files, imports, dependency edges,
   entrypoints come only from static analysis — never from the model's memory.
2. **The model may group, label, and explain — only over extracted facts.** Claude
   adds abstraction and narrative on top of `facts.json`; it must not invent nodes,
   edges, or components with no factual referent.
3. **Provenance everywhere.** Every visual element traces to a file/line/manifest
   entry. Every narrative node carries `factRefs`; every relationship carries
   `factEdgeIds`.
4. **Interpretation is labeled.** Each narrative element has a `confidence`
   (`high|medium|low`) and an `interpretation` flag. Low-confidence content is visibly
   marked in the UI and can be toggled off to show "verified structure only."
5. **Adaptive, not fixed tiers.** The agent assesses each repo and chooses the number
   and labels of abstraction levels (guided by C4 vocabulary), rather than forcing a
   business/dev/architecture triad.
6. **Language-agnostic floor, deep where possible.** A universal extraction path must
   work on any repo; per-ecosystem tools are optional fidelity boosts, never required.
7. **Single self-contained HTML output.** No server, no build step, no external state.
   Data inlined; CDN libs with graceful behavior if offline.

## 2. Deliverable & plugin structure

A distributable Claude Code plugin. Proposed layout:

```
explain-project/
├── .claude-plugin/
│   └── plugin.json                 # manifest: name, version, description, author
├── skills/
│   └── explain-project/
│       ├── SKILL.md                # the workflow Claude follows (see §4)
│       ├── scripts/
│       │   ├── extract.py          # orchestrator → writes facts.json
│       │   ├── extractors/
│       │   │   ├── filetree.py     # inventory: paths, lang, LOC, size
│       │   │   ├── manifests.py    # parse dependency manifests + entrypoints
│       │   │   ├── git_signals.py  # churn, recency, co-change coupling
│       │   │   ├── imports_treesitter.py   # generic import edges via tree-sitter
│       │   │   ├── imports_heuristic.py    # regex fallback when no grammar
│       │   │   └── ecosystem/      # OPTIONAL higher-fidelity adapters
│       │   │       ├── js_dependency_cruiser.py
│       │   │       └── python_pydeps.py
│       │   ├── build_report.py     # facts.json + narrative.json → report.html
│       │   └── verify.py           # anti-hallucination gate (see §7)
│       ├── schema/
│       │   ├── facts.schema.json
│       │   └── narrative.schema.json
│       └── templates/
│           └── report.html.tmpl    # Cytoscape.js single-file template
├── tests/
│   └── fixtures/                   # sample repos + golden snapshots (see §8)
└── README.md
```

Notes for the implementer:
- `plugin.json` follows the Claude Code plugin manifest format; the skill is discovered
  under `skills/<name>/SKILL.md`. Keep the skill `description` trigger-rich
  ("visualize/understand/explain/map a codebase or repo, architecture diagram,
  drill-down code map").
- Scripts target **Python 3.10+** and must run with **no network access** for the core
  path. Keep third-party deps minimal and vendored/declared (see §6).
- Scripts must be runnable standalone (`python extract.py <repo> --out facts.json`) so
  they're testable without the agent, and so Claude Code can iterate on them directly.

## 3. Data contracts (the heart of the design)

Two JSON files are the source of truth; the HTML is a pure projection of them.

### 3.1 `facts.json` (produced deterministically; never written by the model)

```jsonc
{
  "schemaVersion": "1.0",
  "repo": { "root": "abs/or/rel/path", "headCommit": "sha", "branch": "main",
            "generatedAt": "ISO-8601", "totalFiles": 0, "totalLoc": 0 },
  "files": [
    { "id": "f0001", "path": "src/auth/login.ts", "lang": "typescript",
      "loc": 124, "sizeBytes": 4096, "churn": 17, "lastModified": "ISO-8601" }
  ],
  "modules": [                       // candidate modules = directories (and packages)
    { "id": "m001", "path": "src/auth", "fileIds": ["f0001","f0002"] }
  ],
  "edges": [                         // internal import/dependency edges
    { "id": "e0001", "type": "import", "from": "f0001", "to": "f0002",
      "evidence": { "file": "src/auth/login.ts", "line": 3,
                    "raw": "import { hash } from './crypto'" },
      "resolution": "resolved|unresolved", "extractor": "treesitter|heuristic|dependency-cruiser" }
  ],
  "entrypoints": [
    { "fileId": "f0001", "kind": "cli|web|service|lib|test",
      "evidence": "package.json#scripts.start | __main__ | route decorator" }
  ],
  "externalDependencies": [
    { "name": "react", "version": "18.2.0", "ecosystem": "npm",
      "manifest": "package.json", "usedByFileIds": ["f0010"] }
  ],
  "gitCoupling": [                   // files/modules that frequently change together
    { "a": "m001", "b": "m004", "coChangeCount": 12 }
  ],
  "extractionReport": {              // transparency about coverage/limits
    "languagesDetected": ["typescript","python"],
    "importEdgesResolved": 410, "importEdgesUnresolved": 38,
    "ecosystemToolsUsed": ["dependency-cruiser"],
    "skipped": ["vendor/","node_modules/"], "warnings": [] }
}
```

Rules: every `edge` MUST carry `evidence` (file + line + raw text). IDs are stable and
content-addressable enough to diff across runs. Nothing in this file is the model's
opinion.

### 3.2 `narrative.json` (produced by Claude, validated against facts)

```jsonc
{
  "schemaVersion": "1.0",
  "basedOnFactsCommit": "sha",       // must match facts.json repo.headCommit
  "tiers": [                          // adaptive; agent chooses count + labels
    { "level": 0, "name": "System Overview" },
    { "level": 1, "name": "Subsystems" },
    { "level": 2, "name": "Modules" }
  ],
  "nodes": [
    { "id": "n01", "tier": 0, "label": "Authentication",
      "description": "Handles login, sessions, and token issuance.",
      "factRefs": { "moduleIds": ["m001"], "fileIds": ["f0001","f0002"] }, // MUST be non-empty
      "children": ["n05","n06"],
      "confidence": "high",          // high = directly grounded; medium/low = inferred
      "interpretation": false },     // true when the label/role is inferred, not stated in code/docs
    { "id": "n02", "tier": 0, "label": "Billing",
      "description": "Inferred from module names; no README confirmation.",
      "factRefs": { "moduleIds": ["m004"], "fileIds": [] },
      "children": [], "confidence": "low", "interpretation": true }
  ],
  "relationships": [
    { "from": "n01", "to": "n02", "label": "issues tokens used by",
      "factEdgeIds": ["e0001","e0044"], "confidence": "medium" } // MUST reference real edges
  ],
  "openQuestions": [ "Is `legacy/` still in use? No recent churn but imported by f0210." ]
}
```

Rules: `factRefs` for every node must reference ≥1 real `module`/`file` ID from
`facts.json`. Every relationship's `factEdgeIds` must reference real edges (or be
explicitly marked `interpretation:true` + `confidence:"low"` with a written
justification in `description`). The verifier (§7) enforces this.

## 4. The workflow (what SKILL.md instructs Claude to do)

Four phases. The skill orchestrates scripts and does the reasoning between them.

**Phase 1 — Extract (deterministic).** Run `extract.py <repo>` to produce `facts.json`.
This does: file-tree inventory (respect `.gitignore`, skip vendored/build dirs); parse
all dependency manifests; build the internal import graph (tree-sitter generic first,
heuristic fallback, optional ecosystem tools when detected); detect entrypoints; compute
git signals (churn, recency, co-change). Claude does **not** hand-write any of this.

**Phase 2 — Narrate (Claude, grounded).**
1. Read `facts.json` first (not raw code). Form a structural picture from real data.
2. Cluster modules/files into subsystems; decide how many abstraction tiers fit *this*
   repo and name them (use C4 Context/Container/Component/Code as a mental guide, but
   adapt). Build the node tree.
3. Do **targeted** code reading to confirm labels: READMEs, entrypoints, a few
   representative files per cluster. Confirmed → `confidence:"high"`,
   `interpretation:false`. Inferred-from-names-only → `low/medium` +
   `interpretation:true`.
4. Write `narrative.json` referencing facts IDs. Put genuine unknowns in
   `openQuestions` rather than guessing.

**Phase 3 — Render.** Run `build_report.py --facts facts.json --narrative narrative.json
--out report.html`. Produces the self-contained interactive report (§5).

**Phase 4 — Verify (gate).** Run `verify.py` (§7). If it reports orphan references or
missing files, Claude must fix `narrative.json` and re-render before presenting. Then
Claude presents `report.html` to the user and summarizes confidence/coverage and any
open questions.

Inputs the skill accepts: target repo path (default: current/selected folder), optional
`--focus <subdir>`, optional max tier hint. Outputs land in `<repo>/.explain-project/`
(`facts.json`, `narrative.json`, `report.html`), analogous to CodeBoarding's
`.codeboarding/`.

## 5. The interactive report (`report.html`)

Single self-contained file. Recommended: **Cytoscape.js** for the explorable graph
(zoom/pan/drag, click events, scales to large graphs), data inlined as JSON.

Required behaviors:
- **Drill-down:** top tier shows tier-0 nodes; clicking a node expands/navigates to its
  `children` (next tier); leaf nodes reveal the backing files, each linking to the real
  file (relative path; `file://` link or copy-path). Breadcrumb + back navigation.
- **Side panel:** on select, show label, description, the list of backing files/modules
  (provenance), inbound/outbound relationships, and a **confidence badge**.
- **Verified-only toggle:** hide all `interpretation:true` / low-confidence elements to
  display only deterministically-grounded structure — the visible proof of grounding.
- **Coverage banner:** surface `extractionReport` (languages, % import edges resolved,
  ecosystem tools used, skipped dirs) so the reader knows the map's limits.
- **Legend:** confidence colors, edge types (import vs. inferred), tier indicator.
- Optional: embed Mermaid for any fixed sub-diagram; Cytoscape is primary.

Keep all rendering logic driven by the two JSON blobs so the HTML can never show
something absent from the data.

## 6. Toolchain & dependencies

- **Language:** Python 3.10+ for all scripts.
- **Core libs (declare in plugin):** `tree_sitter` + a bundled grammar pack
  (`tree-sitter-language-pack` or `tree_sitter_languages`); `pathspec` (gitignore);
  stdlib `tomllib`/`json` + `pyyaml` for manifests; `subprocess` for `git`.
- **Manifest parsers to support:** `package.json`, `requirements.txt`/`pyproject.toml`/
  `setup.cfg`, `go.mod`, `pom.xml`/`build.gradle`, `Cargo.toml`, `Gemfile`,
  `composer.json`, `*.csproj`. Extract declared deps, scripts, and declared entrypoints.
- **Optional ecosystem adapters (auto-detected, skip if absent):**
  `dependency-cruiser` via `npx` for JS/TS; `pydeps`/import graph for Python; `go list`
  for Go. Each writes into the same `edges`/`externalDependencies` shape with
  `extractor` set accordingly.
- **Renderer:** Cytoscape.js (CDN `<script>` with a vendored copy fallback). No bundler.

## 7. Anti-hallucination verification (`verify.py`) — required gate

Deterministic checks that must pass before a report is presented:
1. **Referential integrity:** every `narrative.nodes[].factRefs` ID exists in
   `facts.json`; every `relationships[].factEdgeIds` ID exists. Any orphan → FAIL.
2. **No empty grounding:** every node has ≥1 `factRef` OR is explicitly
   `interpretation:true` + `confidence:"low"` with a non-empty `description`. Else FAIL.
3. **File existence:** every file path referenced still exists on disk. Else FAIL.
4. **Commit match:** `narrative.basedOnFactsCommit == facts.repo.headCommit`. Else WARN
   (stale narrative).
5. **Coverage sanity:** report counts (nodes, % files covered by some node, unresolved
   edges) so low coverage is visible, not hidden.

Output a machine-readable `verify.report.json` + human summary. Additionally, instruct
the skill to run a **subagent verification pass** for high-stakes/large repos: a fresh
agent spot-checks a sample of nodes against the actual files and flags any
label/role that the code doesn't support.

## 8. Testing strategy

- **Fixtures (`tests/fixtures/`):** (a) a small JS/TS app, (b) a small Python package,
  (c) a polyglot repo, (d) this repo itself. Keep them tiny but realistic (entrypoints,
  nested modules, a circular import, an unresolved import).
- **Golden snapshots:** assert `extract.py` output is stable (sorted, deterministic IDs)
  per fixture; diff-friendly.
- **Schema validation:** validate `facts.json`/`narrative.json` against the JSON Schemas
  in CI.
- **Verifier tests:** craft a deliberately-bad `narrative.json` (orphan ref, missing
  file, empty grounding) and assert `verify.py` FAILs each case.
- **Render smoke test:** `build_report.py` produces valid HTML; headless check that the
  inlined JSON parses and the graph initializes.
- **Determinism:** running `extract.py` twice on an unchanged repo yields identical
  `facts.json`.

## 9. Build milestones (suggested order for Claude Code)

- **M0 — Scaffold:** plugin dir, `plugin.json`, `SKILL.md` skeleton, schemas stubbed,
  empty scripts with CLIs and `--help`.
- **M1 — Generic extractor:** `filetree.py` + `manifests.py` + `git_signals.py` →
  valid `facts.json` (no edges yet). Schema + validator green on fixtures.
- **M2 — Import graph:** `imports_treesitter.py` (+ `imports_heuristic.py` fallback);
  populate `edges` with evidence, mark resolved/unresolved.
- **M3 — Narrative contract:** finalize `narrative.schema.json`; write the Phase-2
  instructions in `SKILL.md`; produce a sample `narrative.json` for a fixture by hand to
  validate the schema and verifier.
- **M4 — Renderer:** `build_report.py` + `report.html.tmpl` with Cytoscape drill-down,
  side panel, verified-only toggle, coverage banner.
- **M5 — Verifier + tests:** `verify.py` with all §7 checks; the §8 test suite green.
- **M6 — Ecosystem adapters (optional):** `dependency-cruiser`, `pydeps` integration
  behind auto-detection.
- **M7 — Package & docs:** README, end-to-end run on this repo + a fixture, bundle as a
  distributable `.plugin`.

## 10. Definition of done

- Pointed at any of the test fixtures (and at least one real external repo), the plugin
  produces `facts.json`, `narrative.json`, and a working `report.html`.
- `verify.py` passes (no orphan/missing references); the verified-only toggle shows a
  coherent, fully-grounded structure.
- Drill-down works from the top tier down to real files, with provenance and confidence
  visible per node.
- Runs on a language not specially handled (generic path) and clearly reports its
  coverage limits rather than fabricating structure.

## 11. Non-goals (v1)

Runtime/dynamic tracing; editing the target codebase; hosting a live server; deep
call-graph analysis for every language; pulling external context from Notion/Linear/
GitHub issues (noted as a later enhancement in `context.md`).

## 12. Open questions to resolve during implementation

- Final import-resolution strategy per language with tree-sitter (module-path → file
  mapping is the fiddly part; lean on manifests + path conventions, mark unresolved
  honestly).
- Exact heuristic for the agent choosing tier count/labels consistently across repos
  (encode concrete guidance in `SKILL.md`).
- Whether to also emit a Markdown/Mermaid companion (CodeBoarding-style) for
  repo-native/PR viewing, or keep HTML-only for v1.
- Cytoscape layout choice for large graphs (e.g. `fcose`/`dagre`) and node-count
  thresholds before collapsing to module level.

## 13. Reference implementations to study (from research)

- **CodeBoarding** (MIT) — closest prior art: static analysis + LLM, layered drill-down
  via Mermaid `click`, `static_analyzer`/`output_generators` split, incremental updates.
  Mine its structure; don't adopt its weight (we skip the external LLM API — Claude is
  the engine).
- **dependency-cruiser** — its navigable HTML report and directory-boundary rendering
  are a good UX reference for the JS/TS skeleton.
- **C4 model / Structurizr** — vocabulary and leveling model for the adaptive tiers.
- **Cytoscape.js / Mermaid** — rendering + clickable-node drill-down mechanics.

(Full links in `context.md` → Research → Source links.)
