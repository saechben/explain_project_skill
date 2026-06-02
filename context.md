# Project Context — Codebase Visualizer Plugin

> Working notes for the agent. Captures what we're building, why, and the decisions
> made during the kickoff interview (2026-06-02). Read this first in any future session.

## Goal

Build a **Claude plugin** that visualizes *any* codebase across multiple levels of
abstraction, so a reader can understand a system from a high-level architect's
bird's-eye view all the way down to file/function detail — with **click-through
drill-down** between levels. The single most important requirement: the
visualization must be **grounded in the actual code, never hallucinated.**

## The core problem we're solving

Codebase comprehension is slow and the usual aids fail in opposite ways:
hand-drawn architecture diagrams drift out of date and lie, while raw
auto-generated dependency graphs are accurate but unreadable (hairballs). LLM
"explain this repo" summaries are readable but routinely invent components,
relationships, and intent that aren't in the code. We want the readability of a
curated diagram with the trustworthiness of static analysis.

## Audience

Anyone trying to understand an unfamiliar (or large) codebase: a new engineer
onboarding, an architect reviewing a system, a tech lead explaining it to
stakeholders. The plugin should adapt its top abstraction level to be legible to
a non-author, while still letting a developer drill into real code.

## Success looks like

Point the plugin at a repo and get an interactive visualization where:
- the top level shows the system's major subsystems with clear, sensible abstractions;
- every box/edge traces back to real files/dependencies (verifiable);
- clicking a high-level component drills into its lower-level detail, eventually
  down to actual files;
- interpreted/narrative content is visibly distinguished from extracted fact, with
  confidence flags on low-confidence inferences;
- it works on a codebase in a language we didn't special-case.

## Key decisions (from the interview)

1. **Grounding = hybrid.** Deterministic static analysis produces the *structural
   skeleton* (file tree, dependency manifests, import/require graph, entrypoints,
   git signals). Claude adds the *narrative* (what subsystems are, what they do,
   sensible abstractions) **on top of** that skeleton. Verified facts and Claude's
   interpretation must be clearly separated; low-confidence inferences are flagged.
   Every node/edge should trace to a real artifact.

2. **Output = interactive HTML with drill-down.** Format was left to our judgment,
   but the explicit requirement to "click into a component from a high-level view to
   get the low-level view" makes an interactive, self-contained HTML report the
   right primary artifact. Nodes link to the real files that back them. (We may also
   emit a durable, diffable source-of-truth file — e.g. a structured facts JSON
   and/or Mermaid — that the HTML renders from. TBD during design.)

3. **Scope = language-agnostic, any repo.** Must work on any codebase. Rely on
   universal signals (file tree, git history, dependency manifests, import
   statements parsed generically) plus Claude's reading. Deeper per-language tooling
   can be a later enhancement, not a v1 requirement.

4. **Views = agent decides per-repo.** Do NOT hardcode a fixed "business / dev /
   architecture" triad. Instead the skill assesses each codebase and picks the most
   fitting abstraction levels and labels for *that* repo. The original three-view
   idea is reframed as a **continuum of zoom levels** (high-level abstractions →
   components/services/data flow → files/modules/functions), chosen adaptively.
   - Note: "business view" was deemed the wrong term. The top level is closer to a
     **system architect's high-level view** with clear abstractions, assessed by the
     agent — not a marketing/product framing.

5. **Packaging = plugin.** Deliver a distributable plugin bundling: the skill
   (instructions), the deterministic analysis scripts, and the HTML render template.
   Installable, versioned, self-contained, shareable.

## Scope

- **In scope:** static-analysis extraction of structure; adaptive multi-level
  visualization; interactive HTML with drill-down to real files; hybrid
  fact/narrative separation with confidence flags; language-agnostic operation;
  plugin packaging.
- **Out of scope (v1):** deep per-language AST/call-graph analysis for every
  ecosystem; live/runtime tracing; editing the target code; hosting a server.
- **Maybe later:** language-aware analyzers for top stacks; pulling external context
  from connected tools (Notion/Linear/GitHub issues) to enrich the narrative;
  diffing visualizations across commits.

## Anti-hallucination principles (non-negotiable)

- Deterministic tools, not the LLM, decide *what exists* (files, deps, edges).
- The LLM may *group, label, and explain* — but only over the extracted skeleton.
- Each visual element carries provenance (which file(s)/manifest entry it came from).
- Interpretation is labeled as interpretation; uncertainty is shown, not hidden.

## Open questions (to resolve during design)

