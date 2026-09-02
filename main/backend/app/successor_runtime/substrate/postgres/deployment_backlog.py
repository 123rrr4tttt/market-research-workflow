"""Exact rolling-deploy installation snapshots and backlog reconciliation.

Deployment availability is an execution-boundary fact, not permission to
reinterpret a frozen :class:`RuntimeAssignment`.  A rollout may therefore only
move an unclaimed READY item to ``WAITING/INTERPRETER_UNAVAILABLE`` (or return
that same item to READY when its exact installation comes back).  The immutable
assignment, handler binding, plan, and payload references are never rewritten.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, Self

from sqlalchemy import and_, or_, select, update
from sqlalchemy.engine import Connection

from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
    RuntimeAssignment,
    canonical_digest,
    require_digest,
)
from app.successor_runtime.runtime.node import (
    DeploymentBinding,
    NodeIdentity,
    RuntimeClaim,
    RuntimeHandler,
    RuntimeNodeProfile,
    RuntimeNodeProtocol,
)
from app.successor_runtime.runtime.ports import (
    RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION,
    ControlPlaneScope,
)

from .runtime_journal import (
    ExactBindingConflict,
    _mapping_rows,
    _table,
    validate_runtime_assignment_row,
)


@dataclass(frozen=True, slots=True)
class InstalledHandlerSnapshot:
    """One exact handler realization present in a process installation."""

    handler_binding_digest: str
    interpreter_profile_digest: str | None
    operation_contract_digest: str | None

    def __post_init__(self) -> None:
        require_digest(self.handler_binding_digest, "installed handler binding digest")
        if self.interpreter_profile_digest is not None:
            require_digest(
                self.interpreter_profile_digest,
                "installed interpreter profile digest",
            )
        if self.operation_contract_digest is not None:
            require_digest(
                self.operation_contract_digest,
                "installed operation contract digest",
            )


@dataclass(frozen=True, slots=True)
class DeploymentInstallationSnapshot:
    """Immutable exact catalog/profile/protocol/handler installation fact."""

    catalog_digest: str
    node_profile_digest: str
    runtime_protocol_version: str
    supported_assignment_kinds: frozenset[AssignmentKind]
    interpreter_profile_digests: frozenset[str]
    handlers: tuple[InstalledHandlerSnapshot, ...]

    def __post_init__(self) -> None:
        require_digest(self.catalog_digest, "installation catalog digest")
        require_digest(self.node_profile_digest, "installation node profile digest")
        if not self.runtime_protocol_version:
            raise ValueError("installation snapshot requires runtime protocol version")
        if not self.supported_assignment_kinds:
            raise ValueError("installation snapshot requires assignment kinds")
        for digest in self.interpreter_profile_digests:
            require_digest(digest, "installation interpreter profile digest")
        if not self.handlers:
            raise ValueError("installation snapshot requires exact handler bindings")
        ordered = tuple(
            sorted(self.handlers, key=lambda item: item.handler_binding_digest)
        )
        if ordered != self.handlers:
            raise ValueError("installation handler snapshots must be digest ordered")
        digests = [item.handler_binding_digest for item in self.handlers]
        if len(set(digests)) != len(digests):
            raise ValueError("installation handler binding digest must be unique")
        for item in self.handlers:
            if (
                item.interpreter_profile_digest is not None
                and item.interpreter_profile_digest
                not in self.interpreter_profile_digests
            ):
                raise ValueError(
                    "installed handler profile is absent from the node profile"
                )

    @classmethod
    def from_runtime(
        cls,
        *,
        deployment: DeploymentBinding,
        profile: RuntimeNodeProfile,
        protocol: RuntimeNodeProtocol,
        handlers: Sequence[RuntimeHandler],
    ) -> Self:
        if deployment.node_profile_digest != profile.profile_digest:
            raise ValueError("installation deployment/node profile drift")
        if deployment.runtime_protocol_version != protocol.version:
            raise ValueError("installation deployment/runtime protocol drift")
        snapshots = tuple(
            sorted(
                (
                    InstalledHandlerSnapshot(
                        handler_binding_digest=handler.handler_binding_digest,
                        interpreter_profile_digest=handler.interpreter_profile_digest,
                        operation_contract_digest=getattr(
                            handler, "operation_contract_digest", None
                        ),
                    )
                    for handler in handlers
                ),
                key=lambda item: item.handler_binding_digest,
            )
        )
        return cls(
            catalog_digest=deployment.catalog_digest,
            node_profile_digest=profile.profile_digest,
            runtime_protocol_version=protocol.version,
            supported_assignment_kinds=profile.supported_assignment_kinds,
            interpreter_profile_digests=profile.interpreter_profile_digests,
            handlers=snapshots,
        )

    @property
    def snapshot_digest(self) -> str:
        return canonical_digest(
            {
                "catalog_digest": self.catalog_digest,
                "node_profile_digest": self.node_profile_digest,
                "runtime_protocol_version": self.runtime_protocol_version,
                "supported_assignment_kinds": sorted(
                    kind.value for kind in self.supported_assignment_kinds
                ),
                "interpreter_profile_digests": sorted(self.interpreter_profile_digests),
                "handlers": [
                    {
                        "handler_binding_digest": item.handler_binding_digest,
                        "interpreter_profile_digest": (item.interpreter_profile_digest),
                        "operation_contract_digest": item.operation_contract_digest,
                    }
                    for item in self.handlers
                ],
            }
        )

    def supports(
        self,
        row: Mapping[str, Any],
        assignment: RuntimeAssignment,
    ) -> bool:
        """Check exact frozen compatibility without compiling or rebinding."""

        if (
            assignment.assignment_kind not in self.supported_assignment_kinds
            or assignment.deployment_catalog_digest != self.catalog_digest
            or assignment.runtime_protocol_version != self.runtime_protocol_version
            or row["required_node_profile_selector"] != self.node_profile_digest
            or row["deployment_catalog_digest"] != self.catalog_digest
            or row["runtime_protocol_version"] != self.runtime_protocol_version
        ):
            return False
        expected_profile = getattr(
            assignment.handler_binding, "interpreter_profile_digest", None
        )
        if expected_profile is not None and (
            expected_profile not in self.interpreter_profile_digests
            or row["interpreter_profile_digest"] != expected_profile
        ):
            return False
        for installed in self.handlers:
            if installed.handler_binding_digest != assignment.handler_binding_digest:
                continue
            return (
                installed.interpreter_profile_digest == expected_profile
                and installed.operation_contract_digest
                == assignment.operation_contract_digest
            )
        return False


@dataclass(frozen=True, slots=True)
class DeploymentInstallationSet:
    """Exact installations declared available at one rollout observation."""

    snapshots: tuple[DeploymentInstallationSnapshot, ...]

    def __post_init__(self) -> None:
        if not self.snapshots:
            raise ValueError("deployment availability requires at least one snapshot")
        digests = [item.snapshot_digest for item in self.snapshots]
        if len(set(digests)) != len(digests):
            raise ValueError("deployment installation snapshot is duplicated")

    def supports(
        self,
        row: Mapping[str, Any],
        assignment: RuntimeAssignment,
    ) -> bool:
        return any(item.supports(row, assignment) for item in self.snapshots)

    def require_contains(self, snapshot: DeploymentInstallationSnapshot) -> None:
        if snapshot.snapshot_digest not in {
            item.snapshot_digest for item in self.snapshots
        }:
            raise ValueError(
                "running node installation is absent from availability set"
            )


@dataclass(frozen=True, slots=True)
class DeploymentBacklogReport:
    waiting_work_item_ids: tuple[str, ...] = ()
    ready_work_item_ids: tuple[str, ...] = ()
    lost_cas_work_item_ids: tuple[str, ...] = ()


class DeploymentBacklogRepository:
    """CAS owner for executable, never-claimed rolling-deploy backlog."""

    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def reconcile(
        self,
        availability: DeploymentInstallationSet,
        *,
        observed_at: datetime,
    ) -> DeploymentBacklogReport:
        work = _table("runtime_work_items")
        rows = _mapping_rows(
            self.connection.execute(
                select(work).where(
                    or_(
                        work.c.state == "READY",
                        and_(
                            work.c.state == "WAITING",
                            work.c.wait_reason == "INTERPRETER_UNAVAILABLE",
                        ),
                    ),
                    work.c.lease_token.is_(None),
                    work.c.lease_owner.is_(None),
                    work.c.claim_attempt_id.is_(None),
                )
            )
        )
        waiting: list[str] = []
        ready: list[str] = []
        lost: list[str] = []
        for row in rows:
            assignment = validate_runtime_assignment_row(row)
            if assignment.assignment_digest != row["assignment_digest"]:
                raise ExactBindingConflict("deployment backlog assignment digest drift")
            supported = availability.supports(row, assignment)
            if row["state"] == "READY" and not supported:
                changed = self._transition(
                    row,
                    from_state="READY",
                    from_wait_reason=None,
                    to_state="WAITING",
                    to_wait_reason="INTERPRETER_UNAVAILABLE",
                    observed_at=observed_at,
                )
                (waiting if changed else lost).append(str(row["work_item_id"]))
            elif (
                row["state"] == "WAITING"
                and row["wait_reason"] == "INTERPRETER_UNAVAILABLE"
                and supported
            ):
                changed = self._transition(
                    row,
                    from_state="WAITING",
                    from_wait_reason="INTERPRETER_UNAVAILABLE",
                    to_state="READY",
                    to_wait_reason=None,
                    observed_at=observed_at,
                )
                (ready if changed else lost).append(str(row["work_item_id"]))
        return DeploymentBacklogReport(
            waiting_work_item_ids=tuple(waiting),
            ready_work_item_ids=tuple(ready),
            lost_cas_work_item_ids=tuple(lost),
        )

    def _transition(
        self,
        row: Mapping[str, Any],
        *,
        from_state: str,
        from_wait_reason: str | None,
        to_state: str,
        to_wait_reason: str | None,
        observed_at: datetime,
    ) -> bool:
        work = _table("runtime_work_items")
        predicates = [
            work.c.work_item_id == row["work_item_id"],
            work.c.project_key == row["project_key"],
            work.c.state == from_state,
            work.c.revision == row["revision"],
            work.c.assignment_kind == row["assignment_kind"],
            work.c.assignment_digest == row["assignment_digest"],
            work.c.handler_binding_digest == row["handler_binding_digest"],
            work.c.deployment_catalog_digest == row["deployment_catalog_digest"],
            work.c.runtime_protocol_version == row["runtime_protocol_version"],
            work.c.required_node_profile_selector
            == row["required_node_profile_selector"],
            work.c.lease_token.is_(None),
            work.c.lease_owner.is_(None),
            work.c.claim_attempt_id.is_(None),
        ]
        for column_name in (
            "operation_contract_digest",
            "interpreter_profile_digest",
        ):
            column = getattr(work.c, column_name)
            value = row[column_name]
            predicates.append(column.is_(None) if value is None else column == value)
        predicates.append(
            work.c.wait_reason.is_(None)
            if from_wait_reason is None
            else work.c.wait_reason == from_wait_reason
        )
        result = self.connection.execute(
            update(work)
            .where(*predicates)
            .values(
                state=to_state,
                wait_reason=to_wait_reason,
                revision=int(row["revision"]) + 1,
                updated_at=observed_at,
            )
        )
        return getattr(result, "rowcount", None) == 1


class _ClaimPort(Protocol):
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


class _UnitOfWork(Protocol):
    connection: Connection

    def __enter__(self) -> Self: ...

    def commit(self) -> None: ...

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None: ...


class _UnitOfWorkFactory(Protocol):
    def __call__(self) -> _UnitOfWork: ...


class PostgresBacklogAwareClaimPort:
    """Claim port decorator that observes install availability before claim."""

    def __init__(
        self,
        delegate: _ClaimPort,
        uow_factory: _UnitOfWorkFactory,
        availability: DeploymentInstallationSet,
    ) -> None:
        self._delegate = delegate
        self._uow_factory = uow_factory
        self.availability = availability
        self.last_report = DeploymentBacklogReport()

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
        control_scope.require_permission(RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION)
        with self._uow_factory() as uow:
            self.last_report = DeploymentBacklogRepository(uow.connection).reconcile(
                self.availability, observed_at=observed_at
            )
            uow.commit()
        return self._delegate.claim_due(
            control_scope=control_scope,
            node=node,
            profile=profile,
            deployment=deployment,
            protocol=protocol,
            limit=limit,
            observed_at=observed_at,
        )

    def heartbeat(
        self,
        *,
        control_scope: ControlPlaneScope,
        claim: RuntimeClaim,
        expected_revision: int,
        new_expiry: datetime,
    ) -> RuntimeClaim:
        return self._delegate.heartbeat(
            control_scope=control_scope,
            claim=claim,
            expected_revision=expected_revision,
            new_expiry=new_expiry,
        )


__all__ = [
    "DeploymentBacklogReport",
    "DeploymentBacklogRepository",
    "DeploymentInstallationSet",
    "DeploymentInstallationSnapshot",
    "InstalledHandlerSnapshot",
    "PostgresBacklogAwareClaimPort",
]
