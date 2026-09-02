"""Content-addressed, internal-only delivery interpreter.

This interpreter has no network dependency.  It writes an exact idempotency
binding *before* the content-addressed blob effect, so crash readback can
distinguish a prepared-but-not-started attempt from an exported blob.  The
marker contains only identities/digests and an immutable receipt, never the
artifact bytes.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from app.successor_runtime.language.object_contracts import OperationContractRef
from app.successor_runtime.research.artifacts import DeliveryIntent, DeliveryReceiptRef
from app.successor_runtime.research.codec import canonical_bytes
from app.successor_runtime.runtime.assignments import canonical_digest, require_digest
from app.successor_runtime.runtime.ports import RuntimeScope
from app.successor_runtime.runtime.reconciliation import (
    AuthoritativeEffectReadback,
    EffectAttemptObservation,
)
from app.successor_runtime.runtime.recovery import NonStartProof
from app.successor_runtime.runtime.transitions import EffectDisposition

from .store import BlobNotFound, ProjectBlobStore


class InternalExportError(RuntimeError):
    """Base internal-export boundary error."""


class InternalExportBindingConflict(InternalExportError):
    """One idempotency identity was reused for different exact content."""


class InternalExportReadbackUnavailable(InternalExportError):
    """The authoritative marker cannot currently be read."""


class ApprovalReader(Protocol):
    def require_current(
        self,
        approval_id: str,
        *,
        run_id: str,
        step_id: str,
        payload_digest: str,
        authority_digest: str,
        now: datetime,
    ) -> object: ...


@dataclass(frozen=True, slots=True)
class InternalExportRequest:
    project_key: str
    project_scope_digest: str
    run_id: str
    step_id: str
    attempt_id: str
    assignment_digest: str
    operation_contract_ref: OperationContractRef
    handler_binding_digest: str
    delivery_intent: DeliveryIntent
    artifact_bytes: bytes
    artifact_digest: str
    payload_digest: str

    def __post_init__(self) -> None:
        for name in (
            "project_key",
            "run_id",
            "step_id",
            "attempt_id",
            "assignment_digest",
            "handler_binding_digest",
            "artifact_digest",
            "payload_digest",
            "project_scope_digest",
        ):
            if not getattr(self, name):
                raise ValueError(f"InternalExportRequest requires {name}")
        for name in (
            "project_scope_digest",
            "attempt_id",
            "assignment_digest",
            "handler_binding_digest",
            "artifact_digest",
            "payload_digest",
            "operation_contract_ref.contract_digest",
        ):
            value = (
                self.operation_contract_ref.contract_digest
                if name == "operation_contract_ref.contract_digest"
                else getattr(self, name)
            )
            require_digest(value, name)
        actual = hashlib.sha256(self.artifact_bytes).hexdigest()
        if actual != self.artifact_digest:
            raise ValueError("artifact bytes do not match artifact_digest")
        intent = self.delivery_intent
        if intent.artifact_ref == "" or intent.content_digest is None:
            raise ValueError("delivery intent must bind an exact artifact and content")
        if intent.approval_refs == ():
            raise ValueError("internal export requires human approval refs")

    @property
    def request_digest(self) -> str:
        intent = self.delivery_intent
        return canonical_digest(
            {
                "schema_version": "mrw.internal-export.request.v1",
                "project_key": self.project_key,
                "project_scope_digest": self.project_scope_digest,
                "run_id": self.run_id,
                "step_id": self.step_id,
                "attempt_id": self.attempt_id,
                "assignment_digest": self.assignment_digest,
                "operation_contract_ref": {
                    "kind": self.operation_contract_ref.kind,
                    "contract_version": self.operation_contract_ref.contract_version,
                    "contract_digest": self.operation_contract_ref.contract_digest,
                },
                "handler_binding_digest": self.handler_binding_digest,
                "delivery_intent_id": intent.delivery_intent_id,
                "delivery_intent_digest": intent.content_digest,
                "artifact_ref": intent.artifact_ref,
                "artifact_digest": self.artifact_digest,
                "approval_refs": intent.approval_refs,
                "authority_digest": intent.authority_digest,
                "idempotency_key": intent.idempotency_key,
                "payload_digest": self.payload_digest,
            }
        )


@dataclass(frozen=True, slots=True)
class InternalExportExecutionContext:
    scope: RuntimeScope
    approvals: ApprovalReader
    now: datetime


@dataclass(frozen=True, slots=True)
class InternalExportOutcome:
    receipt: DeliveryReceiptRef
    readback: AuthoritativeEffectReadback


@dataclass(frozen=True, slots=True)
class NonStartUnprovable:
    attempt_id: str
    reason: str


class InternalExportInterpreter:
    """Deterministic filesystem interpreter for the frozen internal channel."""

    interpreter_id = "successor-native.internal-export"
    interpreter_version = "1.0.0"
    provider_id = "mrw.internal-content-addressed-export"
    provider_version = "1.0.0"

    def __init__(
        self,
        *,
        operation_contract_ref: OperationContractRef,
        blob_store: ProjectBlobStore,
    ) -> None:
        self.operation_contract_ref = operation_contract_ref
        self.blob_store = blob_store
        self.operation_kinds = frozenset({operation_contract_ref.kind})

    def execute(
        self,
        step: object,
        context: object,
    ) -> InternalExportOutcome:
        if not isinstance(step, InternalExportRequest):
            raise TypeError("internal export requires InternalExportRequest")
        if not isinstance(context, InternalExportExecutionContext):
            raise TypeError("internal export requires InternalExportExecutionContext")
        self._require_exact_request(step, context.scope)
        now = _as_utc(context.now)
        intent = step.delivery_intent
        for approval_ref in intent.approval_refs:
            context.approvals.require_current(
                approval_ref,
                run_id=step.run_id,
                step_id=step.step_id,
                payload_digest=step.payload_digest,
                authority_digest=intent.authority_digest,
                now=now,
            )

        marker = self._ensure_prepared(step, now)
        existing = self._readback_request(step, marker=marker)
        if existing is not None:
            return existing

        # ProjectBlobStore verifies temp bytes, fsyncs, and atomically renames.
        blob = self.blob_store.store(step.project_scope_digest, step.artifact_bytes)
        if blob.digest != step.artifact_digest:
            raise InternalExportError("content-addressed export digest drift")
        succeeded = dict(marker)
        succeeded.update(
            state="SUCCEEDED",
            provider_locator=_provider_locator(step),
            outcome_time=marker["prepared_at"],
        )
        receipt_body = _receipt_body(step, succeeded)
        receipt_digest = hashlib.sha256(canonical_bytes(receipt_body)).hexdigest()
        succeeded["receipt_digest"] = receipt_digest
        self._write_marker_replace(step, succeeded)
        outcome = self._readback_request(step, marker=succeeded)
        if outcome is None:  # pragma: no cover - defensive filesystem failure
            raise InternalExportReadbackUnavailable(
                "internal export succeeded but authoritative readback is absent"
            )
        return outcome

    def readback(self, attempt: object) -> AuthoritativeEffectReadback:
        """Read authoritative marker/blob state without mutating either."""

        if isinstance(attempt, InternalExportRequest):
            try:
                marker = self._load_marker(attempt)
            except FileNotFoundError:
                return _unknown_readback(
                    attempt.attempt_id,
                    "IDEMPOTENCY_MARKER_ABSENT",
                    {"attempt_id": attempt.attempt_id, "marker": "ABSENT"},
                )
            failed = _failed_readback_from_marker(attempt.attempt_id, marker)
            if failed is not None:
                return failed
            outcome = self._readback_request(attempt, marker=marker)
            if outcome is None:
                return _unknown_readback(
                    attempt.attempt_id,
                    "PREPARED_EXPORT_BLOB_ABSENT",
                    {"attempt_id": attempt.attempt_id, "marker": marker},
                )
            return outcome.readback
        if isinstance(attempt, EffectAttemptObservation):
            try:
                marker = self._load_marker_locator(
                    attempt.authoritative_readback_locator
                )
            except FileNotFoundError:
                return _unknown_readback(
                    attempt.attempt_id,
                    "IDEMPOTENCY_MARKER_ABSENT",
                    {"attempt_id": attempt.attempt_id, "marker": "ABSENT"},
                )
            self._require_attempt_marker(attempt, marker)
            failed = _failed_readback_from_marker(attempt.attempt_id, marker)
            if failed is not None:
                return failed
            digest = str(marker["artifact_digest"])
            try:
                self.blob_store.readback(str(marker["project_scope_digest"]), digest)
            except BlobNotFound:
                return _unknown_readback(
                    attempt.attempt_id,
                    "PREPARED_EXPORT_BLOB_ABSENT",
                    {"attempt_id": attempt.attempt_id, "marker": marker},
                )
            receipt_digest = marker.get("receipt_digest")
            if not isinstance(receipt_digest, str):
                receipt_digest = hashlib.sha256(
                    canonical_bytes(_receipt_body_from_marker(marker))
                ).hexdigest()
            return AuthoritativeEffectReadback(
                attempt_id=attempt.attempt_id,
                disposition=EffectDisposition.SUCCEEDED,
                provider_locator=str(marker["provider_locator"]),
                receipt_digest=receipt_digest,
                observation_digest=canonical_digest(
                    {
                        "attempt_id": attempt.attempt_id,
                        "provider_locator": marker["provider_locator"],
                        "receipt_digest": receipt_digest,
                        "artifact_digest": digest,
                    }
                ),
            )
        raise TypeError(
            "readback requires InternalExportRequest or EffectAttemptObservation"
        )

    def readback_exact(
        self, request: InternalExportRequest
    ) -> InternalExportOutcome | AuthoritativeEffectReadback:
        """Reconstruct an exact receipt through the read-only request facade.

        Recovery needs the typed ``DeliveryReceiptRef`` that is intentionally
        omitted from the generic ``ReadbackInterpreter`` contract.  This
        facade performs the same marker/blob observations as ``readback`` but
        returns the exact receipt together with authoritative evidence when
        the effect is known to have succeeded.  It never prepares a marker,
        stores a blob, or dispatches the export effect.
        """

        return InternalExportReadbackFacade(
            operation_contract_ref=self.operation_contract_ref,
            blob_store=self.blob_store,
        ).readback_exact(request)

    def prove_not_started(self, attempt: object) -> NonStartProof | NonStartUnprovable:
        """Prove absence only from this interpreter's authoritative marker/blob."""

        if isinstance(attempt, InternalExportRequest):
            locator = self.readback_locator(attempt)
            attempt_id = attempt.attempt_id
            idempotency_key = attempt.delivery_intent.idempotency_key
            try:
                marker = self._load_marker(attempt)
            except FileNotFoundError:
                marker = None
            if self.blob_store.exists(
                attempt.project_scope_digest, attempt.artifact_digest
            ):
                return NonStartUnprovable(attempt_id, "EXPORT_BLOB_EXISTS")
            if marker is not None:
                self._require_marker_binding(attempt, marker)
        elif isinstance(attempt, EffectAttemptObservation):
            locator = attempt.authoritative_readback_locator
            attempt_id = attempt.attempt_id
            idempotency_key = attempt.external_idempotency_key
            try:
                marker = self._load_marker_locator(locator)
            except FileNotFoundError:
                marker = None
            if marker is not None:
                self._require_attempt_marker(attempt, marker)
                if self.blob_store.exists(
                    str(marker["project_scope_digest"]),
                    str(marker["artifact_digest"]),
                ):
                    return NonStartUnprovable(attempt_id, "EXPORT_BLOB_EXISTS")
        else:
            raise TypeError(
                "prove_not_started requires InternalExportRequest or EffectAttemptObservation"
            )

        observed_at = datetime.now(UTC)
        observation = {
            "schema_version": "mrw.internal-export.non-start-observation.v1",
            "attempt_id": attempt_id,
            "authoritative_readback_locator": locator,
            "marker_state": None if marker is None else marker.get("state"),
            "blob_exists": False,
        }
        content = {
            "attempt_id": attempt_id,
            "interpreter_id": self.interpreter_id,
            "interpreter_version": self.interpreter_version,
            "provider_id": self.provider_id,
            "provider_version": self.provider_version,
            "external_idempotency_key": idempotency_key,
            "authoritative_readback_locator": locator,
            "authoritative_observation_digest": canonical_digest(observation),
            "observed_at": observed_at,
        }
        provisional = NonStartProof.model_construct(
            **content,
            proof_digest="0" * 64,
        )
        return NonStartProof(
            **content,
            proof_digest=canonical_digest(
                provisional,
                exclude_fields={"proof_digest"},
            ),
        )

    def cancel(self, attempt: object) -> MappingResult:
        """Internal export has no mid-blob cancellation point."""

        attempt_id = getattr(attempt, "attempt_id", None)
        if not isinstance(attempt_id, str):
            raise TypeError("cancel requires an attempt identity")
        return MappingResult(
            attempt_id=attempt_id,
            state="CANCEL_OBSERVED_AT_STEP_BOUNDARY",
        )

    def readback_locator(self, request: InternalExportRequest) -> str:
        key_digest = hashlib.sha256(
            request.delivery_intent.idempotency_key.encode("utf-8")
        ).hexdigest()
        return f"internal-export-index:{request.project_scope_digest}:{key_digest}"

    def _marker_path(self, request: InternalExportRequest) -> Path:
        key_digest = hashlib.sha256(
            request.delivery_intent.idempotency_key.encode("utf-8")
        ).hexdigest()
        return (
            self.blob_store.root
            / "projects"
            / request.project_scope_digest
            / "internal-export-idempotency"
            / key_digest[:2]
            / f"{key_digest}.json"
        )

    def _locator_path(self, locator: str) -> Path:
        prefix = "internal-export-index:"
        if not locator.startswith(prefix):
            raise InternalExportReadbackUnavailable("invalid internal export locator")
        parts = locator[len(prefix) :].split(":")
        if len(parts) != 2:
            raise InternalExportReadbackUnavailable("invalid internal export locator")
        scope_digest, key_digest = parts
        require_digest(scope_digest, "locator scope digest")
        require_digest(key_digest, "locator idempotency digest")
        return (
            self.blob_store.root
            / "projects"
            / scope_digest
            / "internal-export-idempotency"
            / key_digest[:2]
            / f"{key_digest}.json"
        )

    def _ensure_prepared(
        self, request: InternalExportRequest, now: datetime
    ) -> dict[str, Any]:
        marker = _prepared_marker(request, now, self.readback_locator(request))
        path = self._marker_path(request)
        path.parent.mkdir(parents=True, exist_ok=True)
        encoded = canonical_bytes(marker)
        temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            with open(temp, "xb") as handle:
                handle.write(encoded)
                handle.flush()
                if self.blob_store.fsync:
                    os.fsync(handle.fileno())
            try:
                os.link(temp, path)
            except FileExistsError:
                existing = self._load_marker(request)
                self._require_marker_binding(request, existing)
                return existing
            if self.blob_store.fsync:
                ProjectBlobStore._fsync_directory(path.parent)
            return marker
        finally:
            temp.unlink(missing_ok=True)

    def _write_marker_replace(
        self, request: InternalExportRequest, marker: dict[str, Any]
    ) -> None:
        self._require_marker_binding(request, marker)
        path = self._marker_path(request)
        temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        encoded = canonical_bytes(marker)
        with open(temp, "xb") as handle:
            handle.write(encoded)
            handle.flush()
            if self.blob_store.fsync:
                os.fsync(handle.fileno())
        os.replace(temp, path)
        if self.blob_store.fsync:
            ProjectBlobStore._fsync_directory(path.parent)

    def _load_marker(self, request: InternalExportRequest) -> dict[str, Any]:
        marker = _load_json(self._marker_path(request))
        self._require_marker_binding(request, marker)
        return marker

    def _load_marker_locator(self, locator: str) -> dict[str, Any]:
        return _load_json(self._locator_path(locator))

    def _require_exact_request(
        self, request: InternalExportRequest, scope: RuntimeScope
    ) -> None:
        if request.operation_contract_ref != self.operation_contract_ref:
            raise InternalExportBindingConflict("operation contract digest drift")
        if (
            request.project_key != scope.project_scope.project_key
            or request.project_scope_digest != scope.project_scope.scope_digest
        ):
            raise InternalExportBindingConflict("project scope drift")
        if request.delivery_intent.authority_digest == "":
            raise InternalExportBindingConflict("delivery authority is absent")

    @staticmethod
    def _require_marker_binding(
        request: InternalExportRequest, marker: dict[str, Any]
    ) -> None:
        expected = {
            "project_key": request.project_key,
            "project_scope_digest": request.project_scope_digest,
            "run_id": request.run_id,
            "step_id": request.step_id,
            "attempt_id": request.attempt_id,
            "assignment_digest": request.assignment_digest,
            "operation_contract_digest": request.operation_contract_ref.contract_digest,
            "handler_binding_digest": request.handler_binding_digest,
            "delivery_intent_id": request.delivery_intent.delivery_intent_id,
            "delivery_intent_digest": request.delivery_intent.content_digest,
            "artifact_ref": request.delivery_intent.artifact_ref,
            "artifact_digest": request.artifact_digest,
            "authority_digest": request.delivery_intent.authority_digest,
            "idempotency_key": request.delivery_intent.idempotency_key,
            "payload_digest": request.payload_digest,
            "request_digest": request.request_digest,
        }
        if any(marker.get(key) != value for key, value in expected.items()):
            raise InternalExportBindingConflict(
                "idempotency marker has a different exact binding"
            )

    @staticmethod
    def _require_attempt_marker(
        attempt: EffectAttemptObservation, marker: dict[str, Any]
    ) -> None:
        expected = {
            "attempt_id": attempt.attempt_id,
            "assignment_digest": attempt.assignment_digest,
            "handler_binding_digest": attempt.handler_binding_digest,
            "idempotency_key": attempt.external_idempotency_key,
        }
        if any(marker.get(key) != value for key, value in expected.items()):
            raise InternalExportBindingConflict("attempt readback marker drift")

    def _readback_request(
        self,
        request: InternalExportRequest,
        *,
        marker: dict[str, Any],
    ) -> InternalExportOutcome | None:
        self._require_marker_binding(request, marker)
        try:
            self.blob_store.readback(
                request.project_scope_digest,
                request.artifact_digest,
            )
        except BlobNotFound:
            return None
        provider_locator = str(
            marker.get("provider_locator") or _provider_locator(request)
        )
        normalized = dict(marker)
        normalized["provider_locator"] = provider_locator
        normalized["outcome_time"] = marker.get("outcome_time") or marker["prepared_at"]
        receipt_body = _receipt_body(request, normalized)
        receipt_digest = hashlib.sha256(canonical_bytes(receipt_body)).hexdigest()
        supplied = marker.get("receipt_digest")
        if supplied is not None and supplied != receipt_digest:
            raise InternalExportBindingConflict("internal export receipt digest drift")
        receipt = DeliveryReceiptRef(
            receipt_ref=f"receipt:sha256:{receipt_digest}",
            delivery_intent_ref=request.delivery_intent.delivery_intent_id,
            attempt_ref=request.attempt_id,
            provider_locator=provider_locator,
            receipt_digest=receipt_digest,
            outcome_time=datetime.fromisoformat(str(normalized["outcome_time"])),
        )
        readback = AuthoritativeEffectReadback(
            attempt_id=request.attempt_id,
            disposition=EffectDisposition.SUCCEEDED,
            provider_locator=provider_locator,
            receipt_digest=receipt_digest,
            observation_digest=canonical_digest(
                {
                    "request_digest": request.request_digest,
                    "provider_locator": provider_locator,
                    "receipt_digest": receipt_digest,
                    "artifact_digest": request.artifact_digest,
                }
            ),
        )
        return InternalExportOutcome(receipt=receipt, readback=readback)


