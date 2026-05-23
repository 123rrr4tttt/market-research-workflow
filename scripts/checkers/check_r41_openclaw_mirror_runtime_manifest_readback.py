#!/usr/bin/env python3
"""Wave20 repo-local R41 OpenClaw mirror/runtime manifest readback gate.

This checker converts the existing Wave12/Wave15 R41 OpenClaw mirror gates into
a downstream-readable manifest. It intentionally stays inside this repository:
it does not read the external OpenClaw workspace, run OpenClaw commands, or claim
that the external runtime is sealed.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
TOPIC_NAME = "2026-03-04-r41-openclaw-autodispatch"
CURRENT_TOPIC_REL = Path("development/latest-dev-docs/development-plans/CURRENT_DEV") / TOPIC_NAME
ARCHIVE_EXTERNAL_BLOCKED_TOPIC_REL = (
    Path("development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED") / TOPIC_NAME
)
TOPIC_CANDIDATE_RELS = (ARCHIVE_EXTERNAL_BLOCKED_TOPIC_REL, CURRENT_TOPIC_REL)
TOPIC_REL = ARCHIVE_EXTERNAL_BLOCKED_TOPIC_REL
DEFAULT_OUT_DIR = Path("development/latest-dev-docs/automation-runs/wave20-openclaw-mirror-readback/2026-05-22")
RUNTIME_HANDOFF_SCRIPT = Path("scripts/checkers/check_r41_openclaw_runtime_handoff.py")

STATUS_LOCAL_MIRROR_PASSED = "local_mirror_passed"
STATUS_LOCAL_MIRROR_FAILED = "local_mirror_failed"
STATUS_EXTERNAL_RUNTIME_UNVERIFIED = "external_runtime_unverified"
STATUS_MISSING_ARTIFACT = "missing_artifact"

WAVE12_EVIDENCE_REL = Path("implementation/WAVE12_R41_OPENCLAW_AUTODISPATCH_GATE_EVIDENCE.md")
WAVE20_EVIDENCE_REL = Path("implementation/WAVE20_R41_OPENCLAW_MIRROR_READBACK_EVIDENCE.md")
INTERFACE_CONTRACT_REL = Path("R41_INTERFACE_CONTRACT.md")
CONTRACT_VERSION = "wave20-openclaw-mirror-runtime-readback.v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a repo-local R41 OpenClaw mirror/runtime handoff manifest "
            "without probing the external OpenClaw runtime."
        )
    )
    parser.add_argument(
        "--root",
        "--repo-root",
        dest="root",
        default=str(REPO_ROOT),
        help="Repository root; defaults to this checkout.",
    )
    parser.add_argument(
        "--topic",
        default=None,
        help=(
            "R41 topic folder relative to --root, or an absolute topic path. "
            "Defaults to the first existing archive/current-dev topic path."
        ),
    )
    parser.add_argument(
        "--out-dir",
        default=str(DEFAULT_OUT_DIR),
        help="Automation-run output directory relative to --root, or an absolute path.",
    )
    return parser.parse_args()


def load_runtime_handoff_checker(root: Path) -> ModuleType:
    script_path = root / RUNTIME_HANDOFF_SCRIPT
    spec = importlib.util.spec_from_file_location("check_r41_openclaw_runtime_handoff_wave20", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load runtime handoff checker: {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def display_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def resolve_topic_path(root: Path, topic: Path | None = None) -> Path:
    if topic is not None:
        return topic if topic.is_absolute() else root / topic
    for relative in TOPIC_CANDIDATE_RELS:
        candidate = root / relative
        if candidate.is_dir():
            return candidate
    return root / TOPIC_REL


def required_artifacts(runtime_checker: ModuleType) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = [
        {
            "artifact_id": "autodispatch_runtime_state",
            "path": runtime_checker.AUTODISPATCH_REL,
            "kind": "runtime_state",
        },
        {
            "artifact_id": "interface_contract",
            "path": INTERFACE_CONTRACT_REL,
            "kind": "interface_contract",
        },
        {
            "artifact_id": "codex_handoff_manifest",
            "path": runtime_checker.CODEX_HANDOFF_REL,
            "kind": "handoff_manifest",
        },
        {
            "artifact_id": "reference_index",
            "path": runtime_checker.REFERENCE_INDEX_REL,
            "kind": "reference_pool",
        },
        {
            "artifact_id": "reference_dedup_boundary",
            "path": runtime_checker.DEDUP_DIFF_REL,
            "kind": "reference_pool",
        },
        {
            "artifact_id": "interface_alignment",
            "path": runtime_checker.INTERFACE_ALIGNMENT_REL,
            "kind": "reference_pool",
        },
        {
            "artifact_id": "wave12_autodispatch_gate_evidence",
            "path": WAVE12_EVIDENCE_REL,
            "kind": "evidence",
        },
        {
            "artifact_id": "wave15_runtime_handoff_evidence",
            "path": runtime_checker.EVIDENCE_REL,
            "kind": "evidence",
        },
        {
            "artifact_id": "wave20_mirror_readback_topic_evidence",
            "path": WAVE20_EVIDENCE_REL,
            "kind": "evidence",
        },
    ]
    for doc in runtime_checker.IMPLEMENTATION_DOCS:
        artifacts.append(
            {
                "artifact_id": f"implementation_{doc.label.lower()}",
                "path": doc.path,
                "kind": "implementation_doc",
            }
        )
    for name in runtime_checker.EXPECTED_REFERENCE_FILES:
        artifacts.append(
            {
                "artifact_id": f"reference_file_{Path(name).stem.replace('-', '_')}",
                "path": runtime_checker.REFERENCE_POOL_REL / name,
                "kind": "reference_file",
            }
        )
    return artifacts


def artifact_rows(topic: Path, root: Path, runtime_checker: ModuleType, *, local_mirror_ok: bool) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for artifact in required_artifacts(runtime_checker):
        rel_path = Path(artifact["path"])
        full_path = topic / rel_path
        exists = full_path.is_file()
        nonempty = exists and bool(full_path.read_text(encoding="utf-8").strip())
        status = (
            STATUS_MISSING_ARTIFACT
            if not exists or not nonempty
            else STATUS_LOCAL_MIRROR_PASSED
            if local_mirror_ok
            else STATUS_LOCAL_MIRROR_FAILED
        )
        rows.append(
            {
                "artifact_id": artifact["artifact_id"],
                "kind": artifact["kind"],
                "path": display_path(full_path, root),
                "status": status,
                "exists": exists,
                "nonempty": nonempty,
            }
        )
    return rows


def problem_rows(runtime_result: Any, root: Path) -> list[dict[str, Any]]:
    return [
        {
            "path": display_path(problem.path, root),
            "line_no": problem.line_no,
            "message": problem.message,
        }
        for problem in runtime_result.problems
    ]


def handoff_line_rows(topic: Path, runtime_checker: ModuleType) -> list[dict[str, Any]]:
    path = topic / runtime_checker.CODEX_HANDOFF_REL
    if not path.is_file():
        return [
            {
                "line": line,
                "task_ids": [],
                "expected_task_ids": list(runtime_checker.EXPECTED_HANDOFF_TASKS[line]),
                "status": STATUS_MISSING_ARTIFACT,
            }
            for line in runtime_checker.EXPECTED_LINES
        ]
    tasks = runtime_checker.parse_handoff_tasks(path.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    for line in runtime_checker.EXPECTED_LINES:
        actual = list(tasks.get(line, ()))
        expected = list(runtime_checker.EXPECTED_HANDOFF_TASKS[line])
        rows.append(
            {
                "line": line,
                "task_ids": actual,
                "expected_task_ids": expected,
                "status": STATUS_LOCAL_MIRROR_PASSED if actual == expected else STATUS_LOCAL_MIRROR_FAILED,
            }
        )
    return rows


def status_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = {
        STATUS_LOCAL_MIRROR_PASSED: 0,
        STATUS_LOCAL_MIRROR_FAILED: 0,
        STATUS_EXTERNAL_RUNTIME_UNVERIFIED: 0,
        STATUS_MISSING_ARTIFACT: 0,
    }
    for row in rows:
        status = str(row.get("status"))
        counts[status] = counts.get(status, 0) + 1
    return counts


def build_contract(*, root: Path | None = None, topic: Path | None = None) -> dict[str, Any]:
    root = (root or REPO_ROOT).resolve()
    runtime_checker = load_runtime_handoff_checker(root)
    topic = resolve_topic_path(root, topic).resolve()
    runtime_result = runtime_checker.check_topic(topic, root)
    local_mirror_ok = bool(runtime_result.ok)
    artifacts = artifact_rows(topic, root, runtime_checker, local_mirror_ok=local_mirror_ok)
    missing_count = sum(1 for row in artifacts if row["status"] == STATUS_MISSING_ARTIFACT)
    handoff_rows = handoff_line_rows(topic, runtime_checker)
    external_boundary = {
        "status": STATUS_EXTERNAL_RUNTIME_UNVERIFIED,
        "external_openclaw_runtime_live_verified": False,
        "external_runtime_checked": False,
        "closure_claim_allowed": False,
        "reason": "Repo-local mirror/runtime handoff readback only; external OpenClaw runtime was not probed.",
        "required_next_evidence": [
            "fresh external OpenClaw runtime invocation in the OpenClaw workspace",
            "run-state artifact produced by that invocation and copied into the governed evidence path",
            "separate checker proving the live run artifact before any closure claim",
        ],
    }
    rows_for_counts = [*artifacts, external_boundary]
    counts = status_counts(rows_for_counts)
    status = "passed" if local_mirror_ok and missing_count == 0 else "failed"
    runtime_problems = problem_rows(runtime_result, root)

    return {
        "contract_version": CONTRACT_VERSION,
        "generated_by": "scripts/checkers/check_r41_openclaw_mirror_runtime_manifest_readback.py",
        "status": status,
        "scope": "repo_local_openclaw_mirror_runtime_handoff_manifest_readback_no_external_runtime_probe",
        "topic": display_path(topic, root),
        "readback_state": {
            "local_mirror_status": STATUS_LOCAL_MIRROR_PASSED if local_mirror_ok else STATUS_LOCAL_MIRROR_FAILED,
            "local_mirror_passed": local_mirror_ok,
            "external_runtime_status": STATUS_EXTERNAL_RUNTIME_UNVERIFIED,
            "external_runtime_unverified": True,
            "missing_artifact_count": missing_count,
            "status_codes_seen": sorted(status for status, count in counts.items() if count),
        },
        "runtime_handoff_gate": {
            "status": STATUS_LOCAL_MIRROR_PASSED if runtime_result.ok else STATUS_LOCAL_MIRROR_FAILED,
            "mirror_line_rows": runtime_result.mirror_line_rows,
            "handoff_task_count": runtime_result.handoff_task_count,
            "implementation_doc_count": runtime_result.implementation_doc_count,
            "reference_file_count": runtime_result.reference_file_count,
            "problems": runtime_problems,
        },
        "handoff_manifest": {
            "status": STATUS_LOCAL_MIRROR_PASSED if all(row["status"] == STATUS_LOCAL_MIRROR_PASSED for row in handoff_rows) else STATUS_LOCAL_MIRROR_FAILED,
            "batch": runtime_checker.BATCH,
            "line_count": len(handoff_rows),
            "line_rows": handoff_rows,
        },
        "required_artifacts": artifacts,
        "external_runtime_boundary": external_boundary,
        "closure_claim_allowed": False,
        "gate_semantics": {
            "status_passed_means": (
                "R41 repo-local mirror artifacts and handoff manifest are present and "
                "read back consistently from repository-controlled files"
            ),
            "status_passed_does_not_mean": (
                "the external OpenClaw runtime has been executed, verified, sealed, "
                "or converted into a closure claim"
            ),
        },
        "assertions": [
            "runtime handoff gate returns local_mirror_passed",
            "handoff manifest contains two M tasks for each line A-F",
            "required repo-local artifacts do not return missing_artifact",
            "external runtime boundary remains external_runtime_unverified",
            "closure_claim_allowed=false",
        ],
        "failures": [
            *(f"runtime_handoff_gate: {problem['path']}: {problem['message']}" for problem in runtime_problems),
            *(f"missing artifact: {row['path']}" for row in artifacts if row["status"] == STATUS_MISSING_ARTIFACT),
        ],
    }


def write_outputs(out_dir: Path, root: Path, contract: dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "openclaw_mirror_runtime_manifest_readback.json").write_text(
        json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    handoff_rows = [
        "| {line} | {tasks} | {status} |".format(
            line=row["line"],
            tasks=", ".join(row["task_ids"]),
            status=row["status"],
        )
        for row in contract["handoff_manifest"]["line_rows"]
    ]
    artifact_rows_md = [
        "| {artifact_id} | {kind} | {status} |".format(
            artifact_id=row["artifact_id"],
            kind=row["kind"],
            status=row["status"],
        )
        for row in contract["required_artifacts"]
    ]
    readme = [
        "# Wave20 OpenClaw Mirror Runtime Manifest Readback",
        "",
        f"- status: `{contract['status']}`",
        f"- contract_version: `{contract['contract_version']}`",
        f"- scope: `{contract['scope']}`",
        f"- local_mirror_status: `{contract['readback_state']['local_mirror_status']}`",
        f"- external_runtime_status: `{contract['readback_state']['external_runtime_status']}`",
        f"- missing_artifact_count: `{contract['readback_state']['missing_artifact_count']}`",
        f"- closure_claim_allowed: `{str(bool(contract['closure_claim_allowed'])).lower()}`",
        "",
        "## Handoff Manifest Readback",
        "",
        "| line | task_ids | status |",
        "|---|---|---|",
        *handoff_rows,
        "",
        "## Required Artifact Readback",
        "",
        "| artifact_id | kind | status |",
        "|---|---|---|",
        *artifact_rows_md,
        "",
        "## External Runtime Boundary",
        "",
        f"- external_openclaw_runtime_live_verified: `{str(bool(contract['external_runtime_boundary']['external_openclaw_runtime_live_verified'])).lower()}`",
        f"- external_runtime_checked: `{str(bool(contract['external_runtime_boundary']['external_runtime_checked'])).lower()}`",
        f"- boundary_status: `{contract['external_runtime_boundary']['status']}`",
        "",
        "## Gate Semantics",
        "",
        f"- status passed means: {contract['gate_semantics']['status_passed_means']}",
        f"- status passed does not mean: {contract['gate_semantics']['status_passed_does_not_mean']}",
        "",
        "## Rerun",
        "",
        "```bash",
        f"python3 scripts/checkers/check_r41_openclaw_mirror_runtime_manifest_readback.py --out-dir {display_path(out_dir, root)}",
        "```",
        "",
        "Full deterministic output is in `openclaw_mirror_runtime_manifest_readback.json`.",
        "",
    ]
    (out_dir / "README.md").write_text("\n".join(readme), encoding="utf-8")


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    topic_arg = Path(args.topic) if args.topic else None
    topic = resolve_topic_path(root, topic_arg)
    out_arg = Path(args.out_dir)
    out_dir = out_arg if out_arg.is_absolute() else root / out_arg

    contract = build_contract(root=root, topic=topic)
    write_outputs(out_dir, root, contract)
    print(
        json.dumps(
            {
                "status": contract["status"],
                "contract_version": contract["contract_version"],
                "local_mirror_status": contract["readback_state"]["local_mirror_status"],
                "external_runtime_status": contract["readback_state"]["external_runtime_status"],
                "missing_artifact_count": contract["readback_state"]["missing_artifact_count"],
                "out_dir": display_path(out_dir, root),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if contract["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
