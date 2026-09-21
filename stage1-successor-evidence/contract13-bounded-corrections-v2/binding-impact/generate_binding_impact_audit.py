#!/usr/bin/env python3
"""Create/check the Contract 13 bounded exact-binding impact audit."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterator


ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
CHANGED_REL = Path("stage1-successor-evidence/residual-disposition-v1/changed-paths.v1.json")
CONTRACT_REL = Path(
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-09-04-formal-production-release/"
    "13_contract12-supervisor-review-and-return.v1.md"
)
PRODUCTION_DECLARATION_REL = Path(
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-09-04-formal-production-release/stage1-evidence/"
    "production-contract-implementation.v1.json"
)
STAGE0_RECORD_REL = Path(
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-09-04-formal-production-release/stage0-evidence/"
    "functorial-refactor-completion.v4.json"
)
SUCCESSOR_EVIDENCE = Path(
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration/evidence"
)
EXACT_ROOT = SUCCESSOR_EVIDENCE / "exact-byte-rebind"
ALL_LINES_RECORDS = (
    SUCCESSOR_EVIDENCE / "all-lines-investigation/AllLinesDonorByteClosure.v1.json",
    SUCCESSOR_EVIDENCE
    / "all-lines-investigation/AllLinesSuccessorMovementInventory.v1.json",
)
REGISTRY_RELS = tuple(sorted(Path("registries").glob("*.json")))
FAMILIES = ("C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9", "I1")
IMPORT_BOUNDARY_PATHS = (
    "main/backend/app/models/base.py",
    "main/backend/app/startup_hooks.py",
    "main/backend/app/services/workflow_graph/__init__.py",
    "main/backend/app/services/workflow_graph/runtime.py",
    "main/backend/app/services/workflow_graph/executors/__init__.py",
    "main/backend/app/services/workflow_graph/handoff_store.py",
    "main/backend/tests/unit/test_schema_startup_boundary_unittest.py",
    "main/backend/tests/unit/test_workflow_graph_import_boundary_unittest.py",
)
CONTRACT_SHA256 = "ac1629315b3ae91aa9de59b7ae87da04a5f10c54d643e406d8785a0783071717"
CHANGED_SHA256 = "d946cf88b022d21cc71c0a1ea424b9cb8f7d2c5a7975fe31c66c67f741790d9b"
AUDIT_NAME = "binding-impact-audit.v2.json"
RECEIPT_NAME = "binding-impact-receipt.v2.md"
VALIDATION_NAME = "binding-impact-audit.validation.v2.json"


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def read_json(relative: Path) -> Any:
    with (ROOT / relative).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def walk(value: Any, pointer: str = "") -> Iterator[tuple[str, Any]]:
    yield pointer or "/", value
    if isinstance(value, dict):
        for key in sorted(value):
            escaped = key.replace("~", "~0").replace("/", "~1")
            yield from walk(value[key], f"{pointer}/{escaped}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from walk(item, f"{pointer}/{index}")


def binding_artifacts() -> list[dict[str, str]]:
    result: list[dict[str, str]] = [
        {
            "path": PRODUCTION_DECLARATION_REL.as_posix(),
            "binding_set": "CURRENT_PRODUCTION_DECLARATION",
        },
        {
            "path": STAGE0_RECORD_REL.as_posix(),
            "binding_set": "DECLARED_STAGE0_COMPLETION_V4_RECORD",
        },
    ]
    result.extend(
        {"path": path.as_posix(), "binding_set": "CURRENT_ALL_LINES_RECORD"}
        for path in ALL_LINES_RECORDS
    )
    result.extend(
        {"path": path.as_posix(), "binding_set": "CURRENT_ROOT_REGISTRY"}
        for path in REGISTRY_RELS
    )

    declared_stages = (
        ("stage-b19-2026-09-05", "DECLARED_STAGE0_V4_FAMILY_CURRENT"),
        ("stage-b22-2026-09-05", "DECLARED_STAGE0_V4_I1_CURRENT"),
        ("stage-b23-2026-09-05", "CURRENT_STAGE2_INTAKE_B23"),
    )
    for stage, binding_set in declared_stages:
        families = FAMILIES
        if stage == "stage-b19-2026-09-05":
            families = FAMILIES[:-1]
        elif stage == "stage-b22-2026-09-05":
            families = ("I1",)
        for family in families:
            base = EXACT_ROOT / stage
            for relative in (
                Path("fragments") / f"{family}.json",
                Path("manifests") / f"{family}.json",
                Path("candidates") / family / "candidate.v2.json",
            ):
                result.append(
                    {
                        "path": (base / relative).as_posix(),
                        "binding_set": binding_set,
                    }
                )
    return result


def hash_from_binding(value: dict[str, Any]) -> tuple[str | None, str | None]:
    for key in (
        "successor_sha256",
        "file_sha256",
        "sha256",
        "bytes_sha256",
        "head_sha256",
        "predecessor_sha256",
    ):
        candidate = value.get(key)
        if isinstance(candidate, str) and len(candidate) == 64:
            return candidate, key
    return None, None


def discover_references(
    artifacts: list[dict[str, str]], changed_paths: set[str]
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    references = {path: [] for path in changed_paths}
    inventory: list[dict[str, Any]] = []
    for artifact in artifacts:
        relative = Path(artifact["path"])
        payload = (ROOT / relative).read_bytes()
        value = json.loads(payload)
        inventory.append(
            {
                **artifact,
                "sha256": sha256(payload),
                "parse": "PASS",
            }
        )
        for pointer, node in walk(value):
            if not isinstance(node, dict):
                continue
            bound_path = node.get("path")
            if bound_path not in changed_paths:
                continue
            bound_sha256, hash_field = hash_from_binding(node)
            if bound_sha256 is None:
                continue
            references[bound_path].append(
                {
                    "artifact": relative.as_posix(),
                    "binding_set": artifact["binding_set"],
                    "json_pointer": pointer,
                    "hash_field": hash_field,
                    "bound_sha256": bound_sha256,
                    "role": node.get("role"),
                    "cell_id": node.get("cell_id"),
                }
            )
    for path in references:
        references[path].sort(
            key=lambda item: (
                item["binding_set"], item["artifact"], item["json_pointer"]
            )
        )
    return references, inventory


def surface_kinds(path: str) -> list[str]:
    kinds: list[str] = []
    name = Path(path).name
    if path.endswith(".py"):
        kinds.append("CODE")
    if path.startswith("main/backend/app/") and path.endswith(".py"):
        kinds.append("RUNTIME")
    if "contract" in name.lower() or "contract" in path.lower():
        kinds.append("CONTRACT")
    if path.endswith(".py") and (
        "/tests/" in path
        or path.startswith("tests/")
        or name.startswith(("test_", "check_"))
        or "/scripts/check_" in path
    ):
        kinds.append("CHECKER")
    if not kinds:
        kinds.append("EVIDENCE_OR_REVIEW_ARTIFACT")
    return kinds


def rebind_requirement(references: list[dict[str, Any]], current_hash: str) -> str:
    drift_sets = {
        item["binding_set"]
        for item in references
        if item["bound_sha256"] != current_hash
    }
    if not references:
        return "NONE_NOT_BOUND_WITHIN_DETERMINISTIC_SEARCH_SCOPE"
    if not drift_sets:
        return "NONE_CURRENT_BINDINGS_MATCH_CURRENT_BYTES"
    actions: list[str] = []
    if any("B23" in item or "STAGE2" in item for item in drift_sets):
        actions.append("AUTHORIZED_CREATE_ONLY_SUCCESSOR_STAGE_REBIND; DO_NOT_OVERWRITE_B23")
    if any("STAGE0" in item for item in drift_sets):
        actions.append("VERSIONED_STAGE0_DECLARATION_ALIGNMENT_AND_ADDITIVE_REBIND")
    if "CURRENT_PRODUCTION_DECLARATION" in drift_sets:
        actions.append("VERSIONED_SUCCESSOR_PRODUCTION_CONTRACT_DECLARATION")
    if "CURRENT_ALL_LINES_RECORD" in drift_sets:
        actions.append("VERSIONED_SUCCESSOR_ALL_LINES_BYTE_CLOSURE_RECORD")
    return "; ".join(actions)


def build_audit() -> dict[str, Any]:
    contract_bytes = (ROOT / CONTRACT_REL).read_bytes()
    changed_bytes = (ROOT / CHANGED_REL).read_bytes()
    if sha256(contract_bytes) != CONTRACT_SHA256:
        raise ValueError("contract 13 hash drift")
    if sha256(changed_bytes) != CHANGED_SHA256:
        raise ValueError("changed-paths v1 hash drift")
    changed = json.loads(changed_bytes)
    entries = changed["entries"]
    if changed.get("entry_count") != 105 or len(entries) != 105:
        raise ValueError("changed-paths entry count is not 105")
    paths = [item["path"] for item in entries]
    if len(paths) != len(set(paths)):
        raise ValueError("changed-paths contains duplicate paths")

    artifacts = binding_artifacts()
    references, artifact_inventory = discover_references(artifacts, set(paths))
    audit_entries: list[dict[str, Any]] = []
    for index, item in enumerate(entries):
        relative = Path(item["path"])
        payload = (ROOT / relative).read_bytes()
        current_hash = sha256(payload)
        if current_hash != item["after_sha256"]:
            raise ValueError(f"current bytes drifted after changed-paths v1: {relative}")
        refs = references[item["path"]]
        for ref in refs:
            ref["current_sha256"] = current_hash
            ref["drift"] = ref["bound_sha256"] != current_hash
        task_start_recorded = item.get("before_hash_kind") == "task_start"
        audit_entries.append(
            {
                "changed_paths_index": index,
                "path": item["path"],
                "surface_kinds": surface_kinds(item["path"]),
                "current_sha256": current_hash,
                "changed_paths_after_sha256": item["after_sha256"],
                "task_change_attribution": {
                    "classification": (
                        "TASK_LOCAL_CHANGE_WITH_RECORDED_TASK_START"
                        if task_start_recorded
                        else "INHERITED_OR_UNATTRIBUTABLE_NO_TASK_START_BYTES"
                    ),
                    "before_hash_kind": item.get("before_hash_kind"),
                    "recorded_task_start_sha256": (
                        item.get("before_sha256") if task_start_recorded else None
                    ),
                    "head_used_as_before": False,
                },
                "binding_status": "BOUND" if refs else "NOT_BOUND",
                "binding_reference_count": len(refs),
                "any_binding_drift": any(ref["drift"] for ref in refs),
                "binding_references": refs,
                "required_additive_rebind": rebind_requirement(refs, current_hash),
            }
        )

    code_contract_checker = [
        entry
        for entry in audit_entries
        if set(entry["surface_kinds"]) & {"CODE", "CONTRACT", "CHECKER"}
    ]
    bound = [entry for entry in audit_entries if entry["binding_status"] == "BOUND"]
    drifted = [entry for entry in bound if entry["any_binding_drift"]]
    import_entries = [
        next(entry for entry in audit_entries if entry["path"] == path)
        for path in IMPORT_BOUNDARY_PATHS
    ]
    declaration_sources = [
        {
            "path": "scripts/formal_release/stage2_candidate_intake.py",
            "line_anchor": "57-64",
            "declaration": "B23 for C2-C9 and I1",
            "status": "CURRENT_STAGE2_INTAKE",
        },
        {
            "path": "main/backend/tests/successor_runtime/i1_binding_candidate_support.py",
            "line_anchor": "20-41",
            "declaration": "B23 I1 with exact candidate/fragment/manifest identities",
            "status": "CURRENT_I1_TEST_DECLARATION",
        },
        {
            "path": "main/backend/tests/successor_runtime/current_candidate_support.py",
            "line_anchor": "21",
            "declaration": "B19 default family current stage",
            "status": "OLDER_CURRENT_FAMILY_TEST_DECLARATION",
        },
        {
            "path": "scripts/formal_release/generate_stage0_completion.py",
            "line_anchor": "62-68",
            "declaration": "B19 for C2-C9; B22 for I1",
            "status": "STAGE0_V4_DECLARATION",
        },
        {
            "path": STAGE0_RECORD_REL.as_posix(),
            "json_pointer": "/bindings/candidate_stages",
            "declaration": "B19 for C2-C9; B22 for I1",
            "status": "STAGE0_V4_PERSISTED_RECORD",
        },
    ]
    return {
        "schema_version": "mrw.stage1.contract13.binding-impact-audit.v2",
        "record_id": "contract13-bounded-binding-impact-v2",
        "authoritative": False,
        "status": (
            "BINDING_DRIFT_FOUND_ADDITIVE_REBIND_REVIEW_REQUIRED"
            if drifted
            else "CURRENT_BINDINGS_INTACT_WITHIN_DECLARED_SCOPE"
        ),
        "authority_ceiling": (
            "READ_ONLY_AUDIT_NO_BINDING_WRITE_NO_CANDIDATE_OR_HISTORY_MUTATION_"
            "NO_PRODUCTION_WRITE_NO_DEPLOY_NO_LIVE_NO_RELEASE_AUTHORITY"
        ),
        "source_contract": {
            "path": CONTRACT_REL.as_posix(),
            "sha256": CONTRACT_SHA256,
            "required_item": 3,
        },
        "changed_paths_source": {
            "path": CHANGED_REL.as_posix(),
            "sha256": CHANGED_SHA256,
            "entry_count": 105,
        },
        "deterministic_search_scope": {
            "rule": (
                "Direct path-plus-hash objects were recursively inspected in every listed "
                "JSON artifact. Snapshots and historical stages other than declared B19/B22 "
                "and Stage 2 B23 were excluded. Python declaration anchors were read only to "
                "identify the competing current-stage declarations."
            ),
            "binding_artifact_count": len(artifact_inventory),
            "binding_artifacts": artifact_inventory,
            "declaration_sources": declaration_sources,
            "registry_paths": [path.as_posix() for path in REGISTRY_RELS],
            "not_bound_meaning": (
                "No direct path-plus-SHA binding was found in the enumerated current "
                "declarations, root registries, B19/B22 declared candidate chains, B23 Stage 2 "
                "candidate chains, production declaration, or current all-lines records."
            ),
        },
        "declaration_alignment": {
            "status": "DIVERGENT_CURRENT_STAGE_DECLARATIONS",
            "stage2_intake": "B23_C2_C9_I1",
            "i1_runtime_test_support": "B23_I1",
            "family_test_support": "B19_C2_C9_DEFAULT",
            "stage0_v4_record": "B19_C2_C9_B22_I1",
            "effect": (
                "Binding impact is reported separately for every declaration set; no source "
                "was silently selected as the sole authority."
            ),
        },
        "summary": {
            "changed_path_entry_count": len(audit_entries),
            "code_contract_checker_subset_count": len(code_contract_checker),
            "code_contract_checker_audited_count": len(code_contract_checker),
            "bound_path_count": len(bound),
            "not_bound_path_count": len(audit_entries) - len(bound),
            "drifted_bound_path_count": len(drifted),
            "intact_bound_path_count": len(bound) - len(drifted),
            "task_start_recorded_count": sum(
                entry["task_change_attribution"]["recorded_task_start_sha256"]
                is not None
                for entry in audit_entries
            ),
            "task_start_missing_count": sum(
                entry["task_change_attribution"]["recorded_task_start_sha256"]
                is None
                for entry in audit_entries
            ),
            "import_boundary_path_count": len(import_entries),
            "import_boundary_bound_count": sum(
                entry["binding_status"] == "BOUND" for entry in import_entries
            ),
            "import_boundary_drift_count": sum(
                entry["any_binding_drift"] for entry in import_entries
            ),
        },
        "import_time_db_boundary_audit": import_entries,
        "entries": audit_entries,
        "limits": [
            "A matching or drifting hash is byte correspondence only, not semantic acceptance.",
            "NOT_BOUND is bounded to the deterministic search scope above.",
            "Only recorded task_start hashes are before evidence; HEAD is never substituted.",
            "No additive rebind, registry write, candidate mutation, or release action occurred.",
            "PRODUCTION_RELEASE_NOT_AUTHORIZED",
        ],
    }


def build_receipt(audit: dict[str, Any]) -> bytes:
    summary = audit["summary"]
    lines = [
        "# Contract 13 binding-impact receipt v2",
        "",
        f"Status: `{audit['status']}`.",
        "",
        "This is a read-only byte-binding audit. It does not modify declarations, registries, "
        "candidate/history bytes, runtime code, or production state.",
        "",
        "## Coverage",
        "",
        f"- Changed-path entries: {summary['changed_path_entry_count']}/105.",
        "- Code/contract/checker subset: "
        f"{summary['code_contract_checker_audited_count']}/"
        f"{summary['code_contract_checker_subset_count']} audited.",
        f"- Bound paths: {summary['bound_path_count']}; NOT_BOUND paths: "
        f"{summary['not_bound_path_count']}.",
        f"- Drifted bound paths: {summary['drifted_bound_path_count']}; intact bound paths: "
        f"{summary['intact_bound_path_count']}.",
        "- Task attribution: only "
        f"{summary['task_start_recorded_count']} recorded task-start hashes are accepted as "
        f"before evidence; {summary['task_start_missing_count']} remain inherited or "
        "unattributable. HEAD was not used as before evidence.",
        "",
        "## Current-declaration alignment",
        "",
        "Stage 2 intake and I1 test support declare B23 current, while the Stage 0 v4 "
        "generator/record declares B19 for C2-C9 and B22 for I1; family test support defaults "
        "to B19. The JSON reports every declaration set separately and does not silently pick "
        "one authority.",
        "",
        "## Eight import-time DB boundary paths",
        "",
        "| Path | Binding | Drift | Required disposition |",
        "|---|---:|---:|---|",
    ]
    for entry in audit["import_time_db_boundary_audit"]:
        lines.append(
            f"| `{entry['path']}` | {entry['binding_status']} "
            f"({entry['binding_reference_count']}) | "
            f"{'YES' if entry['any_binding_drift'] else 'NO'} | "
            f"`{entry['required_additive_rebind']}` |"
        )
    lines.extend(
        [
            "",
            "## Bound changed paths",
            "",
            "| Path | Current SHA-256 | References | Drift |",
            "|---|---|---:|---:|",
        ]
    )
    for entry in audit["entries"]:
        if entry["binding_status"] != "BOUND":
            continue
        lines.append(
            f"| `{entry['path']}` | `{entry['current_sha256']}` | "
            f"{entry['binding_reference_count']} | "
            f"{'YES' if entry['any_binding_drift'] else 'NO'} |"
        )
    lines.extend(
        [
            "",
            "Every reference, old bound hash, current hash, JSON pointer, drift result, "
            "task-start attribution, and additive-rebind requirement is recorded in "
            f"`{AUDIT_NAME}`. `NOT_BOUND` is limited to the exact enumerated search universe; "
            "it is not a repository-global absence claim.",
            "",
            "Authority ceiling: `PRODUCTION_RELEASE_NOT_AUTHORIZED`.",
            "",
        ]
    )
    return "\n".join(lines).encode("utf-8")


def expected_documents() -> tuple[bytes, bytes, bytes]:
    audit = build_audit()
    audit_payload = json_bytes(audit)
    receipt_payload = build_receipt(audit)
    generator_hash = sha256(Path(__file__).read_bytes())
    validation = {
        "schema_version": "mrw.stage1.contract13.binding-impact-audit.validation.v2",
        "status": "PASS",
        "authoritative": False,
        "checks": {
            "contract_sha256": "PASS",
            "changed_paths_sha256": "PASS",
            "changed_paths_unique": "PASS",
            "changed_paths_total_105": "PASS",
            "current_hash_matches_changed_paths_after": "105/105 PASS",
            "code_contract_checker_subset_covered": (
                f"{audit['summary']['code_contract_checker_audited_count']}/"
                f"{audit['summary']['code_contract_checker_subset_count']} PASS"
            ),
            "import_boundary_paths_covered": "8/8 PASS",
            "binding_artifact_json_parse": (
                f"{audit['deterministic_search_scope']['binding_artifact_count']}/"
                f"{audit['deterministic_search_scope']['binding_artifact_count']} PASS"
            ),
            "binding_reference_path_membership": "PASS",
            "head_used_as_before": "0",
        },
        "artifacts": {
            AUDIT_NAME: sha256(audit_payload),
            RECEIPT_NAME: sha256(receipt_payload),
            Path(__file__).name: generator_hash,
        },
        "limits": "BYTE_AND_REFERENCE_VALIDATION_ONLY_NOT_RELEASE_AUTHORITY",
    }
    return audit_payload, receipt_payload, json_bytes(validation)


def write_create_only(path: Path, payload: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(payload)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    documents = dict(zip(
        (AUDIT_NAME, RECEIPT_NAME, VALIDATION_NAME), expected_documents(), strict=True
    ))
    if args.check:
        for name, payload in documents.items():
            path = OUT / name
            if not path.is_file() or path.read_bytes() != payload:
                raise SystemExit(f"DRIFT: {name}")
        print("PASS: 105/105 changed paths; code/contract/checker and 8/8 boundary coverage")
        return 0
    for name, payload in documents.items():
        write_create_only(OUT / name, payload)
    print("CREATED: " + ", ".join(documents))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
