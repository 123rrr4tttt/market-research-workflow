"""PostgreSQL realization of the infrastructure-free ``RuntimeNode`` ports.

Every public method opens one caller-configured :class:`RuntimeUnitOfWork`.
Repositories receive that UoW's exact connection and never commit internally.
Cross-project claim remains the only global operation; subsequent lifecycle
transitions reconstruct a validated project scope from the server-owned run and
scope-registry rows before touching project-scoped state.

The adapter intentionally keeps no mutable handler or authorization selector.
A single node context can therefore claim different steps with different exact
``StepAuthorizationBinding`` digests.  The only in-memory state is a bounded
record of claims this process durably moved to ``IN_FLIGHT``; losing that cache
fails closed and leaves lease-expiry reconciliation as the recovery owner.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any, Protocol, Self

from sqlalchemy import MetaData, select
from sqlalchemy.engine import Connection

from app.successor_runtime.runtime.assignments import AssignmentKind, canonical_digest
from app.successor_runtime.runtime.claims import ClaimBinding
from app.successor_runtime.runtime.node import (
    DeploymentBinding,
    InterpreterOutcome,
    LeaseLost,
    NodeIdentity,
    RuntimeClaim,
    RuntimeNodeProfile,
    RuntimeNodeProtocol,
)
from app.successor_runtime.runtime.ports import (
    RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION,
    ControlPlaneScope,
    RuntimeScope,
)
from app.successor_runtime.runtime.reconciliation import (
    ReconciliationHandlerOutcome,
    ReconciliationState,
)
from app.successor_runtime.runtime.resources import FairSharePolicy
from app.successor_runtime.runtime.transitions import (
    EffectDisposition,
    StepEvent,
    StepState,
)

from .models import project_tables
from .reconciliation import PostgresReconciliationOwner
from .runtime_failures import RuntimeFailureRepository
from .runtime_journal import (
    ExactBindingConflict,
    RecordNotFound,
    StaleRevisionError,
    _one_mapping,
    _table,
    validate_runtime_assignment_row,
)
from .runtime_lifecycle import (
    ClaimedLifecycle,
    EffectTerminalKind,
    RuntimeLifecycleRepository,
    TerminalOutcome,
)
from .session import ProjectScopeStale, ServerProjectScopeResolver
from .unit_of_work import RuntimeUnitOfWork
from .work_items import (
    ClaimConflict,
    ClaimRecord,
    NodeClaimContext,
    WorkItemClaimRepository,
)


class NodeAdapterError(RuntimeError):
    """Base class for fail-closed adapter binding failures."""


class LifecycleCacheMiss(NodeAdapterError):
    """This process did not durably start the exact effect attempt."""


class ReceiptDigestUnavailable(NodeAdapterError):
    """A receipt ref was supplied without a verifiable content digest."""


class _UnitOfWorkView(Protocol):
    connection: Connection

    def __enter__(self) -> Self: ...

    def commit(self) -> None: ...

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None: ...


class _ClaimRepositoryView(Protocol):
    def claim_due(
        self,
        control_scope: ControlPlaneScope,
        context: NodeClaimContext,
        *,
        limit: int,
        fairness: FairSharePolicy | None = None,
        cursor: int | None = None,
        now: Any | None = None,
    ) -> tuple[ClaimRecord, ...]: ...

    def heartbeat(
        self,
        control_scope: ControlPlaneScope,
        work_item_id: str,
        lease_token: str,
        *,
        expected_revision: int,
        new_expiry: Any,
    ) -> Mapping[str, Any]: ...


class _LifecycleRepositoryView(Protocol):
    def start_claim(
        self, claimed: ClaimedLifecycle, *, observed_at: datetime | None = None
    ) -> None: ...

    def commit_outcome(self, outcome: TerminalOutcome) -> None: ...


class _ReconciliationOwnerView(Protocol):
    def adopt(
        self,
        *,
        claim: RuntimeClaim,
        outcome: ReconciliationHandlerOutcome,
        actor_id: str,
        observed_at: datetime,
    ) -> None: ...


class _ClaimStateReaderView(Protocol):
    def runtime_claim(self, record: ClaimRecord) -> RuntimeClaim: ...

    def renewed_claim(
        self,
        previous: RuntimeClaim,
        row: Mapping[str, Any],
    ) -> RuntimeClaim: ...

    def claimed_lifecycle(
        self,
        claim: RuntimeClaim,
        control_scope: ControlPlaneScope,
        *,
        require_started: bool,
    ) -> tuple[RuntimeScope, ClaimedLifecycle]: ...


UowFactory = Callable[[], _UnitOfWorkView]
ClaimRepositoryFactory = Callable[[Connection], _ClaimRepositoryView]
LifecycleRepositoryFactory = Callable[
    [Connection, RuntimeScope], _LifecycleRepositoryView
]
ClaimStateReaderFactory = Callable[[Connection], _ClaimStateReaderView]
ReconciliationOwnerFactory = Callable[[Connection], _ReconciliationOwnerView]
RuntimeFailureRepositoryFactory = Callable[
    [Connection, RuntimeScope], RuntimeFailureRepository
]


class TerminalCommitHook(Protocol):
    """Capability-local work enlisted in the exact terminal UoW."""

    def prepare_terminal(
        self,
        *,
        connection: Connection,
        scope: RuntimeScope,
        claim: RuntimeClaim,
        lifecycle: ClaimedLifecycle,
        outcome: InterpreterOutcome,
        terminal: TerminalOutcome,
    ) -> TerminalOutcome: ...

    def after_terminal(
        self,
        *,
        connection: Connection,
        scope: RuntimeScope,
        claim: RuntimeClaim,
        lifecycle: ClaimedLifecycle,
        outcome: InterpreterOutcome,
        terminal: TerminalOutcome,
    ) -> None: ...


def _default_claim_repository(connection: Connection) -> WorkItemClaimRepository:
    return WorkItemClaimRepository(connection)


def _default_lifecycle_repository(
    connection: Connection, scope: RuntimeScope
) -> RuntimeLifecycleRepository:
    return RuntimeLifecycleRepository(connection, scope)


def _default_state_reader(connection: Connection) -> _PostgresClaimStateReader:
    return _PostgresClaimStateReader(connection)


def _default_reconciliation_owner(
    connection: Connection,
) -> PostgresReconciliationOwner:
    return PostgresReconciliationOwner(connection)


def _default_runtime_failure_repository(
    connection: Connection,
    scope: RuntimeScope,
) -> RuntimeFailureRepository:
    return RuntimeFailureRepository(
        connection,
        project_tables(MetaData(), scope.project_scope.resolved_schema),
    )


class _PostgresClaimStateReader:
    """Reload and verify exact durable claim/lifecycle rows on one connection."""

    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def runtime_claim(self, record: ClaimRecord) -> RuntimeClaim:
        work = self._work(record.project_key, record.work_item_id)
        assignment = validate_runtime_assignment_row(work)
        stored_claim = self._stored_claim(work)
        exact = (
            assignment == record.assignment
            and stored_claim == record.claim_binding
            and work["project_key"] == record.project_key
            and work["run_id"] == record.run_id
            and work["step_id"] == record.step_id
            and work["assignment_digest"] == record.assignment_digest
            and work["lease_token"] == record.lease_token
            and work["claim_attempt_id"] == record.attempt_id
            and work["state"] == "CLAIMED"
        )
        if not exact:
            raise ExactBindingConflict("claimed work row differs from ClaimRecord")
        return RuntimeClaim(
            assignment=assignment,
            claim_binding=stored_claim,
            work_item_revision=int(work["revision"]),
            effect_disposition=self._effect_disposition(
                record.project_key, record.attempt_id
            ),
        )

    def renewed_claim(
        self,
        previous: RuntimeClaim,
        row: Mapping[str, Any],
    ) -> RuntimeClaim:
        assignment = validate_runtime_assignment_row(row)
        stored_claim = self._stored_claim(row)
        exact = (
            assignment == previous.assignment
            and row["project_key"] == previous.assignment.project_key
            and row["work_item_id"] == previous.assignment.work_item_id
            and row["state"] == "CLAIMED"
            and row["lease_token"] == previous.claim_binding.lease_token
            and stored_claim.attempt_id == previous.claim_binding.attempt_id
        )
        if not exact:
            raise ExactBindingConflict("heartbeat returned a different exact claim")
        return RuntimeClaim(
            assignment=assignment,
            claim_binding=stored_claim,
            work_item_revision=int(row["revision"]),
            effect_disposition=self._effect_disposition(
                assignment.project_key, stored_claim.attempt_id
            ),
        )

    def claimed_lifecycle(
        self,
        claim: RuntimeClaim,
        control_scope: ControlPlaneScope,
        *,
        require_started: bool,
    ) -> tuple[RuntimeScope, ClaimedLifecycle]:
        assignment = claim.assignment
        work = self._work(assignment.project_key, assignment.work_item_id)
        durable_assignment = validate_runtime_assignment_row(work)
        stored_claim = self._stored_claim(work)
        if (
            durable_assignment != assignment
            or stored_claim != claim.claim_binding
            or int(work["revision"]) != claim.work_item_revision
            or work["state"] != "CLAIMED"
            or work["lease_token"] != claim.claim_binding.lease_token
            or work["claim_binding_digest"] != claim.claim_binding.binding_digest
        ):
            raise ExactBindingConflict("RuntimeClaim differs from durable work row")

        run = self._one(
            "runtime_runs",
            project_key=assignment.project_key,
            run_id=assignment.run_id,
        )
        if (
            run["incarnation"] != assignment.incarnation
            or run["program_digest"] != assignment.program_digest
            or int(run["execution_epoch"]) != assignment.execution_epoch
        ):
            raise ExactBindingConflict("RuntimeClaim run binding drift")
        scope = self._scope(run, control_scope.system_actor_id)

        step_id = assignment.step_id
        reservation_id = claim.claim_binding.execution_reservation_ref
        if step_id is None or reservation_id is None:
            raise ExactBindingConflict(
                "effect lifecycle requires exact step and reservation identity"
            )
        step = self._one(
            "runtime_steps",
            project_key=assignment.project_key,
            run_id=assignment.run_id,
            step_id=step_id,
        )
        attempt = self._one(
            "runtime_effect_attempts",
            project_key=assignment.project_key,
            attempt_id=claim.claim_binding.attempt_id,
        )
        reservation = self._one(
            "runtime_resource_reservations",
            project_key=assignment.project_key,
            reservation_id=reservation_id,
        )
        expected_disposition = (
            EffectDisposition.IN_FLIGHT.value
            if require_started
            else EffectDisposition.NOT_STARTED.value
        )
        if attempt["disposition"] != expected_disposition:
            raise ExactBindingConflict(
                "durable attempt disposition differs from RuntimeNode phase"
            )
        lifecycle = ClaimedLifecycle(
            claim=claim.claim_binding,
            run_id=assignment.run_id,
            step_id=step_id,
            work_item_id=assignment.work_item_id,
            attempt_id=claim.claim_binding.attempt_id,
            reservation_id=reservation_id,
            expected_run_revision=int(run["revision"]),
            expected_step_revision=int(step["revision"]),
            expected_work_revision=int(work["revision"]),
            expected_attempt_revision=int(attempt["revision"]),
            expected_reservation_revision=int(reservation["revision"]),
        )
        return scope, lifecycle

    def _scope(self, run: Mapping[str, Any], actor_id: str) -> RuntimeScope:
        resolver = ServerProjectScopeResolver(connection=self.connection)
        resolved = resolver.resolve_expected(
            str(run["project_key"]),
            int(run["project_registry_revision"]),
            str(run["project_scope_digest"]),
        )
        if isinstance(resolved, ProjectScopeStale):
            raise ExactBindingConflict("run project scope digest is stale")
        current = resolver.resolve(str(run["project_key"]))
        if resolved != current or current.resolved_schema != run["resolved_schema"]:
            raise ExactBindingConflict("run project scope is no longer current")
        return RuntimeScope(project_scope=current, actor_id=actor_id)

    def _work(self, project_key: str, work_item_id: str) -> Mapping[str, Any]:
        return self._one(
            "runtime_work_items",
            project_key=project_key,
            work_item_id=work_item_id,
        )

    def _one(self, table_name: str, **identity: object) -> Mapping[str, Any]:
        table = _table(table_name)
        statement = select(table)
        for name, value in identity.items():
            statement = statement.where(getattr(table.c, name) == value)
        row = _one_mapping(self.connection.execute(statement.with_for_update()))
        if row is None:
            rendered = ", ".join(f"{key}={value!r}" for key, value in identity.items())
            raise RecordNotFound(f"{table_name} row not found: {rendered}")
        return row

    @staticmethod
    def _stored_claim(work: Mapping[str, Any]) -> ClaimBinding:
        payload = work.get("claim_binding_json")
        if payload is None:
            raise ExactBindingConflict("claimed work row lacks ClaimBinding")
        try:
            return ClaimBinding.model_validate(payload)
        except Exception as exc:
            raise ExactBindingConflict("stored ClaimBinding is malformed") from exc

    def _effect_disposition(
        self, project_key: str, attempt_id: str | None
    ) -> EffectDisposition:
        if attempt_id is None:
            return EffectDisposition.NOT_STARTED
        table = _table("runtime_effect_attempts")
        row = _one_mapping(
            self.connection.execute(
                select(table).where(
                    table.c.project_key == project_key,
                    table.c.attempt_id == attempt_id,
                )
            )
        )
        if row is None:
            return EffectDisposition.NOT_STARTED
        return EffectDisposition(str(row["disposition"]))


class PostgresRuntimeNodeAdapter:
    """Concrete ``ClaimBatchPort`` and ``OutcomeCommitPort`` realization."""

    def __init__(
        self,
        uow_factory: UowFactory,
        *,
        fairness: FairSharePolicy | None = None,
        reservation_lease: timedelta = timedelta(seconds=60),
        claim_repository_factory: ClaimRepositoryFactory = _default_claim_repository,
        lifecycle_repository_factory: LifecycleRepositoryFactory = (
            _default_lifecycle_repository
        ),
        state_reader_factory: ClaimStateReaderFactory = _default_state_reader,
        reconciliation_owner_factory: ReconciliationOwnerFactory = (
            _default_reconciliation_owner
        ),
        runtime_failure_repository_factory: RuntimeFailureRepositoryFactory = (
            _default_runtime_failure_repository
        ),
        terminal_hook: TerminalCommitHook | None = None,
    ) -> None:
        if reservation_lease <= timedelta(0):
            raise ValueError("reservation lease must be positive")
        self._uow_factory = uow_factory
        self._fairness = fairness or FairSharePolicy()
        self._reservation_lease = reservation_lease
        self._claim_repository_factory = claim_repository_factory
        self._lifecycle_repository_factory = lifecycle_repository_factory
        self._state_reader_factory = state_reader_factory
        self._reconciliation_owner_factory = reconciliation_owner_factory
        self._runtime_failure_repository_factory = runtime_failure_repository_factory
        self._terminal_hook = terminal_hook
        self._started: dict[str, ClaimedLifecycle] = {}

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
    ) -> tuple[RuntimeClaim, ...]:
        self._require_node_context(control_scope, node, profile, deployment, protocol)
        context = NodeClaimContext(
            node_id=node.node_id,
            node_profile_digest=profile.profile_digest,
            deployment_catalog_digest=deployment.catalog_digest,
            runtime_protocol_version=protocol.version,
            authority_snapshot_digest=canonical_digest(
                {
                    "system_actor_id": control_scope.system_actor_id,
                    "permission": control_scope.permission,
                    "authority_epoch": control_scope.authority_epoch,
                }
            ),
            interpreter_profile_digests=profile.interpreter_profile_digests,
            lease_seconds=max(1, int(protocol.heartbeat_extension.total_seconds())),
            reservation_seconds=max(1, int(self._reservation_lease.total_seconds())),
        )
        with self._uow_factory() as uow:
            repository = self._claim_repository_factory(uow.connection)
            reader = self._state_reader_factory(uow.connection)
            records = repository.claim_due(
                control_scope,
                context,
                limit=limit,
                fairness=self._fairness,
                now=observed_at,
            )
            claims = tuple(reader.runtime_claim(record) for record in records)
            uow.commit()
        return claims

    def heartbeat(
        self,
        *,
        control_scope: ControlPlaneScope,
        claim: RuntimeClaim,
        expected_revision: int,
        new_expiry: datetime,
    ) -> RuntimeClaim:
        # The repository compares the existing lease to the database clock.
        # ``new_expiry`` is the requested successor value, not an observation
        # time, so using it to test the old lease would reject every extension.
        self._require_claim_authority(control_scope, claim, observed_at=None)
        if expected_revision != claim.work_item_revision:
            raise LeaseLost("heartbeat expected revision differs from RuntimeClaim")
        if new_expiry <= claim.claim_binding.lease_expires_at:
            raise ValueError("heartbeat must extend the current lease")
        try:
            with self._uow_factory() as uow:
                repository = self._claim_repository_factory(uow.connection)
                row = repository.heartbeat(
                    control_scope,
                    claim.assignment.work_item_id,
                    claim.claim_binding.lease_token,
                    expected_revision=expected_revision,
                    new_expiry=new_expiry,
                )
                renewed = self._state_reader_factory(uow.connection).renewed_claim(
                    claim, row
                )
                self._require_successor_claim(claim, renewed)
                cached = self._started.get(claim.claim_binding.attempt_id)
                refreshed_cache = None
                if cached is not None:
                    refreshed_cache = replace(
                        cached,
                        claim=renewed.claim_binding,
                        expected_work_revision=cached.expected_work_revision + 1,
                        expected_attempt_revision=cached.expected_attempt_revision + 1,
                        expected_reservation_revision=(
                            cached.expected_reservation_revision + 1
                        ),
                    )
                uow.commit()
            if refreshed_cache is not None:
                self._started[renewed.claim_binding.attempt_id] = refreshed_cache
            return renewed
        except (ClaimConflict, StaleRevisionError, RecordNotFound) as exc:
            raise LeaseLost("heartbeat lost exact lease/revision authority") from exc

    def begin_in_flight(
        self,
        *,
        control_scope: ControlPlaneScope,
        claim: RuntimeClaim,
        expected_revision: int,
        started_at: datetime,
    ) -> RuntimeClaim:
        self._require_claim_authority(control_scope, claim, observed_at=started_at)
        if claim.effect_disposition is not EffectDisposition.NOT_STARTED:
            raise ExactBindingConflict("begin_in_flight requires NOT_STARTED claim")
        if expected_revision != claim.work_item_revision:
            raise LeaseLost("start expected revision differs from RuntimeClaim")
        try:
            with self._uow_factory() as uow:
                reader = self._state_reader_factory(uow.connection)
                scope, claimed = reader.claimed_lifecycle(
                    claim, control_scope, require_started=False
                )
                if claimed.expected_work_revision != expected_revision:
                    raise StaleRevisionError("start work-item revision drift")
                repository = self._lifecycle_repository_factory(uow.connection, scope)
                repository.start_claim(claimed, observed_at=started_at)
                started_claim = replace(
                    claim,
                    work_item_revision=expected_revision + 1,
                    effect_disposition=EffectDisposition.IN_FLIGHT,
                )
                started_lifecycle = replace(
                    claimed,
                    expected_run_revision=claimed.expected_run_revision + 1,
                    expected_step_revision=claimed.expected_step_revision + 1,
                    expected_work_revision=claimed.expected_work_revision + 1,
                    expected_attempt_revision=claimed.expected_attempt_revision + 1,
                )
                uow.commit()
            self._started[started_claim.claim_binding.attempt_id] = started_lifecycle
            return started_claim
        except (ClaimConflict, StaleRevisionError, RecordNotFound) as exc:
            raise LeaseLost("start lost exact lease/revision authority") from exc
        except ExactBindingConflict as exc:
            if "lease has expired" in str(exc):
                raise LeaseLost("claim expired before durable start") from exc
            raise

    def commit_outcome(
        self,
        *,
        control_scope: ControlPlaneScope,
        claim: RuntimeClaim,
        outcome: InterpreterOutcome | ReconciliationHandlerOutcome,
        expected_revision: int,
        observed_at: datetime,
    ) -> None:
        self._require_claim_authority(control_scope, claim, observed_at=observed_at)
        if claim.assignment.assignment_kind is AssignmentKind.RECONCILE:
            if not isinstance(outcome, ReconciliationHandlerOutcome):
                raise ExactBindingConflict(
                    "RECONCILE commit requires ReconciliationHandlerOutcome"
                )
            if expected_revision != claim.work_item_revision:
                raise LeaseLost(
                    "reconciliation expected revision differs from RuntimeClaim"
                )
            try:
                with self._uow_factory() as uow:
                    self._reconciliation_owner_factory(uow.connection).adopt(
                        claim=claim,
                        outcome=outcome,
                        actor_id=control_scope.system_actor_id,
                        observed_at=observed_at,
                    )
                    after_reconciliation = (
                        None
                        if self._terminal_hook is None
                        else getattr(
                            self._terminal_hook,
                            "after_reconciliation",
                            None,
                        )
                    )
                    if (
                        callable(after_reconciliation)
                        and outcome.result.state is ReconciliationState.RESOLVED
                        and outcome.result.disposition is EffectDisposition.SUCCEEDED
                    ):
                        runs = _table("runtime_runs")
                        run = _one_mapping(
                            uow.connection.execute(
                                select(runs).where(
                                    runs.c.project_key == claim.assignment.project_key,
                                    runs.c.run_id == claim.assignment.run_id,
                                )
                            )
                        )
                        if run is None:
                            raise RecordNotFound(
                                f"runtime run not found: {claim.assignment.run_id}"
                            )
                        scope = _PostgresClaimStateReader(uow.connection)._scope(
                            run,
                            control_scope.system_actor_id,
                        )
                        after_reconciliation(
                            connection=uow.connection,
                            scope=scope,
                            claim=claim,
                            outcome=outcome,
                            observed_at=observed_at,
                        )
                    uow.commit()
                return
            except (ClaimConflict, StaleRevisionError, RecordNotFound) as exc:
                raise LeaseLost(
                    "reconciliation commit lost exact lease/revision authority"
                ) from exc
        if not isinstance(outcome, InterpreterOutcome):
            raise ExactBindingConflict(
                "ordinary terminal commit requires InterpreterOutcome"
            )
        if claim.effect_disposition is not EffectDisposition.IN_FLIGHT:
            raise ExactBindingConflict("terminal commit requires IN_FLIGHT claim")
        if expected_revision != claim.work_item_revision:
            raise LeaseLost("terminal expected revision differs from RuntimeClaim")
        attempt_id = claim.claim_binding.attempt_id
        cached = self._started.get(attempt_id)
        if cached is None:
            raise LifecycleCacheMiss(
                "exact attempt was not durably started by this adapter instance"
            )
        self._require_cached_identity(cached, claim)
        try:
            with self._uow_factory() as uow:
                reader = self._state_reader_factory(uow.connection)
                scope, current = reader.claimed_lifecycle(
                    claim, control_scope, require_started=True
                )
                if current.expected_work_revision != expected_revision:
                    raise StaleRevisionError("terminal work-item revision drift")
                self._require_cached_identity(cached, claim)
                repository = self._lifecycle_repository_factory(uow.connection, scope)
                terminal = self._terminal_outcome(
                    outcome,
                    claimed=current,
                    authority_digest=claim.claim_binding.authorization_digest,
                    observed_at=observed_at,
                )
                if outcome.disposition is EffectDisposition.FAILED:
                    assert outcome.failure_code is not None
                    failure = self._runtime_failure_repository_factory(
                        uow.connection,
                        scope,
                    ).put_exact(
                        scope,
                        assignment=claim.assignment,
                        claim=claim.claim_binding,
                        failure_code=outcome.failure_code,
                    )
                    terminal = replace(
                        terminal,
                        failure_ref=failure.failure_ref,
                        failure_digest=failure.failure_digest,
                    )
                if self._terminal_hook is not None:
                    terminal = self._terminal_hook.prepare_terminal(
                        connection=uow.connection,
                        scope=scope,
                        claim=claim,
                        lifecycle=current,
                        outcome=outcome,
                        terminal=terminal,
                    )
                terminal = self._bind_terminal_event(
                    terminal,
                    assignment=claim.assignment,
                )
                repository.commit_outcome(terminal)
                if self._terminal_hook is not None:
                    self._terminal_hook.after_terminal(
                        connection=uow.connection,
                        scope=scope,
                        claim=claim,
                        lifecycle=terminal.claimed,
                        outcome=outcome,
                        terminal=terminal,
                    )
                uow.commit()
            self._started.pop(attempt_id, None)
        except (ClaimConflict, StaleRevisionError) as exc:
            raise LeaseLost(
                f"terminal commit lost exact lease/revision authority: {exc}"
            ) from exc
        except ExactBindingConflict as exc:
            if "claim lease has expired" in str(exc):
                raise LeaseLost("claim expired before terminal commit") from exc
            raise

    @staticmethod
    def _require_node_context(
        control_scope: ControlPlaneScope,
        node: NodeIdentity,
        profile: RuntimeNodeProfile,
        deployment: DeploymentBinding,
        protocol: RuntimeNodeProtocol,
    ) -> None:
        control_scope.require_permission(RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION)
        if control_scope.system_actor_id != node.node_id:
            raise PermissionError("control-plane actor differs from RuntimeNode")
        if deployment.node_profile_digest != profile.profile_digest:
            raise ExactBindingConflict("deployment/node profile digest drift")
        if deployment.runtime_protocol_version != protocol.version:
            raise ExactBindingConflict("deployment/runtime protocol drift")

    @staticmethod
    def _require_claim_authority(
        control_scope: ControlPlaneScope,
        claim: RuntimeClaim,
        *,
        observed_at: datetime | None,
    ) -> None:
        control_scope.require_permission(RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION)
        claim.validate_exact()
        binding = claim.claim_binding
        if binding.node_id != control_scope.system_actor_id:
            raise PermissionError("control-plane actor does not own the claim")
        if binding.claim_authority_epoch != control_scope.authority_epoch:
            raise PermissionError("control-plane authority epoch drift")
        if binding.authorization_digest != binding.authority_digest:
            raise ExactBindingConflict("claim authorization/authority digest drift")
        if observed_at is not None and binding.lease_expires_at <= observed_at:
            raise LeaseLost("claim lease has expired")

    @staticmethod
    def _require_successor_claim(previous: RuntimeClaim, renewed: RuntimeClaim) -> None:
        if renewed.assignment != previous.assignment:
            raise ExactBindingConflict("heartbeat changed RuntimeAssignment")
        old = previous.claim_binding
        new = renewed.claim_binding
        for field_name in (
            "attempt_id",
            "lease_token",
            "node_id",
            "node_profile_digest",
            "interpreter_profile_digest",
            "authority_digest",
            "authorization_digest",
            "execution_reservation_ref",
            "execution_reservation_digest",
            "claim_authority_epoch",
        ):
            if getattr(old, field_name) != getattr(new, field_name):
                raise ExactBindingConflict(
                    f"heartbeat changed exact {field_name} binding"
                )
        if renewed.work_item_revision != previous.work_item_revision + 1:
            raise StaleRevisionError("heartbeat revision did not advance once")
        if renewed.effect_disposition is not previous.effect_disposition:
            raise ExactBindingConflict("heartbeat changed effect disposition")

    @staticmethod
    def _require_cached_identity(cached: ClaimedLifecycle, claim: RuntimeClaim) -> None:
        if (
            cached.attempt_id != claim.claim_binding.attempt_id
            or cached.work_item_id != claim.assignment.work_item_id
            or cached.run_id != claim.assignment.run_id
            or cached.step_id != claim.assignment.step_id
            or cached.claim.lease_token != claim.claim_binding.lease_token
            or cached.claim.binding_digest != claim.claim_binding.binding_digest
        ):
            raise ExactBindingConflict("cached started lifecycle identity drift")

    @staticmethod
    def _terminal_outcome(
        outcome: InterpreterOutcome,
        *,
        claimed: ClaimedLifecycle,
        authority_digest: str,
        observed_at: datetime,
    ) -> TerminalOutcome:
        common: dict[str, object] = {
            "claimed": claimed,
            "authority_digest": authority_digest,
            "observed_at": observed_at,
        }
        if outcome.disposition is EffectDisposition.SUCCEEDED:
            receipt_digest = None
            if outcome.receipt_ref is not None:
                prefix = "receipt:sha256:"
                candidate = (
                    outcome.receipt_ref[len(prefix) :]
                    if outcome.receipt_ref.startswith(prefix)
                    else ""
                )
                if len(candidate) != 64 or any(
                    character not in "0123456789abcdef" for character in candidate
                ):
                    raise ReceiptDigestUnavailable(
                        "receipt_ref must be content-addressed as receipt:sha256:<digest>"
                    )
                receipt_digest = candidate
            return TerminalOutcome(
                **common,
                kind=EffectTerminalKind.SUCCEEDED,
                output_digest=outcome.result_digest,
                receipt_ref=outcome.receipt_ref,
                receipt_digest=receipt_digest,
            )
        if outcome.disposition is EffectDisposition.FAILED:
            assert outcome.failure_code is not None
            failure_digest = canonical_digest(
                {
                    "schema": "mrw.runtime.failure-code.v1",
                    "failure_code": outcome.failure_code,
                }
            )
            return TerminalOutcome(
                **common,
                kind=EffectTerminalKind.FAILED,
                failure_ref=f"failure-code:{outcome.failure_code}",
                failure_digest=failure_digest,
            )
        if outcome.disposition is EffectDisposition.OUTCOME_UNKNOWN:
            return TerminalOutcome(
                **common,
                kind=EffectTerminalKind.OUTCOME_UNKNOWN,
            )
        raise ValueError("InterpreterOutcome is not terminal")

    @staticmethod
    def _bind_terminal_event(
        terminal: TerminalOutcome,
        *,
        assignment: object,
    ) -> TerminalOutcome:
        """RuntimeNode adapter emits the typed event; persistence only folds it."""

        if terminal.kind is EffectTerminalKind.FAILED:
            return replace(
                terminal,
                step_event=StepEvent.EFFECT_FAILED,
                target_step_state=StepState.FAILED,
                event_type=StepEvent.EFFECT_FAILED.value,
                event_schema_version="mrw.runtime.event.effect_failed.v1",
            )
        if terminal.kind is EffectTerminalKind.OUTCOME_UNKNOWN:
            return replace(
                terminal,
                step_event=StepEvent.EFFECT_RECEIPT_LOST,
                target_step_state=StepState.RECONCILING,
                event_type=StepEvent.EFFECT_RECEIPT_LOST.value,
                event_schema_version="mrw.runtime.event.outcome_unknown.v1",
            )
        if getattr(assignment, "assignment_kind", None) is AssignmentKind.VERIFY_ADMIT:
            return replace(
                terminal,
                step_event=StepEvent.COMMIT_READBACK_CONFIRMED,
                target_step_state=StepState.SUCCEEDED,
                event_type=StepEvent.COMMIT_READBACK_CONFIRMED.value,
                event_schema_version="mrw.runtime.event.commit_readback_confirmed.v1",
            )
        event = (
            StepEvent.OUTCOME_STAGED
            if terminal.staged_artifact_id is not None
            else StepEvent.RUNTIME_VALUE_PRODUCED
        )
        return replace(
            terminal,
            step_event=event,
            target_step_state=StepState.SUCCEEDED,
            event_type=event.value,
            event_schema_version="mrw.runtime.event.effect_succeeded.v1",
        )


def runtime_uow_factory(engine: Any) -> UowFactory:
    """Return a fresh-UoW factory suitable for a RuntimeNode process."""

    return lambda: RuntimeUnitOfWork(engine=engine)


__all__ = [
    "LifecycleCacheMiss",
    "NodeAdapterError",
    "PostgresRuntimeNodeAdapter",
    "ReceiptDigestUnavailable",
    "TerminalCommitHook",
    "runtime_uow_factory",
]