- Exact deterministic extractors for "language-agnostic" import graphs (tree-sitter
  vs. regex heuristics vs. existing OSS like dependency-cruiser/madge per-ecosystem).
- Source-of-truth format the HTML renders from (JSON facts? Mermaid? both?).
- How the agent decides the number/labels of abstraction tiers consistently.
- Visualization library for the interactive HTML (e.g. Cytoscape.js, D3, vis.js).

## Suggested next steps

1. Research existing tools/skills/OSS to use as a baseline (see Research section, appended below).
2. Decide the extraction toolchain + source-of-truth format.
3. Prototype the structural extractor on a sample repo, then the HTML renderer.
4. Wrap into a plugin with SKILL.md + scripts + template.

---

# Research — existing tools & baselines (2026-06-02)

## Headline finding

The exact approach we landed on (deterministic static analysis + LLM narrative,
layered diagrams with drill-down) **already exists and is proven** in an OSS project:
**CodeBoarding**. No equivalent exists as a Claude *plugin/skill* (the plugin
registry only surfaced generic diagramming — Miro, Figma — nothing that maps a
codebase). So: novel in the Claude ecosystem, but we have an excellent reference
implementation to learn from and partially reuse.

## Closest baseline: CodeBoarding (MIT, ~2.1k stars)

https://github.com/CodeBoarding/CodeBoarding · https://codeboarding.org

What it is: "combines static analysis with LLM reasoning to generate architecture
diagrams, component-level documentation, and navigable outputs." This is essentially
our hybrid spec, already built.

Why it's the strongest reference for us:
- **Hybrid grounding, same philosophy** — a `static_analyzer` (built on Language
  Server Protocol / language servers) feeds an `LLM_Agent_Core`; the agent organizes
  the codebase into conceptual modules/abstractions but works *over* extracted facts.
  Vision statement: "a visual, accurate, high-level representation … that both humans
  and agents can use." Directly aligned with our anti-hallucination stance.
- **Layered, drill-down output** — emits high-level system diagrams plus deeper
  per-subsystem component diagrams; `--depth-level` controls depth; components have
  stable IDs (e.g. `1.2`) you can re-analyze individually.
- **Drill-down mechanism = Mermaid `click` directives** — each node has
  `click NodeName href "…/Component.md"`, linking a high-level box to its detailed
  doc. This is the simple, robust pattern for our "click a component → go deeper."
- **Language-agnostic-ish** — supports Python, TS, JS, Java, Go, PHP, Rust, C# via
  language servers (LSP), not bespoke parsers per language. Good model for breadth.
- **Multiple delivery surfaces** — CLI, VS Code extension, GitHub Action; outputs
  Mermaid + Markdown into `.codeboarding/`. It is itself agent-friendly (ships
  `CLAUDE.md` / `AGENTS.md` / `llms.txt`).
- **Pragmatics we can lift**: caching + incremental re-analysis (`incremental`,
  `partial --component-id`), and a `diagram_analysis` / `output_generators` split.

