"""S2 C8.3 report-export/token-state successor focused unit tests."""

from __future__ import annotations

import base64
import dataclasses
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.successor_runtime.capabilities.c8_report_export import (
    DEFAULT_LOCAL_TOKEN_SECRET,
    ReportExportSigningInput,
    ReportExportTokenAuthority,
    ReportExportTokenError,
    SignedReportExportToken,
    actor_id_from_secret,
    build_report_export_receipt,
    canonical_payload,
    sign_report_export_token,
    verify_report_export_token,
)
from app.successor_runtime.capabilities.c8_report_export_token_state import (
    ClaimExportTokenCommand,
    LocalSuccessorReportExportTokenStore,
    PruneExportTokenStatesCommand,
    ReadbackExportTokenCommand,
    ReportExportTokenStateAuthority,
    ReportExportTokenStateRecord,
    ReportExportTokenStateValue,
    RevokeExportTokenCommand,
    TokenStateBackendUnavailableError,
    TokenStateCredentialError,
    claim_report_export_token_once,
    prune_report_export_token_states,
    readback_report_export_token,
    revoke_report_export_token,
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
from app.successor_runtime.substrate.postgres.c8_export_token_state_handler import (
    C8_3ExportTokenStateRuntimeHandler,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 2, 1, 0, 0, tzinfo=UTC)
ISSUED_AT = NOW
EXPIRES_AT = NOW + timedelta(hours=1)
MARKDOWN_SHA256 = hashlib.sha256(b"report markdown").hexdigest()
ACTOR_DIGEST = actor_id_from_secret("authenticated", "alice@example.test")

_OP_DIGEST = hashlib.sha256(b"report.export_token_state.v1").hexdigest()
_PROFILE_DIGEST = hashlib.sha256(b"c8.3-export-token-state-interpreter").hexdigest()
_DEPLOYMENT_DIGEST = hashlib.sha256(
    b"c8.3-export-token-state-local-deployment"
).hexdigest()
_SCOPE_DIGEST = hashlib.sha256(b"local-s2b-c8-scope").hexdigest()
_AUTHORITY_DIGEST = hashlib.sha256(b"c8.3-export-token-state-authority").hexdigest()


def _signing_input(
    *,
    artifact_id: str = "artifact:c8-export:001",
    actor_digest: str = ACTOR_DIGEST,
    one_time_use: bool = True,
    issued_at: datetime = ISSUED_AT,
    expires_at: datetime = EXPIRES_AT,
) -> ReportExportSigningInput:
    return ReportExportSigningInput(
        artifact_id=artifact_id,
        markdown_sha256=MARKDOWN_SHA256,
        export_format="pdf",
        trace_id="trace:c8-export:001",
        request_id="request:c8-export:001",
        project_key="mrw-successor-c8",
        job_id=101,
        actor_digest=actor_digest,
        gate_snapshot={
            "decision": "pass",
            "gate_version": "v1",
            "hard_failures": [],
            "soft_failures": [],
            "missing_items": [],
        },
        issued_at=issued_at,
        expires_at=expires_at,
        one_time_use=one_time_use,
    )


def _signed() -> SignedReportExportToken:
    return sign_report_export_token(_signing_input())


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _token_from_payload_bytes(raw: bytes, token_secret: str) -> str:
    payload_part = _b64url(raw)
    signature = hmac.new(
        token_secret.encode("utf-8"),
        payload_part.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"llmrpt-v1.{payload_part}.{_b64url(signature)}"


def _re_signed(payload: dict[str, Any]) -> str:
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _token_from_payload_bytes(raw, DEFAULT_LOCAL_TOKEN_SECRET)


def _verify(
    token: str,
    *,
    markdown_sha256: str = MARKDOWN_SHA256,
    actor_digest: str = ACTOR_DIGEST,
    token_secret: str = DEFAULT_LOCAL_TOKEN_SECRET,
    now: datetime = NOW + timedelta(minutes=30),
    revoked_check: Any = None,
    used_check: Any = None,
) -> dict[str, Any]:
    return verify_report_export_token(
        token,
        markdown_sha256=markdown_sha256,
        actor_digest=actor_digest,
        token_secret=token_secret,
        now=now,
        revoked_check=revoked_check,
        used_check=used_check,
    )


def _claim_command(
    *,
    artifact_id: str = "artifact:c8-export:001",
    actor_digest: str = ACTOR_DIGEST,
    payload_digest: str | None = None,
) -> ClaimExportTokenCommand:
    return ClaimExportTokenCommand(
        artifact_id=artifact_id,
        actor_digest=actor_digest,
        project_key="mrw-successor-c8",
        trace_id="trace:c8-export:001",
        request_id="request:c8-export:001",
        job_id=101,
        payload_digest=payload_digest,
    )


def test_s2b_c8_sign_verify_round_trip_and_receipt() -> None:
    signed = _signed()
    payload = _verify(signed.artifact_token)

    assert signed.artifact_token.startswith("llmrpt-v1.")
    assert len(signed.token_ref) > 0
    assert len(signed.payload_digest) == 64
    assert len(signed.authority.to_plain()) == 9
    assert payload["artifact_id"] == "artifact:c8-export:001"
    assert payload["contract_version"] == "mrw.successor.c8.report-export-token.v1"
    assert payload["actor_digest"] == ACTOR_DIGEST
    assert "actor_id" not in payload

    receipt = build_report_export_receipt(
        _signing_input(),
        token=signed,
    )
    assert len(receipt.receipt_digest) == 64
    assert receipt.delivery_state == "NOT_DELIVERED"
    receipt_fields = dataclasses.asdict(receipt)
    assert "artifact_token" not in receipt_fields
    assert DEFAULT_LOCAL_TOKEN_SECRET not in receipt_fields.get("token_ref", "")


def test_s2b_c8_canonical_payload_never_contains_secret_or_token() -> None:
    signing_input = _signing_input()
    signed = _signed()

    plain = json.dumps(signing_input.payload_plain(), sort_keys=True)
    canonical = canonical_payload(signing_input)

    assert DEFAULT_LOCAL_TOKEN_SECRET not in plain
    assert signed.artifact_token not in plain
    assert DEFAULT_LOCAL_TOKEN_SECRET not in canonical.decode("utf-8")
    assert signed.artifact_token not in canonical.decode("utf-8")
    assert "alice@example.test" not in plain


def test_s2b_c8_verify_typed_reason_codes() -> None:
    signed = _signed()
    token = signed.artifact_token
    base_payload = _signing_input().payload_plain()

    def expect(callable_fn: Any, reason_code: str) -> None:
        with pytest.raises(ReportExportTokenError) as exc:
            callable_fn()
        assert exc.value.reason_code == reason_code

    expect(lambda: _verify("llmrpt-v1.abc"), "invalid_export_token_format")

    tampered_signature = token[:-1] + ("A" if token[-1] != "A" else "B")
    expect(lambda: _verify(tampered_signature), "invalid_export_token_signature")

    invalid_payload_token = _token_from_payload_bytes(
        b"{not-json",
        DEFAULT_LOCAL_TOKEN_SECRET,
    )
    expect(
        lambda: _verify(invalid_payload_token),
        "invalid_export_token_payload",
    )

    unsupported = {**base_payload, "contract_version": "legacy.export.v1"}
    expect(
        lambda: _verify(_re_signed(unsupported)),
        "unsupported_export_token_contract",
    )

    expect(
        lambda: _verify(token, markdown_sha256="1" * 64),
        "export_token_markdown_hash_mismatch",
    )

    missing_expiry = {**base_payload}
    missing_expiry.pop("expires_at", None)
    expect(
        lambda: _verify(_re_signed(missing_expiry)),
        "export_token_missing_expiry",
    )

    expired_payload = {
        **base_payload,
        "expires_at": (NOW - timedelta(minutes=1)).isoformat(),
    }
    expect(
        lambda: _verify(_re_signed(expired_payload)),
        "export_token_expired",
    )

    expect(
        lambda: _verify(token, actor_digest="authenticated:0000000000000000"),
        "export_token_actor_mismatch",
    )

    expect(
        lambda: _verify(token, revoked_check=lambda _artifact_id: True),
        "export_token_revoked",
    )
    expect(
        lambda: _verify(token, used_check=lambda _artifact_id: True),
        "export_token_already_used",
    )

    non_one_time = sign_report_export_token(
        _signing_input(artifact_id="artifact:c8-export:multi", one_time_use=False)
    )
    assert (
        _verify(
            non_one_time.artifact_token,
            used_check=lambda _artifact_id: True,
        )["one_time_use"]
        is False
    )


def test_s2b_c8_claim_is_exactly_once_and_crash_recovery_is_plan_only() -> None:
    store = LocalSuccessorReportExportTokenStore()
    signed = _signed()
    command = _claim_command(payload_digest=signed.payload_digest)

    first = claim_report_export_token_once(store, command)
    assert first.claimed is True
    assert first.already_used is False
    assert first.revoked is False
    assert first.degraded is False

    second = claim_report_export_token_once(store, command)
    assert second.claimed is False
    assert second.already_used is True
    assert second.revoked is False
    assert second.claimed_at >= first.claimed_at

    readback = readback_report_export_token(
        store,
        ReadbackExportTokenCommand(artifact_id=command.artifact_id),
    )
    assert readback.found is True
    assert readback.state is ReportExportTokenStateValue.USED
    assert readback.used is True
    assert readback.claimed is True
    assert readback.used_at == first.claimed_at
    assert readback.delivery_receipt_absent is True
    assert readback.delivery_receipt_present is False
    assert readback.recovery_mode == "plan_only"
    assert readback.recovery_outcome == "outcome_unknown"
    assert readback.plan_only_recovery is True
    assert readback.outcome_unknown_recovery is True

    third = claim_report_export_token_once(store, command)
    assert third.claimed is False
    assert third.already_used is True

    with pytest.raises(ReportExportTokenError) as exc:
        _verify(
            signed.artifact_token,
            used_check=lambda _artifact_id: readback.used,
        )
    assert exc.value.reason_code == "export_token_already_used"


def test_s2b_c8_revoked_token_cannot_be_claimed() -> None:
    store = LocalSuccessorReportExportTokenStore()
    revoke = revoke_report_export_token(
        store,
        RevokeExportTokenCommand(
            artifact_id="artifact:c8-export:revoked",
            actor_digest=ACTOR_DIGEST,
            reason="manual_revoke",
        ),
    )
    assert revoke.revoked is True
    assert revoke.revoked_at is not None

    claim = claim_report_export_token_once(
        store,
        _claim_command(artifact_id="artifact:c8-export:revoked"),
    )
    assert claim.claimed is False
    assert claim.revoked is True
    assert claim.already_used is False


def test_s2b_c8_revoke_after_use_preserves_used_and_revoked() -> None:
    store = LocalSuccessorReportExportTokenStore()
    artifact_id = "artifact:c8-export:revoked-after-use"
    claim = claim_report_export_token_once(
        store,
        _claim_command(artifact_id=artifact_id),
    )
    revoke = revoke_report_export_token(
        store,
        RevokeExportTokenCommand(
            artifact_id=artifact_id,
            actor_digest=ACTOR_DIGEST,
            reason="post_use_revoke",
        ),
    )

    assert revoke.revoked is True
    assert revoke.already_used is True
    assert revoke.used_at == claim.claimed_at
    assert revoke.revoked_at is not None

    readback = readback_report_export_token(
        store,
        ReadbackExportTokenCommand(artifact_id=artifact_id),
    )
    assert readback.state is ReportExportTokenStateValue.USED_AND_REVOKED
    assert readback.used is True
    assert readback.revoked is True
    assert readback.used_at == claim.claimed_at
    assert readback.revoked_at == revoke.revoked_at


def test_s2b_c8_prune_dry_run_and_execute_only_terminal_rows() -> None:
    old_now = datetime(2026, 8, 1, 0, 0, 0, tzinfo=UTC)
    store = LocalSuccessorReportExportTokenStore(now_provider=lambda: old_now)
    old_used = "artifact:c8-export:old-used"
    old_revoked = "artifact:c8-export:old-revoked"
    old_both = "artifact:c8-export:old-both"
    claim_report_export_token_once(store, _claim_command(artifact_id=old_used))
    revoke_report_export_token(
        store,
        RevokeExportTokenCommand(
            artifact_id=old_revoked,
            actor_digest=ACTOR_DIGEST,
            reason="old_revoke",
        ),
    )
    claim_report_export_token_once(store, _claim_command(artifact_id=old_both))
    revoke_report_export_token(
        store,
        RevokeExportTokenCommand(
            artifact_id=old_both,
            actor_digest=ACTOR_DIGEST,
            reason="old_both_revoke",
        ),
    )

    recent = "artifact:c8-export:recent"
    store.now_provider = lambda: NOW
    claim_report_export_token_once(store, _claim_command(artifact_id=recent))

    dry_run = prune_report_export_token_states(
        store,
        PruneExportTokenStatesCommand(
            retention_days=30,
            dry_run=True,
            now=NOW,
        ),
    )
    assert dry_run.candidate_count == 3
    assert dry_run.deleted_count == 0
    assert (
        readback_report_export_token(
            store,
            ReadbackExportTokenCommand(artifact_id=old_used),
        ).found
        is True
    )

    executed = prune_report_export_token_states(
        store,
        PruneExportTokenStatesCommand(
            retention_days=30,
            dry_run=False,
            now=NOW,
        ),
    )
    assert executed.candidate_count == 3
    assert executed.deleted_count == 3
    assert (
        readback_report_export_token(
            store,
            ReadbackExportTokenCommand(artifact_id=old_used),
        ).found
        is False
    )
    assert (
        readback_report_export_token(
            store,
            ReadbackExportTokenCommand(artifact_id=recent),
        ).found
        is True
    )


def test_s2b_c8_degraded_store_fails_closed_without_claim() -> None:
    store = LocalSuccessorReportExportTokenStore(degraded=True)
    claim_command = _claim_command(artifact_id="artifact:c8-export:degraded")

    with pytest.raises(TokenStateBackendUnavailableError):
        claim_report_export_token_once(store, claim_command)
    with pytest.raises(TokenStateBackendUnavailableError):
        revoke_report_export_token(
            store,
            RevokeExportTokenCommand(
                artifact_id="artifact:c8-export:degraded",
                actor_digest=ACTOR_DIGEST,
                reason="revoke",
            ),
        )
    with pytest.raises(TokenStateBackendUnavailableError):
        readback_report_export_token(
            store,
            ReadbackExportTokenCommand(artifact_id="artifact:c8-export:degraded"),
        )
    with pytest.raises(TokenStateBackendUnavailableError):
        prune_report_export_token_states(
            store,
            PruneExportTokenStatesCommand(
                retention_days=30,
                dry_run=True,
                now=NOW,
            ),
        )

    assert store._rows == {}
    assert store.reads == 0
    assert store.writes == 0


def test_s2b_c8_actor_digest_is_used_everywhere_not_raw_actor() -> None:
    raw_actor = "alice@example.test"
    digest = actor_id_from_secret("authenticated", raw_actor)
    signing_input = _signing_input(actor_digest=digest)
    signed = sign_report_export_token(signing_input)

    assert raw_actor not in signed.artifact_token
    assert raw_actor not in canonical_payload(signing_input).decode("utf-8")

    store = LocalSuccessorReportExportTokenStore()
    claim = claim_report_export_token_once(
        store,
        _claim_command(
            artifact_id="artifact:c8-export:digest",
            actor_digest=digest,
            payload_digest=signed.payload_digest,
        ),
    )
    readback = readback_report_export_token(
        store,
        ReadbackExportTokenCommand(artifact_id="artifact:c8-export:digest"),
    )

    assert claim.actor_digest == digest
    assert readback.actor_digest == digest
    assert raw_actor not in str(claim)
    assert raw_actor not in str(readback)
    assert "alice@example.test" not in str(claim)
    assert "alice@example.test" not in str(readback)


def test_s2b_c8_records_never_contain_credentials_or_full_tokens() -> None:
    signed = _signed()
    store = LocalSuccessorReportExportTokenStore()
    artifact_id = "artifact:c8-export:no-credentials"
    claim = claim_report_export_token_once(
        store,
        _claim_command(
            artifact_id=artifact_id,
            payload_digest=signed.payload_digest,
        ),
    )
    readback = readback_report_export_token(
        store,
        ReadbackExportTokenCommand(artifact_id=artifact_id),
    )

    for text in (
        str(claim),
        str(readback),
        json.dumps(
            dataclasses.asdict(readback),
            default=str,
            sort_keys=True,
        ),
    ):
        assert DEFAULT_LOCAL_TOKEN_SECRET not in text
        assert signed.artifact_token not in text
        assert "llmrpt-v1." not in text

    with pytest.raises(TokenStateCredentialError):
        RevokeExportTokenCommand(
            artifact_id=artifact_id,
            actor_digest=ACTOR_DIGEST,
            reason=signed.artifact_token,
        )
    with pytest.raises(TokenStateCredentialError):
        ClaimExportTokenCommand(
            artifact_id=artifact_id,
            actor_digest=signed.artifact_token,
        )
    with pytest.raises(TokenStateCredentialError):
        ReportExportTokenStateRecord(
            artifact_id=signed.artifact_token,
            actor_digest=ACTOR_DIGEST,
            state=ReportExportTokenStateValue.UNUSED,
        )


def test_s2b_c8_authorities_are_all_false_and_true_raises() -> None:
    export_authority = ReportExportTokenAuthority()
    state_authority = ReportExportTokenStateAuthority()

    export_plain = export_authority.to_plain()
    state_plain = state_authority.to_plain()
    assert export_plain["schema_ref"] == ("mrw.successor.c8.report-export.authority.v1")
    assert state_plain["schema_ref"] == (
        "mrw.successor.c8.report-export-token-state.authority.v1"
    )
    assert all(
        export_plain[name] is False
        for name in (
            "live_provider",
            "canonical_write",
            "cutover",
            "external_delivery",
            "authority_transfer",
            "scheduler",
            "executor",
            "credential_read",
        )
    )
    assert all(
        state_plain[name] is False
        for name in (
            "live_provider",
            "canonical_write",
            "cutover",
            "external_delivery",
            "authority_transfer",
            "scheduler",
            "executor",
            "credential_read",
            "legacy_db_write",
        )
    )

    for field_name in (
        "live_provider",
        "canonical_write",
        "cutover",
        "external_delivery",
        "authority_transfer",
        "scheduler",
        "executor",
        "credential_read",
    ):
        with pytest.raises(ValueError):
            ReportExportTokenAuthority(**{field_name: True})

    for field_name in (
        "live_provider",
        "canonical_write",
        "cutover",
        "external_delivery",
        "authority_transfer",
        "scheduler",
        "executor",
        "credential_read",
        "legacy_db_write",
    ):
        with pytest.raises(ValueError):
            ReportExportTokenStateAuthority(**{field_name: True})


def _binding(
    *,
    operation_digest: str = _OP_DIGEST,
    interpreter_profile_digest: str = _PROFILE_DIGEST,
    deployment_catalog_digest: str = _DEPLOYMENT_DIGEST,
) -> InterpreterBinding:
    return InterpreterBinding.from_content(
        operation_contract_digest=operation_digest,
        interpreter_profile_digest=interpreter_profile_digest,
        deployment_catalog_digest=deployment_catalog_digest,
        runtime_protocol_version="mrw.runtime.protocol.v1",
        project_scope_digest=_SCOPE_DIGEST,
        resource_policy_epoch=1,
        authority_requirement_digest=_AUTHORITY_DIGEST,
    )


def _return_binding() -> ReturnContractBinding:
    return ReturnContractBinding.from_contract(
        "mrw.successor.c8.report-export-token-state.readback.v1",
        ReturnContract(
            success_modes=("SUCCEEDED",),
            failure_modes=("FAILED",),
            admission_required=False,
            wait_modes=(),
            cancel_modes=(),
        ),
    )


def _handler(
    command: Any,
    store: LocalSuccessorReportExportTokenStore,
    binding: InterpreterBinding | None = None,
) -> C8_3ExportTokenStateRuntimeHandler:
    if binding is None:
        binding = _binding()
    return C8_3ExportTokenStateRuntimeHandler(
        store=store,
        command=command,
        handler_binding_digest=binding.binding_digest,
        interpreter_profile_digest=binding.interpreter_profile_digest,
        operation_contract_digest=binding.operation_contract_digest,
        deployment_catalog_digest=binding.deployment_catalog_digest,
    )


def _assignment(
    binding: InterpreterBinding,
    *,
    work_item_id: str = "work:s2b-c8-export-token:001",
) -> RuntimeAssignment:
    return RuntimeAssignment(
        runtime_protocol_version="mrw.runtime.protocol.v1",
        work_item_id=work_item_id,
        assignment_kind=AssignmentKind.INTERPRET,
        project_key="mrw-successor-c8",
        run_id="run:s2b-c8-export-token:001",
        step_id="step:c8-3:export-token-state",
        step_role=CompiledStepRole.EFFECT,
        capability_id="report.export_token_state.v1",
        operation_contract_ref=OperationContractRef(
            kind="report.export_token_state.v1",
            contract_version="1.0.0",
            contract_digest=binding.operation_contract_digest,
        ),
        operation_contract_digest=binding.operation_contract_digest,
        return_contract_binding=_return_binding(),
        handler_binding_kind=HandlerBindingKind.INTERPRETER,
        handler_binding_ref=(f"handler-binding:sha256:{binding.binding_digest}"),
        handler_binding_digest=binding.binding_digest,
        handler_binding=binding,
        program_digest=binding.binding_digest,
        deployment_catalog_digest=binding.deployment_catalog_digest,
        execution_epoch=1,
        incarnation="inc:s2b-c8-export-token:001",
        input_refs=(),
        queue_eligibility_digest="0" * 64,
        resource_policy_epoch=1,
        claim_authority_epoch=1,
        claim_policy_digest="0" * 64,
        expected_step_revision=0,
        trace_id="trace:s2b-c8-export-token:001",
    )


def _claim(
    handler: C8_3ExportTokenStateRuntimeHandler,
    assignment: RuntimeAssignment,
) -> ClaimBinding:
    return ClaimBinding.bind(
        assignment,
        authorization_digest="0" * 64,
        lease_token="lease:s2b-c8-export-token",
        lease_expires_at=NOW + timedelta(hours=1),
        node_id="node:s2b-c8-export-token",
        node_profile_digest="0" * 64,
        authority_digest="0" * 64,
        interpreter_profile_digest=handler.interpreter_profile_digest,
    )


def _context() -> RuntimeExecutionContext:
    return RuntimeExecutionContext(
        node=NodeIdentity(
            node_id="node:s2b-c8-export-token",
            incarnation="node-inc:s2b-c8-export-token",
            started_at=NOW,
        ),
        observed_at=NOW,
    )


def test_s2b_c8_handler_executes_token_state_command_with_exact_binding() -> None:
    store = LocalSuccessorReportExportTokenStore()
    artifact_id = "artifact:c8-export:handler"
    command = _claim_command(artifact_id=artifact_id)
    handler = _handler(command, store)
    binding = _binding()
    assignment = _assignment(binding)
    claim = _claim(handler, assignment)

    outcome = handler.execute(assignment, claim, _context())

    assert handler.execute_calls == 1
    assert handler.last_record is not None
    assert handler.last_record.claimed is True
    assert len(outcome.result_digest) == 64
    assert outcome.result_digest == handler.last_record.record_digest
    assert outcome.receipt_ref == f"receipt:report-export-token-state:{artifact_id}"


def test_s2b_c8_handler_exact_binding_drift_fails_closed() -> None:
    store = LocalSuccessorReportExportTokenStore()
    handler = _handler(
        _claim_command(artifact_id="artifact:c8-export:binding-drift"),
        store,
    )
    drifted_binding = _binding(
        operation_digest=hashlib.sha256(b"different-operation").hexdigest()
    )
    assignment = _assignment(drifted_binding)
    claim = _claim(handler, assignment)

    with pytest.raises(DefiniteInterpreterFailure) as exc:
        handler.execute(assignment, claim, _context())

    assert exc.value.failure_code == (
        "EXACT_C8_3_EXPORT_TOKEN_STATE_HANDLER_BINDING_DRIFT"
    )
    assert handler.execute_calls == 0
    assert handler.last_record is None


def test_s2b_c8_handler_claim_assignment_drift_fails_closed() -> None:
    store = LocalSuccessorReportExportTokenStore()
    binding = _binding()
    handler = _handler(
        _claim_command(artifact_id="artifact:c8-export:claim-drift"),
        store,
        binding=binding,
    )
    first_assignment = _assignment(
        binding,
        work_item_id="work:s2b-c8-export-token:first",
    )
    second_assignment = _assignment(
        binding,
        work_item_id="work:s2b-c8-export-token:second",
    )
    claim_for_second = _claim(handler, second_assignment)

    with pytest.raises(DefiniteInterpreterFailure) as exc:
        handler.execute(first_assignment, claim_for_second, _context())

    assert exc.value.failure_code == "CLAIM_ASSIGNMENT_BINDING_DRIFT"
    assert handler.execute_calls == 0
    assert handler.last_record is None
