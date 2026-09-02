"""CW12: rolling deploy preserves exact old assignments and active claims."""

from __future__ import annotations

import hashlib
from datetime import timedelta

import pytest
import sqlalchemy as sa

from app.successor_runtime.runtime.assignments import AssignmentKind
from app.successor_runtime.runtime.node import (
    DeploymentBinding,
    NodeIdentity,
    RuntimeNodeProfile,
    RuntimeNodeProtocol,
)
from app.successor_runtime.runtime.ports import (
    RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION,
    ControlPlaneScope,
)
from app.successor_runtime.substrate.postgres.composition_root import (
    InstalledMaterialReadHandler,
    compose_postgres_first_specimen_runtime,
)
from app.successor_runtime.substrate.postgres.deployment_backlog import (
    DeploymentBacklogRepository,
    DeploymentInstallationSet,
    DeploymentInstallationSnapshot,
    InstalledHandlerSnapshot,
)
from app.successor_runtime.substrate.postgres.models import PUBLIC_TABLES
from app.successor_runtime.substrate.postgres.nodes import RuntimeNodeRepository
from app.successor_runtime.substrate.postgres.unit_of_work import RuntimeUnitOfWork

from .p0c_postgres_fixture import (  # noqa: F401 - imported fixtures are collected
    DEPLOYMENT_CATALOG_DIGEST,
    NOW,
    LiveP0CDatabase,
    live_p0c_database,
    p0c_database,
)
from .test_p0c_two_nodes_postgres import (
    AUTHORITY_EPOCH,
    NODE_PROFILE_DIGEST,
    _prepare_execution,
)

pytestmark = pytest.mark.integration


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class _AdvancingClock:
    def __init__(self) -> None:
        self._now = NOW

    def now(self):
        observed = self._now
        self._now += timedelta(milliseconds=10)
        return observed


def _snapshot(
    *,
    catalog_digest: str,
    node_profile_digest: str,
    interpreter_profile_digest: str,
    handler_binding_digest: str,
    operation_contract_digest: str,
) -> DeploymentInstallationSnapshot:
    return DeploymentInstallationSnapshot(
        catalog_digest=catalog_digest,
        node_profile_digest=node_profile_digest,
        runtime_protocol_version="1",
        supported_assignment_kinds=frozenset({AssignmentKind.INTERPRET}),
        interpreter_profile_digests=frozenset({interpreter_profile_digest}),
        handlers=(
            InstalledHandlerSnapshot(
                handler_binding_digest=handler_binding_digest,
                interpreter_profile_digest=interpreter_profile_digest,
                operation_contract_digest=operation_contract_digest,
            ),
        ),
    )


def _rows(connection, table_name: str, *predicates):
    return tuple(
        connection.execute(sa.select(PUBLIC_TABLES[table_name]).where(*predicates))
        .mappings()
        .all()
    )


def _compose_old_node(
    database: LiveP0CDatabase,
    *,
    node_id: str,
    old_snapshot: DeploymentInstallationSnapshot,
    installation: InstalledMaterialReadHandler,
):
    return compose_postgres_first_specimen_runtime(
        engine=database.engine,
        identity=NodeIdentity(
            node_id=node_id,
            incarnation=f"{node_id}:incarnation:1",
            started_at=NOW - timedelta(minutes=1),
        ),
        profile=RuntimeNodeProfile(
            profile_digest=NODE_PROFILE_DIGEST,
            supported_assignment_kinds=frozenset({AssignmentKind.INTERPRET}),
            interpreter_profile_digests=frozenset(
                {old_snapshot.handlers[0].interpreter_profile_digest or ""}
            ),
        ),
        deployment=DeploymentBinding(
            catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
            node_profile_digest=NODE_PROFILE_DIGEST,
            runtime_protocol_version="1",
        ),
        protocol=RuntimeNodeProtocol(version="1", claim_batch_size=1),
        control_scope=ControlPlaneScope(
            system_actor_id=node_id,
            permission=RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION,
            authority_epoch=AUTHORITY_EPOCH,
        ),
        installations=(installation,),
        available_installations=(old_snapshot,),
        clock=_AdvancingClock(),
    )


