"""Inline the source text of files referenced by a narrative, for the report's
read-only code viewer.

Only files referenced by at least one node (across all perspectives) are read, so
the inlined payload stays proportional to what the narrative actually surfaces.
Per-file and total byte caps keep the report bounded on large repos; over-cap
files are truncated or dropped and flagged so the viewer can say so honestly.
"""
from __future__ import annotations

import pathlib


def _referenced_file_ids(narrative: dict) -> set:
    """Collect every fileId referenced by any node, in v1 or v2 narratives."""
    if narrative.get("perspectives") is not None:
        node_groups = [p.get("nodes", []) or [] for p in (narrative.get("perspectives") or [])]
    else:
        node_groups = [narrative.get("nodes", []) or []]
    refs: set = set()
    for nodes in node_groups:
        for node in nodes:
            fr = node.get("factRefs", {}) or {}
            refs.update(fr.get("fileIds", []) or [])
    return refs


def collect(
    facts: dict,
    narrative: dict,
    repo_root,
    *,
    per_file_cap: int = 200_000,
    total_cap: int = 5_000_000,
) -> dict:
    """Return {fileId: {path, lang, content, truncated[, missing, dropped]}}.

    - Only files referenced by the narrative are included.
    - A file larger than ``per_file_cap`` (in bytes of its text) is truncated and
      flagged ``truncated: True``.
    - Once the cumulative content reaches ``total_cap``, further files are recorded
      with ``dropped: True`` and no content rather than read in full.
    - A referenced file missing from disk is recorded with ``missing: True``.
    """
    repo_root = pathlib.Path(repo_root)
    referenced = _referenced_file_ids(narrative)
    meta_by_id = {f.get("id"): f for f in (facts.get("files", []) or [])}

    out: dict = {}
    total = 0
    # Deterministic order so total-cap drops are stable across runs.
    for fid in sorted(referenced):
        meta = meta_by_id.get(fid)
        if not meta:
            continue  # unknown id; verify.py flags this as a referential error
        path = meta.get("path")
        lang = meta.get("lang", "unknown")
        disk = repo_root / path
        try:
            text = disk.read_text(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            out[fid] = {"path": path, "lang": lang, "missing": True,
                        "content": "", "truncated": False}
            continue

        truncated = False
        encoded = text.encode("utf-8")
        if len(encoded) > per_file_cap:
            text = encoded[:per_file_cap].decode("utf-8", errors="ignore")
            truncated = True
            encoded = text.encode("utf-8")

        # Drop once the cumulative budget would be exceeded — but always admit the
        # first file so the viewer is never empty when something was referenced.
        if total > 0 and total + len(encoded) > total_cap:
            out[fid] = {"path": path, "lang": lang, "dropped": True,
                        "content": "", "truncated": False}
            continue

        out[fid] = {"path": path, "lang": lang, "content": text, "truncated": truncated}
        total += len(encoded)

    return out
