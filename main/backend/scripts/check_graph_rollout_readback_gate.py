#!/usr/bin/env python3
"""Gate Wave19 graph rollout readback without live DB or WebGL closure claims."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = SCRIPT_DIR.parents[0]
REPO_ROOT = BACKEND_ROOT.parents[1]
FRONTEND_ROOT = REPO_ROOT / "main" / "frontend-modern"

for path in (BACKEND_ROOT, SCRIPT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.services.graph.persistence.graph_node_live_db_rollout_gate import (  # noqa: E402
    build_graph_node_live_db_rollout_gate,
)
from app.services.graph.persistence.graph_node_rollout_manifest import (  # noqa: E402
    build_graph_node_rollout_manifest,
)
from app.services.graph.persistence.graph_projection_contract import (  # noqa: E402
    build_graph_projection_dry_run,
    build_graph_projection_rollout_readiness,
)
from app.settings.config import settings  # noqa: E402
from check_graph_projection_contract import (  # noqa: E402
    DEFAULT_MIGRATION_ROOT,
    _failure_isolation_checks,
    _fixture_graph,
    _migration_checks,
    _split_projects,
    _validate as _validate_projection_dry_run,
)
from check_graph_visual_data_smoke_gate import (  # noqa: E402
    build_gate_snapshot as build_visual_data_gate_snapshot,
    validate_gate_snapshot as validate_visual_data_gate_snapshot,
)


CONTRACT_VERSION = "graph.rollout_readback_gate.v1"

DEFAULT_SOURCE_DOCS = [
    "development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/2026-03-02-graph-node-standardization-a-then-b-plan/07_wave17-rollout-manifest-readback-2026-05-22.md",
    "development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-02-graph-3d-force-engine-parallel-migration/06_wave17-runtime-pixel-shape-gate-2026-05-22.md",
]

STAGE_ORDER = [
    "manifest_shape_readback",
    "projection_contract_readback",
    "rollback_ready_trace",
    "force3d_visual_boundary_readback",
]

MANIFEST_STAGE_ORDER = [
    "wave7_canonical_id_fixture",
    "wave10_pre_live_db_dry_run_readiness",
    "wave14_live_db_rollout_gate",
]


def _canonical_payload(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _digest(data: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_payload(data).encode("utf-8")).hexdigest()


def _stage(
    *,
    name: str,
    status: str,
    passed: bool,
    validated: bool,
    detail: str,
    gaps: list[str],
    failures: list[str] | None = None,
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "passed": bool(passed),
        "validated": bool(validated),
        "detail": detail,
        "gaps": gaps,
        "failures": failures or [],
        "metrics": metrics or {},
    }


def _read_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _contains_all(source: str, needles: tuple[str, ...]) -> bool:
    return all(needle in source for needle in needles)


def _manifest_shape_failures(manifest: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if manifest.get("contract_version") != "graph.node_rollout_manifest_readback.v1":
        failures.append("manifest contract_version mismatch")
    if manifest.get("status") != "ok":
        failures.append(f"manifest status must be ok, got {manifest.get('status')!r}")
    if manifest.get("deterministic_readback") is not True:
        failures.append("manifest deterministic_readback must be true")
    if manifest.get("closure_claim") is not False:
        failures.append("manifest closure_claim must remain false")
    if manifest.get("live_db_validated") is not False:
        failures.append("Wave19 pre-live gate must not mark live_db_validated")
    if manifest.get("live_db_closure_ready") is not False:
        failures.append("Wave19 pre-live gate must not mark live_db_closure_ready")
    if len(str(manifest.get("manifest_digest") or "")) != 64:
        failures.append("manifest_digest must be a sha256 hex digest")

    stages = manifest.get("stages")
    if not isinstance(stages, list):
        failures.append("manifest stages must be a list")
        stages = []
    stage_names = [stage.get("name") for stage in stages if isinstance(stage, dict)]
    if stage_names != MANIFEST_STAGE_ORDER:
        failures.append(f"manifest stage order mismatch: {stage_names}")

    for stage in stages:
        if not isinstance(stage, dict):
            failures.append("manifest stage must be an object")
            continue
        name = str(stage.get("name") or "<unknown>")
        if stage.get("deterministic") is not True:
            failures.append(f"{name}: deterministic must be true")
        if stage.get("closure_claim") is not False:
            failures.append(f"{name}: closure_claim must remain false")
        if stage.get("live_db_validated") is not False:
            failures.append(f"{name}: live_db_validated must remain false in this pre-live gate")

    if not manifest.get("remaining_live_db_gaps"):
        failures.append("pre-live manifest must retain remaining_live_db_gaps")
    return failures


def _projection_readback_failures(
    *,
    first_report: dict[str, Any],
    second_report: dict[str, Any],
    first_readiness: dict[str, Any],
    second_readiness: dict[str, Any],
) -> list[str]:
    failures = list(_validate_projection_dry_run(first_report))
    if _digest(first_report) != _digest(second_report):
        failures.append("projection dry-run digest changed across repeated readback")
    if _digest(first_readiness) != _digest(second_readiness):
        failures.append("projection readiness digest changed across repeated readback")
    if first_readiness.get("closure_claim") is not False:
        failures.append("projection readiness closure_claim must remain false")
    if first_readiness.get("live_db_validated") is not False:
        failures.append("projection readiness live_db_validated must remain false")
    if first_readiness.get("ready_for_live_db_dry_run") is not True:
        failures.append("projection readiness must be ready_for_live_db_dry_run in the default pre-live slice")
    failures.extend(
        f"readiness.{check.get('name')}: {check.get('detail')}"
        for check in first_readiness.get("checks", [])
        if isinstance(check, dict) and not check.get("passed")
    )
    if not first_readiness.get("live_db_gap"):
        failures.append("projection readiness must retain live_db_gap")
    return failures


def _force3d_rollback_checks(frontend_root: Path = FRONTEND_ROOT) -> dict[str, bool]:
    graph_page = _read_file(frontend_root / "src" / "pages" / "GraphPage.tsx")
    mode_switch = _read_file(frontend_root / "src" / "pages" / "graph" / "hooks" / "useGraphModeSwitch.ts")
    e2e = _read_file(frontend_root / "tests" / "e2e" / "graphpage.spec.ts")
    runtime_gate = _read_file(frontend_root / "tests" / "e2e" / "graph-runtime-pixel-gate.spec.ts")
    return {
        "force3d_load_and_render_fallback_to_legacy": _contains_all(
            graph_page,
            (
                "handleForceGraphRenderError",
                "requestProjectionEngineChange('legacy')",
                "3D引擎渲染失败，已自动降级到 legacy-projection",
                "3D引擎加载失败，已自动降级到 legacy-projection",
            ),
        ),
        "force3d_manual_engine_switch_available": _contains_all(
            graph_page,
            (
                '<option value="legacy">legacy-projection</option>',
                '<option value="force3d">react-force-graph-3d</option>',
            ),
        )
        and _contains_all(
            mode_switch,
            (
                "export type ProjectionEngine = 'legacy' | 'force3d'",
                "requestProjectionEngineChange",
                "window.clearTimeout(projectionEngineSwitchTimerRef.current)",
            ),
        ),
        "force3d_switch_readback_covered_by_mocked_e2e": _contains_all(
            e2e,
            (
                "graph page survives rapid 3D engine switch with viewport evidence or fallback",
                "selectOption('legacy')",
                "selectOption('force3d')",
                "已自动降级到 legacy-projection",
            ),
        ),
        "runtime_pixel_gate_has_fallback_data_framing": _contains_all(
            runtime_gate,
            (
                "fallback-data-framing",
                "tenantDbRequired: false",
                "externalGpuRequired: false",
            ),
        ),
    }


def _rollback_ready_trace(
    *,
    failure_isolation_checks: dict[str, bool],
    force3d_rollback_checks: dict[str, bool],
) -> dict[str, Any]:
    steps = [
        {
            "name": "graph_b_write_shadow_failure",
            "trigger": "B projection shadow write raises while serving graph response",
            "rollback_action": "rollback graph_b_write session and continue A response",
            "readback_anchor": "admin_shadow_write_rollback_and_continue",
            "ready": bool(failure_isolation_checks.get("admin_shadow_write_rollback_and_continue")),
        },
        {
            "name": "graph_b_read_canary_failure",
            "trigger": "B projection read path raises in b_canary or b_primary",
            "rollback_action": "rollback graph_b_read session and fall back to A graph read",
            "readback_anchor": "admin_b_read_fallback_to_a",
            "ready": bool(failure_isolation_checks.get("admin_b_read_fallback_to_a")),
        },
        {
            "name": "graph_node_backfill_apply_failure",
            "trigger": "graph node backfill apply path raises after opening a transaction",
            "rollback_action": "rollback backfill session and re-raise for operator visibility",
            "readback_anchor": "backfill_apply_rollback_on_failure",
            "ready": bool(failure_isolation_checks.get("backfill_apply_rollback_on_failure")),
        },
        {
            "name": "force3d_load_or_render_failure",
            "trigger": "react-force-graph-3d load or render boundary fails",
            "rollback_action": "switch projection engine to legacy-projection and keep GraphPage usable",
            "readback_anchor": "force3d_load_and_render_fallback_to_legacy",
            "ready": bool(force3d_rollback_checks.get("force3d_load_and_render_fallback_to_legacy")),
        },
        {
            "name": "force3d_manual_switch_or_mocked_readback",
            "trigger": "operator or mocked gate needs to compare force3d and legacy framing",
            "rollback_action": "keep legacy/force3d selector and mocked fallback-data-framing evidence available",
            "readback_anchor": "force3d_manual_engine_switch_available+runtime_pixel_gate_has_fallback_data_framing",
            "ready": bool(force3d_rollback_checks.get("force3d_manual_engine_switch_available"))
            and bool(force3d_rollback_checks.get("force3d_switch_readback_covered_by_mocked_e2e"))
            and bool(force3d_rollback_checks.get("runtime_pixel_gate_has_fallback_data_framing")),
        },
    ]
    failures = [step["readback_anchor"] for step in steps if not step["ready"]]
    payload = {
        "trace_version": "graph.rollback_ready_trace.v1",
        "closure_claim": False,
        "live_db_validated": False,
        "webgl_live_visual_validated": False,
        "steps": steps,
    }
    return {
        **payload,
        "trace_digest": _digest(payload),
        "failures": failures,
    }


def build_gate_snapshot(
    *,
    read_mode: str = "b_canary",
    write_mode: str = "shadow",
    canary_projects: list[str] | tuple[str, ...] | set[str] | None = None,
    backfill_dry_run: bool = True,
    backfill_limit: int | None = 10,
    max_dry_run_limit: int = 1000,
    migration_root: Path = DEFAULT_MIGRATION_ROOT,
    database_url: str | None = None,
    source_docs: list[str] | tuple[str, ...] | None = None,
    migration_checks: dict[str, bool] | None = None,
    failure_isolation_checks: dict[str, bool] | None = None,
    force3d_rollback_checks: dict[str, bool] | None = None,
    visual_gate_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic pre-live rollout/readback gate.

    This gate composes existing graph rollout evidence but intentionally does
    not open a tenant DB, run backfill against tenant data, or prove WebGL live
    rendering. Those remain explicit gaps in the returned snapshot.
    """
    no_db_first = build_graph_projection_dry_run(_fixture_graph())
    no_db_second = build_graph_projection_dry_run(_fixture_graph())
    migrations = migration_checks if migration_checks is not None else _migration_checks(Path(migration_root))
    isolation = failure_isolation_checks if failure_isolation_checks is not None else _failure_isolation_checks()
    projects = sorted({str(project).strip() for project in (canary_projects or ["demo_proj"]) if str(project).strip()})
    readiness_first = build_graph_projection_rollout_readiness(
        read_mode=read_mode,
        write_mode=write_mode,
        canary_projects=projects,
        backfill_dry_run=backfill_dry_run,
        backfill_limit=backfill_limit,
        migration_checks=migrations,
        failure_isolation_checks=isolation,
        max_dry_run_limit=max_dry_run_limit,
    )
    readiness_second = build_graph_projection_rollout_readiness(
        read_mode=read_mode,
        write_mode=write_mode,
        canary_projects=projects,
        backfill_dry_run=backfill_dry_run,
        backfill_limit=backfill_limit,
        migration_checks=migrations,
        failure_isolation_checks=isolation,
        max_dry_run_limit=max_dry_run_limit,
    )
    live_db_gate = build_graph_node_live_db_rollout_gate(
        no_db_report=no_db_first,
        readiness_report=readiness_first,
        database_url=database_url,
        live_db_evidence=None,
    )
    manifest = build_graph_node_rollout_manifest(
        no_db_report=no_db_first,
        readiness_report=readiness_first,
        gate_report=live_db_gate,
        source_docs=[*(source_docs or DEFAULT_SOURCE_DOCS)],
    )

    manifest_dict = manifest.to_dict()
    manifest_failures = _manifest_shape_failures(manifest_dict)
    manifest_stage = _stage(
        name="manifest_shape_readback",
        status="passed" if not manifest_failures else "failed",
        passed=not manifest_failures,
        validated=not manifest_failures,
        detail=(
            f"manifest_id={manifest.manifest_id} stages={len(manifest.stages)} "
            f"digest={manifest.manifest_digest[:12]}"
        ),
        gaps=list(manifest.remaining_live_db_gaps),
        failures=manifest_failures,
        metrics={
            "manifest_id": manifest.manifest_id,
            "manifest_digest": manifest.manifest_digest,
            "manifest_stage_order": [stage.name for stage in manifest.stages],
        },
    )

    projection_failures = _projection_readback_failures(
        first_report=no_db_first.to_dict(),
        second_report=no_db_second.to_dict(),
        first_readiness=readiness_first.to_dict(),
        second_readiness=readiness_second.to_dict(),
    )
    projection_stage = _stage(
        name="projection_contract_readback",
        status="passed" if not projection_failures else "failed",
        passed=not projection_failures,
        validated=not projection_failures,
        detail=(
            f"read_mode={readiness_first.read_mode} write_mode={readiness_first.write_mode} "
            f"ready_for_live_db_dry_run={readiness_first.ready_for_live_db_dry_run}"
        ),
        gaps=list(readiness_first.live_db_gap),
        failures=projection_failures,
        metrics={
            "projection_digest": _digest(no_db_first.to_dict()),
            "readiness_digest": _digest(readiness_first.to_dict()),
            "unique_node_count": no_db_first.unique_node_count,
            "writeable_edge_count": no_db_first.writeable_edge_count,
            "unresolved_edge_count": no_db_first.unresolved_edge_count,
        },
    )

    trace = _rollback_ready_trace(
        failure_isolation_checks=isolation,
        force3d_rollback_checks=force3d_rollback_checks
        if force3d_rollback_checks is not None
        else _force3d_rollback_checks(),
    )
    rollback_stage = _stage(
        name="rollback_ready_trace",
        status="passed" if not trace["failures"] else "failed",
        passed=not trace["failures"],
        validated=not trace["failures"],
        detail=f"rollback trace steps={len(trace['steps'])} digest={trace['trace_digest'][:12]}",
        gaps=[] if not trace["failures"] else ["restore rollback/fallback anchors before live rollout"],
        failures=list(trace["failures"]),
        metrics={
            "trace_digest": trace["trace_digest"],
            "trace_steps": [step["name"] for step in trace["steps"]],
        },
    )

    visual_snapshot = visual_gate_snapshot if visual_gate_snapshot is not None else build_visual_data_gate_snapshot()
    visual_failures = validate_visual_data_gate_snapshot(visual_snapshot)
    if visual_snapshot.get("live_ui_smoke_validated") is True:
        visual_failures.append("Wave19 pre-live gate must not mark live_ui_smoke_validated")
    if visual_snapshot.get("closure_claim") is not False:
        visual_failures.append("visual smoke gate closure_claim must remain false")
    visual_stage = _stage(
        name="force3d_visual_boundary_readback",
        status="passed" if not visual_failures else "failed",
        passed=not visual_failures,
        validated=not visual_failures,
        detail=(
            f"visual_readiness_state={visual_snapshot.get('readiness_state')} "
            f"live_ui_smoke_validated={visual_snapshot.get('live_ui_smoke_validated')}"
        ),
        gaps=list(visual_snapshot.get("remaining_gaps") or []),
        failures=visual_failures,
        metrics={
            "visual_contract_version": visual_snapshot.get("contract_version"),
            "fixture_smoke_validated": visual_snapshot.get("fixture_smoke_validated"),
            "backend_data_visual_smoke_validated": visual_snapshot.get("backend_data_visual_smoke_validated"),
            "live_ui_smoke_validated": visual_snapshot.get("live_ui_smoke_validated"),
        },
    )

    stages = [manifest_stage, projection_stage, rollback_stage, visual_stage]
    failures = [failure for stage in stages for failure in stage["failures"]]
    payload = {
        "contract_version": CONTRACT_VERSION,
        "status": "passed" if not failures else "failed",
        "readiness_state": "pre_live_rollout_readback_ready" if not failures else "blocked",
        "closure_claim": False,
        "live_tenant_db_validated": False,
        "webgl_live_visual_validated": False,
        "manifest_digest": manifest.manifest_digest,
        "projection_digest": projection_stage["metrics"]["projection_digest"],
        "rollback_trace_digest": trace["trace_digest"],
        "source_docs": sorted({str(doc).strip() for doc in (source_docs or DEFAULT_SOURCE_DOCS) if str(doc).strip()}),
        "stages": stages,
        "rollback_trace": trace,
        "remaining_live_gaps": sorted({gap for stage in stages for gap in stage["gaps"]}),
    }
    validation_failures = validate_gate_snapshot(payload)
    if validation_failures:
        payload = {
            **payload,
            "status": "failed",
            "readiness_state": "blocked",
            "validation_failures": validation_failures,
        }
    return payload


