# Scope: src-layout / package-root import resolution

**Goal:** resolve absolute first-party Python imports that cross a package boundary
(e.g. `from roadrisk.config import settings` in `demo/`, `pipelines/`, `tests/`),
which today stay `unresolved` because the package lives under `src/`.

**Granularity (agreed):** package/module level only. `from roadrisk.backbone import
load_segments` resolves to `src/roadrisk/backbone/__init__.py` (the module), not to the
file that defines `load_segments`. No symbol-level chasing.

---

## Root cause (confirmed)

`resolve_python(module, level, importing_path, index)` in
`scripts/extractors/imports_heuristic.py` builds, for an **absolute** import (`level==0`):

```
candidates = ["/".join(parts) + ".py", "/".join(parts) + "/__init__.py"]
```

For `roadrisk.config` that is `roadrisk/config.py` — but the file is at
`src/roadrisk/config.py`, so `index.id_for_path()` misses → `to: null`.

Why the *internal* graph is already complete: intra-package imports are **relative**
(`from ..config import settings`, `level==2`), and the relative branch anchors to the
importing file's real path (which includes `src/`). Only **absolute cross-boundary**
imports fail. On the hackathon repo that is exactly **14 edges** (5 pipeline→subsystem,
plus demo/tests/scripts); the other 89 unresolved are genuine stdlib/third-party and
must stay unresolved.

Ground truth is even spelled out in the repo's `pyproject.toml`:
```
[tool.setuptools]
package-dir = {"roadrisk" = "src/roadrisk", "pipelines" = "pipelines"}
```

---

## Design

### 1. Build a package-root map (once, in the combiner)

`imports.collect()` is the single place both extractors are invoked — compute the map
there and thread it down.

```
build_package_roots(file_index) -> dict[str, list[str]]
# top-level package name -> sorted list of source-dir prefixes
# e.g. {"roadrisk": ["src"], "pipelines": [""]}
```

**Primary mechanism — filesystem detection (zero-config, language-general):**
a top-level package is a directory containing `__init__.py` whose **parent** does *not*
contain `__init__.py`. Map `pkgname -> parent_dir_prefix` (repo root → `""`). This alone
fixes the hackathon repo: `src/roadrisk/__init__.py` → `roadrisk` rooted at `src`;
`pipelines/__init__.py` → `pipelines` rooted at `""`.

**Optional precision augment — `pyproject.toml`:** parse `[tool.setuptools] package-dir`
and `[tool.setuptools.packages.find] where`. Only needed for PEP-420 namespace packages
(no `__init__.py`, which filesystem detection can't see) or renamed dist mappings. Reuse
the `tomllib` pattern already in `manifests.py`. **Recommend deferring** unless a target
repo needs it — filesystem detection covers the common case.

### 2. Extend the resolver

```
resolve_python(module, level, importing_path, index, package_roots=None)
```
After the existing `level==0` candidates miss, if `parts[0]` is a known package and
`package_roots` is provided, retry with each prefix prepended (sorted, first hit wins):
```
for prefix in package_roots[parts[0]]:
    base = f"{prefix}/{'/'.join(parts)}".lstrip("/")
    try base + ".py", base + "/__init__.py"
```
Relative-import branch untouched. `package_roots=None` → today's exact behavior.

### 3. Thread the map through

`imports.collect()` → `imports_treesitter.collect()` / `imports_heuristic.collect()` →
the per-file walkers → `resolve_python(...)`. One extra parameter at each hop.

---

## Why it's safe

- **Cannot fabricate edges.** A candidate only resolves if `index.id_for_path()` finds a
  real file. Worst case of a mis-detected root is *no* match, not a false one.
- **Edge IDs stay stable.** IDs are assigned after sorting by `(file, line, raw)`;
  resolution flips `to`/`resolution` only, never the sort key. Re-running yields the same
  IDs, just some `unresolved → resolved`.
- **Anti-hallucination gate unaffected.** More *grounded* edges = less reliance on the
  interpretation escape hatch; `verify.py` logic is untouched.

## Scope guardrails (explicitly out)

- No symbol-level resolution (module granularity only).
- No PEP-420 namespace packages in the filesystem path (pyproject augment if ever needed).
- No stdlib/third-party resolution — those stay correctly unresolved.
- No `sys.path` emulation — rooting by package name makes the `demo/app.py` runtime hack
  irrelevant.
- Ambiguous same-dotted-module under two roots: deterministic (sorted prefix, first wins);
  note as a known limitation.

## Test plan (TDD, matches project discipline)

`build_package_roots`: src layout, flat layout, multiple packages, none.
`resolve_python`:
- `roadrisk.config` + root `src` → `src/roadrisk/config.py` (high-value case)
- `roadrisk.backbone` → `src/roadrisk/backbone/__init__.py`
- flat layout (`pkg.mod` at repo root, prefix `""`) still resolves — no double-prefix
- `numpy` → `None` (third-party stays unresolved)
- relative imports unchanged (regression)
End-to-end: a src-layout fixture; assert the cross-boundary edges resolve, first-party
unresolved drops to 0, external count unchanged; existing `py_app` fixture facts unchanged.

## Expected impact (hackathon repo)

14 first-party edges `unresolved → resolved`. The 5 `pipelines/pNN → roadrisk.<subsystem>`
edges become real `edges[].id`s, so the **Functional/pipeline lens links promote from
`interpretation: true` (empty `factEdgeIds`) to import-grounded `high` confidence**, and
the **Demo node** gains its `demo → core` edge. 89 external edges stay unresolved (correct).

## Effort / risk

~1 new function (~25 LOC) + one extended signature threaded through 3 files + tests.
~half a day with TDD. Risk low — confined to resolution; no change to schema, ordering,
or ID assignment.
