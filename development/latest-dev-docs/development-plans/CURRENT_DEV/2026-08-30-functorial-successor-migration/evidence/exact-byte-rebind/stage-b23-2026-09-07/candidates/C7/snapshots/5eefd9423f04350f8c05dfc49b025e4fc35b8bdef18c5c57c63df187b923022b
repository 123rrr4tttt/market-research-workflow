"""S2b C7.2 ingest submission registry focused acceptance tests."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

import pytest

from app.successor_runtime.capabilities.ingest_c7_registry import (
    IngestRegistryAuthority,
    IngestRegistryBackendUnavailableError,
    IngestRegistryCompleteCommand,
    IngestRegistryConflictError,
    IngestRegistryCredentialError,
    IngestRegistryForgetCommand,
    IngestRegistryReadback,
    IngestRegistryReserveCommand,
    IngestRegistryState,
    LocalSuccessorIngestRegistryStore,
    complete_submission,
    derive_registry_identity,
    forget_submission,
    reserve_submission,
)
from app.successor_runtime.language.object_contracts import (
    OperationContractRef,
    ReturnContract,
)
from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
    CompiledStepRole,
    HandlerBindingKind,
    InterpreterBinding,
    ReturnContractBinding,
    RuntimeAssignment,
)
from app.successor_runtime.runtime.claims import ClaimBinding
from app.successor_runtime.runtime.node import (
    DefiniteInterpreterFailure,
    NodeIdentity,
    RuntimeExecutionContext,
)
from app.successor_runtime.substrate.postgres.ingest_c7_registry_handler import (
    C7IngestRegistryRuntimeHandler,
)

pytestmark = pytest.mark.unit

_PROJECT_KEY = "proj-a"
_TRIGGER_TYPE = "ingest.url.single"
_IDEMPOTENCY_KEY = "idem-1"


def _hex_digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _request_payload() -> dict[str, Any]:
    return {
        "url": "https://example.com/source",
        "params": {"limit": 3, "query": "\u4e2d\u6587\u6750\u6599"},
    }


def _subject_payload() -> dict[str, Any]:
    return {"title": "market material", "tags": ["mrw", "c7"]}


def _identity(
    payload: dict[str, Any] | None = None,
    *,
    idempotency_key: str = _IDEMPOTENCY_KEY,
) -> Any:
    return derive_registry_identity(
        _PROJECT_KEY,
        _TRIGGER_TYPE,
        idempotency_key,
        payload if payload is not None else _request_payload(),
    )


def _reserve_command(
    *,
    request_payload: dict[str, Any] | None = None,
    subject_payload: dict[str, Any] | None = None,
    idempotency_key: str = _IDEMPOTENCY_KEY,
    authority: IngestRegistryAuthority | None = None,
) -> IngestRegistryReserveCommand:
    resolved_request = (
        request_payload if request_payload is not None else _request_payload()
    )
    return IngestRegistryReserveCommand(
        identity=_identity(resolved_request, idempotency_key=idempotency_key),
        subject_payload=(
            subject_payload if subject_payload is not None else _subject_payload()
        ),
        request_payload=resolved_request,
        authority=authority,
    )


def _binding(
    handler: C7IngestRegistryRuntimeHandler,
) -> InterpreterBinding:
    return InterpreterBinding.from_content(
        operation_contract_digest=handler.operation_contract_digest,
        interpreter_profile_digest=handler.interpreter_profile_digest,
        deployment_catalog_digest=handler.deployment_catalog_digest,
        runtime_protocol_version="mrw.runtime.protocol.v1",
        project_scope_digest=_hex_digest("c7-project-scope"),
        resource_policy_epoch=1,
        authority_requirement_digest=_hex_digest("c7-authority"),
    )


def _new_handler(
    store: LocalSuccessorIngestRegistryStore,
    command: object,
    *,
    handler_binding_digest: str | None = None,
) -> tuple[C7IngestRegistryRuntimeHandler, InterpreterBinding]:
    binding = InterpreterBinding.from_content(
        operation_contract_digest=_hex_digest("c7-operation"),
        interpreter_profile_digest=_hex_digest("c7-interpreter"),
        deployment_catalog_digest=_hex_digest("c7-deployment-catalog"),
        runtime_protocol_version="mrw.runtime.protocol.v1",
        project_scope_digest=_hex_digest("c7-project-scope"),
        resource_policy_epoch=1,
        authority_requirement_digest=_hex_digest("c7-authority"),
    )
    handler = C7IngestRegistryRuntimeHandler(
        store=store,
        command=command,  # type: ignore[arg-type]
        handler_binding_digest=(
            handler_binding_digest
            if handler_binding_digest is not None
            else binding.binding_digest
        ),
        interpreter_profile_digest=binding.interpreter_profile_digest,
        operation_contract_digest=binding.operation_contract_digest,
        deployment_catalog_digest=binding.deployment_catalog_digest,
    )
    return handler, binding


def _assignment(
    handler: C7IngestRegistryRuntimeHandler,
    binding: InterpreterBinding,
    *,
    trace_id: str = "trace:c7-registry:001",
) -> RuntimeAssignment:
    return RuntimeAssignment(
        runtime_protocol_version="mrw.runtime.protocol.v1",
        work_item_id="work:c7-registry:001",
        assignment_kind=AssignmentKind.INTERPRET,
        project_key=_PROJECT_KEY,
        run_id="run:c7-registry:001",
        step_id="step:c7-registry:001",
        step_role=CompiledStepRole.EFFECT,
        capability_id="mrw.successor.ingest-c7.registry.v1",
        operation_contract_ref=OperationContractRef(
            kind="ingest_index.submission_registry.v1",
            contract_version="1.0.0",
            contract_digest=handler.operation_contract_digest,
        ),
        operation_contract_digest=handler.operation_contract_digest,
        return_contract_binding=ReturnContractBinding.from_contract(
            "mrw.successor.ingest-c7.registry.readback.v1",
            ReturnContract(
                success_modes=("SUCCEEDED",),
                failure_modes=("FAILED",),
                admission_required=False,
                wait_modes=(),
                cancel_modes=(),
            ),
        ),
        handler_binding_kind=HandlerBindingKind.INTERPRETER,
        handler_binding_ref=f"handler-binding:sha256:{binding.binding_digest}",
        handler_binding_digest=binding.binding_digest,
        handler_binding=binding,
        program_digest=binding.binding_digest,
        deployment_catalog_digest=handler.deployment_catalog_digest,
        execution_epoch=1,
        incarnation="inc:c7-registry:001",
        input_refs=(),
        queue_eligibility_digest="0" * 64,
        resource_policy_epoch=1,
        claim_authority_epoch=1,
        claim_policy_digest="0" * 64,
        expected_step_revision=0,
        trace_id=trace_id,
    )


def _claim(
    handler: C7IngestRegistryRuntimeHandler,
    assignment: RuntimeAssignment,
) -> ClaimBinding:
    return ClaimBinding.bind(
        assignment,
        authorization_digest="0" * 64,
        lease_token="lease:c7-registry",
        lease_expires_at=datetime(2026, 9, 2, 2, 0, tzinfo=UTC),
        node_id="node:c7-registry",
        node_profile_digest="0" * 64,
        authority_digest="0" * 64,
        interpreter_profile_digest=handler.interpreter_profile_digest,
    )


def _context() -> RuntimeExecutionContext:
    return RuntimeExecutionContext(
        node=NodeIdentity(
            node_id="node:c7-registry",
            incarnation="node-inc:c7-registry",
            started_at=datetime(2026, 9, 2, 1, 0, tzinfo=UTC),
        ),
        observed_at=datetime(2026, 9, 2, 1, 0, tzinfo=UTC),
    )


def _observability_json(readback: IngestRegistryReadback) -> str:
    payload: dict[str, Any] = {
        "identity": readback.identity.to_plain(),
        "lifecycle_state": readback.lifecycle_state.value,
        "observed_status": readback.observed_status,
        "duplicate": readback.duplicate,
        "task_id": readback.task_id,
        "subject_payload": readback.subject_payload,
        "response_payload": readback.response_payload,
        "value_ref": readback.value_ref,
        "revision": readback.revision,
        "created_at": readback.created_at,
        "updated_at": readback.updated_at,
        "authority": readback.authority.to_plain(),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def test_s2b_c7_registry_identity_is_deterministic_and_canonical() -> None:
    payload = _request_payload()
    identity = derive_registry_identity(
        _PROJECT_KEY,
        _TRIGGER_TYPE,
        _IDEMPOTENCY_KEY,
        payload,
    )

    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    expected_request_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    expected_registry_key = f"{_TRIGGER_TYPE}:{_PROJECT_KEY}:{_IDEMPOTENCY_KEY}"
    expected_submission_id = (
        "sub_" + hashlib.sha256(expected_registry_key.encode("utf-8")).hexdigest()[:20]
    )

    assert identity.registry_key == expected_registry_key
    assert identity.request_hash == expected_request_hash
    assert identity.submission_id == expected_submission_id
    assert identity.submission_id.startswith("sub_")
    assert len(identity.request_hash) == 64
    repeated = derive_registry_identity(
        _PROJECT_KEY,
        _TRIGGER_TYPE,
        _IDEMPOTENCY_KEY,
        payload,
    )
    assert repeated == identity


def test_s2b_c7_reserve_first_duplicate_and_hash_conflict() -> None:
    store = LocalSuccessorIngestRegistryStore()
    command = _reserve_command()

    first = reserve_submission(store, command)

    assert first.duplicate is False
    assert first.lifecycle_state is IngestRegistryState.SUBMITTED
    assert first.observed_status == "submitted"
    assert first.revision == 1
    assert first.response_payload is None
    assert store.inserts == 1
    assert store.updates == 0

    duplicate = reserve_submission(store, command)
    assert duplicate.duplicate is True
    assert duplicate.identity == first.identity
    assert duplicate.subject_payload == first.subject_payload
    assert store.inserts == 1

    duplicate_again = reserve_submission(store, command)
    assert duplicate_again == duplicate
    assert duplicate_again.readback_digest == duplicate.readback_digest

    conflicting = _reserve_command(
        request_payload={"url": "https://example.com/other"},
        idempotency_key=_IDEMPOTENCY_KEY,
    )
    with pytest.raises(IngestRegistryConflictError):
        reserve_submission(store, conflicting)
    assert store.find(first.identity.registry_key) is not None
    assert store.inserts == 1


def test_s2b_c7_complete_terminal_replay_and_terminal_conflict() -> None:
    store = LocalSuccessorIngestRegistryStore()
    command = _reserve_command()
    reserved = reserve_submission(store, command)
    registry_key = reserved.identity.registry_key

    queued = complete_submission(
        store,
        IngestRegistryCompleteCommand(
            registry_key=registry_key,
            lifecycle_state=IngestRegistryState.QUEUED,
            observed_status="queued",
            response_payload={"stage": "queued"},
            task_id="task-1",
        ),
    )
    assert queued.lifecycle_state is IngestRegistryState.QUEUED
    assert queued.task_id == "task-1"
    assert queued.revision == 2

    queued_replay = complete_submission(
        store,
        IngestRegistryCompleteCommand(
            registry_key=registry_key,
            lifecycle_state=IngestRegistryState.QUEUED,
            observed_status="queued",
            response_payload={"stage": "queued"},
            task_id="task-1",
        ),
    )
    assert queued_replay == queued
    assert queued_replay.readback_digest == queued.readback_digest
    assert store.updates == 1

    completed_response = {"status": "ok", "rows": [1, 2, 3]}
    completed = complete_submission(
        store,
        IngestRegistryCompleteCommand(
            registry_key=registry_key,
            lifecycle_state=IngestRegistryState.COMPLETED,
            observed_status="completed",
            response_payload=completed_response,
            task_id="task-1",
        ),
    )
    assert completed.lifecycle_state is IngestRegistryState.COMPLETED
    assert completed.revision == 3
    assert completed.response_payload == completed_response
    assert store.updates == 2

    replay = complete_submission(
        store,
        IngestRegistryCompleteCommand(
            registry_key=registry_key,
            lifecycle_state=IngestRegistryState.COMPLETED,
            observed_status="completed",
            response_payload=completed_response,
            task_id="task-1",
        ),
    )
    assert replay == completed
    assert replay.readback_digest == completed.readback_digest
    assert store.updates == 2

    with pytest.raises(IngestRegistryConflictError):
        complete_submission(
            store,
            IngestRegistryCompleteCommand(
                registry_key=registry_key,
                lifecycle_state=IngestRegistryState.FAILED,
                observed_status="failed",
                response_payload={"error": "terminal conflict"},
                task_id="task-1",
            ),
        )
    with pytest.raises(IngestRegistryConflictError):
        complete_submission(
            store,
            IngestRegistryCompleteCommand(
                registry_key=registry_key,
                lifecycle_state=IngestRegistryState.COMPLETED,
                observed_status="completed",
                response_payload={"status": "different-terminal-content"},
                task_id="task-1",
            ),
        )
    assert store.updates == 2


def test_s2b_c7_forget_missing_noop_and_allows_re_reserve() -> None:
    store = LocalSuccessorIngestRegistryStore()
    command = _reserve_command()
    first = reserve_submission(store, command)
    registry_key = first.identity.registry_key

    deleted = forget_submission(
        store,
        IngestRegistryForgetCommand(registry_key=registry_key),
    )
    assert deleted.deleted is True
    assert deleted.registry_key == registry_key
    assert store.find(registry_key) is None
    assert store.deletes == 1

    missing = forget_submission(
        store,
        IngestRegistryForgetCommand(registry_key=registry_key),
    )
    assert missing.deleted is False
    assert store.deletes == 1

    again = reserve_submission(store, command)
    assert again.duplicate is False
    assert store.inserts == 2
    assert store.find(registry_key) is not None


def test_s2b_c7_authority_stays_false_and_true_construction_raises() -> None:
    authority = IngestRegistryAuthority()
    plain = authority.to_plain()
    assert plain["schema_ref"] == "mrw.successor.ingest-c7.registry.authority.v1"
    for name, value in plain.items():
        if name != "schema_ref":
            assert value is False

    for name in (
        "live_provider",
        "canonical_write",
        "cutover",
        "external_delivery",
        "authority_transfer",
        "scheduler",
        "executor",
        "legacy_db_write",
        "candidate_created",
    ):
        with pytest.raises(ValueError):
            IngestRegistryAuthority(**{name: True})

    store = LocalSuccessorIngestRegistryStore()
    readback = reserve_submission(store, _reserve_command(authority=authority))
    assert readback.authority.to_plain()["canonical_write"] is False
    assert readback.authority.to_plain()["live_provider"] is False


@pytest.mark.parametrize(
    "marker",
    ("secret", "password", "credential", "api_key", "token_secret"),
)
def test_s2b_c7_rejects_credential_like_keys_without_readback_leak(
    marker: str,
) -> None:
    secret_value = "super-secret-value"
    for payload_field in ("subject", "request"):
        store = LocalSuccessorIngestRegistryStore()
        poisoned: dict[str, Any] = {"nested": {marker: secret_value}}
        if payload_field == "subject":
            command = _reserve_command(subject_payload=poisoned)
        else:
            command = _reserve_command(request_payload=poisoned)
        with pytest.raises(IngestRegistryCredentialError) as exc:
            reserve_submission(store, command)
        assert secret_value not in str(exc.value)
        assert store.find(command.identity.registry_key) is None
        assert store.inserts == 0

    store = LocalSuccessorIngestRegistryStore()
    clean = reserve_submission(store, _reserve_command())
    with pytest.raises(IngestRegistryCredentialError):
        complete_submission(
            store,
            IngestRegistryCompleteCommand(
                registry_key=clean.identity.registry_key,
                lifecycle_state=IngestRegistryState.COMPLETED,
                observed_status="completed",
                response_payload={"api_key": secret_value},
            ),
        )
    assert store.updates == 0

    store = LocalSuccessorIngestRegistryStore()
    observable = reserve_submission(store, _reserve_command())
    blob = _observability_json(observable).lower()
    assert "secret" not in blob
    assert "password" not in blob
    assert "api_key" not in blob


def test_s2b_c7_store_only_uses_successor_registry_table() -> None:
    store = LocalSuccessorIngestRegistryStore()
    assert store.table_name == "successor_ingest_submission_registry"
    assert store.legacy_table_writes == 0

    first = reserve_submission(store, _reserve_command())
    assert store.inserts == 1
    complete_submission(
        store,
        IngestRegistryCompleteCommand(
            registry_key=first.identity.registry_key,
            lifecycle_state=IngestRegistryState.COMPLETED,
            observed_status="completed",
            response_payload={"status": "ok"},
        ),
    )
    assert store.updates == 1
    forget_submission(
        store,
        IngestRegistryForgetCommand(registry_key=first.identity.registry_key),
    )
    assert store.deletes == 1
    assert store.legacy_table_writes == 0

    with pytest.raises(TypeError):
        LocalSuccessorIngestRegistryStore(table_name="ingest_submission_registry")
    assert store.legacy_table_writes == 0


def test_s2b_c7_store_reserve_duplicate_and_conflict() -> None:
    command = _reserve_command()
    source_store = LocalSuccessorIngestRegistryStore()
    readback = reserve_submission(source_store, command)

    store = LocalSuccessorIngestRegistryStore()
    stored, duplicate = store.reserve(readback)
    assert duplicate is False
    assert stored.identity == readback.identity
    assert store.inserts == 1

    _, duplicate_again = store.reserve(readback)
    assert duplicate_again is True
    assert store.inserts == 1

    conflicting_source = LocalSuccessorIngestRegistryStore()
    conflicting = reserve_submission(
        conflicting_source,
        _reserve_command(
            request_payload={"url": "https://example.com/conflict"},
            idempotency_key=_IDEMPOTENCY_KEY,
        ),
    )
    with pytest.raises(IngestRegistryConflictError):
        store.reserve(conflicting)


class _UnavailableStore:
    def find(self, registry_key: str) -> IngestRegistryReadback | None:
        raise IngestRegistryBackendUnavailableError(
            "successor registry backend unavailable",
            registry_key=registry_key,
        )

    def delete(self, registry_key: str) -> bool:
        raise IngestRegistryBackendUnavailableError(
            "successor registry backend unavailable",
            registry_key=registry_key,
        )


def test_s2b_c7_backend_unavailable_is_not_degraded_to_memory() -> None:
    command = _reserve_command()
    registry_key = command.identity.registry_key

    with pytest.raises(IngestRegistryBackendUnavailableError):
        reserve_submission(_UnavailableStore(), command)
    with pytest.raises(IngestRegistryBackendUnavailableError):
        complete_submission(
            _UnavailableStore(),
            IngestRegistryCompleteCommand(
                registry_key=registry_key,
                lifecycle_state=IngestRegistryState.COMPLETED,
                observed_status="completed",
                response_payload={"status": "ok"},
            ),
        )
    with pytest.raises(IngestRegistryBackendUnavailableError):
        forget_submission(
            _UnavailableStore(),
            IngestRegistryForgetCommand(registry_key=registry_key),
        )


def test_s2b_c7_handler_executes_reserve_command() -> None:
    store = LocalSuccessorIngestRegistryStore()
    command = _reserve_command()
    handler, binding = _new_handler(store, command)
    assignment = _assignment(handler, binding)
    claim = _claim(handler, assignment)

    outcome = handler.execute(assignment, claim, _context())

    assert handler.execute_calls == 1
    assert isinstance(handler.last_readback, IngestRegistryReadback)
    assert handler.last_readback.duplicate is False
    assert handler.operation_reason == "INGEST_REGISTRY_RESERVE_READBACK_ONLY"
    assert store.inserts == 1
    assert outcome.result_digest == handler.last_readback.readback_digest
    assert outcome.receipt_ref == (
        f"receipt:ingest-registry:{command.identity.registry_key}"
    )


def test_s2b_c7_handler_executes_complete_command() -> None:
    store = LocalSuccessorIngestRegistryStore()
    reserved = reserve_submission(store, _reserve_command())
    registry_key = reserved.identity.registry_key
    command = IngestRegistryCompleteCommand(
        registry_key=registry_key,
        lifecycle_state=IngestRegistryState.COMPLETED,
        observed_status="completed",
        response_payload={"status": "ok"},
        task_id="task-handler",
    )
    handler, binding = _new_handler(store, command)
    assignment = _assignment(handler, binding)
    claim = _claim(handler, assignment)

    outcome = handler.execute(assignment, claim, _context())

    assert handler.execute_calls == 1
    assert isinstance(handler.last_readback, IngestRegistryReadback)
    assert handler.last_readback.lifecycle_state is IngestRegistryState.COMPLETED
    assert handler.operation_reason == "INGEST_REGISTRY_COMPLETE_READBACK_ONLY"
    assert store.updates == 1
    assert outcome.result_digest == handler.last_readback.readback_digest
    assert outcome.receipt_ref == f"receipt:ingest-registry:{registry_key}"


def test_s2b_c7_handler_executes_forget_command() -> None:
    store = LocalSuccessorIngestRegistryStore()
    reserved = reserve_submission(store, _reserve_command())
    registry_key = reserved.identity.registry_key
    command = IngestRegistryForgetCommand(registry_key=registry_key)
    handler, binding = _new_handler(store, command)
    assignment = _assignment(handler, binding)
    claim = _claim(handler, assignment)

    outcome = handler.execute(assignment, claim, _context())

    assert handler.execute_calls == 1
    assert handler.last_readback is not None
    assert handler.last_readback.registry_key == registry_key
    assert handler.last_readback.deleted is True
    assert handler.operation_reason == "INGEST_REGISTRY_FORGET_READBACK_ONLY"
    assert store.find(registry_key) is None
    assert outcome.receipt_ref == f"receipt:ingest-registry:{registry_key}"


def test_s2b_c7_handler_claim_drift_fails_closed() -> None:
    store = LocalSuccessorIngestRegistryStore()
    handler, binding = _new_handler(store, _reserve_command())
    assignment = _assignment(handler, binding, trace_id="trace:claim-bind")
    claim = _claim(handler, assignment)
    drifted = _assignment(handler, binding, trace_id="trace:claim-drift")

    with pytest.raises(DefiniteInterpreterFailure) as exc:
        handler.execute(drifted, claim, _context())

    assert exc.value.failure_code == "CLAIM_ASSIGNMENT_BINDING_DRIFT"
    assert handler.execute_calls == 0
    assert store.inserts == 0


def test_s2b_c7_handler_digest_drift_fails_closed() -> None:
    store = LocalSuccessorIngestRegistryStore()
    command = _reserve_command()
    handler, binding = _new_handler(
        store,
        command,
        handler_binding_digest=_hex_digest("wrong-c7-handler-binding"),
    )
    assignment = _assignment(handler, binding)
    claim = _claim(handler, assignment)

    with pytest.raises(DefiniteInterpreterFailure) as exc:
        handler.execute(assignment, claim, _context())

    assert exc.value.failure_code == "EXACT_C7_INGEST_REGISTRY_HANDLER_BINDING_DRIFT"
    assert handler.execute_calls == 0
    assert store.inserts == 0