def validate_gate_snapshot(snapshot: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if snapshot.get("contract_version") != CONTRACT_VERSION:
        failures.append("unexpected contract_version")
    if snapshot.get("closure_claim") is not False:
        failures.append("closure_claim must remain false")
    if snapshot.get("live_tenant_db_validated") is not False:
        failures.append("live_tenant_db_validated must remain false for this pre-live gate")
    if snapshot.get("webgl_live_visual_validated") is not False:
        failures.append("webgl_live_visual_validated must remain false for this pre-live gate")

    stages = snapshot.get("stages")
    if not isinstance(stages, list):
        failures.append("stages must be a list")
        stages = []
    stage_names = [stage.get("name") for stage in stages if isinstance(stage, dict)]
    if stage_names != STAGE_ORDER:
        failures.append(f"stage order mismatch: {stage_names}")
    for stage in stages:
        if not isinstance(stage, dict):
            failures.append("stage must be an object")
            continue
        if stage.get("passed") is not True:
            failures.extend(str(failure) for failure in stage.get("failures") or [f"{stage.get('name')} did not pass"])
    trace = snapshot.get("rollback_trace")
    if not isinstance(trace, dict):
        failures.append("rollback_trace must be an object")
    else:
        if trace.get("closure_claim") is not False:
            failures.append("rollback_trace closure_claim must remain false")
        steps = trace.get("steps")
        if not isinstance(steps, list) or len(steps) != 5:
            failures.append("rollback_trace must contain five ordered steps")
        elif any(step.get("ready") is not True for step in steps if isinstance(step, dict)):
            failures.append("rollback_trace contains unready steps")
        if len(str(trace.get("trace_digest") or "")) != 64:
            failures.append("rollback_trace digest must be a sha256 hex digest")

    remaining = " ".join(str(gap) for gap in snapshot.get("remaining_live_gaps") or [])
    if "live tenant" not in remaining and "tenant DB" not in remaining:
        failures.append("remaining_live_gaps must retain live tenant DB boundary")
    if "live UI" not in remaining and "GraphPage" not in remaining:
        failures.append("remaining_live_gaps must retain live UI/WebGL boundary")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check Wave19 graph rollout/readback gate without live DB or WebGL closure claims"
    )
    parser.add_argument("--format", choices=("json", "text"), default="json")
    parser.add_argument("--database-url", default=str(settings.database_url or ""))
    parser.add_argument("--read-mode", default=str(settings.graph_node_projection_read_mode or "b_canary"))
    parser.add_argument("--write-mode", default=str(settings.graph_node_projection_write_mode or "shadow"))
    parser.add_argument("--canary-projects", default=str(settings.graph_node_projection_canary_projects or "demo_proj"))
    parser.add_argument("--backfill-limit", type=int, default=10)
    parser.add_argument("--max-dry-run-limit", type=int, default=1000)
    parser.add_argument("--backfill-apply", action="store_true", help="validate apply-mode readiness; should fail pre-live")
    parser.add_argument("--migration-root", default=str(DEFAULT_MIGRATION_ROOT))
    args = parser.parse_args()

    snapshot = build_gate_snapshot(
        read_mode=args.read_mode,
        write_mode=args.write_mode,
        canary_projects=_split_projects(args.canary_projects),
        backfill_dry_run=not args.backfill_apply,
        backfill_limit=args.backfill_limit,
        max_dry_run_limit=args.max_dry_run_limit,
        migration_root=Path(args.migration_root),
        database_url=args.database_url,
    )

    if args.format == "json":
        print(json.dumps(snapshot, ensure_ascii=False, sort_keys=True))
    else:
        print(f"status={snapshot['status']}")
        print(f"readiness_state={snapshot['readiness_state']}")
        print(f"closure_claim={snapshot['closure_claim']}")
        print(f"live_tenant_db_validated={snapshot['live_tenant_db_validated']}")
        print(f"webgl_live_visual_validated={snapshot['webgl_live_visual_validated']}")
        print(f"manifest_digest={snapshot['manifest_digest']}")
        print(f"projection_digest={snapshot['projection_digest']}")
        print(f"rollback_trace_digest={snapshot['rollback_trace_digest']}")
        for stage in snapshot["stages"]:
            print(f"{stage['name']}={stage['status']} validated={stage['validated']}")
        if snapshot["remaining_live_gaps"]:
            print("remaining_live_gaps:")
            for gap in snapshot["remaining_live_gaps"]:
                print(f"- {gap}")
        if snapshot.get("validation_failures"):
            print("validation_failures:")
            for failure in snapshot["validation_failures"]:
                print(f"- {failure}")

    return 0 if snapshot["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
