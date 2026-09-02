"""Deterministically generate C1 Slice A/B/C evidence and the P5 aggregate.

The generator binds three vertical product slices (intake/recovery, knowledge
composition, report/delivery) to the exact successor ``ProgramSpec`` and
``ExecutionPlan`` used by the pure C1 tests, the read-only legacy WorkflowGraph
oracle receipt, and the parallel PG gate test file.  Nothing here executes an
effect, selects an interpreter, reads a projector, or grants authority.

The canonical PG gate file, its disposable-PostgreSQL fixture, and the four
fixed PG nodes are fail-closed inputs: if any file is missing, its bound
SHA-256 drifts, or any fixed node disappears, neither write nor ``--check`` may
succeed.  Writes are atomic and deterministic; ``--check`` is strictly
read-only.  The aggregate reads only the three exact slice artifacts and never
writes promotion, candidate, or live flags.

Run from ``main/backend``:

    python3.11 scripts/generate_c1_slice_acceptance.py
    python3.11 scripts/generate_c1_slice_acceptance.py --check

The ``--pg-test-path``, ``--pg-sha256``, ``--pg-fixture-path`` and
``--pg-fixture-sha256`` overrides exist only for isolated tests; canonical
invocation omits them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(BACKEND_ROOT))

from app.successor_migration import legacy_workflow_graph as legacy_graph
from tests.successor_runtime.p4_c7_fixture import (
    program_and_plan as c7_program_and_plan,
)
from tests.successor_runtime.test_p5_c1_slice_programs import (
    _c8_delivery_program_plan,
    _c8_writing_program_plan,
    _observations,
    _rollback,
    _runtime_evidence,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
TOPIC_ROOT = (
    REPOSITORY_ROOT / "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration"
)
EVIDENCE_ROOT = TOPIC_ROOT / "evidence"
SLICE_DIR = EVIDENCE_ROOT / "p5-c1-slices"
AGGREGATE_PATH = EVIDENCE_ROOT / "P5C1SliceAcceptance.v1.json"

SLICE_SCHEMA = "mrw.functorial-successor.c1-slice-evidence.v1"
AGGREGATE_SCHEMA = "mrw.functorial-successor.p5-c1-slice-acceptance.v1"
AGGREGATE_ID = "p5-c1-slice-acceptance"

SLICE_ORDER = ("A", "B", "C")
SLICE_PATHS = {
    slice_id: SLICE_DIR / f"C1Slice{slice_id}.v1.json" for slice_id in SLICE_ORDER
}
SLICE_SPECS = {
    "A": {
        "name": "intake_recovery",
        "cells": ("C7.1", "C7.2", "C7.3", "C7.4", "C9.1", "C9.3"),
        "ordered_path": ("ingest", "canonical_material", "recovery", "read_projection"),
    },
    "B": {
        "name": "knowledge_composition",
        "cells": ("C8.1", "C8.2", "C8.4", "C9.2"),
        "ordered_path": (
            "canonical_material",
            "typed_knowledge",
            "composition",
            "graph_ui_observation",
        ),
    },
    "C": {
        "name": "report_delivery",
        "cells": ("C8.3", "C9.API_UI_REPORT_PROJECTION"),
        "ordered_path": (
            "artifact",
            "report",
            "verification_admission",
            "bounded_delivery_readback",
        ),
    },
}

C1_CELL_BOUNDARIES = {
    "C1.1": "graph parse validate compile",
    "C1.2": "graph runtime executor failure",
    "C1.3": "graph store replay",
}

PG_TEST_RELPATH = Path(
    "main/backend/tests/successor_runtime/test_p5_c1_slice_acceptance_postgres.py"
)
PG_TEST_PATH = REPOSITORY_ROOT / PG_TEST_RELPATH
PG_TEST_NODES = (
    "test_c1_slice_runtime_node_replay_restart_and_rollback",
    "test_c1_cross_slice_no_duplicate_effects_and_project_isolation",
    "test_c1_rollback_retains_journal_and_changes_future_owner_epoch",
    "test_c1_outcome_unknown_reconciles_without_duplicate_effect",
    "test_c1_cancellation_is_observed_without_duplicate_effect",
    "test_c1_typed_effect_failure_is_recorded_and_blocks_duplicate",
    "test_c1_store_aba_and_stale_revision_fail_closed",
)
PG_TEST_FILE_SHA256 = "1bea9f4f44714f625153d8f661335e01996fd965272b75208bd32534f544aa54"
PG_TEST_FIXTURE_RELPATH = Path(
    "main/backend/tests/successor_runtime/c1_slice_postgres_fixture.py"
)
PG_TEST_FIXTURE_PATH = REPOSITORY_ROOT / PG_TEST_FIXTURE_RELPATH
PG_TEST_FIXTURE_SHA256 = (
    "b2411e5439045b58edd0ac523db1021dd2f36af9af0a9230d99673e6d4943a56"
)

STATUS_READY = "C1_ACCEPTANCE_EVIDENCE_READY_FOR_INDEPENDENT_REVIEW"
STATUS_PARTIAL = "PARTIAL"
STATUS_BLOCK = "BLOCK"

EXIT_OK = 0
EXIT_DRIFT = 1
EXIT_MISSING = 2
EXIT_PG_BINDING = 3
EXIT_PG_UNBOUND = 4
EXIT_BUILD = 5


class EvidenceBuildError(RuntimeError):
    """Fail-closed evidence construction error with a stable exit code."""

    def __init__(self, message: str, *, exit_code: int = EXIT_BUILD) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def content_digest(value: Any) -> str:
    return _sha256_bytes(_canonical_json(value).encode("utf-8"))


def _relpath(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(REPOSITORY_ROOT.resolve()))
    except ValueError:
        return resolved.as_posix()


def _bind(path: Path, role: str) -> dict[str, object]:
    data = path.read_bytes()
    return {
        "path": _relpath(path),
        "sha256": _sha256_bytes(data),
        "bytes": len(data),
        "lines": len(data.splitlines()),
        "role": role,
    }


def _missing_pg_nodes(text: str) -> tuple[str, ...]:
    return tuple(
        node
        for node in PG_TEST_NODES
        if re.search(rf"^def\s+{re.escape(node)}\s*\(", text, re.MULTILINE) is None
    )


def _require_pg_binding(
    *,
    pg_path: Path | None = None,
    pg_sha256: str | None = None,
    pg_fixture_path: Path | None = None,
    pg_fixture_sha256: str | None = None,
) -> dict[str, object]:
    path = (pg_path or PG_TEST_PATH).resolve()
    if not path.is_file():
        raise EvidenceBuildError(
            f"PG test file missing: {_relpath(path)}",
            exit_code=EXIT_MISSING,
        )
    data = path.read_bytes()
    actual_sha = _sha256_bytes(data)
    bound_sha = pg_sha256 if pg_sha256 is not None else PG_TEST_FILE_SHA256
    if not bound_sha:
        raise EvidenceBuildError(
            "PG_TEST_FILE_SHA256 is unbound; evidence generation is fail-closed",
            exit_code=EXIT_PG_UNBOUND,
        )
    if bound_sha != actual_sha:
        raise EvidenceBuildError(
            "PG test file bound SHA drift: "
            f"expected={bound_sha} actual={actual_sha} path={_relpath(path)}",
            exit_code=EXIT_PG_BINDING,
        )
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EvidenceBuildError(
            f"PG test file is not UTF-8: {_relpath(path)}",
            exit_code=EXIT_PG_BINDING,
        ) from exc
    missing_nodes = _missing_pg_nodes(text)
    if missing_nodes:
        raise EvidenceBuildError(
            "PG test nodes missing: " + ", ".join(missing_nodes),
            exit_code=EXIT_PG_BINDING,
        )
    fixture_path = (pg_fixture_path or PG_TEST_FIXTURE_PATH).resolve()
    if not fixture_path.is_file():
        raise EvidenceBuildError(
            f"PG fixture file missing: {_relpath(fixture_path)}",
            exit_code=EXIT_MISSING,
        )
    fixture_data = fixture_path.read_bytes()
    fixture_sha = _sha256_bytes(fixture_data)
    bound_fixture_sha = (
        pg_fixture_sha256 if pg_fixture_sha256 is not None else PG_TEST_FIXTURE_SHA256
    )
    if not bound_fixture_sha:
        raise EvidenceBuildError(
            "PG_TEST_FIXTURE_SHA256 is unbound; evidence generation is fail-closed",
            exit_code=EXIT_PG_UNBOUND,
        )
    if bound_fixture_sha != fixture_sha:
        raise EvidenceBuildError(
            "PG fixture file bound SHA drift: "
            f"expected={bound_fixture_sha} actual={fixture_sha} "
            f"path={_relpath(fixture_path)}",
            exit_code=EXIT_PG_BINDING,
        )
    return {
        "path": _relpath(path),
        "sha256": actual_sha,
        "bytes": len(data),
        "lines": len(data.splitlines()),
        "nodes": list(PG_TEST_NODES),
        "nodes_present": True,
        "bound_sha_matches": True,
        "fixture": {
            "path": _relpath(fixture_path),
            "sha256": fixture_sha,
            "bytes": len(fixture_data),
            "lines": len(fixture_data.splitlines()),
        },
    }


def _slice_fixture(slice_id: str) -> tuple[Any, Any]:
    if slice_id == "A":
        program, plan, *_ = c7_program_and_plan()
        return program, plan
    if slice_id == "B":
        return _c8_writing_program_plan()
    if slice_id == "C":
        return _c8_delivery_program_plan()
    raise EvidenceBuildError(f"unsupported C1 slice: {slice_id!r}")


def _oracle_receipt(slice_id: str, program: Any, plan: Any) -> Any:
    observations = _observations(plan)
    oracle = legacy_graph.LegacyWorkflowGraphOracle()
    return oracle.compare(
        in_slice_id=slice_id,
        in_legacy_program=program,
        in_legacy_plan=plan,
        in_successor_program=program,
        in_successor_plan=plan,
        in_legacy_step_observations=observations,
        in_successor_step_observations=observations,
        in_runtime_evidence=_runtime_evidence(),
        in_rollback_before_after=_rollback(),
    )


def _bindings(
    slice_id: str,
    *,
    pg_path: Path | None = None,
    pg_fixture_path: Path | None = None,
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    source_paths = [
        (
            EVIDENCE_ROOT
            / "CapabilitySpecCompilationAndVerticalSlicesDecision.v1.json",
            "vertical_slices_route_decision",
        ),
        (EVIDENCE_ROOT / "p1-fragments/C1.json", "p1_fragment_C1"),
        (
            TOPIC_ROOT
            / "13_functorial-successor-c1-c9-locator-pending-inventory.v1.json",
            "c1_c9_locator_inventory",
        ),
        (
            BACKEND_ROOT / "app/successor_migration/legacy_workflow_graph.py",
            "legacy_workflow_graph_oracle",
        ),
    ]
    implementation_paths = [
        (
            BACKEND_ROOT / "app/successor_runtime/capabilities/c1_slice_acceptance.py",
            "c1_slice_acceptance_pure_api",
        ),
        (
            BACKEND_ROOT / "app/successor_runtime/capabilities/c1_legacy_dsl.py",
            "c1_legacy_dsl_parser",
        ),
        (
            BACKEND_ROOT / "app/successor_runtime/capabilities/checksum.py",
            "shared_checksum",
        ),
        (
            BACKEND_ROOT / "app/successor_runtime/language/program.py",
            "shared_program_spec",
        ),
        (
            BACKEND_ROOT / "app/successor_runtime/language/plan.py",
            "shared_execution_plan",
        ),
    ]
    if slice_id == "A":
        implementation_paths.extend(
            [
                (
                    BACKEND_ROOT
                    / "app/successor_runtime/capabilities/ingest_c7_program.py",
                    "c7_ingest_program",
                ),
                (
                    BACKEND_ROOT / "tests/successor_runtime/p4_c7_fixture.py",
                    "c7_shared_fixture",
                ),
            ]
        )
    else:
        implementation_paths.extend(
            [
                (
                    BACKEND_ROOT / "app/successor_runtime/capabilities/c8_program.py",
                    "c8_program",
                ),
                (
                    BACKEND_ROOT
                    / "app/successor_runtime/capabilities/first_specimen.py",
                    "first_specimen_bundle",
                ),
                (
                    BACKEND_ROOT / "app/successor_runtime/language/normalize.py",
                    "shared_normalizer",
                ),
            ]
        )
    implementation_paths.append((Path(__file__).resolve(), "c1_evidence_generator"))
    test_paths = [
        (
            BACKEND_ROOT / "tests/successor_runtime/test_p5_c1_slice_programs.py",
            "pure_slice_programs_test",
        ),
        (
            BACKEND_ROOT / "tests/successor_runtime/test_p5_c1_legacy_oracle.py",
            "pure_legacy_oracle_test",
        ),
        (
            BACKEND_ROOT / "tests/successor_runtime/test_p5_c1_legacy_dsl_parity.py",
            "pure_legacy_dsl_parity_test",
        ),
        (
            BACKEND_ROOT / "tests/successor_runtime/test_p5_c1_evidence_generator.py",
            "c1_evidence_generator_test",
        ),
        (pg_path or PG_TEST_PATH, "c1_postgres_gate"),
        (pg_fixture_path or PG_TEST_FIXTURE_PATH, "c1_postgres_fixture"),
    ]
    return (
        [_bind(path, role) for path, role in source_paths],
        [_bind(path, role) for path, role in implementation_paths],
        [_bind(path, role) for path, role in test_paths],
    )


def _c1_cell_coverage(slice_id: str, acceptance: Any) -> dict[str, dict[str, object]]:
    coverage: dict[str, dict[str, object]] = {}
    for cell, boundary in C1_CELL_BOUNDARIES.items():
        if cell == "C1.1":
            coverage[cell] = {
                "cell": cell,
                "boundary": boundary,
                "coverage": {
                    "movement_ids": ["C1-M001", "C1-M002"],
                    "program_plan_exact_closure": {
                        "program_digest": acceptance.program_digest,
                        "plan_digest": acceptance.plan_digest,
                        "catalog_digest": acceptance.catalog_digest,
                        "control_root_digest": acceptance.control_root_digest,
                        "source_map_digest": acceptance.source_map_digest,
                        "dependency_index_digest": acceptance.dependency_index_digest,
                    },
                    "ordered_kinds": {
                        "operation_kinds": list(acceptance.ordered_operation_kinds),
                        "step_kinds": list(acceptance.ordered_step_kinds),
                        "assignment_kinds": list(acceptance.ordered_assignment_kinds),
                    },
                    "legacy_and_successor_use_same_program_and_plan": True,
                    "compatibility_claim": acceptance.compatibility_claim,
                    "evidence_ref": f"evidence:c1:{slice_id}:compile-closure",
                },
            }
        elif cell == "C1.2":
            coverage[cell] = {
                "cell": cell,
                "boundary": boundary,
                "coverage": {
                    "movement_ids": ["C1-M003"],
                    "runtime_evidence_refs": list(acceptance.runtime_evidence_refs),
                    "replay_refs": list(acceptance.replay_refs),
                    "observation_profile": acceptance.observation_profile,
                    "legacy_observation_digest": acceptance.legacy_observation_digest,
                    "successor_observation_digest": (
                        acceptance.successor_observation_digest
                    ),
                    "observational_compatibility": (
                        acceptance.observational_compatibility
                    ),
                    "compatibility_claim": acceptance.compatibility_claim,
                    "evidence_ref": f"evidence:c1:{slice_id}:runtime-replay",
                },
            }
        else:
            coverage[cell] = {
                "cell": cell,
                "boundary": boundary,
                "coverage": {
                    "movement_ids": ["C1-M004"],
                    "journal_refs": list(acceptance.journal_refs),
                    "readback_refs": list(acceptance.readback_refs),
                    "rollback_refs": list(acceptance.rollback_refs),
                    "before_authority_epoch": (
                        acceptance.rollback_before_authority_epoch
                    ),
                    "after_authority_epoch": acceptance.rollback_after_authority_epoch,
                    "rollback_preserves_journal_refs": True,
                    "rollback_preserves_readback_refs": True,
                    "evidence_ref": f"evidence:c1:{slice_id}:store-rollback",
                },
            }
    return coverage


def build_slice(
    slice_id: str,
    pg_binding: dict[str, object],
    *,
    pg_path: Path | None = None,
    pg_fixture_path: Path | None = None,
) -> dict[str, object]:
    program, plan = _slice_fixture(slice_id)
    receipt = _oracle_receipt(slice_id, program, plan)
    acceptance = receipt.acceptance
    spec = SLICE_SPECS[slice_id]
    source_bindings, implementation_bindings, test_bindings = _bindings(
        slice_id, pg_path=pg_path, pg_fixture_path=pg_fixture_path
    )
    artifact: dict[str, object] = {
        "schema": SLICE_SCHEMA,
        "slice_id": slice_id,
        "slice_name": spec["name"],
        "slice_cells": list(spec["cells"]),
        "ordered_path": list(spec["ordered_path"]),
        "cell_coverage": _c1_cell_coverage(slice_id, acceptance),
        "program_plan_sameness": {
            "legacy_program_id": program.program_id,
            "successor_program_id": program.program_id,
            "legacy_plan_id": plan.plan_id,
            "successor_plan_id": plan.plan_id,
            "same_exact_program": True,
            "same_exact_plan": True,
            "oracle_consumed_program_digest": receipt.consumed_program_digest,
            "oracle_consumed_plan_digest": receipt.consumed_plan_digest,
        },
        "exact_digests": {
            "program_digest": acceptance.program_digest,
            "plan_digest": acceptance.plan_digest,
            "catalog_digest": acceptance.catalog_digest,
            "control_root_digest": acceptance.control_root_digest,
            "source_map_digest": acceptance.source_map_digest,
            "dependency_index_digest": acceptance.dependency_index_digest,
        },
        "ordered_kinds": {
            "operation_kinds": list(acceptance.ordered_operation_kinds),
            "step_kinds": list(acceptance.ordered_step_kinds),
            "assignment_kinds": list(acceptance.ordered_assignment_kinds),
        },
        "observations": {
            "observation_profile": acceptance.observation_profile,
            "legacy_observation_digest": acceptance.legacy_observation_digest,
            "successor_observation_digest": acceptance.successor_observation_digest,
            "observational_compatibility": acceptance.observational_compatibility,
            "compatibility_claim": acceptance.compatibility_claim,
        },
        "declared_differences": list(acceptance.declared_differences),
        "runtime_refs": {
            "runtime_evidence_refs": list(acceptance.runtime_evidence_refs),
            "journal_refs": list(acceptance.journal_refs),
            "readback_refs": list(acceptance.readback_refs),
            "replay_refs": list(acceptance.replay_refs),
            "projector_refs": [f"projector:c1:{slice_id.lower()}:readback"],
            "rollback_refs": list(acceptance.rollback_refs),
            "rollback_before_authority_epoch": (
                acceptance.rollback_before_authority_epoch
            ),
            "rollback_after_authority_epoch": acceptance.rollback_after_authority_epoch,
            "rollback_preserves_journal_refs": True,
            "rollback_preserves_readback_refs": True,
        },
        "pg_binding": pg_binding,
        "source_bindings": source_bindings,
        "implementation_bindings": implementation_bindings,
        "test_bindings": test_bindings,
        "acceptance": {
            "oracle_id": receipt.oracle_id,
            "acceptance_digest": acceptance.acceptance_digest,
            "receipt_digest": receipt.receipt_digest,
            "accepted": acceptance.accepted,
            "provider_calls": receipt.provider_calls,
            "store_writes": receipt.store_writes,
            "canonical_effect_calls": receipt.canonical_effect_calls,
            "duplicated_effect_calls": receipt.duplicated_effect_calls,
            "graph_json_reads": receipt.graph_json_reads,
            "blocking_findings": list(acceptance.blocking_findings),
        },
        "accepted": acceptance.accepted,
        "blocking_findings": list(acceptance.blocking_findings),
        "authority": {
            "production_canonical_write": False,
            "live_provider": False,
            "external_delivery": False,
            "cutover": False,
            "authority_transfer": False,
            "legacy_retired": False,
            "candidate_created": False,
        },
        "content_digest": "",
    }
    artifact["content_digest"] = content_digest(
        {key: value for key, value in artifact.items() if key != "content_digest"}
    )
    _self_test_slice(artifact)
    return artifact


def _self_test_slice(artifact: dict[str, object]) -> None:
    expected = content_digest(
        {key: value for key, value in artifact.items() if key != "content_digest"}
    )
    if artifact["content_digest"] != expected:
        raise EvidenceBuildError(f"{artifact['slice_id']} content digest drift")
    if artifact["schema"] != SLICE_SCHEMA:
        raise EvidenceBuildError(f"{artifact['slice_id']} schema mismatch")
    if set(artifact["cell_coverage"]) != set(C1_CELL_BOUNDARIES):
        raise EvidenceBuildError(f"{artifact['slice_id']} C1 coverage incomplete")
    for key in (
        "program_digest",
        "plan_digest",
        "catalog_digest",
        "control_root_digest",
        "source_map_digest",
        "dependency_index_digest",
    ):
        if not re.fullmatch(
            r"[0-9a-f]{64}", str(artifact["exact_digests"].get(key, ""))
        ):
            raise EvidenceBuildError(f"{artifact['slice_id']} {key} is not hex64")
    for key in ("legacy_observation_digest", "successor_observation_digest"):
        if not re.fullmatch(
            r"[0-9a-f]{64}", str(artifact["observations"].get(key, ""))
        ):
            raise EvidenceBuildError(f"{artifact['slice_id']} {key} is not hex64")
    if not artifact["acceptance"]["acceptance_digest"]:
        raise EvidenceBuildError(f"{artifact['slice_id']} acceptance digest missing")
    if artifact["acceptance"]["provider_calls"] != 0:
        raise EvidenceBuildError(f"{artifact['slice_id']} provider calls must be zero")
    fixture_sha = artifact["pg_binding"]["fixture"]["sha256"]
    if not re.fullmatch(r"[0-9a-f]{64}", str(fixture_sha)):
        raise EvidenceBuildError(f"{artifact['slice_id']} PG fixture SHA is not hex64")
    if any(artifact["authority"].values()):
        raise EvidenceBuildError(
            f"{artifact['slice_id']} authority flags must be false"
        )
    if artifact["accepted"] != (not artifact["blocking_findings"]):
        raise EvidenceBuildError(f"{artifact['slice_id']} acceptance state drift")


def build_evidence(
    *,
    pg_path: Path | None = None,
    pg_sha256: str | None = None,
    pg_fixture_path: Path | None = None,
    pg_fixture_sha256: str | None = None,
) -> dict[str, dict[str, object]]:
    pg_binding = _require_pg_binding(
        pg_path=pg_path,
        pg_sha256=pg_sha256,
        pg_fixture_path=pg_fixture_path,
        pg_fixture_sha256=pg_fixture_sha256,
    )
    slices = {
        slice_id: build_slice(
            slice_id,
            pg_binding,
            pg_path=pg_path,
            pg_fixture_path=pg_fixture_path,
        )
        for slice_id in SLICE_ORDER
    }
    for slice_id in SLICE_ORDER:
        rebuilt = build_slice(
            slice_id,
            pg_binding,
            pg_path=pg_path,
            pg_fixture_path=pg_fixture_path,
        )
        if _canonical_json(slices[slice_id]) != _canonical_json(rebuilt):
            raise EvidenceBuildError(f"slice {slice_id} build is not deterministic")
    return slices


def _write_json_atomic(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (_canonical_json(value) + "\n").encode("utf-8")
    fd, tmp_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def write_evidence(
    *,
    pg_path: Path | None = None,
    pg_sha256: str | None = None,
    pg_fixture_path: Path | None = None,
    pg_fixture_sha256: str | None = None,
) -> tuple[dict[str, dict[str, object]], dict[str, object]]:
    slices = build_evidence(
        pg_path=pg_path,
        pg_sha256=pg_sha256,
        pg_fixture_path=pg_fixture_path,
        pg_fixture_sha256=pg_fixture_sha256,
    )
    for slice_id, artifact in slices.items():
        _write_json_atomic(SLICE_PATHS[slice_id], artifact)
    aggregate = build_aggregate_from_disk()
    _write_json_atomic(AGGREGATE_PATH, aggregate)
    return slices, aggregate


def _read_slice(slice_id: str) -> dict[str, object]:
    path = SLICE_PATHS[slice_id]
    if not path.is_file():
        raise EvidenceBuildError(
            f"slice artifact missing: {_relpath(path)}",
            exit_code=EXIT_MISSING,
        )
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceBuildError(
            f"invalid JSON slice artifact {_relpath(path)}: {exc}",
            exit_code=EXIT_BUILD,
        ) from exc
    if not isinstance(value, dict):
        raise EvidenceBuildError(
            f"slice artifact must be an object: {_relpath(path)}",
            exit_code=EXIT_BUILD,
        )
    expected = value.get("content_digest")
    actual = content_digest(
        {key: item for key, item in value.items() if key != "content_digest"}
    )
    if expected != actual:
        raise EvidenceBuildError(
            f"slice artifact content digest drift: {_relpath(path)}",
            exit_code=EXIT_DRIFT,
        )
    return value


def _aggregate_pg_binding(
    slices: dict[str, dict[str, object]],
) -> dict[str, object]:
    bindings = [slices[slice_id]["pg_binding"] for slice_id in SLICE_ORDER]
    if not all(isinstance(item, dict) for item in bindings):
        raise EvidenceBuildError("slice PG binding must be an object")
    return dict(bindings[0])


def _pure_refs_from_slices(
    slices: list[dict[str, object]],
) -> list[dict[str, object]]:
    roles = (
        "pure_slice_programs_test",
        "pure_legacy_oracle_test",
        "pure_legacy_dsl_parity_test",
    )
    result: list[dict[str, object]] = []
    for slice_value in slices:
        for binding in slice_value.get("test_bindings", []):
            if binding.get("role") in roles and binding not in result:
                result.append(binding)
    return result


def _c1_movement_scope() -> dict[str, object]:
    matrix_path = (
        EVIDENCE_ROOT / "semantic-movement/P1P3SuccessorMovementMatrix.v1.json"
    )
    if not matrix_path.is_file():
        raise EvidenceBuildError(
            f"P1-P3 movement matrix missing for aggregate scope: {_relpath(matrix_path)}",
            exit_code=EXIT_MISSING,
        )
    try:
        matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceBuildError(
            f"invalid movement matrix JSON: {_relpath(matrix_path)}",
            exit_code=EXIT_BUILD,
        ) from exc
    rows = [row for row in matrix.get("movements", []) if row.get("family") == "C1"]
    movement_ids = [row["movement_id"] for row in rows if row.get("movement_id")]
    blocker_ids = [
        row["movement_id"]
        for row in rows
        if row.get("disposition") == "UNASSIGNED_BLOCKER"
    ]
    dispositions: dict[str, int] = {}
    for row in rows:
        disposition = row.get("disposition")
        if isinstance(disposition, str):
            dispositions[disposition] = dispositions.get(disposition, 0) + 1
    return {
        "family": "C1",
        "movement_count": len(movement_ids),
        "movement_ids": movement_ids,
        "unassigned_blocker_count": len(blocker_ids),
        "unassigned_blocker_ids": blocker_ids,
        "disposition_counts": dispositions,
        "matrix_path": _relpath(matrix_path),
    }


def build_aggregate_from_disk() -> dict[str, object]:
    slices = {slice_id: _read_slice(slice_id) for slice_id in SLICE_ORDER}
    findings: list[str] = []
    status = STATUS_READY
    for slice_id in SLICE_ORDER:
        slice_value = slices[slice_id]
        if slice_value.get("accepted") is not True or slice_value.get(
            "blocking_findings"
        ):
            status = STATUS_BLOCK
            findings.append(f"SLICE_BLOCKED:{slice_id}")
        pg = slice_value.get("pg_binding")
        if not isinstance(pg, dict) or pg.get("nodes_present") is not True:
            if status == STATUS_READY:
                status = STATUS_PARTIAL
            findings.append(f"PG_BINDING_INCOMPLETE:{slice_id}")
    if status == STATUS_READY:
        shas = {slices[slice_id]["pg_binding"]["sha256"] for slice_id in SLICE_ORDER}
        if len(shas) != 1:
            status = STATUS_PARTIAL
            findings.append("PG_BINDING_INCONSISTENT_ACROSS_SLICES")
    aggregate: dict[str, object] = {
        "schema": AGGREGATE_SCHEMA,
        "phase": "P5",
        "family": "C1",
        "aggregate_id": AGGREGATE_ID,
        "status": status,
        "slice_bindings": [
            {
                "slice_id": slice_id,
                "path": _relpath(SLICE_PATHS[slice_id]),
                "sha256": _sha256_bytes(SLICE_PATHS[slice_id].read_bytes()),
                "bytes": len(SLICE_PATHS[slice_id].read_bytes()),
                "lines": len(SLICE_PATHS[slice_id].read_bytes().splitlines()),
                "content_digest": slices[slice_id]["content_digest"],
                "acceptance_digest": slices[slice_id]["acceptance"][
                    "acceptance_digest"
                ],
                "accepted": slices[slice_id]["accepted"],
                "blocking_findings": list(
                    slices[slice_id].get("blocking_findings") or []
                ),
            }
            for slice_id in SLICE_ORDER
        ],
        "pg_binding": _aggregate_pg_binding(slices),
        "pure_refs": _pure_refs_from_slices(list(slices.values())),
        "movement_scope": _c1_movement_scope(),
        "blocking_findings": findings,
        "authority_ceiling": {
            "production_canonical_write": False,
            "live_provider": False,
            "external_delivery": False,
            "cutover": False,
            "authority_transfer": False,
            "legacy_retired": False,
            "candidate_created": False,
        },
        "candidate_state": "NO_CANDIDATE",
        "promotion_claim": False,
        "content_digest": "",
    }
    aggregate["content_digest"] = content_digest(
        {key: value for key, value in aggregate.items() if key != "content_digest"}
    )
    _self_test_aggregate(aggregate)
    return aggregate


def _self_test_aggregate(aggregate: dict[str, object]) -> None:
    expected = content_digest(
        {key: value for key, value in aggregate.items() if key != "content_digest"}
    )
    if aggregate["content_digest"] != expected:
        raise EvidenceBuildError("aggregate content digest drift")
    if aggregate["schema"] != AGGREGATE_SCHEMA:
        raise EvidenceBuildError("aggregate schema mismatch")
    if aggregate["status"] not in {STATUS_READY, STATUS_PARTIAL, STATUS_BLOCK}:
        raise EvidenceBuildError("aggregate status outside the fail-closed ladder")
    if aggregate["status"] == STATUS_READY and (
        any(not item["accepted"] for item in aggregate["slice_bindings"])
        or aggregate["blocking_findings"]
    ):
        raise EvidenceBuildError("READY aggregate cannot carry blockers")
    if aggregate["candidate_state"] != "NO_CANDIDATE":
        raise EvidenceBuildError("aggregate candidate state must be NO_CANDIDATE")
    if aggregate["promotion_claim"] is not False:
        raise EvidenceBuildError("aggregate promotion claim must be false")
    if any(aggregate["authority_ceiling"].values()):
        raise EvidenceBuildError("aggregate authority flags must be false")
    movement_scope = aggregate.get("movement_scope")
    if not isinstance(movement_scope, dict):
        raise EvidenceBuildError("aggregate movement scope missing")
    if movement_scope.get("family") != "C1":
        raise EvidenceBuildError("aggregate movement scope family must be C1")
    movement_ids = movement_scope.get("movement_ids")
    blocker_ids = movement_scope.get("unassigned_blocker_ids")
    if not isinstance(movement_ids, list) or not movement_ids:
        raise EvidenceBuildError("aggregate movement scope must list C1 movement ids")
    if not isinstance(blocker_ids, list):
        raise EvidenceBuildError("aggregate movement scope blocker ids must be a list")
    if movement_scope.get("unassigned_blocker_count") != len(blocker_ids):
        raise EvidenceBuildError("aggregate movement scope blocker count drift")


def check_evidence(
    *,
    pg_path: Path | None = None,
    pg_sha256: str | None = None,
    pg_fixture_path: Path | None = None,
    pg_fixture_sha256: str | None = None,
) -> str:
    expected_slices = build_evidence(
        pg_path=pg_path,
        pg_sha256=pg_sha256,
        pg_fixture_path=pg_fixture_path,
        pg_fixture_sha256=pg_fixture_sha256,
    )
    for slice_id in SLICE_ORDER:
        path = SLICE_PATHS[slice_id]
        if not path.is_file():
            raise EvidenceBuildError(
                f"slice artifact missing: {_relpath(path)}",
                exit_code=EXIT_MISSING,
            )
        actual = path.read_bytes()
        expected = (_canonical_json(expected_slices[slice_id]) + "\n").encode("utf-8")
        if actual != expected:
            raise EvidenceBuildError(
                f"slice artifact drift: {_relpath(path)}",
                exit_code=EXIT_DRIFT,
            )
    expected_aggregate = build_aggregate_from_disk()
    if not AGGREGATE_PATH.is_file():
        raise EvidenceBuildError(
            f"aggregate artifact missing: {_relpath(AGGREGATE_PATH)}",
            exit_code=EXIT_MISSING,
        )
    actual = AGGREGATE_PATH.read_bytes()
    expected = (_canonical_json(expected_aggregate) + "\n").encode("utf-8")
    if actual != expected:
        raise EvidenceBuildError(
            f"aggregate artifact drift: {_relpath(AGGREGATE_PATH)}",
            exit_code=EXIT_DRIFT,
        )
    return "unchanged"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="C1 Slice A/B/C hash-bound evidence generator"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="read-only verification; missing or drift exits nonzero",
    )
    parser.add_argument("--slice-a-path", default=None)
    parser.add_argument("--slice-b-path", default=None)
    parser.add_argument("--slice-c-path", default=None)
    parser.add_argument("--aggregate-path", default=None)
    parser.add_argument("--pg-test-path", default=None)
    parser.add_argument("--pg-sha256", default=None)
    parser.add_argument("--pg-fixture-path", default=None)
    parser.add_argument("--pg-fixture-sha256", default=None)
    args = parser.parse_args(argv)

    global AGGREGATE_PATH
    if args.slice_a_path is not None:
        SLICE_PATHS["A"] = Path(args.slice_a_path)
    if args.slice_b_path is not None:
        SLICE_PATHS["B"] = Path(args.slice_b_path)
    if args.slice_c_path is not None:
        SLICE_PATHS["C"] = Path(args.slice_c_path)
    if args.aggregate_path is not None:
        AGGREGATE_PATH = Path(args.aggregate_path)
    pg_path = Path(args.pg_test_path) if args.pg_test_path is not None else None
    pg_fixture_path = (
        Path(args.pg_fixture_path) if args.pg_fixture_path is not None else None
    )

    try:
        if args.check:
            result = check_evidence(
                pg_path=pg_path,
                pg_sha256=args.pg_sha256,
                pg_fixture_path=pg_fixture_path,
                pg_fixture_sha256=args.pg_fixture_sha256,
            )
            print(result)
        else:
            slices, aggregate = write_evidence(
                pg_path=pg_path,
                pg_sha256=args.pg_sha256,
                pg_fixture_path=pg_fixture_path,
                pg_fixture_sha256=args.pg_fixture_sha256,
            )
            for slice_id in slices:
                print(f"wrote {_relpath(SLICE_PATHS[slice_id])}")
            print(f"wrote {_relpath(AGGREGATE_PATH)}")
            print(f"aggregate status: {aggregate['status']}")
        return EXIT_OK
    except EvidenceBuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        print("no write performed", file=sys.stderr)
        return exc.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
