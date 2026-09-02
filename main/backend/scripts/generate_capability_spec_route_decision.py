#!/usr/bin/env python3
"""Generate the bounded capability-spec route decision and ownership evidence.

This generator records a user-authorized development decision.  It does not
amend the frozen contract, start a pilot, adopt P4 scaffolding, or authorize a
candidate/live boundary.  ``--check`` is a strictly read-only exact-byte gate:
matching outputs exit 0, drift exits 1, and argparse usage errors exit 2.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
TOPIC_REL = Path(
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration"
)
EVIDENCE_REL = TOPIC_REL / "evidence"

DECISION_REL = (
    EVIDENCE_REL / "CapabilitySpecCompilationAndVerticalSlicesDecision.v1.json"
)
OWNERSHIP_REL = EVIDENCE_REL / "CapabilitySpecGeneratedHandwrittenOwnership.v1.json"

FROZEN_INPUTS = (
    (
        TOPIC_REL / "01_functorial-successor-migration-development-contract.md",
        "frozen_development_contract",
    ),
    (
        TOPIC_REL
        / "02_functorial-successor-migration-development-contract.freeze.json",
        "frozen_manifest",
    ),
    (
        TOPIC_REL
        / "06_functorial-successor-runtime-architecture-correction.draft.zh-CN.md",
        "frozen_runtime_architecture_authority",
    ),
)
P3_AGGREGATE_REL = EVIDENCE_REL / "P3CapabilityMigration.v1.json"
PROGRESS_REL = TOPIC_REL / "03_functorial-successor-migration-development-progress.md"
P4_FRAGMENT_RELS = {
    family: EVIDENCE_REL / f"p4-fragments/{family}.json"
    for family in ("C7", "C8", "C9")
}

GOAL_ID = "01a0504c-47ef-77e1-9783-454dbcbe3697"
ROUTE_NAME = "CAPABILITY_SPEC_COMPILATION_AND_VERTICAL_PRODUCT_SLICES"
P3_FILE_SHA256 = "a80c4f2af17f80b7ebf0399ddcbcb80a64a99a09f26b15512d46c585cfec3609"
P3_CONTENT_DIGEST = "83e56d32cf6d025fdbfc84c0132755f4b5fc859134bb51f1a70f2fd52953faf8"
P3_REVIEW_TASK = "/root/p3_aggregate_exact_review_v2_ds"
P3_REVIEW_DISPOSITION = "ALLOW_P3_AGGREGATE_LOCAL_ONLY_PROMOTION"

DECISION_SCHEMA = "mrw.functorial_successor.capability_spec_route_decision.v1"
OWNERSHIP_SCHEMA = "mrw.functorial_successor.generated_handwritten_ownership.v1"

AUTHORITY_CEILING = {
    "live_provider": False,
    "external_delivery": False,
    "cutover": False,
    "authority_transfer": False,
}

USER_AUTHORIZATION_SEMANTICS = {
    "route_name": ROUTE_NAME,
    "decision_class": "USER_AUTHORIZED_DEVELOPMENT_DECISION_NOT_FROZEN_AMENDMENT",
    "switch_boundary": [
        "P3_AGGREGATE_PROMOTED_FIRST",
        "C2_C6_REMAIN_PROMOTED_REFERENCE_ORACLES",
        "ROUTE_STARTS_WITH_P4_C7_C8_C9",
        "P5_PREFLIGHT_MOVES_INTO_EACH_VERTICAL_SLICE",
    ],
    "core_generation_form": [
        "CapabilityCellSpec",
        "OperationContract_ProgramSkeleton_ProfileRefs",
        "CatalogRegistration_HandlerBindingClosure",
        "EvidenceFragment_BindingManifest",
        "ParameterizedFocusedGates_RollbackHarness",
        "ExactBuildArtifacts",
    ],
    "generator_scope": "MECHANICAL_SCAFFOLDING_ONLY",
    "pilot_cells": ["C7.1", "C8.2", "C9.1"],
    "vertical_slices": [
        "A_INTAKE_RECOVERY",
        "B_KNOWLEDGE_COMPOSITION",
        "C_REPORT_DELIVERY",
    ],
    "c1_cross_cutting_cells": ["C1.1", "C1.2", "C1.3"],
    "dual_identity": ["SEMANTIC_ABI_DIGEST", "EXACT_ARTIFACT_BUILD_DIGEST"],
    "normative_conflict": "FAIL_CLOSED",
    "candidate_state": "NO_CANDIDATE",
    "authority_ceiling": AUTHORITY_CEILING,
}


class DecisionBuildError(RuntimeError):
    """Fail-closed evidence construction error."""


@dataclass(frozen=True, slots=True)
class Snapshot:
    path: str
    data: bytes
    file_sha256: str
    bytes: int
    lines: int

    def binding(self, *, role: str) -> dict[str, Any]:
        return {
            "path": self.path,
            "file_sha256": self.file_sha256,
            "bytes": self.bytes,
            "lines": self.lines,
            "role": role,
        }


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def content_digest(value: Mapping[str, Any]) -> str:
    payload = {key: item for key, item in value.items() if key != "content_digest"}
    return _sha256(_canonical_json_bytes(payload))


def _finalize(value: dict[str, Any]) -> dict[str, Any]:
    result = dict(value)
    result["content_digest"] = content_digest(result)
    return result


def _serialized(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False).encode("utf-8")
        + b"\n"
    )


def _snapshot(root: Path, relative: Path) -> Snapshot:
    path = root / relative
    if not path.is_file():
        raise DecisionBuildError(f"required input missing: {relative.as_posix()}")
    data = path.read_bytes()
    return Snapshot(
        path=relative.as_posix(),
        data=data,
        file_sha256=_sha256(data),
        bytes=len(data),
        lines=data.count(b"\n"),
    )


def _json(snapshot: Snapshot) -> Mapping[str, Any]:
    try:
        value = json.loads(snapshot.data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DecisionBuildError(f"invalid JSON input {snapshot.path}: {exc}") from exc
    if not isinstance(value, Mapping):
        raise DecisionBuildError(f"JSON input must be an object: {snapshot.path}")
    return value


def _validate_content_digest(snapshot: Snapshot, value: Mapping[str, Any]) -> None:
    expected = value.get("content_digest")
    actual = content_digest(value)
    if expected != actual:
        raise DecisionBuildError(
            f"content digest mismatch for {snapshot.path}: {expected!r} != {actual}"
        )


def _p3_review_slice(progress: Snapshot) -> dict[str, Any]:
    try:
        text = progress.data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DecisionBuildError(f"invalid UTF-8 progress input: {exc}") from exc
    matches = [
        (line_number, line)
        for line_number, line in enumerate(text.splitlines(), start=1)
        if line.startswith("- P3 aggregate promotion boundary:")
        and P3_REVIEW_TASK in line
        and P3_REVIEW_DISPOSITION in line
        and P3_FILE_SHA256 in line
        and P3_CONTENT_DIGEST in line
    ]
    if len(matches) != 1:
        raise DecisionBuildError(
            "P3 aggregate ALLOW review record must have exactly one exact promotion anchor"
        )
    line_number, line = matches[0]
    return {
        "source_path": progress.path,
        "binding_kind": "unique_record_slice_not_whole_file",
        "line_number_observed": line_number,
        "record_sha256": _sha256(line.encode("utf-8")),
        "review_task_identity": P3_REVIEW_TASK,
        "disposition": P3_REVIEW_DISPOSITION,
        "p3_file_sha256": P3_FILE_SHA256,
        "p3_content_digest": P3_CONTENT_DIGEST,
    }


def _p4_readiness_binding(
    snapshot: Snapshot, value: Mapping[str, Any], *, family: str
) -> dict[str, Any]:
    _validate_content_digest(snapshot, value)
    if value.get("schema") != "mrw.functorial_successor.p4_fragment.v1":
        raise DecisionBuildError(f"{family} readiness fragment schema mismatch")
    if value.get("phase") != "P4" or value.get("family") != family:
        raise DecisionBuildError(f"{family} readiness fragment identity mismatch")
    if value.get("status") != "AHEAD_OF_TIME_SCAFFOLDING_UNADOPTED":
        raise DecisionBuildError(f"{family} readiness fragment was already adopted")
    authority = value.get("authority")
    if not isinstance(authority, Mapping) or any(
        item is True for item in authority.values()
    ):
        raise DecisionBuildError(f"{family} readiness fragment expands authority")
    binding = snapshot.binding(role=f"current_{family.lower()}_readiness_fragment")
    binding.update(
        {
            "schema": value["schema"],
            "family": family,
            "status": value["status"],
            "content_digest": value["content_digest"],
            "adoption": "UNADOPTED_INPUT_ONLY",
        }
    )
    return binding


def _build_decision(
    *,
    frozen_bindings: Sequence[Mapping[str, Any]],
    p3_binding: Mapping[str, Any],
    p3_review: Mapping[str, Any],
    readiness_bindings: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return _finalize(
        {
            "schema": DECISION_SCHEMA,
            "version": "1.0.0",
            "decision_id": "capability-spec-compilation-and-vertical-slices-v1",
            "goal_id": GOAL_ID,
            "route": {
                "name": ROUTE_NAME,
                "authorization": "USER_AUTHORIZED_DEVELOPMENT_DECISION",
                "normative_class": "NOT_A_FROZEN_AMENDMENT",
                "activation_boundary": "AFTER_P3_AGGREGATE_PROMOTION",
                "p3_reference_implementations": "IMMUTABLE_ORACLE_INPUTS_NOT_REWRITTEN",
                "p4_adoption": "NOT_STARTED_BY_THIS_DECISION",
            },
            "user_authorization_record": {
                "binding_kind": "CANONICAL_SEMANTIC_CAPTURE_OF_USER_AUTHORIZATION",
                "payload": USER_AUTHORIZATION_SEMANTICS,
                "semantic_digest": _sha256(
                    _canonical_json_bytes(USER_AUTHORIZATION_SEMANTICS)
                ),
            },
            "normative_inputs": list(frozen_bindings),
            "p3_prerequisite": {
                "passed": True,
                "aggregate": dict(p3_binding),
                "independent_review": dict(p3_review),
            },
            "current_readiness_inputs": list(readiness_bindings),
            "capability_cell_spec": {
                "purpose": "MECHANICAL_STRUCTURE_ONLY",
                "minimum_fields": [
                    "cell_family_owner_identity",
                    "input_output_object_operation_contract_refs",
                    "program_shape_and_ordered_composition_refs",
                    "interpreter_profile_deployment_binding_refs",
                    "legacy_oracle_and_shadow_observation",
                    "failure_union_and_declared_lossy_projections",
                    "effect_resource_recovery_readback_policy_refs",
                    "authority_ceiling_and_adoption_prerequisites",
                    "source_test_rollback_bindings",
                ],
                "does_not_infer_domain_semantics_or_authority": True,
            },
            "generator_contract": {
                "scope": "REPETITIVE_CONTRACT_CATALOG_BINDING_EVIDENCE_TEST_SCAFFOLDING",
                "runtime_truth_source": False,
                "semantic_truth_source": False,
                "authority_truth_source": False,
                "deterministic": True,
                "canonical": True,
                "versioned": True,
                "content_digested": True,
                "read_only_check_required": True,
                "generated_files_manual_edit": "PROHIBITED",
                "complex_serialization_normalization_aggregation_hashing": (
                    "DETERMINISTIC_PROGRAM_OWNED"
                ),
            },
            "pilot": {
                "status": "AUTHORIZED_PENDING_EXECUTION",
                "representative_cells": ["C7.1", "C8.2", "C9.1"],
                "required_gates": [
                    "deterministic_generation",
                    "read_only_check",
                    "exact_binding",
                    "focused_test",
                    "no_authority_expansion",
                ],
                "failure_fallback": "RETAIN_EXISTING_HANDWRITTEN_SCAFFOLD",
            },
            "vertical_slices": [
                {
                    "slice": "A",
                    "name": "intake_recovery",
                    "cells": ["C7.1", "C7.2", "C7.3", "C7.4", "C9.1", "C9.3"],
                    "ordered_path": [
                        "ingest",
                        "canonical_material",
                        "recovery",
                        "read_projection",
                    ],
                },
                {
                    "slice": "B",
                    "name": "knowledge_composition",
                    "cells": ["C8.1", "C8.2", "C8.4", "C9.2"],
                    "ordered_path": [
                        "canonical_material",
                        "typed_knowledge",
                        "composition",
                        "graph_ui_observation",
                    ],
                },
                {
                    "slice": "C",
                    "name": "report_delivery",
                    "cells": ["C8.3", "C9.API_UI_REPORT_PROJECTION"],
                    "ordered_path": [
                        "artifact",
                        "report",
                        "verification_admission",
                        "bounded_delivery_readback",
                    ],
                },
            ],
            "c1_cross_cutting_surface": {
                "cells": ["C1.1", "C1.2", "C1.3"],
                "role": "PROGRAM_GRAPH_COMPILE_REPLAY_COMPOSITION_INTERFACE",
                "required_evidence": [
                    "coverage",
                    "legacy_replay",
                    "rollback",
                    "final_disposition",
                ],
                "isolated_serial_stage": False,
            },
            "identity_model": {
                "semantic_identity": {
                    "name": "RuntimeKernelABI/CapabilitySpec semantic digest",
                    "purpose": "SEMANTIC_CHANGE_AND_REVIEW_INVALIDATION",
                    "semantic_change_requires_review": True,
                },
                "artifact_identity": {
                    "name": "exact artifact/build digest",
                    "purpose": "EXACT_CANDIDATE_BYTE_IDENTITY",
                    "required_in_addition_to_semantic_identity": True,
                },
                "semantic_review_triggers": [
                    "owner",
                    "effect",
                    "failure",
                    "resource",
                    "authority",
                    "recovery",
                    "observable_contract",
                ],
                "freeze_or_packet_binding_bypass": False,
            },
            "slice_gate_policy": {
                "each_cell_retains_independent_evidence": [
                    "owner",
                    "effect",
                    "failure",
                    "resource",
                    "authority",
                    "readback",
                    "rollback",
                ],
                "each_slice_requires": [
                    "focused_tests",
                    "applicable_disposable_postgresql_gate",
                    "legacy_shadow_gate",
                    "rollback_gate",
                    "assembly_fixture",
                    "rollback_receipt",
                    "authority_ceiling",
                    "candidate_ready_binding",
                ],
                "happy_path_is_not_cell_closure": True,
                "final_p5_scope": (
                    "CROSS_SLICE_COMPOSITION_FULL_MATRIX_EXACT_GIT_IDENTITY_INDEPENDENT_REVIEW"
                ),
            },
            "normative_conflict_policy": {
                "mode": "FAIL_CLOSED",
                "on_conflict": "STOP_DEPENDENT_ADOPTION_AND_REPORT_EXACT_BLOCKER",
                "silent_frozen_contract_change": False,
            },
            "authority_ceiling": dict(AUTHORITY_CEILING),
            "candidate_state": "NO_CANDIDATE",
        }
    )


def _build_ownership(
    *, decision: Mapping[str, Any], generator_binding: Mapping[str, Any]
) -> dict[str, Any]:
    return _finalize(
        {
            "schema": OWNERSHIP_SCHEMA,
            "version": "1.0.0",
            "ownership_map_id": "capability-spec-generated-handwritten-ownership-v1",
            "goal_id": GOAL_ID,
            "route_name": ROUTE_NAME,
            "decision_binding": {
                "path": DECISION_REL.as_posix(),
                "schema": decision["schema"],
                "content_digest": decision["content_digest"],
            },
            "generator_binding": dict(generator_binding),
            "specification_ownership": {
                "owner": "HANDWRITTEN_REVIEWED_CAPABILITY_CELL_SPEC",
                "role": "DECLARE_EXACT_REFS_POLICIES_AND_ADOPTION_PREREQUISITES",
                "automatic_semantic_inference": False,
            },
            "generated_ownership": {
                "owner": "DETERMINISTIC_GENERATOR",
                "responsibilities": [
                    "mechanical_contract_scaffolding",
                    "catalog_registration_scaffolding",
                    "handler_binding_scaffolding",
                    "evidence_fragment_scaffolding",
                    "binding_manifest_scaffolding",
                    "parameterized_focused_gate_scaffolding",
                    "rollback_harness_scaffolding",
                    "exact_build_artifacts",
                ],
                "manual_edit": "PROHIBITED",
                "read_only_check": "REQUIRED",
                "truth_source_exclusions": ["runtime", "semantics", "authority"],
            },
            "handwritten_ownership": {
                "owner": "DOMAIN_INTERPRETER_OR_EXPLICIT_POLICY",
                "responsibilities": [
                    "domain_transformation_semantics",
                    "failure_ownership",
                    "effect_execution_and_ordering",
                    "resource_behavior",
                    "cancellation_behavior",
                    "retry_behavior",
                    "verification_and_admission",
                    "recovery_and_readback",
                    "projection_information_loss",
                    "authority_adoption",
                ],
                "manual_edit": "ALLOWED_WITH_SEMANTIC_REVIEW",
                "exact_binding": "REQUIRED",
            },
            "reference_oracles": {
                "families": ["C3", "C5", "C6"],
                "shapes": ["traversal", "observation_projection", "effect_receipt"],
                "use": "GENERATOR_AND_HARNESS_REVERSE_VALIDATION",
                "promoted_bytes_may_change": False,
                "p3_may_be_invalidated_by_pilot": False,
            },
            "change_policy": {
                "new_capability_may_not_normally_modify": [
                    "shared_ast",
                    "compiler_fold",
                    "runtime_assignment_root_union",
                    "generic_reducer",
                    "work_item_root_schema",
                ],
                "semantic_abi_change": "SERIAL_MAINLINE_REVIEW_REQUIRED",
                "artifact_only_change": "REFRESH_EXACT_BUILD_EVIDENCE",
                "authority_adoption": "SERIAL_MAINLINE_ONLY",
            },
            "authority_ceiling": dict(AUTHORITY_CEILING),
            "candidate_state": "NO_CANDIDATE",
        }
    )


def build_documents(
    root: Path = REPOSITORY_ROOT,
) -> tuple[dict[str, Any], dict[str, Any]]:
    root = root.resolve()
    frozen_bindings = [
        _snapshot(root, relative).binding(role=role) for relative, role in FROZEN_INPUTS
    ]

    p3_snapshot = _snapshot(root, P3_AGGREGATE_REL)
    p3 = _json(p3_snapshot)
    # The aggregate has its own validator-defined canonicalization.  Its frozen
    # exact file hash plus expected aggregate content digest are checked here;
    # do not reinterpret that digest with this generator's JSON canonicalizer.
    if p3_snapshot.file_sha256 != P3_FILE_SHA256:
        raise DecisionBuildError("P3 aggregate exact file SHA-256 mismatch")
    if p3.get("content_digest") != P3_CONTENT_DIGEST:
        raise DecisionBuildError("P3 aggregate exact content digest mismatch")
    p3_binding = p3_snapshot.binding(role="promoted_p3_aggregate_exact_candidate")
    p3_binding.update(
        {
            "schema": p3.get("schema"),
            "status": p3.get("status"),
            "content_digest": p3.get("content_digest"),
        }
    )

    progress = _snapshot(root, PROGRESS_REL)
    p3_review = _p3_review_slice(progress)

    readiness_bindings: list[dict[str, Any]] = []
    for family, relative in P4_FRAGMENT_RELS.items():
        snapshot = _snapshot(root, relative)
        readiness_bindings.append(
            _p4_readiness_binding(snapshot, _json(snapshot), family=family)
        )

    decision = _build_decision(
        frozen_bindings=frozen_bindings,
        p3_binding=p3_binding,
        p3_review=p3_review,
        readiness_bindings=readiness_bindings,
    )
    generator = _snapshot(
        root, Path("main/backend/scripts/generate_capability_spec_route_decision.py")
    ).binding(role="deterministic_evidence_generator")
    ownership = _build_ownership(decision=decision, generator_binding=generator)
    return decision, ownership


def _write_atomic_if_changed(path: Path, data: bytes) -> None:
    if path.is_file() and path.read_bytes() == data:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _resolve_output(root: Path, raw: str | None, default: Path) -> Path:
    if raw is None:
        return root / default
    path = Path(raw)
    return path if path.is_absolute() else root / path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPOSITORY_ROOT))
    parser.add_argument("--decision-output")
    parser.add_argument("--ownership-output")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    root = Path(args.repo_root).resolve()
    decision_path = _resolve_output(root, args.decision_output, DECISION_REL)
    ownership_path = _resolve_output(root, args.ownership_output, OWNERSHIP_REL)
    try:
        decision, ownership = build_documents(root)
        outputs = {
            decision_path: _serialized(decision),
            ownership_path: _serialized(ownership),
        }
        if args.check:
            drift = [
                str(path)
                for path, expected in outputs.items()
                if not path.is_file() or path.read_bytes() != expected
            ]
            if drift:
                print(json.dumps({"status": "DRIFT", "paths": drift}, sort_keys=True))
                return 1
            print(
                json.dumps(
                    {
                        "status": "CHECK_OK",
                        "decision_content_digest": decision["content_digest"],
                        "ownership_content_digest": ownership["content_digest"],
                    },
                    sort_keys=True,
                )
            )
            return 0
        for path, data in outputs.items():
            _write_atomic_if_changed(path, data)
        print(
            json.dumps(
                {
                    "status": "GENERATED",
                    "decision": str(decision_path),
                    "decision_content_digest": decision["content_digest"],
                    "ownership": str(ownership_path),
                    "ownership_content_digest": ownership["content_digest"],
                },
                sort_keys=True,
            )
        )
        return 0
    except (DecisionBuildError, OSError) as exc:
        print(json.dumps({"status": "INVALID", "error": str(exc)}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
