"""Infrastructure-free orchestration loop shared by every RuntimeNode.

The node owns no database session, queue, handler registry, or domain state.
Those effects enter through narrow ports.  In particular, a claimed assignment
already carries its exact :class:`HandlerBinding`; the resolver may only realize
that digest and cannot select an arbitrary handler after claim time.

The loop deliberately performs a lease CAS both before and after execution.
Losing the lease after an effect means that this node has lost write authority:
it returns an uncommitted observation and leaves durable recovery to the claim
expiry/reconciliation path.  It never turns lease loss into success, failure,
or proof that the effect did not start.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Protocol, runtime_checkable

from .assignments import (
    AssignmentKind,
    RuntimeAssignment,
    require_digest,
)
from .claims import ClaimBinding, ClaimBindingMismatch
from .ports import ControlPlaneScope
from .reconciliation import ReconciliationHandlerOutcome
from .transitions import EffectDisposition


class RuntimeNodeState(StrEnum):
    ACTIVE = "ACTIVE"
    DRAINING = "DRAINING"
    OFFLINE = "OFFLINE"


@dataclass(frozen=True, slots=True)
class NodeIdentity:
    """Non-reusable identity of one running node incarnation."""

    node_id: str
    incarnation: str
    started_at: datetime
    state: RuntimeNodeState = RuntimeNodeState.ACTIVE

    def __post_init__(self) -> None:
        if not self.node_id or not self.incarnation:
            raise ValueError("node identity requires node_id and incarnation")
        if self.started_at.tzinfo is None:
            raise ValueError("node started_at must be timezone-aware")


@dataclass(frozen=True, slots=True)
class RuntimeNodeProfile:
    """Installed capability shape without creating process-role subclasses."""

    profile_digest: str
    supported_assignment_kinds: frozenset[AssignmentKind]
    interpreter_profile_digests: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        require_digest(self.profile_digest, "node profile digest")
        if not self.supported_assignment_kinds:
            raise ValueError("node profile must support at least one assignment kind")
        for digest in self.interpreter_profile_digests:
            require_digest(digest, "interpreter profile digest")


@dataclass(frozen=True, slots=True)
class DeploymentBinding:
    """Exact immutable deployment catalog selected before node startup."""

    catalog_digest: str
    node_profile_digest: str
    runtime_protocol_version: str

    def __post_init__(self) -> None:
        require_digest(self.catalog_digest, "deployment catalog digest")
        require_digest(self.node_profile_digest, "deployment node profile digest")
        if not self.runtime_protocol_version:
            raise ValueError("deployment requires runtime protocol version")


@dataclass(frozen=True, slots=True)
class RuntimeNodeProtocol:
    """Versioned loop timings; capability overrides belong to frozen plans."""

    version: str
    claim_batch_size: int = 32
    heartbeat_extension: timedelta = timedelta(seconds=45)

    def __post_init__(self) -> None:
        if not self.version:
            raise ValueError("runtime protocol requires a version")
        if self.claim_batch_size <= 0:
            raise ValueError("claim batch size must be positive")
        if self.heartbeat_extension <= timedelta(0):
            raise ValueError("heartbeat extension must be positive")


@dataclass(frozen=True, slots=True)
class RuntimeClaim:
    """Port-neutral claim returned after durable claim-time reservation."""

    assignment: RuntimeAssignment
    claim_binding: ClaimBinding
    work_item_revision: int
    effect_disposition: EffectDisposition = EffectDisposition.NOT_STARTED

    def __post_init__(self) -> None:
        if self.work_item_revision < 0:
            raise ValueError("work item revision must be non-negative")
        if not isinstance(self.effect_disposition, EffectDisposition):
            raise TypeError("effect disposition must use the frozen runtime enum")

    def validate_exact(self) -> None:
        """Reparse and rebind all caller-visible content before any effect."""

        assignment = RuntimeAssignment.model_validate(
            self.assignment.model_dump(mode="json", exclude_none=False)
        )
        claim = ClaimBinding.model_validate(
            self.claim_binding.model_dump(mode="json", exclude_none=False)
        )
        if assignment != self.assignment or claim != self.claim_binding:
            raise ClaimBindingMismatch("claim serialization changed exact content")
        claim.validate_against(assignment)


@dataclass(frozen=True, slots=True)
class InterpreterOutcome:
    """Opaque, adoptable observation returned by an exact runtime handler."""

    disposition: EffectDisposition
    result_digest: str | None = None
    receipt_ref: str | None = None
    failure_code: str | None = None
    reconciliation_hint: str | None = None

    def __post_init__(self) -> None:
        terminal = {
            EffectDisposition.SUCCEEDED,
            EffectDisposition.FAILED,
            EffectDisposition.OUTCOME_UNKNOWN,
        }
        if self.disposition not in terminal:
            raise ValueError("interpreter outcome must be a terminal observation")
        if self.result_digest is not None:
            require_digest(self.result_digest, "interpreter result digest")
        if self.disposition is EffectDisposition.SUCCEEDED:
            if self.result_digest is None:
                raise ValueError("SUCCEEDED outcome requires result_digest")
            if self.failure_code or self.reconciliation_hint:
                raise ValueError("SUCCEEDED outcome cannot carry failure metadata")
        elif self.disposition is EffectDisposition.FAILED:
            if not self.failure_code:
                raise ValueError("FAILED outcome requires failure_code")
            if self.reconciliation_hint:
                raise ValueError("FAILED outcome cannot carry reconciliation_hint")
        elif not self.reconciliation_hint:
            raise ValueError("OUTCOME_UNKNOWN requires reconciliation_hint")

    @classmethod
    def succeeded(
        cls, result_digest: str, *, receipt_ref: str | None = None
    ) -> InterpreterOutcome:
        return cls(
            disposition=EffectDisposition.SUCCEEDED,
            result_digest=result_digest,
            receipt_ref=receipt_ref,
        )

    @classmethod
    def failed(cls, failure_code: str) -> InterpreterOutcome:
        return cls(
            disposition=EffectDisposition.FAILED,
            failure_code=failure_code,
        )

    @classmethod
    def outcome_unknown(cls, reconciliation_hint: str) -> InterpreterOutcome:
        return cls(
            disposition=EffectDisposition.OUTCOME_UNKNOWN,
            reconciliation_hint=reconciliation_hint,
        )


@dataclass(frozen=True, slots=True)
class MaterializerCommitOutcome:
    """Receipt for one post-run materializer committed in its own exact UoW.

    A materializer consumes a terminal predecessor closure and creates a new
    run.  It therefore cannot reuse the predecessor step's ordinary
    ``READY -> CLAIMED -> RUNNING`` lifecycle.  The exact handler instead
    commits the successor closure, work-item terminal observation and journal
    event atomically, then returns this bounded receipt to the symmetric node.
    """

    assignment_digest: str
    attempt_id: str
    result_digest: str
    receipt_ref: str
    disposition: EffectDisposition = EffectDisposition.SUCCEEDED

    def __post_init__(self) -> None:
        require_digest(self.assignment_digest, "materializer assignment digest")
        require_digest(self.attempt_id, "materializer attempt id")
        require_digest(self.result_digest, "materializer result digest")
        if not self.receipt_ref:
            raise ValueError("materializer commit requires a receipt ref")
        if self.disposition is not EffectDisposition.SUCCEEDED:
            raise ValueError("materializer commit receipt must be SUCCEEDED")


@dataclass(frozen=True, slots=True)
class RuntimeExecutionContext:
    node: NodeIdentity
    observed_at: datetime


@runtime_checkable
class RuntimeHandler(Protocol):
    handler_binding_digest: str
    interpreter_profile_digest: str | None

    def execute(
        self,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
        context: RuntimeExecutionContext,
    ) -> (
        InterpreterOutcome | ReconciliationHandlerOutcome | MaterializerCommitOutcome
    ): ...


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime: ...


@runtime_checkable
class ClaimBatchPort(Protocol):
    def claim_due(
        self,
        *,
        control_scope: ControlPlaneScope,
        node: NodeIdentity,
        profile: RuntimeNodeProfile,
        deployment: DeploymentBinding,
        protocol: RuntimeNodeProtocol,
        limit: int,
        observed_at: datetime,
    ) -> tuple[RuntimeClaim, ...]: ...

    def heartbeat(
        self,
        *,
        control_scope: ControlPlaneScope,
        claim: RuntimeClaim,
        expected_revision: int,
        new_expiry: datetime,
    ) -> RuntimeClaim: ...


@runtime_checkable
class ExactInterpreterResolver(Protocol):
    def resolve_exact(
        self,
        *,
        assignment: RuntimeAssignment,
        handler_binding_digest: str,
    ) -> RuntimeHandler: ...


@runtime_checkable
class OutcomeCommitPort(Protocol):
    def begin_in_flight(
        self,
        *,
        control_scope: ControlPlaneScope,
        claim: RuntimeClaim,
        expected_revision: int,
        started_at: datetime,
    ) -> RuntimeClaim: ...

    def commit_outcome(
        self,
        *,
        control_scope: ControlPlaneScope,
        claim: RuntimeClaim,
        outcome: InterpreterOutcome | ReconciliationHandlerOutcome,
        expected_revision: int,
        observed_at: datetime,
    ) -> None: ...


@runtime_checkable
class CancellationPort(Protocol):
    """Current cancellation and authority checks at the effect boundary."""

    def require_not_cancelled(
        self, *, claim: RuntimeClaim, observed_at: datetime
    ) -> None: ...

    def require_current_authority(
        self,
        *,
        claim: RuntimeClaim,
        expected_authority_digest: str,
        expected_authority_epoch: int,
        observed_at: datetime,
    ) -> None: ...


class LeaseLost(RuntimeError):
    """The exact lease token/revision no longer grants write authority."""


class ExactHandlerMismatch(RuntimeError):
    """The resolver did not realize the assignment's frozen handler digest."""


