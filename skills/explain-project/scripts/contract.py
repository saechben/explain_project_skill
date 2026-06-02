"""Shared data contract for the explain-project extractors.

The orchestrator (extract.py) owns ID assignment and language detection, then hands
extractors a FileIndex so every produced edge/dependency can reference a real file ID.
Extractors return plain dicts shaped like facts.schema.json; this module holds only the
glue that all of them share.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


def file_id(n: int) -> str:
    return f"f{n:04d}"


def module_id(n: int) -> str:
    return f"m{n:03d}"


def edge_id(n: int) -> str:
    return f"e{n:04d}"


# Extension -> language name. Deliberately small and universal; deeper detection is a
# fidelity boost, never required for the generic floor.
_EXT_LANG = {
    ".py": "python",
    ".pyi": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".hpp": "cpp",
    ".swift": "swift",
    ".kt": "kotlin",
    ".scala": "scala",
    ".sh": "shell",
    ".md": "markdown",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".html": "html",
    ".css": "css",
}


def detect_lang(path: str) -> str:
    """Map a file path to a language name by extension; 'unknown' when unrecognized."""
    lower = path.lower()
    dot = lower.rfind(".")
    if dot == -1:
        return "unknown"
    return _EXT_LANG.get(lower[dot:], "unknown")


@dataclass
class FileRecord:
    id: str
    path: str  # repo-relative, posix separators
    lang: str
    loc: int
    sizeBytes: int
    churn: int = 0
    lastModified: Optional[str] = None

    def to_dict(self) -> dict:
        d = {
            "id": self.id,
            "path": self.path,
            "lang": self.lang,
            "loc": self.loc,
            "sizeBytes": self.sizeBytes,
            "churn": self.churn,
        }
        if self.lastModified is not None:
            d["lastModified"] = self.lastModified
        return d


@dataclass
class ModuleRecord:
    id: str
    path: str
    fileIds: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"id": self.id, "path": self.path, "fileIds": list(self.fileIds)}


class FileIndex:
    """Bidirectional lookup between repo-relative paths and file IDs."""

    def __init__(self, records):
        self._records = list(records)
        self._by_path = {r.path: r for r in self._records}
        self._by_id = {r.id: r for r in self._records}

    def id_for_path(self, path: str) -> Optional[str]:
        rec = self._by_path.get(path)
        return rec.id if rec else None

    def record_for_id(self, fid: str) -> Optional[FileRecord]:
        return self._by_id.get(fid)

    @property
    def records(self):
        return list(self._records)

    def paths(self):
        return list(self._by_path.keys())
