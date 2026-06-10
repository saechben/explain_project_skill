#!/usr/bin/env python3
"""extract.py — deterministic structural extraction orchestrator.

Runs the per-concern extractors over a repo and assembles a single facts.json that
conforms to schema/facts.schema.json. Nothing here is the model's opinion: every file,
edge, dependency, and entrypoint comes from static analysis or git.

Usage:
    python extract.py <repo> [--out facts.json] [--focus SUBDIR]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow running both as a module (tests import `extract`) and as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from contract import FileIndex  # noqa: E402
from extractors import filetree, manifests, git_signals, imports, webapps  # noqa: E402

SCHEMA_VERSION = "1.0"


def _git(repo_root: Path, *args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True, text=True,
        )
    except OSError:
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip() or None


def _repo_meta(repo_root: Path, total_files: int, total_loc: int, generated_at: str) -> dict:
    return {
        "root": str(repo_root),
        "headCommit": _git(repo_root, "rev-parse", "HEAD"),
        "branch": _git(repo_root, "rev-parse", "--abbrev-ref", "HEAD"),
        "generatedAt": generated_at,
        "totalFiles": total_files,
        "totalLoc": total_loc,
    }


def extract(repo_root: Path, focus: str | None = None, extra_skip: list[str] | None = None) -> dict:
    """Run all extractors and assemble a schema-valid facts dict for `repo_root`."""
    repo_root = Path(repo_root).resolve()

    # Phase 1: inventory (owns file/module IDs).
    files, modules = filetree.collect(repo_root, extra_skip=extra_skip)
    if focus:
        focus_norm = focus.strip("/")
        files = [f for f in files if f.path == focus_norm or f.path.startswith(focus_norm + "/")]
        keep_ids = {f.id for f in files}
        modules = [
            m for m in modules
            if m.path == focus_norm or m.path.startswith(focus_norm + "/") or m.path == "."
        ]
        for m in modules:
            m.fileIds = [fid for fid in m.fileIds if fid in keep_ids]
        modules = [m for m in modules if m.fileIds]

    index = FileIndex(files)

    # Phase 1b: git signals applied onto file records.
    churn_by_id, last_modified_by_id, coupling = git_signals.collect(repo_root, index)
    for f in files:
        if f.id in churn_by_id:
            f.churn = churn_by_id[f.id]
        if f.id in last_modified_by_id:
            f.lastModified = last_modified_by_id[f.id]

    # Phase 1c: manifests + entrypoints. Manifest-declared entrypoints win; web-app
    # objects (uvicorn/gunicorn-launched ASGI/WSGI apps) backfill files not already claimed.
    external_deps, entrypoints = manifests.collect(repo_root, index)
    declared = {e["fileId"] for e in entrypoints}
    entrypoints.extend(e for e in webapps.collect(repo_root, index) if e["fileId"] not in declared)

    # Phase 1d: import graph (sole edge producer; owns edge IDs).
    edges = imports.collect(repo_root, index)

    resolved = sum(1 for e in edges if e["resolution"] == "resolved")
    unresolved = sum(1 for e in edges if e["resolution"] == "unresolved")
    languages = sorted({f.lang for f in files if f.lang != "unknown"})
    generated_at = datetime.now(timezone.utc).isoformat()

    return {
        "schemaVersion": SCHEMA_VERSION,
        "repo": _repo_meta(repo_root, len(files), sum(f.loc for f in files), generated_at),
        "files": [f.to_dict() for f in files],
        "modules": [m.to_dict() for m in modules],
        "edges": edges,
        "entrypoints": entrypoints,
        "externalDependencies": external_deps,
        "gitCoupling": coupling,
        "extractionReport": {
            "languagesDetected": languages,
            "importEdgesResolved": resolved,
            "importEdgesUnresolved": unresolved,
            "ecosystemToolsUsed": [],
            "skipped": sorted(set(filetree.ALWAYS_SKIP) | set(extra_skip or [])),
            "warnings": [],
        },
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Extract a repo's structural facts.json")
    parser.add_argument("repo", help="path to the repository to analyze")
    parser.add_argument("--out", default=None, help="output path (default: <repo>/.explain-project/facts.json)")
    parser.add_argument("--focus", default=None, help="restrict extraction to a subdirectory")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo).resolve()
    facts = extract(repo_root, focus=args.focus)

    out = Path(args.out) if args.out else repo_root / ".explain-project" / "facts.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(facts, indent=2, ensure_ascii=False))
    print(f"Wrote {out} ({facts['repo']['totalFiles']} files, {len(facts['edges'])} edges)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