class DefiniteInterpreterFailure(RuntimeError):
    """Interpreter-declared failure with no uncertain external effect."""

    def __init__(self, failure_code: str) -> None:
        super().__init__(failure_code)
        self.failure_code = failure_code


class OutcomeUncertain(RuntimeError):
    """The interpreter cannot prove whether its effect became observable."""

    def __init__(self, reconciliation_hint: str) -> None:
        super().__init__(reconciliation_hint)
        self.reconciliation_hint = reconciliation_hint


class ClaimRunState(StrEnum):
    COMMITTED = "COMMITTED"
    REJECTED = "REJECTED"
    LEASE_LOST = "LEASE_LOST"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"


@dataclass(frozen=True, slots=True)
class ClaimRunResult:
    work_item_id: str
    attempt_id: str
    state: ClaimRunState
    disposition: EffectDisposition
    executed: bool
    committed: bool
    failure_code: str | None = None


@dataclass(frozen=True, slots=True)
class RunOnceReport:
    node_id: str
    claimed: int
    results: tuple[ClaimRunResult, ...]
    skipped_new_claims: bool = False


class RuntimeNode:
    """One symmetric claim/validate/interpret/commit loop."""

    def __init__(
        self,
        *,
        identity: NodeIdentity,
        profile: RuntimeNodeProfile,
        deployment: DeploymentBinding,
        protocol: RuntimeNodeProtocol,
        control_scope: ControlPlaneScope,
        claims: ClaimBatchPort,
        interpreters: ExactInterpreterResolver,
        outcomes: OutcomeCommitPort,
        cancellation: CancellationPort,
        clock: Clock,
    ) -> None:
        if deployment.node_profile_digest != profile.profile_digest:
            raise ValueError("deployment is bound to a different node profile")
        if deployment.runtime_protocol_version != protocol.version:
            raise ValueError("deployment/runtime protocol version mismatch")
        if control_scope.system_actor_id != identity.node_id:
            raise ValueError("control-plane actor must be the exact node identity")
        self.identity = identity
        self.profile = profile
        self.deployment = deployment
        self.protocol = protocol
        self.control_scope = control_scope
        self.claims = claims
        self.interpreters = interpreters
        self.outcomes = outcomes
        self.cancellation = cancellation
        self.clock = clock

    def run_once(self) -> RunOnceReport:
        """Claim one bounded batch and isolate every claim's observation."""

        if self.identity.state is not RuntimeNodeState.ACTIVE:
            return RunOnceReport(
                node_id=self.identity.node_id,
                claimed=0,
                results=(),
                skipped_new_claims=True,
            )
        observed_at = self._now()
        claimed = self.claims.claim_due(
            control_scope=self.control_scope,
            node=self.identity,
            profile=self.profile,
            deployment=self.deployment,
            protocol=self.protocol,
            limit=self.protocol.claim_batch_size,
            observed_at=observed_at,
        )
        results = tuple(self._run_claim(claim) for claim in claimed)
        return RunOnceReport(
            node_id=self.identity.node_id,
            claimed=len(claimed),
            results=results,
        )

    def _run_claim(self, claim: RuntimeClaim) -> ClaimRunResult:
        try:
            self._validate_claim(claim)
        except LeaseLost as exc:
            if claim.assignment.assignment_kind is AssignmentKind.RECONCILE:
                return self._reconciliation_lease_lost(claim)
            return self._lease_lost(claim, executed=False, reason=str(exc))
        except Exception as exc:  # noqa: BLE001 - isolate malformed claims in a batch
            if claim.assignment.assignment_kind is AssignmentKind.RECONCILE:
                return self._reconciliation_rejected(claim, self._error_code(exc))
            return self._rejected_without_commit(claim, self._error_code(exc))

        if claim.effect_disposition is not EffectDisposition.NOT_STARTED:
            return ClaimRunResult(
                work_item_id=claim.assignment.work_item_id,
                attempt_id=claim.claim_binding.attempt_id,
                state=ClaimRunState.RECOVERY_REQUIRED,
                disposition=claim.effect_disposition,
                executed=False,
                committed=False,
                failure_code="EXISTING_ATTEMPT_REQUIRES_RECOVERY",
            )

        try:
            live_claim = self._heartbeat(claim)
        except LeaseLost as exc:
            if claim.assignment.assignment_kind is AssignmentKind.RECONCILE:
                return self._reconciliation_lease_lost(claim)
            return self._lease_lost(claim, executed=False, reason=str(exc))
        except Exception as exc:  # noqa: BLE001 - port failure is claim-local
            if claim.assignment.assignment_kind is AssignmentKind.RECONCILE:
                return self._reconciliation_rejected(claim, self._error_code(exc))
            return self._rejected_without_commit(claim, self._error_code(exc))

        try:
            self._require_effect_guard(live_claim)
            handler = self.interpreters.resolve_exact(
                assignment=live_claim.assignment,
                handler_binding_digest=live_claim.assignment.handler_binding_digest,
            )
            self._validate_handler(live_claim, handler)
        except LeaseLost:
            if live_claim.assignment.assignment_kind is AssignmentKind.RECONCILE:
                return self._reconciliation_lease_lost(live_claim)
            return self._lease_lost(live_claim, executed=False)
        except ExactHandlerMismatch as exc:
            # Installation loss is a deployment observation, not proof that
            # the frozen operation failed.  The backlog gate normally prevents
            # this claim; a post-claim rollout race remains non-terminal and is
            # recovered after lease expiry without emitting EffectFailed.
            if live_claim.assignment.assignment_kind is AssignmentKind.RECONCILE:
                return self._reconciliation_rejected(
                    live_claim,
                    self._error_code(exc),
                )
            return self._rejected_without_commit(
                live_claim,
                self._error_code(exc),
            )
        except Exception as exc:  # noqa: BLE001 - resolver/guard must fail closed
            if live_claim.assignment.assignment_kind is AssignmentKind.RECONCILE:
                return self._reconciliation_rejected(
                    live_claim,
                    self._error_code(exc),
                )
            return self._commit_pre_effect_failure(live_claim, self._error_code(exc))

        if live_claim.assignment.assignment_kind is AssignmentKind.RECONCILE:
            return self._run_reconciliation(live_claim, handler)
        if (
            live_claim.assignment.assignment_kind
            is AssignmentKind.MATERIALIZE_SUCCESSOR
        ):
            return self._run_materializer(live_claim, handler)

        try:
            in_flight = self.outcomes.begin_in_flight(
                control_scope=self.control_scope,
                claim=live_claim,
                expected_revision=live_claim.work_item_revision,
                started_at=self._now(),
            )
            self._validate_successor_claim(
                live_claim,
                in_flight,
                expected_disposition=EffectDisposition.IN_FLIGHT,
            )
        except LeaseLost:
            return self._lease_lost(live_claim, executed=False)
        except Exception as exc:  # noqa: BLE001 - start failure is claim-local
            return self._commit_pre_effect_failure(live_claim, self._error_code(exc))

        try:
            # Re-check after the durable IN_FLIGHT transition and immediately
            # before crossing the interpreter effect boundary.
            self._require_effect_guard(in_flight)
        except LeaseLost:
            return self._lease_lost(in_flight, executed=False)
        except Exception as exc:  # noqa: BLE001 - guard must fail closed
            return self._commit_pre_effect_failure(in_flight, self._error_code(exc))

        outcome: InterpreterOutcome
        try:
            outcome = handler.execute(
                in_flight.assignment,
                in_flight.claim_binding,
                RuntimeExecutionContext(node=self.identity, observed_at=self._now()),
            )
            if not isinstance(outcome, InterpreterOutcome):
                raise TypeError("exact handler returned a non-InterpreterOutcome")
        except DefiniteInterpreterFailure as exc:
            outcome = InterpreterOutcome.failed(exc.failure_code)
        except OutcomeUncertain as exc:
            outcome = InterpreterOutcome.outcome_unknown(exc.reconciliation_hint)
        except Exception as exc:  # noqa: BLE001 - unknown post-effect errors reconcile
            # Once the effect boundary has been crossed, an unclassified
            # exception cannot safely prove failure or non-start.
            outcome = InterpreterOutcome.outcome_unknown(
                f"UNCLASSIFIED_INTERPRETER_EXCEPTION:{type(exc).__name__}"
            )

        try:
            commit_claim = self._heartbeat(in_flight)
        except LeaseLost:
            return self._lease_lost(in_flight, executed=True)
        except Exception as exc:  # noqa: BLE001 - heartbeat outage cannot authorize commit
            return ClaimRunResult(
                work_item_id=in_flight.assignment.work_item_id,
                attempt_id=in_flight.claim_binding.attempt_id,
                state=ClaimRunState.REJECTED,
                disposition=EffectDisposition.OUTCOME_UNKNOWN,
                executed=True,
                committed=False,
                failure_code=self._error_code(exc),
            )

        try:
            self.outcomes.commit_outcome(
                control_scope=self.control_scope,
                claim=commit_claim,
                outcome=outcome,
                expected_revision=commit_claim.work_item_revision,
                observed_at=self._now(),
            )
        except LeaseLost:
            return self._lease_lost(commit_claim, executed=True)
        except Exception as exc:  # noqa: BLE001 - commit uncertainty stays uncommitted
            return ClaimRunResult(
                work_item_id=commit_claim.assignment.work_item_id,
                attempt_id=commit_claim.claim_binding.attempt_id,
                state=ClaimRunState.REJECTED,
                disposition=EffectDisposition.OUTCOME_UNKNOWN,
                executed=True,
                committed=False,
                failure_code=self._error_code(exc),
            )
        return ClaimRunResult(
            work_item_id=commit_claim.assignment.work_item_id,
            attempt_id=commit_claim.claim_binding.attempt_id,
            state=ClaimRunState.COMMITTED,
            disposition=outcome.disposition,
            executed=True,
            committed=True,
            failure_code=outcome.failure_code,
        )

    def _run_materializer(
        self,
        claim: RuntimeClaim,
        handler: RuntimeHandler,
    ) -> ClaimRunResult:
        """Run one deterministic post-run materializer without reusing a step.

        Crossing the handler boundary may include a PostgreSQL commit.  An
        unclassified exception is therefore outcome-unknown to this node even
        though a later work-item/journal readback can settle it without
        repeating the materialization.
        """

        try:
            outcome = handler.execute(
                claim.assignment,
                claim.claim_binding,
                RuntimeExecutionContext(node=self.identity, observed_at=self._now()),
            )
            if not isinstance(outcome, MaterializerCommitOutcome):
                raise TypeError(
                    "MATERIALIZE_SUCCESSOR handler returned a non-commit receipt"
                )
            if (
                outcome.assignment_digest != claim.assignment.assignment_digest
                or outcome.attempt_id != claim.claim_binding.attempt_id
            ):
                raise ClaimBindingMismatch(
                    "materializer commit receipt exact identity drift"
                )
        except DefiniteInterpreterFailure as exc:
            return self._rejected_without_commit(claim, exc.failure_code)
        except Exception as exc:  # noqa: BLE001 - commit acknowledgement may be lost
            return ClaimRunResult(
                work_item_id=claim.assignment.work_item_id,
                attempt_id=claim.claim_binding.attempt_id,
                state=ClaimRunState.RECOVERY_REQUIRED,
                disposition=EffectDisposition.OUTCOME_UNKNOWN,
                executed=True,
                committed=False,
                failure_code=self._error_code(exc),
            )
        return ClaimRunResult(
            work_item_id=claim.assignment.work_item_id,
            attempt_id=claim.claim_binding.attempt_id,
            state=ClaimRunState.COMMITTED,
            disposition=outcome.disposition,
            executed=True,
            committed=True,
        )

    def _run_reconciliation(
        self,
        claim: RuntimeClaim,
        handler: RuntimeHandler,
    ) -> ClaimRunResult:
        """Read back one original attempt without entering its effect lifecycle."""

        try:
            outcome = handler.execute(
                claim.assignment,
                claim.claim_binding,
                RuntimeExecutionContext(node=self.identity, observed_at=self._now()),
            )
            if not isinstance(outcome, ReconciliationHandlerOutcome):
                raise TypeError(
                    "RECONCILE handler returned a non-ReconciliationHandlerOutcome"
                )
            target_attempt_id = claim.assignment.reconciliation_attempt_id
            if outcome.result.attempt_id != target_attempt_id:
                raise ClaimBindingMismatch(
                    "reconciliation outcome is bound to a different target attempt"
                )
        except Exception as exc:  # noqa: BLE001 - readback cannot fabricate terminality
            return self._reconciliation_rejected(claim, self._error_code(exc))

        try:
            commit_claim = self._heartbeat(claim)
        except LeaseLost:
            return self._reconciliation_lease_lost(claim)
        except Exception as exc:  # noqa: BLE001 - heartbeat outage cannot authorize commit
            return self._reconciliation_rejected(claim, self._error_code(exc))

        try:
            self.outcomes.commit_outcome(
                control_scope=self.control_scope,
                claim=commit_claim,
                outcome=outcome,
                expected_revision=commit_claim.work_item_revision,
                observed_at=self._now(),
            )
        except LeaseLost:
            return self._reconciliation_lease_lost(commit_claim)
        except Exception as exc:  # noqa: BLE001 - failed adoption remains non-terminal
            return self._reconciliation_rejected(
                commit_claim,
                self._error_code(exc),
            )
        return ClaimRunResult(
            work_item_id=commit_claim.assignment.work_item_id,
            attempt_id=commit_claim.claim_binding.attempt_id,
            state=ClaimRunState.COMMITTED,
            disposition=outcome.result.disposition,
            executed=False,
            committed=True,
        )

    def _validate_claim(self, claim: RuntimeClaim) -> None:
        claim.validate_exact()
        assignment = claim.assignment
        binding = claim.claim_binding
        if assignment.assignment_kind not in self.profile.supported_assignment_kinds:
            raise ExactHandlerMismatch("node profile does not support assignment kind")
        if assignment.runtime_protocol_version != self.protocol.version:
            raise ClaimBindingMismatch("assignment runtime protocol drift")
        if assignment.deployment_catalog_digest != self.deployment.catalog_digest:
            raise ClaimBindingMismatch("assignment deployment catalog drift")
        if binding.node_id != self.identity.node_id:
            raise ClaimBindingMismatch("claim is bound to a different node")
        if binding.node_profile_digest != self.profile.profile_digest:
            raise ClaimBindingMismatch("claim node profile drift")
        if binding.claim_authority_epoch != self.control_scope.authority_epoch:
            raise ClaimBindingMismatch("control-plane authority epoch drift")
        if binding.lease_expires_at <= self._now():
            raise LeaseLost("claim lease already expired")
        exact = assignment.handler_binding
        profile_digest = getattr(exact, "interpreter_profile_digest", None)
        if profile_digest is not None:
            if binding.interpreter_profile_digest != profile_digest:
                raise ClaimBindingMismatch("claim interpreter profile drift")
            if profile_digest not in self.profile.interpreter_profile_digests:
                raise ExactHandlerMismatch("interpreter profile is not installed")

    def _validate_handler(self, claim: RuntimeClaim, handler: RuntimeHandler) -> None:
        expected = claim.assignment.handler_binding_digest
        if handler.handler_binding_digest != expected:
            raise ExactHandlerMismatch("resolver returned a different handler digest")
        exact_profile = getattr(
            claim.assignment.handler_binding,
            "interpreter_profile_digest",
            None,
        )
        if handler.interpreter_profile_digest != exact_profile:
            raise ExactHandlerMismatch(
                "resolver returned a different interpreter profile"
            )

    def _require_effect_guard(self, claim: RuntimeClaim) -> None:
        observed_at = self._now()
        self.cancellation.require_not_cancelled(
            claim=claim,
            observed_at=observed_at,
        )
        self.cancellation.require_current_authority(
            claim=claim,
            expected_authority_digest=claim.claim_binding.authority_digest,
            expected_authority_epoch=claim.assignment.claim_authority_epoch,
            observed_at=observed_at,
        )

    def _heartbeat(self, claim: RuntimeClaim) -> RuntimeClaim:
        renewed = self.claims.heartbeat(
            control_scope=self.control_scope,
            claim=claim,
            expected_revision=claim.work_item_revision,
            new_expiry=self._now() + self.protocol.heartbeat_extension,
        )
        self._validate_successor_claim(
            claim,
            renewed,
            expected_disposition=claim.effect_disposition,
        )
        return renewed

    @staticmethod
    def _validate_successor_claim(
        previous: RuntimeClaim,
        successor: RuntimeClaim,
        *,
        expected_disposition: EffectDisposition,
    ) -> None:
        successor.validate_exact()
        if successor.assignment != previous.assignment:
            raise ClaimBindingMismatch("claim renewal changed assignment content")
        if successor.claim_binding.attempt_id != previous.claim_binding.attempt_id:
            raise ClaimBindingMismatch("claim renewal changed attempt identity")
        if successor.claim_binding.lease_token != previous.claim_binding.lease_token:
            raise ClaimBindingMismatch("claim renewal changed lease identity")
        for field_name in (
            "node_id",
            "node_profile_digest",
            "interpreter_profile_digest",
            "authority_digest",
            "execution_reservation_ref",
            "execution_reservation_digest",
            "claim_authority_epoch",
        ):
            if getattr(successor.claim_binding, field_name) != getattr(
                previous.claim_binding, field_name
            ):
                raise ClaimBindingMismatch(
                    f"claim renewal changed exact {field_name} binding"
                )
        if successor.work_item_revision != previous.work_item_revision + 1:
            raise ClaimBindingMismatch(
                "claim CAS revision did not advance exactly once"
            )
        if successor.effect_disposition is not expected_disposition:
            raise ClaimBindingMismatch("claim disposition transition drift")

    def _commit_pre_effect_failure(
        self, claim: RuntimeClaim, failure_code: str
    ) -> ClaimRunResult:
        outcome = InterpreterOutcome.failed(failure_code)
        try:
            self.outcomes.commit_outcome(
                control_scope=self.control_scope,
                claim=claim,
                outcome=outcome,
                expected_revision=claim.work_item_revision,
                observed_at=self._now(),
            )
        except LeaseLost:
            return self._lease_lost(claim, executed=False)
        except Exception as exc:  # noqa: BLE001 - failed commit stays claim-local
            return self._rejected_without_commit(claim, self._error_code(exc))
        return ClaimRunResult(
            work_item_id=claim.assignment.work_item_id,
            attempt_id=claim.claim_binding.attempt_id,
            state=ClaimRunState.COMMITTED,
            disposition=EffectDisposition.FAILED,
            executed=False,
            committed=True,
            failure_code=failure_code,
        )

    @staticmethod
    def _reconciliation_lease_lost(claim: RuntimeClaim) -> ClaimRunResult:
        return ClaimRunResult(
            work_item_id=claim.assignment.work_item_id,
            attempt_id=claim.claim_binding.attempt_id,
            state=ClaimRunState.LEASE_LOST,
            disposition=EffectDisposition.OUTCOME_UNKNOWN,
            executed=False,
            committed=False,
            failure_code="LEASE_LOST_NO_RECONCILIATION_COMMIT",
        )

    @staticmethod
    def _reconciliation_rejected(
        claim: RuntimeClaim,
        failure_code: str,
    ) -> ClaimRunResult:
        return ClaimRunResult(
            work_item_id=claim.assignment.work_item_id,
            attempt_id=claim.claim_binding.attempt_id,
            state=ClaimRunState.REJECTED,
            disposition=EffectDisposition.OUTCOME_UNKNOWN,
            executed=False,
            committed=False,
            failure_code=failure_code,
        )

    @staticmethod
    def _lease_lost(
        claim: RuntimeClaim,
        *,
        executed: bool,
        reason: str | None = None,
    ) -> ClaimRunResult:
        return ClaimRunResult(
            work_item_id=claim.assignment.work_item_id,
            attempt_id=claim.claim_binding.attempt_id,
            state=ClaimRunState.LEASE_LOST,
            disposition=(
                EffectDisposition.OUTCOME_UNKNOWN
                if executed
                else claim.effect_disposition
            ),
            executed=executed,
            committed=False,
            failure_code=(
                "LEASE_LOST_NO_COMMIT"
                if not reason
                else f"LEASE_LOST_NO_COMMIT:{reason}"[:512]
            ),
        )

    @staticmethod
    def _rejected_without_commit(
        claim: RuntimeClaim, failure_code: str
    ) -> ClaimRunResult:
        return ClaimRunResult(
            work_item_id=claim.assignment.work_item_id,
            attempt_id=claim.claim_binding.attempt_id,
            state=ClaimRunState.REJECTED,
            disposition=claim.effect_disposition,
            executed=False,
            committed=False,
            failure_code=failure_code,
        )

    @staticmethod
    def _error_code(exc: Exception) -> str:
        if isinstance(exc, DefiniteInterpreterFailure):
            return exc.failure_code
        text = str(exc).strip().replace(" ", "_").upper()
        return text[:512] or type(exc).__name__.upper()

    def _now(self) -> datetime:
        observed_at = self.clock.now()
        if observed_at.tzinfo is None:
            raise ValueError("runtime clock must return timezone-aware datetimes")
        return observed_at


__all__ = [
    "CancellationPort",
    "ClaimBatchPort",
    "ClaimRunResult",
    "ClaimRunState",
    "Clock",
    "DefiniteInterpreterFailure",
    "DeploymentBinding",
    "ExactHandlerMismatch",
    "ExactInterpreterResolver",
    "InterpreterOutcome",
    "LeaseLost",
    "MaterializerCommitOutcome",
    "NodeIdentity",
    "OutcomeCommitPort",
    "OutcomeUncertain",
    "ReconciliationHandlerOutcome",
    "RunOnceReport",
    "RuntimeClaim",
    "RuntimeExecutionContext",
    "RuntimeHandler",
    "RuntimeNode",
    "RuntimeNodeProfile",
    "RuntimeNodeProtocol",
    "RuntimeNodeState",
]
