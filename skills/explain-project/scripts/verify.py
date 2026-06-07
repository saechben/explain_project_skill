"""Anti-hallucination verification gate for the explain-project plugin.

Validates a model-authored narrative.json against the deterministically
extracted facts.json. Every claim in the narrative must be grounded in the
facts; ungrounded statements are only allowed when explicitly flagged as
low-confidence interpretation.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys


def _perspectives(narrative: dict) -> list[dict]:
    """Normalize a narrative to a list of perspectives.

    v2 narratives carry a ``perspectives`` array. A legacy v1 narrative (root-level
    ``tiers``/``nodes``/``relationships``) is wrapped as a single ``default``
    perspective so every check below runs identically against both shapes.
    """
    if narrative.get("perspectives") is not None:
        return narrative.get("perspectives") or []
    return [{
        "id": "default",
        "name": "Overview",
        "kind": "structural",
        "tiers": narrative.get("tiers", []) or [],
        "nodes": narrative.get("nodes", []) or [],
        "relationships": narrative.get("relationships", []) or [],
    }]


def _verify_business_brief(
    brief: dict,
    *,
    file_ids: set,
    module_ids: set,
    file_path_by_id: dict,
    dep_names: set,
    node_ids_by_pid: dict,
    valid_pids: set,
    repo_root: pathlib.Path | None,
) -> tuple[list[dict], list[dict]]:
    """Validate an optional businessBrief object under node-grade discipline.

    Returns (errors, warnings). Every message is prefixed ``[businessBrief]``.
    The empty-grounding predicate mirrors the node check, keyed on ``text``.
    """
    errors: list[dict] = []
    warnings: list[dict] = []
    P = "[businessBrief]"

    def check_claim(claim: dict, where: str) -> None:
        refs = claim.get("factRefs", {}) or {}
        file_refs = refs.get("fileIds", []) or []
        module_refs = refs.get("moduleIds", []) or []

        # empty-grounding (same predicate as nodes, keyed on text)
        has_refs = bool(file_refs) or bool(module_refs)
        allowed_interpretation = (
            claim.get("interpretation") is True
            and claim.get("confidence") == "low"
            and bool(claim.get("text"))
        )
        if not has_refs and not allowed_interpretation:
            errors.append({
                "check": "empty-grounding",
                "message": f"{P} {where} has no factRefs and is not a low-confidence interpretation",
            })

        # referential-integrity
        for fid in file_refs:
            if fid not in file_ids:
                errors.append({
                    "check": "referential-integrity",
                    "message": f"{P} {where} references unknown fileId {fid!r}",
                })
        for mid in module_refs:
            if mid not in module_ids:
                errors.append({
                    "check": "referential-integrity",
                    "message": f"{P} {where} references unknown moduleId {mid!r}",
                })

        # file-existence (only when repo_root given)
        if repo_root is not None:
            for fid in file_refs:
                path = file_path_by_id.get(fid)
                if path is None:
                    continue  # caught by referential integrity
                if not (repo_root / path).exists():
                    errors.append({
                        "check": "file-existence",
                        "message": f"{P} {where} fileId {fid!r} path {path!r} does not exist under repo root",
                    })

    # headline (grounding-exempt; WARN only)
    if not brief.get("headline"):
        warnings.append({
            "check": "headline",
            "message": f"{P} headline is empty or missing",
        })

    # required claims
    if isinstance(brief.get("problem"), dict):
        check_claim(brief["problem"], "problem")
    if isinstance(brief.get("solution"), dict):
        check_claim(brief["solution"], "solution")
    # optional claim
    if isinstance(brief.get("audience"), dict):
        check_claim(brief["audience"], "audience")

    # capabilities
    for i, cap in enumerate(brief.get("capabilities", []) or []):
        label = cap.get("label") or i
        check_claim(cap, f"capability {label!r}")
        pref = cap.get("perspectiveRef")
        nref = cap.get("nodeRef")
        if pref is not None and pref not in valid_pids:
            errors.append({
                "check": "capability-ref",
                "message": f"{P} capability {label!r} perspectiveRef {pref!r} is not a perspective id",
            })
        if nref is not None:
            if pref is None:
                errors.append({
                    "check": "capability-ref",
                    "message": f"{P} capability {label!r} has nodeRef {nref!r} but no perspectiveRef",
                })
            elif nref not in node_ids_by_pid.get(pref, set()):
                errors.append({
                    "check": "capability-ref",
                    "message": (
                        f"{P} capability {label!r} nodeRef {nref!r} is not a node "
                        f"in perspective {pref!r}"
                    ),
                })

    # techStack
    for ts in brief.get("techStack", []) or []:
        ref = ts.get("factRef")
        if ref not in dep_names:
            errors.append({
                "check": "techstack-ref",
                "message": f"{P} techStack factRef {ref!r} is not an externalDependencies name",
            })

    return errors, warnings


def verify(facts: dict, narrative: dict, repo_root: pathlib.Path | None = None) -> dict:
    """Run all anti-hallucination checks and return a machine-readable report.

    Returns a dict with keys: status, errors, warnings, coverage.
    status is "FAIL" iff errors is non-empty. Each perspective is validated
    independently against the shared facts.
    """
    errors: list[dict] = []
    warnings: list[dict] = []

    files = facts.get("files", []) or []
    modules = facts.get("modules", []) or []
    edges = facts.get("edges", []) or []

    file_ids = {f.get("id") for f in files}
    module_ids = {m.get("id") for m in modules}
    edge_ids = {e.get("id") for e in edges}

    file_path_by_id = {f.get("id"): f.get("path") for f in files}
    module_file_ids = {m.get("id"): set(m.get("fileIds", []) or []) for m in modules}

    perspectives = _perspectives(narrative)

    # --- Structural check: unique perspective ids ---
    seen_pids: set = set()
    for p in perspectives:
        pid = p.get("id")
        if pid in seen_pids:
            errors.append({
                "check": "perspective-ids",
                "message": f"duplicate perspective id {pid!r}",
            })
        seen_pids.add(pid)

    if repo_root is not None:
        repo_root = pathlib.Path(repo_root)

    covered_all: set = set()
    per_perspective_cov: list[dict] = []
    total_files = len(file_ids)
    total_nodes = 0

    node_ids_by_pid: dict = {}
    valid_pids: set = set()

    for p in perspectives:
        pid = p.get("id")
        nodes = p.get("nodes", []) or []
        relationships = p.get("relationships", []) or []
        total_nodes += len(nodes)
        node_ids = {n.get("id") for n in nodes}
        node_ids_by_pid[pid] = set(node_ids)
        valid_pids.add(pid)

        # --- Structural check: unique node ids within the perspective ---
        seen_nids: set = set()
        for n in nodes:
            nid = n.get("id")
            if nid in seen_nids:
                errors.append({
                    "check": "node-ids",
                    "message": f"[{pid}] duplicate node id {nid!r}",
                })
            seen_nids.add(nid)

        # --- Check 1: referential integrity ---
        for node in nodes:
            refs = node.get("factRefs", {}) or {}
            nid = node.get("id")
            for fid in refs.get("fileIds", []) or []:
                if fid not in file_ids:
                    errors.append({
                        "check": "referential-integrity",
                        "message": f"[{pid}] node {nid!r} references unknown fileId {fid!r}",
                    })
            for mid in refs.get("moduleIds", []) or []:
                if mid not in module_ids:
                    errors.append({
                        "check": "referential-integrity",
                        "message": f"[{pid}] node {nid!r} references unknown moduleId {mid!r}",
                    })
        for rel in relationships:
            for eid in rel.get("factEdgeIds", []) or []:
                if eid not in edge_ids:
                    errors.append({
                        "check": "referential-integrity",
                        "message": (
                            f"[{pid}] relationship {rel.get('from')!r}->{rel.get('to')!r} "
                            f"references unknown factEdgeId {eid!r}"
                        ),
                    })
            # relationship endpoints must be nodes in THIS perspective
            for end in ("from", "to"):
                ref = rel.get(end)
                if ref not in node_ids:
                    errors.append({
                        "check": "relationship-endpoints",
                        "message": (
                            f"[{pid}] relationship {end} {ref!r} is not a node in this perspective"
                        ),
                    })

        # --- Check 2: no empty grounding ---
        for node in nodes:
            refs = node.get("factRefs", {}) or {}
            has_refs = bool(refs.get("fileIds")) or bool(refs.get("moduleIds"))
            allowed_interpretation = (
                node.get("interpretation") is True
                and node.get("confidence") == "low"
                and bool(node.get("description"))
            )
            if not has_refs and not allowed_interpretation:
                errors.append({
                    "check": "empty-grounding",
                    "message": (
                        f"[{pid}] node {node.get('id')!r} has no factRefs and is not a "
                        "low-confidence interpretation"
                    ),
                })

        # --- Check 3: file existence (only when repo_root given) ---
        if repo_root is not None:
            referenced_file_ids: set = set()
            for node in nodes:
                refs = node.get("factRefs", {}) or {}
                referenced_file_ids.update(refs.get("fileIds", []) or [])
            for fid in sorted(referenced_file_ids):
                path = file_path_by_id.get(fid)
                if path is None:
                    continue  # caught by referential integrity
                if not (repo_root / path).exists():
                    errors.append({
                        "check": "file-existence",
                        "message": f"[{pid}] fileId {fid!r} path {path!r} does not exist under repo root",
                    })

        # --- Check 5: coverage sanity (reported, never a failure) ---
        covered_p: set = set()
        for node in nodes:
            refs = node.get("factRefs", {}) or {}
            for fid in refs.get("fileIds", []) or []:
                if fid in file_ids:
                    covered_p.add(fid)
            for mid in refs.get("moduleIds", []) or []:
                for fid in module_file_ids.get(mid, set()):
                    if fid in file_ids:
                        covered_p.add(fid)
        covered_all |= covered_p
        per_perspective_cov.append({
            "id": pid,
            "nodeCount": len(nodes),
            "filesCoveredByNode": len(covered_p),
            "fileCoveragePct": round(100.0 * len(covered_p) / total_files, 2) if total_files else 0.0,
        })

    # --- Business brief checks (optional object) ---
    brief = narrative.get("businessBrief")
    if brief is not None:
        dep_names = {d.get("name") for d in facts.get("externalDependencies", []) or []}
        brief_errors, brief_warnings = _verify_business_brief(
            brief,
            file_ids=file_ids,
            module_ids=module_ids,
            file_path_by_id=file_path_by_id,
            dep_names=dep_names,
            node_ids_by_pid=node_ids_by_pid,
            valid_pids=valid_pids,
            repo_root=repo_root,
        )
        errors.extend(brief_errors)
        warnings.extend(brief_warnings)

    # --- Check 4: commit match (warning only) ---
    based_on = narrative.get("basedOnFactsCommit")
    head = (facts.get("repo", {}) or {}).get("headCommit")
    if based_on != head:
        warnings.append({
            "check": "commit-match",
            "message": (
                f"narrative.basedOnFactsCommit {based_on!r} != "
                f"facts.repo.headCommit {head!r}"
            ),
        })

    files_covered = len(covered_all)
    coverage_pct = round(100.0 * files_covered / total_files, 2) if total_files else 0.0
    unresolved_edges = sum(1 for e in edges if e.get("resolution") == "unresolved")

    coverage = {
        "nodeCount": total_nodes,
        "filesCoveredByNode": files_covered,
        "totalFiles": total_files,
        "fileCoveragePct": coverage_pct,
        "unresolvedEdges": unresolved_edges,
        "perspectives": per_perspective_cov,
    }

    return {
        "status": "FAIL" if errors else "PASS",
        "errors": errors,
        "warnings": warnings,
        "coverage": coverage,
    }


def _load_json(path: pathlib.Path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify a narrative.json against facts.json (anti-hallucination gate)."
    )
    parser.add_argument("--facts", required=True, help="Path to facts.json")
    parser.add_argument("--narrative", required=True, help="Path to narrative.json")
    parser.add_argument("--repo", default=None, help="Repo root for file-existence checks")
    parser.add_argument("--out", default=None, help="Output report path (default: verify.report.json next to facts)")
    args = parser.parse_args(argv)

    facts_path = pathlib.Path(args.facts)
    narrative_path = pathlib.Path(args.narrative)
    repo_root = pathlib.Path(args.repo) if args.repo else None
    out_path = pathlib.Path(args.out) if args.out else facts_path.parent / "verify.report.json"

    facts = _load_json(facts_path)
    narrative = _load_json(narrative_path)

    report = verify(facts, narrative, repo_root=repo_root)

    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
        fh.write("\n")

    cov = report["coverage"]
    print(f"verify: {report['status']}")
    print(f"  errors:   {len(report['errors'])}")
    print(f"  warnings: {len(report['warnings'])}")
    print(
        f"  coverage: {cov['filesCoveredByNode']}/{cov['totalFiles']} files "
        f"({cov['fileCoveragePct']}%), unresolved edges: {cov['unresolvedEdges']}"
    )
    for err in report["errors"]:
        print(f"  ERROR [{err['check']}] {err['message']}")
    for warn in report["warnings"]:
        print(f"  WARN  [{warn['check']}] {warn['message']}")
    print(f"  report written to {out_path}")

    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