class InternalExportReadbackFacade:
    """Capability-limited internal-export observer with no execute method."""

    interpreter_id = InternalExportInterpreter.interpreter_id
    interpreter_version = InternalExportInterpreter.interpreter_version
    provider_id = InternalExportInterpreter.provider_id
    provider_version = InternalExportInterpreter.provider_version

    def __init__(
        self,
        *,
        operation_contract_ref: OperationContractRef,
        blob_store: ProjectBlobStore,
    ) -> None:
        self.operation_contract_ref = operation_contract_ref
        self._blob_store = blob_store

    def readback_locator(self, request: InternalExportRequest) -> str:
        key_digest = hashlib.sha256(
            request.delivery_intent.idempotency_key.encode("utf-8")
        ).hexdigest()
        return f"internal-export-index:{request.project_scope_digest}:{key_digest}"

    def readback_exact(
        self, request: InternalExportRequest
    ) -> InternalExportOutcome | AuthoritativeEffectReadback:
        """Observe exact marker/blob state and reconstruct a receipt if present."""

        if not isinstance(request, InternalExportRequest):
            raise TypeError("exact readback requires InternalExportRequest")
        if request.operation_contract_ref != self.operation_contract_ref:
            raise InternalExportBindingConflict("operation contract digest drift")
        key_digest = hashlib.sha256(
            request.delivery_intent.idempotency_key.encode("utf-8")
        ).hexdigest()
        marker_path = (
            self._blob_store.root
            / "projects"
            / request.project_scope_digest
            / "internal-export-idempotency"
            / key_digest[:2]
            / f"{key_digest}.json"
        )
        try:
            marker = _load_json(marker_path)
        except FileNotFoundError:
            return _unknown_readback(
                request.attempt_id,
                "IDEMPOTENCY_MARKER_ABSENT",
                {"attempt_id": request.attempt_id, "marker": "ABSENT"},
            )
        InternalExportInterpreter._require_marker_binding(request, marker)
        failed = _failed_readback_from_marker(request.attempt_id, marker)
        if failed is not None:
            return failed
        try:
            self._blob_store.readback(
                request.project_scope_digest,
                request.artifact_digest,
            )
        except BlobNotFound:
            return _unknown_readback(
                request.attempt_id,
                "PREPARED_EXPORT_BLOB_ABSENT",
                {"attempt_id": request.attempt_id, "marker": marker},
            )
        provider_locator = str(
            marker.get("provider_locator") or _provider_locator(request)
        )
        normalized = dict(marker)
        normalized["provider_locator"] = provider_locator
        normalized["outcome_time"] = marker.get("outcome_time") or marker["prepared_at"]
        receipt_body = _receipt_body(request, normalized)
        receipt_digest = hashlib.sha256(canonical_bytes(receipt_body)).hexdigest()
        supplied = marker.get("receipt_digest")
        if supplied is not None and supplied != receipt_digest:
            raise InternalExportBindingConflict("internal export receipt digest drift")
        receipt = DeliveryReceiptRef(
            receipt_ref=f"receipt:sha256:{receipt_digest}",
            delivery_intent_ref=request.delivery_intent.delivery_intent_id,
            attempt_ref=request.attempt_id,
            provider_locator=provider_locator,
            receipt_digest=receipt_digest,
            outcome_time=datetime.fromisoformat(str(normalized["outcome_time"])),
        )
        readback = AuthoritativeEffectReadback(
            attempt_id=request.attempt_id,
            disposition=EffectDisposition.SUCCEEDED,
            provider_locator=provider_locator,
            receipt_digest=receipt_digest,
            observation_digest=canonical_digest(
                {
                    "request_digest": request.request_digest,
                    "provider_locator": provider_locator,
                    "receipt_digest": receipt_digest,
                    "artifact_digest": request.artifact_digest,
                }
            ),
        )
        return InternalExportOutcome(receipt=receipt, readback=readback)