def test_cw12_installation_snapshot_binds_every_execution_dimension() -> None:
    snapshot = _snapshot(
        catalog_digest=_digest("catalog"),
        node_profile_digest=_digest("node-profile"),
        interpreter_profile_digest=_digest("interpreter-profile"),
        handler_binding_digest=_digest("handler-binding"),
        operation_contract_digest=_digest("operation-contract"),
    )

    assert snapshot.catalog_digest == _digest("catalog")
    assert snapshot.node_profile_digest == _digest("node-profile")
    assert snapshot.runtime_protocol_version == "1"
    assert snapshot.interpreter_profile_digests == frozenset(
        {_digest("interpreter-profile")}
    )
    assert snapshot.handlers[0].handler_binding_digest == _digest("handler-binding")
    assert len(snapshot.snapshot_digest) == 64


def test_cw12_missing_old_install_waits_without_recompile_and_exact_return_claims(
    p0c_database: LiveP0CDatabase,  # noqa: F811 - pytest fixture injection
) -> None:
    prepared = _prepare_execution(p0c_database)
    original = prepared.assignments[0]
    assert original.operation_contract_digest is not None
    old_snapshot = _snapshot(
        catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        node_profile_digest=NODE_PROFILE_DIGEST,
        interpreter_profile_digest=prepared.interpreter_profile_digest,
        handler_binding_digest=original.handler_binding_digest,
        operation_contract_digest=original.operation_contract_digest,
    )
    new_snapshot = _snapshot(
        catalog_digest=_digest("cw12-new-deployment-catalog"),
        node_profile_digest=_digest("cw12-new-node-profile"),
        interpreter_profile_digest=_digest("cw12-new-interpreter-profile"),
        handler_binding_digest=_digest("cw12-new-handler-binding"),
        operation_contract_digest=original.operation_contract_digest,
    )

    work = PUBLIC_TABLES["runtime_work_items"]
    attempts = PUBLIC_TABLES["runtime_effect_attempts"]
    reservations = PUBLIC_TABLES["runtime_resource_reservations"]
    with p0c_database.engine.connect() as connection:
        before_assignments = {
            row["work_item_id"]: (
                row["assignment_digest"],
                row["assignment_binding_json"],
                row["plan_digest"],
            )
            for row in _rows(connection, "runtime_work_items")
        }
        before_compile = tuple(
            (row["work_item_id"], row["assignment_digest"])
            for row in _rows(
                connection,
                "runtime_work_items",
                work.c.assignment_kind == AssignmentKind.COMPILE.value,
            )
        )
        before_attempts = int(
            connection.scalar(sa.select(sa.func.count()).select_from(attempts)) or 0
        )
        before_reservations = int(
            connection.scalar(sa.select(sa.func.count()).select_from(reservations)) or 0
        )

    with RuntimeUnitOfWork(engine=p0c_database.engine) as uow:
        waiting = DeploymentBacklogRepository(uow.connection).reconcile(
            DeploymentInstallationSet((new_snapshot,)),
            observed_at=NOW,
        )
        uow.commit()

    assert set(waiting.waiting_work_item_ids) == {
        assignment.work_item_id for assignment in prepared.assignments
    }
    assert waiting.ready_work_item_ids == ()
    assert waiting.lost_cas_work_item_ids == ()
    with p0c_database.engine.connect() as connection:
        rows = _rows(
            connection,
            "runtime_work_items",
            work.c.work_item_id.in_(
                tuple(assignment.work_item_id for assignment in prepared.assignments)
            ),
        )
        assert {(row["state"], row["wait_reason"]) for row in rows} == {
            ("WAITING", "INTERPRETER_UNAVAILABLE")
        }
        assert all(row["lease_token"] is None for row in rows)
        assert all(row["claim_attempt_id"] is None for row in rows)
        assert (
            int(
                connection.scalar(sa.select(sa.func.count()).select_from(attempts)) or 0
            )
            == before_attempts
        )
        assert (
            int(
                connection.scalar(sa.select(sa.func.count()).select_from(reservations))
                or 0
            )
            == before_reservations
        )
        assert (
            tuple(
                (row["work_item_id"], row["assignment_digest"])
                for row in _rows(
                    connection,
                    "runtime_work_items",
                    work.c.assignment_kind == AssignmentKind.COMPILE.value,
                )
            )
            == before_compile
        )
        after_assignments = {
            row["work_item_id"]: (
                row["assignment_digest"],
                row["assignment_binding_json"],
                row["plan_digest"],
            )
            for row in _rows(connection, "runtime_work_items")
        }
        assert after_assignments == before_assignments

    installation = InstalledMaterialReadHandler(
        handler_binding_digest=original.handler_binding_digest,
        interpreter_profile_digest=prepared.interpreter_profile_digest,
        operation_contract_digest=original.operation_contract_digest,
    )
    old_node = _compose_old_node(
        p0c_database,
        node_id="p0c-node-a",
        old_snapshot=old_snapshot,
        installation=installation,
    )
    report = old_node.node.run_once()

    assert report.claimed == 1
    claimed_id = report.results[0].work_item_id
    assert claimed_id in {item.work_item_id for item in prepared.assignments}
    assert old_node.backlog_claims.last_report.ready_work_item_ids
    with p0c_database.engine.connect() as connection:
        claimed_assignment = (
            connection.execute(
                sa.select(
                    attempts.c.assignment_digest,
                    attempts.c.handler_binding_digest,
                ).where(attempts.c.attempt_id == report.results[0].attempt_id)
            )
            .mappings()
            .one()
        )
        expected = next(
            item for item in prepared.assignments if item.work_item_id == claimed_id
        )
        assert claimed_assignment["assignment_digest"] == expected.assignment_digest
        assert (
            claimed_assignment["handler_binding_digest"]
            == expected.handler_binding_digest
        )

    second_node = _compose_old_node(
        p0c_database,
        node_id="p0c-node-b",
        old_snapshot=old_snapshot,
        installation=installation,
    )
    held = second_node.backlog_claims.claim_due(
        control_scope=second_node.node.control_scope,
        node=second_node.node.identity,
        profile=second_node.node.profile,
        deployment=second_node.node.deployment,
        protocol=second_node.node.protocol,
        limit=1,
        observed_at=NOW + timedelta(seconds=1),
    )
    assert len(held) == 1
    held_id = held[0].assignment.work_item_id
    with RuntimeUnitOfWork(engine=p0c_database.engine) as uow:
        node_row = RuntimeNodeRepository(uow.connection).load("p0c-node-b")
        RuntimeNodeRepository(uow.connection).request_drain(
            "p0c-node-b",
            expected_revision=int(node_row["revision"]),
            requested_at=NOW + timedelta(seconds=2),
        )
        uow.commit()
    with p0c_database.engine.connect() as connection:
        held_before = (
            connection.execute(sa.select(work).where(work.c.work_item_id == held_id))
            .mappings()
            .one()
        )

    with RuntimeUnitOfWork(engine=p0c_database.engine) as uow:
        after_drain = DeploymentBacklogRepository(uow.connection).reconcile(
            DeploymentInstallationSet((new_snapshot,)),
            observed_at=NOW + timedelta(seconds=3),
        )
        uow.commit()

    assert held_id not in after_drain.waiting_work_item_ids
    with p0c_database.engine.connect() as connection:
        held_after = (
            connection.execute(sa.select(work).where(work.c.work_item_id == held_id))
            .mappings()
            .one()
        )
        node_after = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_nodes"]).where(
                    PUBLIC_TABLES["runtime_nodes"].c.node_id == "p0c-node-b"
                )
            )
            .mappings()
            .one()
        )
        assert node_after["state"] == "DRAINING"
        for field in (
            "state",
            "assignment_digest",
            "handler_binding_digest",
            "claim_attempt_id",
            "claim_binding_digest",
            "lease_token",
            "lease_owner",
            "lease_expires_at",
            "revision",
        ):
            assert held_after[field] == held_before[field]
