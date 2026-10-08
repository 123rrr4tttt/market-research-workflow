"""Opt-in TestClient PG coverage for the successor agent-batch dispatch API."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from app.api import agent_batch as agent_batch_api
from app.api.agent_batch import AgentBatchSubmitRequest, AgentBatchSubmitBatch, AgentBatchItemSubmit
from app.composition.production_runtime import install_runtime_authority
from app.services.agent_batch import dispatch as dispatch_module
from app.services import tasks as tasks_module
from app.services.request_identity import RequestActorContext
from app.successor_runtime.capabilities import batch_task as c4, batch_business
from app.successor_runtime.capabilities.catalog import build_operation_catalog
from app.successor_runtime.language.catalog import OperationContractRegistry
from app.successor_runtime.language.object_contracts import OperationContract
from app.successor_runtime.runtime.authority_grants import (
    AuthorityOperationScope,
    AuthorityResourceCeiling,
    AuthorityResourceLimit,
)
from app.successor_runtime.runtime.resources import ResourceClass, ResourcePolicySnapshot
from app.successor_runtime.substrate.postgres.authority import (
    AuthorityGrant,
    CapabilityAuthority,
)

from .test_p0b_postgres_integration import (
    PROJECT_KEY,
    PROJECT_SCHEMA,
    PUBLIC_TABLES,
    SCOPE_DIGEST,
    LiveDatabase,
    _digest,
    _seed_run,
    empty_successor_tables as empty_successor_tables,
    live_database as live_database,
)

pytestmark = pytest.mark.integration

REQUEST_ACTOR_ID = "request-actor-1"


@pytest.fixture(autouse=True)
def _clean_tables(empty_successor_tables: None) -> None:
    return None


def _install(
    live_database: LiveDatabase,
    *,
    actor_id: str = REQUEST_ACTOR_ID,
) -> OperationContract:
    contract = c4.build_batch_task_single_dispatch_contract()
    wait = batch_business.build_batch_business_wait_contract()
    registry = OperationContractRegistry(build_operation_catalog(
        (contract, wait), catalog_id="batch-api-test", catalog_version="2",
    ), (contract, wait))
    now = datetime.now(UTC)
    administrator = RequestActorContext("deployment-admin", "deployment", True, "localdev-installation")
    capability = CapabilityAuthority(
        capability_id=contract.owner_capability_id,
        mode="on",
        authority_epoch=1,
        successor_claim_enabled=True,
        legacy_claim_enabled=False,
        allowlist_digest=_digest("allowlist"),
        config_digest=_digest("config"),
        effective_at=now,
        approval_ref="deployment:controlled-localdev",
        rollback_target_ref="deployment:controlled-localdev-disabled",
    )
    resource = ResourcePolicySnapshot(
        project_key=PROJECT_KEY,
        capability_id=contract.owner_capability_id,
        resource_class=ResourceClass.NETWORK_IO,
        policy_epoch=1,
        policy_digest=_digest("dispatch-policy"),
        max_project_active=1,
        max_capability_active=1,
        max_resource_active=1,
        max_units=1,
    )
    grant = AuthorityGrant(
        grant_id="dispatch-grant",
        actor_id=actor_id,
        capability_id=contract.owner_capability_id,
        operation_scope_json=AuthorityOperationScope.from_content(
            operation_kinds=(contract.ref.kind, wait.ref.kind),
            project_scope_digest=SCOPE_DIGEST,
        ),
        resource_ceiling_json=AuthorityResourceCeiling.from_content(
            limits=(AuthorityResourceLimit(resource_class="NETWORK_IO", units=1),),
            max_active=1,
        ),
        credential_ref=None,
        grant_epoch=1,
        expires_at=now + timedelta(hours=1),
    )
    with live_database.engine.begin() as connection:
        public_names = tuple(PUBLIC_TABLES)
        project_names = tuple(live_database.project_tables.as_dict())
        qualified = [f'"public"."{name}"' for name in public_names]
        qualified.extend(f'"{PROJECT_SCHEMA}"."{name}"' for name in project_names)
        connection.execute(
            sa.text("TRUNCATE TABLE " + ", ".join(qualified) + " RESTART IDENTITY CASCADE")
        )
        _seed_run(connection)
        install_runtime_authority(
            connection,
            administrator=administrator,
            project_scope=live_database.project_scope,
            grant=grant,
            capability=capability,
            resource=resource,
            installed=registry,
        )
    return contract


def _make_client(
    live_database: LiveDatabase,
    monkeypatch: pytest.MonkeyPatch,
    *,
    actor_id: str = REQUEST_ACTOR_ID,
) -> tuple[TestClient, list[str]]:
    from fastapi import FastAPI

    monkeypatch.setattr(agent_batch_api, "engine", live_database.engine)
    monkeypatch.setattr(dispatch_module, "engine", live_database.engine)
    trusted = RequestActorContext(actor_id, "test", True, "test-auth")
    monkeypatch.setattr(
        agent_batch_api,
        "require_trusted_actor_context",
        lambda request: trusted,
    )
    dispatched: list[str] = []

    def _fake_apply_async(args: tuple[Any, ...] = (), queue: str | None = None) -> Any:
        dispatched.append(str(args[0]))
        return SimpleNamespace(id=str(args[0]))

    monkeypatch.setattr(
        tasks_module.task_successor_runtime,
        "apply_async",
        _fake_apply_async,
    )
    app = FastAPI()
    app.include_router(agent_batch_api.router)
    return TestClient(app), dispatched


def _submit(**overrides: object) -> AgentBatchSubmitRequest:
    values: dict[str, object] = {
        "project_key": PROJECT_KEY,
        "idempotency_key": "idem-1",
        "batch": AgentBatchSubmitBatch(
            jobs=[
                AgentBatchItemSubmit(item_id="item-1", channel="source_library", item_key="source:1"),
                AgentBatchItemSubmit(item_id="item-2", channel="search.market", query_terms=["robot"]),
            ]
        ),
    }
    values.update(overrides)
    return AgentBatchSubmitRequest(**values)


def test_post_two_items_returns_run_id_and_two_work_items(
    live_database: LiveDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install(live_database)
    client, dispatched = _make_client(live_database, monkeypatch)
    resp = client.post("/agent-batch/jobs", json=_submit().model_dump())
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["status"] == "accepted"
    assert data["accepted_count"] == 2
    assert len(data["work_item_ids"]) == 1
    assert len(dispatched) == 1


def test_post_same_idempotency_returns_same_run_id(
    live_database: LiveDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install(live_database)
    client, _ = _make_client(live_database, monkeypatch)
    first_response = client.post("/agent-batch/jobs", json=_submit().model_dump())
    assert first_response.status_code == 200, first_response.text
    second_response = client.post("/agent-batch/jobs", json=_submit().model_dump())
    assert second_response.status_code == 200, second_response.text
    first = first_response.json()["data"]
    second = second_response.json()["data"]
    assert second["job_id"] == first["job_id"]


def test_post_changed_payload_rejects(
    live_database: LiveDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install(live_database)
    client, _ = _make_client(live_database, monkeypatch)
    first = client.post("/agent-batch/jobs", json=_submit().model_dump())
    assert first.status_code == 200
    changed = _submit(
        batch=AgentBatchSubmitBatch(
            jobs=[AgentBatchItemSubmit(item_id="item-1", channel="source_library", item_key="source:2")]
        )
    )
    second = client.post("/agent-batch/jobs", json=changed.model_dump())
    assert second.status_code in {400, 409}, second.text


def test_post_revoked_grant_rejects(
    live_database: LiveDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install(live_database)
    client, dispatched = _make_client(live_database, monkeypatch)
    with live_database.engine.begin() as connection:
        connection.execute(
            sa.update(PUBLIC_TABLES["runtime_authority_grants"]).values(
                revoked_at=datetime.now(UTC)
            )
        )
    resp = client.post("/agent-batch/jobs", json=_submit().model_dump())
    assert resp.status_code in {400, 403}, resp.text
    assert dispatched == []


def test_get_job_read_only_returns_run_state(
    live_database: LiveDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install(live_database)
    client, _ = _make_client(live_database, monkeypatch)
    submitted = client.post("/agent-batch/jobs", json=_submit().model_dump()).json()["data"]
    run_id = submitted["job_id"]
    with live_database.engine.begin() as connection:
        connection.execute(sa.update(PUBLIC_TABLES["runtime_authority_grants"]).values(revoked_at=datetime.now(UTC)))
        before = tuple(connection.scalar(sa.select(sa.func.count()).select_from(PUBLIC_TABLES[name]))
                       for name in ("runtime_events", "runtime_work_items"))
    resp = client.get(f"/agent-batch/jobs/{run_id}", params={"project_key": PROJECT_KEY})
    assert resp.status_code == 200, resp.text
    with live_database.engine.connect() as connection:
        after = tuple(connection.scalar(sa.select(sa.func.count()).select_from(PUBLIC_TABLES[name]))
                      for name in ("runtime_events", "runtime_work_items"))
    assert after == before
    data = resp.json()["data"]
    assert data["job_id"] == run_id
    assert data["status"] in {"queued", "running"}


@pytest.mark.parametrize("item_count,pending_first", [(1, False), (2, True)])
def test_post_waits_for_real_business_outputs_in_input_order(
    live_database: LiveDatabase, monkeypatch: pytest.MonkeyPatch,
    item_count: int, pending_first: bool,
) -> None:
    from app.composition.production import execute_successor_work_item, successor_ready_work_ids
    from app.services.agent_batch.business_readback import BusinessTaskObservation, BusinessTaskState

    _install(live_database)
    client, _ = _make_client(live_database, monkeypatch)
    payload = _submit()
    payload.batch.jobs = payload.batch.jobs[:item_count]
    response = client.post("/agent-batch/jobs", json=payload.model_dump())
    assert response.status_code == 200, response.text
    submitted = response.json()["data"]
    run_id, first_work = submitted["job_id"], submitted["work_item_ids"][0]
    dispatched: list[str] = []

    def dispatch(item):
        dispatched.append(item.item.job_id)
        return c4.BatchTaskSingleDispatchAck(
            schema_version=c4.DISPATCH_SINGLE_ACK_SCHEMA, operation_kind=c4.DISPATCH_SINGLE_KIND,
            dispatch_id=item.dispatch_id, channel=item.item.channel, celery_task_id=f"business:{item.item.job_id}",
            lane=item.lane, queue=item.queue, trace_id=item.trace_id,
            workflow_run_id=item.workflow_run_id, runtime_readback=item.runtime_readback,
        )

    class Broker:
        reads = 0
        def read_task(self, task_id):
            self.reads += 1
            state = BusinessTaskState.PENDING if pending_first and self.reads == 1 else BusinessTaskState.SUCCESS
            return BusinessTaskObservation(task_id, state, result={"actual_task": task_id, "document_ids": [731]})
        def cancel_task(self, task_id):
            raise AssertionError("no cancellation requested")

    broker = Broker()
    work_ids = (first_work,)
    executions = 0
    saw_wait = False
    while work_ids:
        assert executions < item_count * 2 + 1
        for work_id in work_ids:
            report = execute_successor_work_item(
                engine=live_database.engine, work_item_id=work_id,
                node_id=f"api-business-{executions}", dispatch=dispatch, business_readback=broker,
            )
            executions += 1
            assert report.results and all(result.committed for result in report.results), report
            assert all(result.failure_code is None for result in report.results), report
            if report.results[0].disposition.value == "OUTCOME_UNKNOWN":
                saw_wait = True
                waiting = client.get(f"/agent-batch/jobs/{run_id}", params={"project_key": PROJECT_KEY}).json()["data"]
                assert waiting["status"] == "unknown"
                assert waiting["business_terminal"] is False
                assert waiting["progress"]["succeeded"] == 0
                assert dispatched == ["item-1"]
                with live_database.engine.begin() as connection:
                    work = PUBLIC_TABLES["runtime_work_items"]
                    connection.execute(sa.update(work).where(work.c.run_id == run_id, work.c.state == "READY").values(due_at=datetime.now(UTC)))
        work_ids = successor_ready_work_ids(live_database.engine, first_work)
    assert saw_wait is pending_first
    assert dispatched == [f"item-{index + 1}" for index in range(item_count)]
    before = broker.reads
    detail = client.get(f"/agent-batch/jobs/{run_id}", params={"project_key": PROJECT_KEY}).json()["data"]
    items = client.get(f"/agent-batch/jobs/{run_id}/items", params={"project_key": PROJECT_KEY}).json()["data"]["items"]
    assert detail["status"] == "completed"
    assert detail["business_terminal"] is True
    assert detail["progress"]["total"] == detail["progress"]["succeeded"] == item_count
    assert [item["task_id"] for item in items] == [f"business:item-{index + 1}" for index in range(item_count)]
    assert [item["output"] for item in items] == [{"actual_task": item["task_id"], "document_ids": [731]} for item in items]
    assert all(item["business_terminal"] for item in items)
    assert broker.reads == before
