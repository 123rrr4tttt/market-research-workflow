"""P4 C9 P1 aggregate/fragment/cell consistency and public payload exclusion."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from app.contracts.successor_runtime import (
    SuccessorRuntimeApiEnvelopeDTO,
    SuccessorRuntimeCommandDTO,
    SuccessorRuntimeMeta,
    SuccessorRuntimeProjectScopeRefDTO,
    SuccessorRuntimeQueryDTO,
    SuccessorRuntimeSseObservationDTO,
    SuccessorRuntimeUiObservationDTO,
)
from pydantic import ValidationError

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_GENERATOR = _BACKEND_ROOT / "scripts/generate_successor_p4_c9_fragment.py"


def _load_generator():
    spec = importlib.util.spec_from_file_location(
        "generate_successor_p4_c9_fragment",
        _GENERATOR,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_p1_aggregate_fragment_and_cell_digests_agree() -> None:
    module = _load_generator()
    artifact = json.loads(
        (module.EVIDENCE_ROOT / "P1FunctorizationEligibility.v1.json").read_text()
    )
    p1_fragment = json.loads(
        (module.EVIDENCE_ROOT / "p1-fragments/C9.json").read_text()
    )
    aggregate = {str(cell["cell"]): cell for cell in artifact["cells"]}
    fragment = {str(cell["cell"]): cell for cell in p1_fragment}
    assert set(fragment) == {"C9.1", "C9.2", "C9.3"}
    for cell_id in ("C9.1", "C9.2", "C9.3"):
        aggregate_digest = module.content_digest(aggregate[cell_id])
        assert aggregate_digest == module.content_digest(fragment[cell_id])
        assert module._p1_cell_digest(cell_id) == aggregate_digest


def _meta() -> dict[str, str]:
    return {
        "project_key": "p4-c9-demo",
        "trace_id": "trace-1",
        "projection_id": "projection.run-summary.v1",
    }


def _command_payload() -> dict[str, object]:
    return {
        "command_id": "cmd-1",
        "command_kind": "rebuild_projection",
        "project_locator": "p4-c9-demo",
        "meta": _meta(),
        "payload": {
            "payload_kind": "rebuild_projection",
            "projection_id": "projection.run-summary.v1",
            "mode": "FULL",
        },
    }


def _query_payload() -> dict[str, object]:
    return {
        "query_id": "query-1",
        "query_kind": "projection_events",
        "project_locator": "p4-c9-demo",
        "meta": _meta(),
        "params": {
            "params_kind": "projection_events",
            "after_seq": 5,
        },
    }


def test_external_request_dto_rejects_caller_schema_counterexample() -> None:
    command = _command_payload()
    for field_name in (
        "resolved_schema",
        "project_registry_revision",
        "incarnation",
        "scope_digest",
        "actor_ref",
    ):
        with pytest.raises(ValidationError):
            SuccessorRuntimeCommandDTO.model_validate(
                {**command, field_name: "caller-supplied"}
            )

    query = _query_payload()
    for field_name in (
        "resolved_schema",
        "project_registry_revision",
        "incarnation",
        "scope_digest",
        "actor_ref",
    ):
        with pytest.raises(ValidationError):
            SuccessorRuntimeQueryDTO.model_validate(
                {**query, field_name: "caller-supplied"}
            )


def test_typed_payload_rejects_nested_authority_and_control() -> None:
    command = _command_payload()
    with pytest.raises(ValidationError):
        SuccessorRuntimeCommandDTO.model_validate(
            {**command, "payload": {**command["payload"], "authority": True}}
        )
    with pytest.raises(ValidationError):
        SuccessorRuntimeCommandDTO.model_validate(
            {
                **command,
                "payload": {**command["payload"], "control_directive": "resume"},
            }
        )

    query = _query_payload()
    with pytest.raises(ValidationError):
        SuccessorRuntimeQueryDTO.model_validate(
            {**query, "params": {**query["params"], "control_feedback": True}}
        )


def _response_meta() -> dict[str, object]:
    scope = SuccessorRuntimeProjectScopeRefDTO(
        project_key="p4-c9-demo",
        resolved_schema="mrw_p4_c9_demo",
        project_registry_revision=1,
        incarnation="scope-inc-c9",
        scope_digest="a" * 64,
    ).model_dump()
    return {
        **_meta(),
        "project_scope_ref": scope,
        "projection_revision": 3,
        "source_digest": "a" * 64,
        "cursor": 2,
    }


def test_public_response_payloads_exclude_control_fields() -> None:
    meta = SuccessorRuntimeMeta(**_meta())
    assert meta.project_key == "p4-c9-demo"

    envelope = {
        "status": "ok",
        "data": {"projection_id": "projection.run-summary.v1"},
        "error": None,
        "meta": _response_meta(),
    }
    assert SuccessorRuntimeApiEnvelopeDTO.model_validate(envelope).status == "ok"
    with pytest.raises(ValidationError):
        SuccessorRuntimeApiEnvelopeDTO.model_validate(
            {**envelope, "control_directive": "resume"}
        )

    ui = {
        "state": "blocked",
        "projection_id": "projection.run-summary.v1",
        "meta": _response_meta(),
        "data": {"items": []},
    }
    assert SuccessorRuntimeUiObservationDTO.model_validate(ui).state == "blocked"
    with pytest.raises(ValidationError):
        SuccessorRuntimeUiObservationDTO.model_validate({**ui, "on_control": "approve"})

    sse = {
        "after_seq": 1,
        "reconnect": False,
        "meta": _response_meta(),
        "events": [],
        "next_seq": 1,
    }
    assert SuccessorRuntimeSseObservationDTO.model_validate(sse).after_seq == 1
    with pytest.raises(ValidationError):
        SuccessorRuntimeSseObservationDTO.model_validate(
            {**sse, "snapshot_authority": "on"}
        )
