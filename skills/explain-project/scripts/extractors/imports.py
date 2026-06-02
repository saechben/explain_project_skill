"""Import-graph combiner — the primary entry point.

Strategy: prefer tree-sitter edges for every file it could parse; cover the
remaining files (no grammar / parse skipped) with the heuristic extractor. Merge,
dedupe on (from, line, raw), then assign final deterministic edge IDs.
"""
from __future__ import annotations

from contract import FileIndex, edge_id

from extractors import imports_heuristic, imports_treesitter


def _sig(edge: dict) -> tuple:
    return (edge["from"], edge["evidence"]["line"], edge["evidence"]["raw"])


def collect(repo_root, file_index: FileIndex) -> list[dict]:
    ts_edges = imports_treesitter.collect(repo_root, file_index)
    heur_edges = imports_heuristic.collect(repo_root, file_index)

    # Files tree-sitter handled (by their evidence file path). For those, the
    # heuristic result is redundant and must not duplicate edges.
    ts_files = {e["evidence"]["file"] for e in ts_edges}

    merged: list[dict] = list(ts_edges)
    seen = {_sig(e) for e in ts_edges}

    for e in heur_edges:
        if e["evidence"]["file"] in ts_files:
            # tree-sitter owns this file; skip heuristic duplicates entirely.
            continue
        sig = _sig(e)
        if sig in seen:
            continue
        seen.add(sig)
        merged.append(e)

    # Deterministic order, then sequential IDs.
    merged.sort(key=lambda e: (e["evidence"]["file"], e["evidence"]["line"], e["evidence"]["raw"]))
    for i, e in enumerate(merged, start=1):
        e["id"] = edge_id(i)
    return merged
