"""Parse dependency manifests and detect declared entrypoints.

Supports: package.json (npm), pyproject.toml — both PEP 621 [project] and Poetry
[tool.poetry] tables (pypi) — and requirements.txt (pypi).
Returns (external_dependencies, entrypoints) shaped like facts.schema.json items.
Deterministic: deps sorted by name, entrypoints sorted by fileId.
"""
from __future__ import annotations

import json
import pathlib
import re
import tomllib

from contract import FileIndex

# Strip a PEP 508 / npm version specifier off a dependency token.
_PY_NAME_SPLIT = re.compile(r"[<>=!~;\[\s]")


def _py_name(token: str) -> str:
    """Extract the bare package name from a requirement string like 'requests>=2.0'."""
    return _PY_NAME_SPLIT.split(token.strip(), 1)[0].strip()


def _py_version(token: str) -> str | None:
    """Best-effort version from a requirement string ('flask==2.0' -> '2.0')."""
    m = re.search(r"==\s*([^\s;,]+)", token)
    return m.group(1) if m else None


def _poetry_version(spec) -> str | None:
    """Version from a Poetry dependency spec: a string ('^1.9') or a table ({version: ...})."""
    if isinstance(spec, str):
        return spec or None
    if isinstance(spec, dict):
        v = spec.get("version")
        return v if isinstance(v, str) and v else None
    return None


def _dep(name: str, version: str | None, ecosystem: str, manifest: str) -> dict:
    return {
        "name": name,
        "version": version,
        "ecosystem": ecosystem,
        "manifest": manifest,
        "usedByFileIds": [],
    }


def _resolve_module(module: str, file_index: FileIndex) -> str | None:
    """Map a dotted module path to a real file id, trying <mod>.py and <mod>/__init__.py."""
    base = module.replace(".", "/")
    for cand in (f"{base}.py", f"{base}/__init__.py"):
        fid = file_index.id_for_path(cand)
        if fid is not None:
            return fid
    return None


def _collect_package_json(path: pathlib.Path, manifest: str, file_index: FileIndex):
    deps: list[dict] = []
    entrypoints: list[dict] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return deps, entrypoints

    for section in ("dependencies", "devDependencies"):
        block = data.get(section)
        if isinstance(block, dict):
            for name, version in block.items():
                ver = version if isinstance(version, str) and version else None
                deps.append(_dep(name, ver, "npm", manifest))

    scripts = data.get("scripts") if isinstance(data.get("scripts"), dict) else {}
    start = scripts.get("start") or scripts.get("main")
    if isinstance(start, str):
        fid = _entry_from_node_cmd(start, file_index)
        if fid is not None:
            kind = "web" if re.search(r"serv", start, re.IGNORECASE) else "cli"
            entrypoints.append(
                {"fileId": fid, "kind": kind, "evidence": f"package.json scripts.start: {start}"}
            )

    main = data.get("main")
    if isinstance(main, str):
        fid = file_index.id_for_path(main.lstrip("./"))
        if fid is not None and not any(e["fileId"] == fid for e in entrypoints):
            entrypoints.append(
                {"fileId": fid, "kind": "lib", "evidence": f'package.json main: {main}'}
            )
    return deps, entrypoints


def _entry_from_node_cmd(cmd: str, file_index: FileIndex) -> str | None:
    """From 'node src/index.js' (or similar) resolve the script path to a file id."""
    for tok in cmd.split():
        tok = tok.strip().lstrip("./")
        if tok.endswith((".js", ".mjs", ".cjs", ".ts")):
            fid = file_index.id_for_path(tok)
            if fid is not None:
                return fid
    return None


def _collect_pyproject(path: pathlib.Path, manifest: str, file_index: FileIndex):
    deps: list[dict] = []
    entrypoints: list[dict] = []
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return deps, entrypoints

    seen: set[str] = set()

    # PEP 621 — [project.dependencies] (list of PEP 508 strings).
    project = data.get("project") if isinstance(data.get("project"), dict) else {}
    for token in project.get("dependencies", []) or []:
        if not isinstance(token, str):
            continue
        name = _py_name(token)
        if name and name not in seen:
            seen.add(name)
            deps.append(_dep(name, _py_version(token), "pypi", manifest))

    scripts = project.get("scripts") if isinstance(project.get("scripts"), dict) else {}
    for value in scripts.values():
        if not isinstance(value, str):
            continue
        module = value.split(":", 1)[0].strip()
        fid = _resolve_module(module, file_index)
        if fid is not None:
            entrypoints.append(
                {"fileId": fid, "kind": "cli", "evidence": f"pyproject [project.scripts]: {value}"}
            )

    # Poetry — [tool.poetry.*] (dependency tables keyed by name; specs are str or table).
    tool = data.get("tool") if isinstance(data.get("tool"), dict) else {}
    poetry = tool.get("poetry") if isinstance(tool.get("poetry"), dict) else {}

    dep_tables = [poetry.get("dependencies"), poetry.get("dev-dependencies")]
    groups = poetry.get("group") if isinstance(poetry.get("group"), dict) else {}
    for group in groups.values():
        if isinstance(group, dict):
            dep_tables.append(group.get("dependencies"))
    for table in dep_tables:
        if not isinstance(table, dict):
            continue
        for name, spec in table.items():
            if name == "python":  # interpreter constraint, not a package
                continue
            if name in seen:
                continue
            seen.add(name)
            deps.append(_dep(name, _poetry_version(spec), "pypi", manifest))

    poetry_scripts = poetry.get("scripts") if isinstance(poetry.get("scripts"), dict) else {}
    for value in poetry_scripts.values():
        if not isinstance(value, str):
            continue
        module = value.split(":", 1)[0].strip()
        fid = _resolve_module(module, file_index)
        if fid is not None and not any(e["fileId"] == fid for e in entrypoints):
            entrypoints.append(
                {"fileId": fid, "kind": "cli",
                 "evidence": f"pyproject [tool.poetry.scripts]: {value}"}
            )
    return deps, entrypoints


def _collect_requirements(path: pathlib.Path, manifest: str):
    deps: list[dict] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return deps
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        name = _py_name(line)
        if name:
            deps.append(_dep(name, _py_version(line), "pypi", manifest))
    return deps


def collect(repo_root: pathlib.Path, file_index: FileIndex) -> tuple[list[dict], list[dict]]:
    """Parse dependency manifests + detect declared entrypoints."""
    repo_root = pathlib.Path(repo_root)
    deps: list[dict] = []
    entrypoints: list[dict] = []

    pkg = repo_root / "package.json"
    if pkg.is_file():
        d, e = _collect_package_json(pkg, "package.json", file_index)
        deps.extend(d)
        entrypoints.extend(e)

    pyproject = repo_root / "pyproject.toml"
    if pyproject.is_file():
        d, e = _collect_pyproject(pyproject, "pyproject.toml", file_index)
        deps.extend(d)
        entrypoints.extend(e)

    req = repo_root / "requirements.txt"
    if req.is_file():
        deps.extend(_collect_requirements(req, "requirements.txt"))

    # Deterministic ordering.
    deps.sort(key=lambda d: (d["name"], d["ecosystem"], d["manifest"]))

    seen: set[tuple[str, str]] = set()
    unique_entries: list[dict] = []
    for e in entrypoints:
        key = (e["fileId"], e["kind"])
        if key not in seen:
            seen.add(key)
            unique_entries.append(e)
    unique_entries.sort(key=lambda e: (e["fileId"], e["kind"]))

    return deps, unique_entries