@dataclass(frozen=True, slots=True)
class MappingResult:
    attempt_id: str
    state: str


def _prepared_marker(
    request: InternalExportRequest, now: datetime, locator: str
) -> dict[str, Any]:
    intent = request.delivery_intent
    return {
        "schema_version": "mrw.internal-export.idempotency-marker.v1",
        "state": "PREPARED",
        "project_key": request.project_key,
        "project_scope_digest": request.project_scope_digest,
        "run_id": request.run_id,
        "step_id": request.step_id,
        "attempt_id": request.attempt_id,
        "assignment_digest": request.assignment_digest,
        "operation_contract_digest": request.operation_contract_ref.contract_digest,
        "handler_binding_digest": request.handler_binding_digest,
        "delivery_intent_id": intent.delivery_intent_id,
        "delivery_intent_digest": intent.content_digest,
        "artifact_ref": intent.artifact_ref,
        "artifact_digest": request.artifact_digest,
        "approval_refs": intent.approval_refs,
        "authority_digest": intent.authority_digest,
        "idempotency_key": intent.idempotency_key,
        "payload_digest": request.payload_digest,
        "request_digest": request.request_digest,
        "authoritative_readback_locator": locator,
        "provider_locator": _provider_locator(request),
        "prepared_at": _as_utc(now).isoformat(),
    }


