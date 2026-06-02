"""Git history signals: churn, last-modified, and co-change coupling.

Shells out to the `git` CLI (subprocess) and parses a single `git log` pass.
Robust by design: any failure (no git, not a repo, parse trouble) yields empty
results rather than an exception. Output is deterministically ordered so the
same repo state always produces identical results.
"""
from __future__ import annotations

import pathlib
import subprocess
from itertools import combinations

from contract import FileIndex

# Record separator between commits, field separator between hash/date.
_REC = "\x1e"
_FLD = "\x1f"
# %cI = committer date, strict ISO-8601. One header line per commit, then the
# name-only file list that the commit touched.
_FORMAT = f"{_REC}%H{_FLD}%cI"


def collect(repo_root: pathlib.Path, file_index: FileIndex) -> tuple[dict, dict, list[dict]]:
    """Compute git history signals. See module docstring / contract for shape."""
    try:
        proc = subprocess.run(
            [
                "git",
                "-C",
                str(repo_root),
                "log",
                "--no-renames",
                "--name-only",
                f"--pretty=format:{_FORMAT}",
            ],
            capture_output=True,
            text=True,
        )
    except (OSError, ValueError):
        return {}, {}, []

    if proc.returncode != 0 or not proc.stdout.strip():
        return {}, {}, []

    churn_by_id: dict[str, int] = {}
    last_modified_by_id: dict[str, str] = {}
    pair_counts: dict[tuple[str, str], int] = {}

    # Commits arrive newest-first; the first time we see a file is its latest touch.
    for block in proc.stdout.split(_REC):
        block = block.strip("\n")
        if not block:
            continue
        header, _, body = block.partition("\n")
        if _FLD not in header:
            continue
        _commit_hash, date = header.split(_FLD, 1)

        ids_in_commit = []
        for raw in body.splitlines():
            path = raw.strip()
            if not path:
                continue
            fid = file_index.id_for_path(path)
            if fid is None:
                continue
            churn_by_id[fid] = churn_by_id.get(fid, 0) + 1
            # Newest commit seen first -> only set last-modified once.
            last_modified_by_id.setdefault(fid, date)
            ids_in_commit.append(fid)

        # Co-change pairs within this commit (dedupe ids first).
        unique_ids = sorted(set(ids_in_commit))
        for a, b in combinations(unique_ids, 2):
            pair_counts[(a, b)] = pair_counts.get((a, b), 0) + 1

    coupling = [
        {"a": a, "b": b, "coChangeCount": count}
        for (a, b), count in pair_counts.items()
        if count >= 2
    ]
    coupling.sort(key=lambda e: (e["a"], e["b"]))

    return churn_by_id, last_modified_by_id, coupling