Gaps vs. our goal (where we'd differ / add value):
- It's a heavyweight Python app needing language-server binaries + an LLM API key; our
  deliverable is a lightweight Claude **plugin** where Claude *is* the LLM, so we can
  skip the external API and most of the orchestration plumbing.
- Output is Mermaid-in-Markdown (GitHub-native) rather than a single interactive
  **HTML** report with smooth pan/zoom and in-page drill-down — that's our differentiator.
- We want the agent to **choose abstraction tiers per repo**; CodeBoarding uses a
  fixed depth-level knob.

## Other tools & reusable pieces

Architecture-from-code generators (LLM-based, simpler than CodeBoarding):
- **Swark** (VS Code ext) — repo → Mermaid architecture diagrams via LLM. Good for
  fast onboarding diagrams; less rigorous grounding.
- **C4InterFlow** — "Architecture as Code"; generates many C4 diagrams from a model;
  .NET-focused static extraction.
- **Eraserbot** — AI agent that generates & auto-updates diagrams from a codebase.

The C4 model + Structurizr (the established *conceptual* framework for leveled views):
- **C4 model** (Context → Container → Component → Code) is the canonical way to express
  exactly our "zoom levels," and a vocabulary worth adopting for our adaptive tiers.
- **Structurizr** = "models as code" / DSL; people, systems, containers defined
  manually, **components extracted automatically via static analysis** (Java
  `ComponentFinder`). Recent write-ups show Claude Code generating Structurizr DSL from
  a codebase → diagrams. Structurizr DSL is a candidate source-of-truth format, but may
  be heavier than we need vs. a plain JSON facts file.

Deterministic structural extractors (the "skeleton" layer, per-ecosystem):
- **dependency-cruiser** (JS/TS) — robust, supports rules, directory boundaries, and a
  **navigable HTML report** with incoming/outgoing deps on hover. Closest to what we
  want for the JS/TS skeleton; worth studying its HTML report.
- **madge** (JS/TS) — easy import graphs (SVG/DOT via Graphviz); graphs get unwieldy on
  big repos.
- **pydeps** (Python), **lakos** (Dart), language-specific equivalents elsewhere.
- Caveat noted across sources: raw dependency graphs become unreadable "hairballs" on
  large repos — reinforces the need for LLM-driven grouping/abstraction on top.

Language-agnostic extraction (key for our "any repo" requirement):
- **tree-sitter** — incremental parser with grammars for ~all languages; "agnostic …
  as long as there is a grammar." Extract imports by walking for `import_statement` /
  `import_declaration` nodes. Basis for several language-agnostic dep-graph efforts.
- **Stack Graphs** (GitHub) + tree-sitter — used in research for language-agnostic
  dependency graphs; powers GitHub's `semantic` across 9 languages / 6M repos.
- **Graph-sitter** — Python lib over tree-sitter building a multi-lingual graph of
  functions/classes/imports/relationships. Candidate dependency for deep extraction.
- Practical lightweight fallback: regex/heuristic import scanning per file extension +
  file tree + dependency manifests (package.json, requirements.txt, go.mod, pom.xml,
  Cargo.toml, etc.) + git signals. Cheap, universal, lower fidelity — good v1 floor.

Interactive HTML rendering libraries (for our drill-down report):
- **Cytoscape.js** — purpose-built interactive graph lib; zoom/pan/drag, click events,
  handles large graphs (thousands of nodes with optimization). Best fit for an
  explorable, drill-downable graph.
- **Mermaid.js** — easy diagram-as-code, supports clickable nodes (`click` → link/tooltip,
  events bound after DOM insert). Great for the diagrams themselves; weaker for dynamic
  add/remove and very large interactive graphs.
- **D3 / vis.js** — more control / alternatives if Cytoscape doesn't fit.
- Likely pattern: Cytoscape.js for the explorable multi-level graph + optional Mermaid
  for fixed sub-diagrams, all in one self-contained HTML file.

## Recommended baseline approach (for plan/design phase)

1. **Borrow CodeBoarding's architecture, not its weight.** Adopt its
   static-analysis→LLM-narrative pipeline and its node-level drill-down idea, but
   implement as a Claude plugin where Claude is the reasoning engine (no external LLM
   API), and target an interactive HTML report instead of Markdown/Mermaid files.
2. **Adopt C4 vocabulary** (Context/Container/Component/Code) as the mental model for
   the adaptive zoom tiers, while letting the agent pick tier count/labels per repo.
3. **Extraction = tiered fallback for "any repo":** generic layer always available
   (file tree + manifests + git + heuristic/tree-sitter import scan → structured JSON
   facts); optionally shell out to best-in-class per-ecosystem tools when present
   (dependency-cruiser for JS/TS, pydeps for Python, etc.) for higher fidelity.
4. **Source of truth = a structured JSON "facts" file** with provenance per node/edge;
   the HTML renders from it. Keeps verified-fact vs. Claude-narrative cleanly separable
   and makes the no-hallucination guarantee auditable.
5. **Render = single self-contained HTML** using Cytoscape.js for the explorable,
   drill-down graph (nodes link to real files), narrative panels alongside, confidence
   flags on inferred content.
6. **Study before building:** dependency-cruiser's HTML report (UX), CodeBoarding's
   `static_analyzer` + `output_generators` (structure), and Mermaid/Cytoscape click APIs.

## Source links

- CodeBoarding — https://github.com/CodeBoarding/CodeBoarding · https://codeboarding.org/diagrams
- Swark — https://github.com/swark-io/swark
- C4InterFlow — https://github.com/SlavaVedernikov/C4InterFlow
- C4 model / Structurizr — https://structurizr.com/ · https://www.workingsoftware.dev/ai-assisted-software-architecture-generating-the-c4-model-and-views-directly-from-code/
- dependency-cruiser — https://github.com/sverweij/dependency-cruiser
- madge — https://www.npmjs.com/package/madge
- tree-sitter — https://github.com/tree-sitter/tree-sitter · Graph-sitter — https://graph-sitter.com/
- Cytoscape.js — https://js.cytoscape.org/ · Mermaid — https://mermaid.js.org/
