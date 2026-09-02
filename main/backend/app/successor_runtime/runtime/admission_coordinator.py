"""Exact-contract canonical admission coordination.

The coordinator deliberately separates the three durable phases of an
admission whose canonical owner is outside the runtime journal transaction:

``prepare CommitIntent -> canonical readback/commit -> finalize receipt``.

Dispatch is keyed by the exact :class:`OperationContractRef` digest.  Candidate
Python classes are validation details inside a capability handler; they never
select the handler or canonical owner.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from pydantic import Field, model_validator

from app.successor_runtime.language.object_contracts import OperationContractRef

from .admission import CommitIntent, VerificationBinding, require_admission_binding
from .assignments import (
    AssignmentKind,
    Digest,
    FrozenContract,
    RuntimeAssignment,
    canonical_digest,
)
from .ports import RuntimeScope


class AdmissionCoordinatorError(RuntimeError):
    """Base fail-closed admission error."""


class AdmissionRegistryError(AdmissionCoordinatorError):
    """An exact operation contract has no unique admission realization."""


class AdmissionBindingError(AdmissionCoordinatorError):
    """The assignment, verification, scope, or canonical head drifted."""


class CanonicalReadbackKind(StrEnum):
    FOUND = "FOUND"
    NOT_FOUND = "NOT_FOUND"
    UNAVAILABLE = "UNAVAILABLE"


class AdmissionProgress(StrEnum):
    PREPARED = "PREPARED"
    CANONICAL_COMMITTED = "CANONICAL_COMMITTED"
    FINALIZED = "FINALIZED"
    WAITING_READBACK = "WAITING_READBACK"


class CanonicalCommit(FrozenContract):
    """Exact canonical observation returned by commit or authoritative readback."""

    schema_version: str = "mrw.runtime.canonical_commit.v1"
    commit_intent_id: str = Field(min_length=1)
    canonical_owner: str = Field(min_length=1)
    project_key: str = Field(min_length=1)
    object_id: str = Field(min_length=1)
    canonical_ref: str = Field(min_length=1)
    canonical_revision: int = Field(ge=1)
    canonical_incarnation: str = Field(min_length=1)
    content_digest: Digest
    receipt_digest: Digest


class CanonicalCommitReadback(FrozenContract):
    """Authoritative canonical-store readback; absence is explicit."""

    kind: CanonicalReadbackKind
    commit: CanonicalCommit | None = None
    observation_digest: Digest
    reason: str | None = None

    @model_validator(mode="after")
    def validate_kind_payload(self) -> "CanonicalCommitReadback":
        if (self.kind is CanonicalReadbackKind.FOUND) != (self.commit is not None):
            raise ValueError("FOUND readback requires exactly one CanonicalCommit")
        return self

    @classmethod
    def found(cls, commit: CanonicalCommit) -> "CanonicalCommitReadback":
        return cls(
            kind=CanonicalReadbackKind.FOUND,
            commit=commit,
            observation_digest=canonical_digest(commit),
        )

    @classmethod
    def absent(cls, *, observation: Mapping[str, object]) -> "CanonicalCommitReadback":
        return cls(
            kind=CanonicalReadbackKind.NOT_FOUND,
            observation_digest=canonical_digest(dict(observation)),
        )

    @classmethod
    def unavailable(cls, *, reason: str, observation: Mapping[str, object]) -> "CanonicalCommitReadback":
        return cls(
            kind=CanonicalReadbackKind.UNAVAILABLE,
            observation_digest=canonical_digest(dict(observation)),
            reason=reason,
        )


class AdmissionHandler(Protocol):
    """Capability-owned exact admission implementation."""

    canonical_owner: str

    def commit(
        self,
        scope: RuntimeScope,
        intent: CommitIntent,
        candidate: object,
        binding: VerificationBinding,
    ) -> CanonicalCommit: ...

    def readback(
        self,
        scope: RuntimeScope,
        intent: CommitIntent,
        candidate: object,
    ) -> CanonicalCommitReadback: ...


class CommitIntentStore(Protocol):
    """Runtime-side intent store adapter used without importing infrastructure."""

    def prepare(self, binding: object) -> Mapping[str, Any]: ...

    def load(self, commit_intent_id: str) -> Mapping[str, Any]: ...

    def mark_committed(
        self,
        commit_intent_id: str,
        *,
        expected_revision: int,
        canonical_commit_ref: str,
        receipt_digest: str,
    ) -> Mapping[str, Any]: ...

    def mark_outcome_unknown(
        self,
        commit_intent_id: str,
        *,
        expected_revision: int,
    ) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class AdmissionRegistration:
    operation_contract_ref: OperationContractRef
    handler: AdmissionHandler


class ExactAdmissionRegistry:
    """Immutable-by-convention digest registry for admission realizations."""

    def __init__(self, registrations: Sequence[AdmissionRegistration]) -> None:
        by_digest: dict[str, AdmissionRegistration] = {}
        by_kind_version: dict[tuple[str, str], str] = {}
        for registration in registrations:
            ref = registration.operation_contract_ref
            if ref.contract_digest in by_digest:
                raise AdmissionRegistryError(
                    f"duplicate admission operation digest: {ref.contract_digest}"
                )
            kind_version = (ref.kind, ref.contract_version)
            previous = by_kind_version.get(kind_version)
            if previous is not None and previous != ref.contract_digest:
                raise AdmissionRegistryError(
                    "ambiguous admission contract kind/version; exact frozen epoch required"
                )
            by_digest[ref.contract_digest] = registration
            by_kind_version[kind_version] = ref.contract_digest
        self._by_digest = by_digest

    def resolve_required(
        self, operation_contract_ref: OperationContractRef
    ) -> AdmissionRegistration:
        registration = self._by_digest.get(operation_contract_ref.contract_digest)
        if registration is None:
            raise AdmissionRegistryError(
                "no admission handler for exact operation contract digest"
            )
        if registration.operation_contract_ref != operation_contract_ref:
            raise AdmissionRegistryError("operation contract ref/digest registry drift")
        return registration


@dataclass(frozen=True, slots=True)
class PreparedAdmission:
    scope: RuntimeScope
    assignment: RuntimeAssignment
    intent: CommitIntent
    binding: VerificationBinding
    candidate: object
    registration: AdmissionRegistration
    intent_revision: int


@dataclass(frozen=True, slots=True)
class AdmissionResult:
    progress: AdmissionProgress
    intent_revision: int
    canonical_commit: CanonicalCommit | None = None
    readback: CanonicalCommitReadback | None = None


class AdmissionCoordinator:
    """Coordinate exact admission without collapsing two transaction domains."""

    def __init__(
        self,
        *,
        registry: ExactAdmissionRegistry,
        commit_intents: CommitIntentStore,
        commit_binding_factory: Any,
    ) -> None:
        self.registry = registry
        self.commit_intents = commit_intents
        self.commit_binding_factory = commit_binding_factory

    def prepare(
        self,
        *,
        scope: RuntimeScope,
        assignment: RuntimeAssignment,
        intent: CommitIntent,
        candidate: object,
        binding: VerificationBinding,
        current_authority_digest: str,
        current_base_revision: int,
        current_incarnation: str,
        ordered_event_payloads: Sequence[object],
    ) -> PreparedAdmission:
        """Validate and durably prepare; caller commits this phase before effects."""

        registration = self._require_exact_runtime_binding(
            scope=scope,
            assignment=assignment,
            intent=intent,
            binding=binding,
        )
        if registration.handler.canonical_owner != intent.canonical_owner:
            raise AdmissionBindingError("canonical owner differs from exact handler")
        try:
            require_admission_binding(
                binding,
                intent,
                current_authority_digest=current_authority_digest,
                current_base_revision=current_base_revision,
                current_incarnation=current_incarnation,
                ordered_event_payloads=list(ordered_event_payloads),
            )
        except ValueError as exc:
            raise AdmissionBindingError(str(exc)) from exc

        commit_binding = self.commit_binding_factory(
            assignment=assignment,
            intent=intent,
        )
        row = self.commit_intents.prepare(commit_binding)
        state = _state_value(row)
        if state not in {"PREPARED", "OUTCOME_UNKNOWN", "COMMITTED"}:
            raise AdmissionBindingError(f"commit intent cannot proceed from {state}")
        revision = _revision(row)
        return PreparedAdmission(
            scope=scope,
            assignment=assignment,
            intent=intent,
            binding=binding,
            candidate=candidate,
            registration=registration,
            intent_revision=revision,
        )

    def commit_prepared(self, prepared: PreparedAdmission) -> AdmissionResult:
        """Read back first, then commit only after authoritative NOT_FOUND.

        This method never finalizes runtime state.  A crash after the returned
        canonical commit is therefore repaired by :meth:`recover`, not by
        invoking this method again blindly.
        """

        row = self.commit_intents.load(prepared.intent.commit_intent_id)
        revision = _revision(row)
        if _state_value(row) == "COMMITTED":
            readback = self._readback_exact(prepared)
            if readback.kind is not CanonicalReadbackKind.FOUND:
                raise AdmissionBindingError(
                    "runtime says COMMITTED but canonical readback is unavailable"
                )
            return AdmissionResult(
                progress=AdmissionProgress.FINALIZED,
                intent_revision=revision,
                canonical_commit=readback.commit,
                readback=readback,
            )

        readback = self._readback_exact(prepared)
        if readback.kind is CanonicalReadbackKind.FOUND:
            return AdmissionResult(
                progress=AdmissionProgress.CANONICAL_COMMITTED,
                intent_revision=revision,
                canonical_commit=readback.commit,
                readback=readback,
            )
        if readback.kind is CanonicalReadbackKind.UNAVAILABLE:
            unknown = self._mark_unknown_once(prepared, revision)
            return AdmissionResult(
                progress=AdmissionProgress.WAITING_READBACK,
                intent_revision=_revision(unknown),
                readback=readback,
            )

        try:
            committed = prepared.registration.handler.commit(
                prepared.scope,
                prepared.intent,
                prepared.candidate,
                prepared.binding,
            )
            self._require_exact_commit(prepared, committed)
        except Exception:
            if getattr(
                prepared.registration.handler,
                "atomic_with_caller_uow",
                False,
            ):
                # This handler shares the caller's transaction; the outer UoW
                # rolls back every canonical mutation, so the failure is
                # definite and must not be mislabeled OUTCOME_UNKNOWN.
                raise
            # The call may have crossed the canonical boundary.  One immediate
            # readback is safe; an unavailable/absent observation must never
            # trigger another commit in this call.
            after_failure = self._readback_exact(prepared)
            if after_failure.kind is CanonicalReadbackKind.FOUND:
                return AdmissionResult(
                    progress=AdmissionProgress.CANONICAL_COMMITTED,
                    intent_revision=revision,
                    canonical_commit=after_failure.commit,
                    readback=after_failure,
                )
            unknown = self._mark_unknown_once(prepared, revision)
            return AdmissionResult(
                progress=AdmissionProgress.WAITING_READBACK,
                intent_revision=_revision(unknown),
                readback=after_failure,
            )
        return AdmissionResult(
            progress=AdmissionProgress.CANONICAL_COMMITTED,
            intent_revision=revision,
            canonical_commit=committed,
            readback=readback,
        )

    def finalize(
        self,
        prepared: PreparedAdmission,
        commit: CanonicalCommit,
    ) -> AdmissionResult:
        """Finalize the runtime receipt; caller appends its event in this UoW."""

        self._require_exact_commit(prepared, commit)
        row = self.commit_intents.load(prepared.intent.commit_intent_id)
        if _state_value(row) == "COMMITTED":
            if (
                row.get("canonical_commit_ref") != commit.canonical_ref
                or row.get("receipt_digest") != commit.receipt_digest
            ):
                raise AdmissionBindingError("finalized commit receipt drift")
            return AdmissionResult(
                progress=AdmissionProgress.FINALIZED,
                intent_revision=_revision(row),
                canonical_commit=commit,
            )
        updated = self.commit_intents.mark_committed(
            prepared.intent.commit_intent_id,
            expected_revision=_revision(row),
            canonical_commit_ref=commit.canonical_ref,
            receipt_digest=commit.receipt_digest,
        )
        return AdmissionResult(
            progress=AdmissionProgress.FINALIZED,
            intent_revision=_revision(updated),
            canonical_commit=commit,
        )

    def recover(self, prepared: PreparedAdmission) -> AdmissionResult:
        """Read back and finalize only; never call canonical ``commit``."""

        row = self.commit_intents.load(prepared.intent.commit_intent_id)
        readback = self._readback_exact(prepared)
        if readback.kind is not CanonicalReadbackKind.FOUND:
            if _state_value(row) != "OUTCOME_UNKNOWN":
                row = self._mark_unknown_once(prepared, _revision(row))
            return AdmissionResult(
                progress=AdmissionProgress.WAITING_READBACK,
                intent_revision=_revision(row),
                readback=readback,
            )
        assert readback.commit is not None
        return self.finalize(prepared, readback.commit)

    def _readback_exact(self, prepared: PreparedAdmission) -> CanonicalCommitReadback:
        readback = prepared.registration.handler.readback(
            prepared.scope,
            prepared.intent,
            prepared.candidate,
        )
        if readback.kind is CanonicalReadbackKind.FOUND:
            assert readback.commit is not None
            self._require_exact_commit(prepared, readback.commit)
        return readback

    def _mark_unknown_once(
        self, prepared: PreparedAdmission, expected_revision: int
    ) -> Mapping[str, Any]:
        current = self.commit_intents.load(prepared.intent.commit_intent_id)
        if _state_value(current) == "OUTCOME_UNKNOWN":
            return current
        if _state_value(current) == "COMMITTED":
            return current
        return self.commit_intents.mark_outcome_unknown(
            prepared.intent.commit_intent_id,
            expected_revision=expected_revision,
        )

    def _require_exact_runtime_binding(
        self,
        *,
        scope: RuntimeScope,
        assignment: RuntimeAssignment,
        intent: CommitIntent,
        binding: VerificationBinding,
    ) -> AdmissionRegistration:
        if assignment.assignment_kind is not AssignmentKind.VERIFY_ADMIT:
            raise AdmissionBindingError("admission requires VERIFY_ADMIT assignment")
        ref = assignment.operation_contract_ref
        if ref is None or assignment.operation_contract_digest != ref.contract_digest:
            raise AdmissionBindingError("assignment lacks exact operation contract ref")
        registration = self.registry.resolve_required(ref)
        project_scope = scope.project_scope
        if assignment.project_key != project_scope.project_key:
            raise AdmissionBindingError("assignment project scope drift")
        if (
            binding.project_key != project_scope.project_key
            or binding.project_registry_revision
            != project_scope.project_registry_revision
            or binding.project_scope_digest != project_scope.scope_digest
            or binding.resolved_schema != project_scope.resolved_schema
        ):
            raise AdmissionBindingError("verification project scope drift")
        if binding.actor_id != scope.actor_id:
            raise AdmissionBindingError("verification actor drift")
        if (
            binding.program_digest != assignment.program_digest
            or binding.plan_digest != assignment.plan_digest
            or binding.step_id != assignment.step_id
        ):
            raise AdmissionBindingError("verification assignment identity drift")
        compiled = assignment.compiled_admission_binding
        if compiled is None or compiled.operation_contract_digest != ref.contract_digest:
            raise AdmissionBindingError("compiled admission contract digest drift")
        if (
            intent.project_key != project_scope.project_key
            or intent.project_registry_revision
            != project_scope.project_registry_revision
            or intent.project_scope_digest != project_scope.scope_digest
        ):
            raise AdmissionBindingError("commit intent project scope drift")
        return registration

    @staticmethod
    def _require_exact_commit(
        prepared: PreparedAdmission, commit: CanonicalCommit
    ) -> None:
        intent = prepared.intent
        expected = {
            "commit_intent_id": intent.commit_intent_id,
            "canonical_owner": intent.canonical_owner,
            "project_key": intent.project_key,
            "object_id": intent.object_id,
            "canonical_incarnation": intent.expected_incarnation,
            "content_digest": intent.content_digest,
        }
        actual = commit.model_dump(mode="python")
        drift = tuple(key for key, value in expected.items() if actual[key] != value)
        if drift:
            raise AdmissionBindingError(
                "canonical commit readback drift: " + ", ".join(drift)
            )
        if commit.canonical_revision != intent.expected_base_revision + 1:
            raise AdmissionBindingError("canonical commit revision drift")


def _state_value(row: Mapping[str, Any]) -> str:
    value = row.get("state")
    return value.value if hasattr(value, "value") else str(value)


def _revision(row: Mapping[str, Any]) -> int:
    value = row.get("revision")
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise AdmissionBindingError("commit intent row has invalid revision")
    return value


__all__ = [
    "AdmissionBindingError",
    "AdmissionCoordinator",
    "AdmissionCoordinatorError",
    "AdmissionHandler",
    "AdmissionProgress",
    "AdmissionRegistration",
    "AdmissionRegistryError",
    "AdmissionResult",
    "CanonicalCommit",
    "CanonicalCommitReadback",
    "CanonicalReadbackKind",
    "CommitIntentStore",
    "ExactAdmissionRegistry",
    "PreparedAdmission",
]