def _provider_locator(request: InternalExportRequest) -> str:
    return (
        "internal-export://"
        f"{request.project_scope_digest}/sha256/{request.artifact_digest}"
    )


def _receipt_body(
    request: InternalExportRequest, marker: dict[str, Any]
) -> dict[str, Any]:
    return {
        "schema_version": "mrw.internal-export.receipt.v1",
        "delivery_intent_ref": request.delivery_intent.delivery_intent_id,
        "attempt_ref": request.attempt_id,
        "provider_locator": marker["provider_locator"],
        "artifact_digest": request.artifact_digest,
        "request_digest": request.request_digest,
        "outcome_time": marker["outcome_time"],
    }


def _receipt_body_from_marker(marker: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "mrw.internal-export.receipt.v1",
        "delivery_intent_ref": marker["delivery_intent_id"],
        "attempt_ref": marker["attempt_id"],
        "provider_locator": marker["provider_locator"],
        "artifact_digest": marker["artifact_digest"],
        "request_digest": marker["request_digest"],
        "outcome_time": marker.get("outcome_time") or marker["prepared_at"],
    }


def _unknown_readback(
    attempt_id: str, reason: str, observation: dict[str, object]
) -> AuthoritativeEffectReadback:
    return AuthoritativeEffectReadback(
        attempt_id=attempt_id,
        disposition=EffectDisposition.OUTCOME_UNKNOWN,
        observation_digest=canonical_digest(observation),
        reason=reason,
    )


