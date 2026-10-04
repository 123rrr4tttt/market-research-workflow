"""Deterministically generate the normalized P4 C9 evidence fragment.

Root schema: ``mrw.functorial_successor.p4_fragment.v1``.  The fragment
records C9 as an ahead-of-time, contract-only scaffold with
``AHEAD_OF_TIME_SCAFFOLDING_UNADOPTED`` / ``P4_NOT_STARTED``:

- C9.1: runtime facade plus transport API (command/query binding, API
  ``status/data/error/meta`` envelope, SSE ``after_seq`` observation);
- C9.2: frontend observation/interaction as a design-only typed contract
  (no frontend bytes are written);
- C9.3: projector registry, exact offset key/CAS, ABA/stale and rebuild
  aligned to ``ProjectionOffsetKey``/``ProjectionOffsetRepository``.

The generator binds frozen 01/02/06/09/13 documents, the P1 eligibility
artifact/fragment and current project donor files as read-only evidence,
derives each cell digest from the P1 C9 cells, materializes the owner
mapping, and records all authority flags as false.  It never executes,
promotes, wires a route, writes to a database or touches the frontend.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.contracts import successor_runtime as c9t
from app.successor_runtime.runtime import facade_contracts as c9f
from app.successor_runtime.substrate.projections import registry as c9r

PROJECT_KEY = "p4-c9-fragment"
FRAGMENT_ID = "p4-c9-family-local-ahead-of-time-scaffolding"
FRAGMENT_SCHEMA = "mrw.functorial_successor.p4_fragment.v1"
FRAGMENT_PHASE = "P4"
FRAGMENT_FAMILY = "C9"
FRAGMENT_STATUS = "AHEAD_OF_TIME_SCAFFOLDING_UNADOPTED"
FRAGMENT_P4_STATUS = "P4_NOT_STARTED"

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_ROOT = (
    REPOSITORY_ROOT / "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration/evidence"
)
FRAGMENT_PATH = EVIDENCE_ROOT / "p4-fragments/C9.json"

_CELL_IDS = ("C9.1", "C9.2", "C9.3")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def content_digest(value: Any) -> str:
    return _sha256_bytes(_canonical_json(value).encode("utf-8"))


def _bind(path: Path, role: str) -> dict[str, object]:
    resolved = path.resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"cannot bind missing path {resolved}")
    relative = resolved.relative_to(REPOSITORY_ROOT.resolve())
    data = resolved.read_bytes()
    return {
        "path": str(relative),
        "sha256": _sha256_bytes(data),
        "bytes": len(data),
        "lines": len(data.splitlines()),
        "role": role,
    }


def _p1_cells() -> dict[str, dict[str, Any]]:
    artifact = json.loads(
        (EVIDENCE_ROOT / "P1FunctorizationEligibility.v1.json").read_text()
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


def _bindings() -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    source_paths = [
        (
            EVIDENCE_ROOT.parent
            / "01_functorial-successor-migration-development-contract.md",
            "frozen_contract_document",
        ),
        (
            EVIDENCE_ROOT.parent
            / "02_functorial-successor-migration-development-contract.freeze.json",
            "frozen_contract_manifest",
        ),
        (
            EVIDENCE_ROOT.parent
            / "06_functorial-successor-runtime-architecture-correction"
            ".draft.zh-CN.md",
            "frozen_architecture",
        ),
        (
            EVIDENCE_ROOT.parent
            / "09_functorial-successor-f0-semantic-owner-inventory.v1.json",
            "frozen_inventory",
        ),
        (
            EVIDENCE_ROOT.parent
            / "13_functorial-successor-c1-c9-locator-pending-inventory.v1.json",
            "frozen_locator_inventory",
        ),
        (
            EVIDENCE_ROOT / "P1FunctorizationEligibility.v1.json",
            "p1_eligibility",
        ),
        (
            EVIDENCE_ROOT / "p1-fragments/C9.json",
            "p1_fragment",
        ),
        (
            REPOSITORY_ROOT / "main/backend/app/contracts/responses.py",
            "legacy_envelope_donor",
        ),
        (
            REPOSITORY_ROOT / "main/backend/app/api/agent_sessions.py",
            "legacy_sse_donor",
        ),
        (
            REPOSITORY_ROOT / "main/backend/app/main.py",
            "legacy_envelope_middleware_donor",
        ),
        (
            REPOSITORY_ROOT / "main/backend/app/services/agent_sessions/store.py",
            "legacy_projection_donor_agent_sessions",
        ),
        (
            REPOSITORY_ROOT / "main/backend/app/services/agent_sessions/service.py",
            "legacy_projection_donor_agent_sessions",
        ),
        (
            REPOSITORY_ROOT / "main/backend/app/services/graph/backfill_graph_nodes.py",
            "legacy_projection_donor_graph_backfill",
        ),
        (
            REPOSITORY_ROOT / "main/backend/app/services/indexer/policy.py",
            "legacy_projection_donor_indexer",
        ),
        (
            REPOSITORY_ROOT
            / "main/backend/app/successor_runtime/substrate/projections/"
            "runtime_run.py",
            "successor_projector_pattern",
        ),
        (
            REPOSITORY_ROOT / "main/backend/app/successor_runtime/substrate/postgres/"
            "projection_offsets.py",
            "successor_offset_pattern",
        ),
        (
            REPOSITORY_ROOT / "main/backend/tests/contract/test_contracts_unittest.py",
            "legacy_envelope_test_donor",
        ),
    ]
    implementation_paths = [
        (
            REPOSITORY_ROOT
            / "main/backend/app/successor_runtime/runtime/facade_contracts.py",
            "facade_contracts",
        ),
        (
            REPOSITORY_ROOT
            / "main/backend/app/successor_runtime/substrate/projections/registry.py",
            "projector_registry",
        ),
        (
            REPOSITORY_ROOT / "main/backend/app/contracts/successor_runtime.py",
            "transport_dto",
        ),
        (Path(__file__).resolve(), "evidence_generator"),
    ]
    test_paths = [
        (
            REPOSITORY_ROOT
            / "main/backend/tests/successor_runtime/test_p4_c9_1_facade_contracts.py",
            "c9_1_facade_contracts",
        ),
        (
            REPOSITORY_ROOT
            / "main/backend/tests/successor_runtime/test_p4_c9_2_projector_registry.py",
            "c9_2_projector_registry",
        ),
        (
            REPOSITORY_ROOT
            / "main/backend/tests/successor_runtime/test_p4_c9_3_transport_dto.py",
            "c9_3_transport_dto",
        ),
        (
            REPOSITORY_ROOT
            / "main/backend/tests/successor_runtime/test_p4_c9_4_evidence_generator.py",
            "c9_4_evidence_generator",
        ),
        (
            REPOSITORY_ROOT / "main/backend/tests/successor_runtime/"
            "test_p4_c9_5_p1_consistency_and_public_payload.py",
            "c9_5_public_payload_and_caller_schema",
        ),
        (
            REPOSITORY_ROOT / "main/backend/tests/successor_runtime/"
            "test_p4_c9_6_fragment_stability.py",
            "c9_6_fragment_stability",
        ),
    ]
    return (
        [_bind(path, role) for path, role in source_paths],
        [_bind(path, role) for path, role in implementation_paths],
        [_bind(path, role) for path, role in test_paths],
    )


def build_fragment() -> dict[str, object]:
    source_bindings, implementation_bindings, test_bindings = _bindings()
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
        "source_bindings": source_bindings,
        "implementation_bindings": implementation_bindings,
        "test_bindings": test_bindings,
        "authority": {
            "production_canonical_write": False,
            "live_provider": False,
            "live_credential": False,
            "network": False,
            "cutover": False,
            "authority_transfer": False,
            "legacy_retired": False,
            "p4_promotion": False,
        },
        "open_findings": [
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
                    "SSE after_seq exclusivity and reconnect semantics are "
                    "validated as pure contracts only; no live stream "
                    "observation exists"
                ),
            },
            {
                "id": "C9_FRONTEND_DESIGN_ONLY_NO_BYTES",
                "severity": "P2",
                "description": (
                    "C9.2 is a design-only typed UI observation/interaction "
                    "contract; no frontend file was written"
                ),
            },
            {
                "id": "C9_PROJECTOR_REGISTRY_PURE_NO_POSTGRES",
                "severity": "P2",
                "description": (
                    "C9.3 aligns to ProjectionOffsetKey/Repository semantics "
                    "as a pure contract; no PostgreSQL offset or projection "
                    "write is executed"
                ),
            },
            {
                "id": "C9_ROUTE_AND_FRONTEND_OUT_OF_SCOPE",
                "severity": "P2",
                "description": (
                    "transport DTO is deliberately route-free and no frontend "
                    "product code was written"
                ),
            },
        ],
        "content_digest": "",
    }


def _self_test(fragment: dict[str, object]) -> None:
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


def main() -> None:
    first = build_fragment()
    second = build_fragment()
    assert _canonical_json(first) == _canonical_json(second), (
        "non-deterministic fragment"
    )
    digest = content_digest(
        {key: value for key, value in first.items() if key != "content_digest"}
    )
    first["content_digest"] = digest
    _self_test(first)
    FRAGMENT_PATH.parent.mkdir(parents=True, exist_ok=True)
    text = _canonical_json(first) + "\n"
    FRAGMENT_PATH.write_text(text)
    persisted = json.loads(FRAGMENT_PATH.read_text())
    assert _canonical_json(persisted) == _canonical_json(first)
    print(f"wrote {FRAGMENT_PATH}")
    print(f"content_digest {first['content_digest']}")
    print(f"cells {[cell['cell_id'] for cell in first['cells']]}")


if __name__ == "__main__":
    main()
