"""File-tree extractor: inventory repo files and directory-modules.

Walks ``repo_root``, honours ``.gitignore`` via the ``pathspec`` library, and always
skips a fixed set of noise directories. Produces deterministic FileRecord / ModuleRecord
lists: files are sorted by repo-relative POSIX path and numbered f0001.., directory
modules are sorted by path and numbered m001...
"""
from __future__ import annotations

import pathlib
from typing import Optional

import pathspec

from contract import FileRecord, ModuleRecord, detect_lang, file_id, module_id

# Directories skipped no matter what .gitignore says.
ALWAYS_SKIP = {
    ".git",
    ".venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    "dist",
    "build",
    ".explain-project",
}


def _load_gitignore(repo_root: pathlib.Path) -> Optional[pathspec.PathSpec]:
    gi = repo_root / ".gitignore"
    if not gi.is_file():
        return None
    lines = gi.read_text(encoding="utf-8", errors="replace").splitlines()
    return pathspec.PathSpec.from_lines("gitignore", lines)


def _loc(data: bytes) -> int:
    return data.count(b"\n")


def collect(
    repo_root: pathlib.Path,
    extra_skip: list[str] | None = None,
) -> tuple[list[FileRecord], list[ModuleRecord]]:
    """Inventory the repo's files and directory-modules. See module docstring."""
    repo_root = pathlib.Path(repo_root)
    skip = ALWAYS_SKIP | set(extra_skip or [])
    spec = _load_gitignore(repo_root)

    rel_paths: list[str] = []
    for entry in sorted(repo_root.rglob("*")):
        if not entry.is_file() or entry.is_symlink():
            continue
        rel = entry.relative_to(repo_root)
        parts = rel.parts
        if any(part in skip for part in parts):
            continue
        rel_posix = rel.as_posix()
        if spec is not None and spec.match_file(rel_posix):
            continue
        rel_paths.append(rel_posix)

    rel_paths.sort()

    files: list[FileRecord] = []
    for i, rel_posix in enumerate(rel_paths, start=1):
        data = (repo_root / rel_posix).read_bytes()
        files.append(
            FileRecord(
                id=file_id(i),
                path=rel_posix,
                lang=detect_lang(rel_posix),
                loc=_loc(data),
                sizeBytes=len(data),
            )
        )

    # Group files by their direct parent directory ('' -> '.').
    dir_to_ids: dict[str, list[str]] = {}
    for rec in files:
        parent = rec.path.rsplit("/", 1)[0] if "/" in rec.path else "."
        dir_to_ids.setdefault(parent, []).append(rec.id)

    modules: list[ModuleRecord] = []
    for i, dir_path in enumerate(sorted(dir_to_ids), start=1):
        modules.append(
            ModuleRecord(
                id=module_id(i),
                path=dir_path,
                fileIds=sorted(dir_to_ids[dir_path]),
            )
        )

    return files, modules