def _failed_readback_from_marker(
    attempt_id: str, marker: dict[str, Any]
) -> AuthoritativeEffectReadback | None:
    if marker.get("state") != EffectDisposition.FAILED.value:
        return None
    failure_digest = marker.get("failure_digest")
    if not isinstance(failure_digest, str):
        raise InternalExportBindingConflict(
            "failed internal export marker lacks failure digest"
        )
    require_digest(failure_digest, "failed marker failure_digest")
    return AuthoritativeEffectReadback(
        attempt_id=attempt_id,
        disposition=EffectDisposition.FAILED,
        failure_digest=failure_digest,
        observation_digest=canonical_digest(
            {
                "attempt_id": attempt_id,
                "failure_digest": failure_digest,
                "request_digest": marker.get("request_digest"),
            }
        ),
        reason="AUTHORITATIVE_INTERNAL_EXPORT_FAILURE",
    )


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InternalExportReadbackUnavailable(
            f"invalid internal export marker: {path}"
        ) from exc
    if not isinstance(value, dict):
        raise InternalExportReadbackUnavailable(
            "internal export marker is not an object"
        )
    return value


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


__all__ = [
    "ApprovalReader",
    "InternalExportBindingConflict",
    "InternalExportError",
    "InternalExportExecutionContext",
    "InternalExportInterpreter",
    "InternalExportOutcome",
    "InternalExportReadbackFacade",
    "InternalExportReadbackUnavailable",
    "InternalExportRequest",
    "MappingResult",
    "NonStartUnprovable",
]
