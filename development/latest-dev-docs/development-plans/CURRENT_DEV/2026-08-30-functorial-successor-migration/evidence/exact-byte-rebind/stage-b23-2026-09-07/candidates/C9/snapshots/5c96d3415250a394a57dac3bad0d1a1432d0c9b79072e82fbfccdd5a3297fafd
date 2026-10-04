"""Thin C9/P4 family fragment config for the shared family generator.

This module declares only the C9 family data and differences: family identity,
the C9.1 capability cell spec and runtime kernel ABI inputs, exact binding
targets, the three C9.1-C9.3 p3-style cell declarations, the owner mapping and
the family observation glue that calls the existing C9 contract modules.  No
full fragment generator pipeline is copied; shared schema/digest/path/authority
mechanics and the read-only check gate live in ``shared_family_generator``.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.contracts import successor_runtime as c9t
from app.successor_runtime.runtime import facade_contracts as c9f
from app.successor_runtime.specification.shared_family_generator import (
    BindingsByKind,
    BindingTarget,
    FamilyFragmentConfig,
    content_digest,
)
from app.successor_runtime.substrate.projections import registry as c9r

PROJECT_KEY = "p4-c9-fragment"
FRAGMENT_ID = "p4-c9-family-local-ahead-of-time-scaffolding"
FRAGMENT_SCHEMA = "mrw.functorial_successor.p4_fragment.v1"
FRAGMENT_PHASE = "P4"
FRAGMENT_FAMILY = "C9"
FRAGMENT_STATUS = "AHEAD_OF_TIME_SCAFFOLDING_UNADOPTED"
FRAGMENT_P4_STATUS = "P4_NOT_STARTED"

_DEV_ROOT = (
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration"
)
_EVIDENCE_ROOT = f"{_DEV_ROOT}/evidence"
REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
CELL_SPEC_PATH = f"{_EVIDENCE_ROOT}/capability-specs/C9.1.v1.json"
RUNTIME_KERNEL_ABI_PATH = f"{_EVIDENCE_ROOT}/capability-specs/RuntimeKernelABI.v1.json"
FRAGMENT_OUTPUT_REL = f"{_EVIDENCE_ROOT}/p4-fragments/C9.json"

_CELL_IDS = ("C9.1", "C9.2", "C9.3")

AUTHORITY = {
    "production_canonical_write": False,
    "live_provider": False,
    "live_credential": False,
    "network": False,
    "cutover": False,
    "authority_transfer": False,
    "legacy_retired": False,
    "p4_promotion": False,
}

OPEN_FINDINGS = (
    {
        "id": "C9_AHEAD_OF_TIME_SCAFFOLDING_UNADOPTED",
        "severity": "P1",
        "description": (
            "contract-only scaffold: no API route, frontend adoption, "
            "migration, PostgreSQL execution, live provider or cutover"
        ),
    },
    {
        "id": "C9_SSE_LIVE_RECONNECT_NOT_OBSERVED",
        "severity": "P2",
        "description": (
            "SSE after_seq exclusivity and reconnect semantics are validated "
            "as pure contracts only; no live stream observation exists"
        ),
    },
    {
        "id": "C9_FRONTEND_DESIGN_ONLY_NO_BYTES",
        "severity": "P2",
        "description": (
            "C9.2 is a design-only typed UI observation/interaction contract; "
            "no frontend file was written"
        ),
    },
    {
        "id": "C9_PROJECTOR_REGISTRY_PURE_NO_POSTGRES",
        "severity": "P2",
        "description": (
            "C9.3 aligns to ProjectionOffsetKey/Repository semantics as a "
            "pure contract; no PostgreSQL offset or projection write is "
            "executed"
        ),
    },
    {
        "id": "C9_ROUTE_AND_FRONTEND_OUT_OF_SCOPE",
        "severity": "P2",
        "description": (
            "transport DTO is deliberately route-free and no frontend product "
            "code was written"
        ),
    },
)


def _p1_cells() -> dict[str, dict[str, Any]]:
    artifact = json.loads(
        (
            REPOSITORY_ROOT / _EVIDENCE_ROOT / "P1FunctorizationEligibility.v1.json"
        ).read_text(encoding="utf-8")
    )
    return {str(cell["cell"]): cell for cell in artifact["cells"]}


def _p1_cell_digest(cell_id: str) -> str:
    cell = _p1_cells()[cell_id]
    return content_digest(cell)


def _operation_binding(
    operation_kind: str,
    role: str,
    surface: Any,
) -> dict[str, object]:
    surface_digest = content_digest(surface)
    return {
        "operation_kind": operation_kind,
        "contract_digest": content_digest(
            {
                "operation_kind": operation_kind,
                "role": role,
                "surface_digest": surface_digest,
            }
        ),
        "role": role,
    }


def _no_program() -> dict[str, object]:
    return {
        "value": None,
        "reason": (
            "ahead-of-time scaffold; no successor Program is compiled or "
            "executed for this contract surface"
        ),
    }


def _no_plan() -> dict[str, object]:
    return {
        "value": None,
        "reason": (
            "ahead-of-time scaffold; no compiled plan, runtime schedule or "
            "rebuild execution exists"
        ),
    }


def _rollback_observation(
    cell_id: str,
    **claims: bool,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "cell_id": cell_id,
        "claim_owner": "ahead_of_time_scaffold",
    }
    payload.update(claims)
    return {
        "rollback_digest": content_digest(payload),
        **payload,
    }


def _c9_1_surface() -> dict[str, Any]:
    return {
        "api_status_kinds": c9f.API_STATUS_KINDS,
        "command_fields": [
            field.name for field in dataclasses.fields(c9f.FacadeCommand)
        ],
        "query_fields": [field.name for field in dataclasses.fields(c9f.FacadeQuery)],
        "envelope_fields": [
            field.name for field in dataclasses.fields(c9f.ApiEnvelope)
        ],
        "sse_fields": [field.name for field in dataclasses.fields(c9f.SseObservation)],
        "transport_dto_fields": [
            name for name in c9t.SuccessorRuntimeCommandDTO.model_fields
        ],
        "external_request_fields": (
            "project_locator",
            "command_kind",
            "typed_payload",
        ),
        "server_injected_fields": (
            "actor_ref",
            "project_scope_ref",
            "idempotency_key",
            "expected_revision_or_incarnation",
            "approval_ref",
        ),
        "payload_kinds": ("rebuild_projection", "invalidate_projection"),
        "commands_never_execute": True,
        "control_feedback": False,
    }


def _c9_2_surface() -> dict[str, Any]:
    return {
        "ui_observation_states": c9f.UI_OBSERVATION_STATES,
        "ui_observation_fields": [
            field.name for field in dataclasses.fields(c9f.UiObservation)
        ],
        "frontend_bytes_written": 0,
        "design_only": True,
        "control_feedback": False,
    }


def _c9_3_surface() -> dict[str, Any]:
    return {
        "projector_key_fields": [
            field.name for field in dataclasses.fields(c9r.ProjectorKey)
        ],
        "offset_fields": [
            field.name for field in dataclasses.fields(c9r.ProjectionOffset)
        ],
        "expectation_fields": [
            field.name for field in dataclasses.fields(c9r.OffsetExpectation)
        ],
        "receipt_fields": [
            field.name for field in dataclasses.fields(c9r.ProjectionRebuildReceipt)
        ],
        "rebuild_modes": c9r.REBUILD_MODES,
        "cas_codes": (
            "OFFSET_ABA_DETECTED",
            "OFFSET_GENERATION_MISMATCH",
            "SOURCE_STALE",
            "SOURCE_REVISION_REGRESSION",
            "SOURCE_REVISION_DIGEST_CONFLICT",
            "OFFSET_ID_MISMATCH",
        ),
        "full_rebuild_binding": "exact_source_revision_digest_or_closure_receipt",
        "registry_revision_advance": True,
        "rebuild_execute": False,
    }


def _cell_9_1() -> dict[str, object]:
    surface = _c9_1_surface()
    return {
        "cell_id": "C9.1",
        "p1_cell_digest": _p1_cell_digest("C9.1"),
        "operation_bindings": [
            _operation_binding(
                "facade.command.description_validation.v1",
                "runtime_facade_command",
                surface,
            ),
            _operation_binding(
                "facade.query.read_only.v1",
                "runtime_facade_query",
                surface,
            ),
            _operation_binding(
                "api.envelope.status_data_error_meta.v1",
                "transport_api_envelope",
                surface,
            ),
            _operation_binding(
                "api.status.ok_error_unavailable_blocked_waiting.v1",
                "transport_api_status",
                surface,
            ),
            _operation_binding(
                "facade.sse.after_seq_exclusive.v1",
                "transport_sse_observation",
                surface,
            ),
            _operation_binding(
                "facade.response.control_feedback_forbidden.v1",
                "no_control_feedback",
                surface,
            ),
        ],
        "owner_capability_id": "api_frontend.c9.v1",
        "program_digest": _no_program(),
        "plan_digest": _no_plan(),
        "legacy_observation": {
            "interpreter_id": "legacy.fastapi-command-query-envelope.v1",
            "provider_calls": 0,
            "dispatch_executed": False,
        },
        "successor_observation": {
            "api_status_union": list(c9f.API_STATUS_KINDS),
            "envelope": ["status", "data", "error", "meta"],
            "external_request_fields": list(surface["external_request_fields"]),
            "server_injected_fields": list(surface["server_injected_fields"]),
            "command_bindings": [
                "project_scope_ref",
                "actor_ref",
                "idempotency_key",
                "expected_revision_or_incarnation",
                "approval_ref",
            ],
            "query_bindings": ["project_scope_ref", "after_seq"],
            "commands_never_execute": True,
            "control_feedback": False,
            "route_defined": False,
            "provider_calls": 0,
            "network_required": False,
        },
        "rollback_observation": _rollback_observation(
            "C9.1",
            no_route_cutover=True,
            envelope_contract_retained=True,
        ),
        "provider_calls": 0,
        "postgres_requirement": "not_required",
    }


def _cell_9_2() -> dict[str, object]:
    surface = _c9_2_surface()
    return {
        "cell_id": "C9.2",
        "p1_cell_digest": _p1_cell_digest("C9.2"),
        "operation_bindings": [
            _operation_binding(
                "frontend.observation.six_states.v1",
                "frontend_observation",
                surface,
            ),
            _operation_binding(
                "frontend.interaction.command_submit.v1",
                "frontend_interaction",
                surface,
            ),
            _operation_binding(
                "frontend.no_control_feedback.v1",
                "no_control_feedback",
                surface,
            ),
            _operation_binding(
                "frontend.design_only_typed_contract.v1",
                "frontend_design_only",
                surface,
            ),
        ],
        "owner_capability_id": "api_frontend.c9.v1",
        "program_digest": _no_program(),
        "plan_digest": _no_plan(),
        "legacy_observation": {
            "interpreter_id": "legacy.react19-tanstack-axios-projection-ui.v1",
            "provider_calls": 0,
            "frontend_bytes_written": 0,
        },
        "successor_observation": {
            "ui_observation_states": list(c9f.UI_OBSERVATION_STATES),
            "design_only_typed_contract": True,
            "frontend_bytes_written": 0,
            "interaction_kind": "typed_command_submit_only",
            "control_feedback": False,
            "provider_calls": 0,
            "network_required": False,
        },
        "rollback_observation": _rollback_observation(
            "C9.2",
            no_frontend_bytes=True,
            ui_contract_design_only=True,
        ),
        "provider_calls": 0,
        "postgres_requirement": "not_required",
    }


def _cell_9_3() -> dict[str, object]:
    surface = _c9_3_surface()
    return {
        "cell_id": "C9.3",
        "p1_cell_digest": _p1_cell_digest("C9.3"),
        "operation_bindings": [
            _operation_binding(
                "projector.registry.exact_key.v1",
                "projector_registry",
                surface,
            ),
            _operation_binding(
                "projector.offset.cas_advance.v1",
                "projector_offset_cas",
                surface,
            ),
            _operation_binding(
                "projector.offset.aba_stale.v1",
                "projector_offset_aba_stale",
                surface,
            ),
            _operation_binding(
                "projector.rebuild.plan_only.v1",
                "projector_rebuild",
                surface,
            ),
            _operation_binding(
                "projector.source_offsets.snapshot.v1",
                "projector_offset_snapshot",
                surface,
            ),
        ],
        "owner_capability_id": "api_frontend.c9.v1",
        "program_digest": _no_program(),
        "plan_digest": _no_plan(),
        "legacy_observation": {
            "interpreter_id": (
                "legacy.agent-session-graph-indexer-projection-cluster.v1"
            ),
            "provider_calls": 0,
            "rebuild_executed": False,
        },
        "successor_observation": {
            "projector_key_fields": surface["projector_key_fields"],
            "offset_fields": surface["offset_fields"],
            "receipt_fields": surface["receipt_fields"],
            "cas_codes": list(surface["cas_codes"]),
            "rebuild_modes": list(c9r.REBUILD_MODES),
            "full_rebuild_binding": surface["full_rebuild_binding"],
            "registry_revision_advance": surface["registry_revision_advance"],
            "rebuild_execute": False,
            "postgres_executed": False,
            "control_feedback": False,
            "provider_calls": 0,
            "network_required": False,
        },
        "rollback_observation": _rollback_observation(
            "C9.3",
            no_postgres_write=True,
            offset_cas_plan_only=True,
        ),
        "provider_calls": 0,
        "postgres_requirement": "not_required",
    }


def _owner_mapping() -> dict[str, dict[str, str]]:
    p1 = _p1_cells()
    return {
        cell_id: {
            "cell_id": cell_id,
            "boundary": p1[cell_id]["boundary"],
            "legacy_owner": p1[cell_id]["legacy_interpreter"],
            "successor_owner": "api_frontend.c9.v1",
            "canonical_owner": p1[cell_id]["canonical_owner"],
        }
        for cell_id in _CELL_IDS
    }


_SOURCE_BINDINGS = (
    BindingTarget(
        f"{_DEV_ROOT}/01_functorial-successor-migration-development-contract.md",
        "frozen_contract_document",
    ),
    BindingTarget(
        f"{_DEV_ROOT}/02_functorial-successor-migration-development-contract.freeze.json",
        "frozen_contract_manifest",
    ),
    BindingTarget(
        f"{_DEV_ROOT}/06_functorial-successor-runtime-architecture-correction.draft.zh-CN.md",
        "frozen_architecture",
    ),
    BindingTarget(
        f"{_DEV_ROOT}/09_functorial-successor-f0-semantic-owner-inventory.v1.json",
        "frozen_inventory",
    ),
    BindingTarget(
        f"{_DEV_ROOT}/13_functorial-successor-c1-c9-locator-pending-inventory.v1.json",
        "frozen_locator_inventory",
    ),
    BindingTarget(
        f"{_EVIDENCE_ROOT}/P1FunctorizationEligibility.v1.json", "p1_eligibility"
    ),
    BindingTarget(f"{_EVIDENCE_ROOT}/p1-fragments/C9.json", "p1_fragment"),
    BindingTarget(
        "main/backend/app/contracts/responses.py",
        "legacy_envelope_donor",
    ),
    BindingTarget(
        "main/backend/app/api/agent_sessions.py",
        "legacy_sse_donor",
    ),
    BindingTarget(
        "main/backend/app/main.py",
        "legacy_envelope_middleware_donor",
    ),
    BindingTarget(
        "main/backend/app/services/agent_sessions/store.py",
        "legacy_projection_donor_agent_sessions",
    ),
    BindingTarget(
        "main/backend/app/services/agent_sessions/service.py",
        "legacy_projection_donor_agent_sessions",
    ),
    BindingTarget(
        "main/backend/app/services/graph/backfill_graph_nodes.py",
        "legacy_projection_donor_graph_backfill",
    ),
    BindingTarget(
        "main/backend/app/services/indexer/policy.py",
        "legacy_projection_donor_indexer",
    ),
    BindingTarget(
        "main/backend/app/successor_runtime/substrate/projections/runtime_run.py",
        "successor_projector_pattern",
    ),
    BindingTarget(
        "main/backend/app/successor_runtime/substrate/postgres/projection_offsets.py",
        "successor_offset_pattern",
    ),
    BindingTarget(
        "main/backend/tests/contract/test_contracts_unittest.py",
        "legacy_envelope_test_donor",
    ),
)

_IMPLEMENTATION_BINDINGS = (
    BindingTarget(
        "main/backend/app/successor_runtime/runtime/facade_contracts.py",
        "facade_contracts",
    ),
    BindingTarget(
        "main/backend/app/successor_runtime/substrate/projections/registry.py",
        "projector_registry",
    ),
    BindingTarget(
        "main/backend/app/contracts/successor_runtime.py",
        "transport_dto",
    ),
    BindingTarget(
        "main/backend/scripts/generate_successor_p4_c9_fragment.py",
        "evidence_generator",
    ),
)

_TEST_BINDINGS = (
    BindingTarget(
        "main/backend/tests/successor_runtime/test_p4_c9_1_facade_contracts.py",
        "c9_1_facade_contracts",
    ),
    BindingTarget(
        "main/backend/tests/successor_runtime/test_p4_c9_2_projector_registry.py",
        "c9_2_projector_registry",
    ),
    BindingTarget(
        "main/backend/tests/successor_runtime/test_p4_c9_3_transport_dto.py",
        "c9_3_transport_dto",
    ),
    BindingTarget(
        "main/backend/tests/successor_runtime/test_p4_c9_4_evidence_generator.py",
        "c9_4_evidence_generator",
    ),
    BindingTarget(
        "main/backend/tests/successor_runtime/test_p4_c9_5_p1_consistency_and_public_payload.py",
        "c9_5_public_payload_and_caller_schema",
    ),
    BindingTarget(
        "main/backend/tests/successor_runtime/test_p4_c9_6_fragment_stability.py",
        "c9_6_fragment_stability",
    ),
)


def _build_body(_root: Path, bindings: BindingsByKind) -> dict[str, Any]:
    cells = [_cell_9_1(), _cell_9_2(), _cell_9_3()]
    return {
        "schema": FRAGMENT_SCHEMA,
        "phase": FRAGMENT_PHASE,
        "family": FRAGMENT_FAMILY,
        "fragment_id": FRAGMENT_ID,
        "status": FRAGMENT_STATUS,
        "p4_status": FRAGMENT_P4_STATUS,
        "cells": cells,
        "owner_mapping": _owner_mapping(),
        "source_bindings": bindings["source_bindings"],
        "implementation_bindings": bindings["implementation_bindings"],
        "test_bindings": bindings["test_bindings"],
        "authority": dict(AUTHORITY),
        "open_findings": [dict(finding) for finding in OPEN_FINDINGS],
    }


def _self_check(fragment: Mapping[str, Any]) -> None:
    assert fragment["schema"] == FRAGMENT_SCHEMA
    assert fragment["phase"] == FRAGMENT_PHASE
    assert fragment["family"] == FRAGMENT_FAMILY
    assert fragment["status"] == FRAGMENT_STATUS
    assert fragment["p4_status"] == FRAGMENT_P4_STATUS
    body = {key: value for key, value in fragment.items() if key != "content_digest"}
    assert fragment["content_digest"] == content_digest(body)
    required_roots = {
        "schema",
        "phase",
        "family",
        "fragment_id",
        "status",
        "p4_status",
        "cells",
        "owner_mapping",
        "source_bindings",
        "implementation_bindings",
        "test_bindings",
        "authority",
        "open_findings",
        "content_digest",
    }
    assert set(fragment) == required_roots
    assert [cell["cell_id"] for cell in fragment["cells"]] == [
        "C9.1",
        "C9.2",
        "C9.3",
    ]
    assert set(fragment["owner_mapping"]) == set(_CELL_IDS)
    rollback_digests = set()
    for cell in fragment["cells"]:
        digest = cell["p1_cell_digest"]
        assert isinstance(digest, str) and len(digest) == 64
        for binding in cell["operation_bindings"]:
            contract_digest = binding["contract_digest"]
            assert isinstance(contract_digest, str) and len(contract_digest) == 64
        rollback = cell["rollback_observation"]
        assert isinstance(rollback["rollback_digest"], str)
        assert len(rollback["rollback_digest"]) == 64
        rollback_digests.add(rollback["rollback_digest"])
    assert len(rollback_digests) == 3
    assert all(not value for value in fragment["authority"].values()), (
        "authority flags must all be false"
    )


CONFIG = FamilyFragmentConfig(
    family_id=FRAGMENT_FAMILY,
    phase=FRAGMENT_PHASE,
    schema=FRAGMENT_SCHEMA,
    fragment_id=FRAGMENT_ID,
    status=FRAGMENT_STATUS,
    fragment_output_rel=FRAGMENT_OUTPUT_REL,
    cell_spec_path=CELL_SPEC_PATH,
    runtime_kernel_abi_path=RUNTIME_KERNEL_ABI_PATH,
    source_bindings=_SOURCE_BINDINGS,
    implementation_bindings=_IMPLEMENTATION_BINDINGS,
    test_bindings=_TEST_BINDINGS,
    authority=AUTHORITY,
    open_findings=OPEN_FINDINGS,
    body_builder=_build_body,
    self_check=_self_check,
)
