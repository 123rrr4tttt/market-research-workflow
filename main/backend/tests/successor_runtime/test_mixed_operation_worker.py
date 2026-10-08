"""Rebuilt production Nodes carry a mixed dispatch -> business-wait Program."""
import json
from collections import deque
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from app.composition.production import build_program_activation, execute_successor_work_item, successor_ready_work_ids
from app.composition.production_runtime import install_runtime_authority
from app.services.agent_batch.business_readback import BusinessTaskObservation, BusinessTaskState
from app.services.request_identity import RequestActorContext
from app.successor_runtime.capabilities import batch_business as business, batch_task as c4
from app.successor_runtime.capabilities.batch_task_program import (
    build_batch_task_single_dispatch_program,
    build_ordered_dispatch_merge_registry,
)
from app.successor_runtime.capabilities.catalog import build_operation_catalog
from app.successor_runtime.capabilities.checksum import canonical_json, content_digest
from app.successor_runtime.language.checksum import canonical_bytes
from app.successor_runtime.language.algebra import OperationSpec, ValueRef, freeze_json_object
from app.successor_runtime.language.catalog import OperationContractRegistry
from app.successor_runtime.language.compile import compile_program
from app.successor_runtime.language.object_contracts import ReturnContract
from app.successor_runtime.language.program import atom_node, program_atoms, then_node
from app.successor_runtime.runtime.authority_grants import AuthorityOperationScope, AuthorityResourceCeiling, AuthorityResourceLimit
from app.successor_runtime.runtime.resources import ResourceClass, ResourcePolicySnapshot
from app.successor_runtime.substrate.postgres.authority import AuthorityGrant, CapabilityAuthority
from app.successor_runtime.substrate.postgres.first_specimen_activation import ActivationTrigger, compiled_submission_request_digest, submit_compiled_program
from app.successor_runtime.substrate.postgres.idempotency import IdempotencyBinding
from app.successor_runtime.substrate.postgres.models import PUBLIC_TABLES
from .test_p0b_postgres_integration import (PROJECT_KEY, PROJECT_SCHEMA, REGISTRY_REVISION, SCOPE_DIGEST, SCOPE_INCARNATION,
    LiveDatabase, _seed_run, _digest, empty_successor_tables as empty_successor_tables, live_database as live_database)


@pytest.mark.parametrize("pending_first", [False, True])
def test_mixed_worker_rebuild_reads_actual_ack_and_business_result(live_database: LiveDatabase, pending_first: bool) -> None:
    now = datetime.now(UTC)
    dispatch_contract = c4.build_batch_task_single_dispatch_contract()
    wait_contract = business.build_batch_business_wait_contract()
    catalog = build_operation_catalog((dispatch_contract, wait_contract), catalog_id="controlled-mixed", catalog_version="1")
    registry = OperationContractRegistry(catalog, (dispatch_contract, wait_contract))
    payload = c4.BatchTaskSingleDispatchPayload(
        schema_version=c4.DISPATCH_SINGLE_PAYLOAD_SCHEMA, operation_kind=c4.DISPATCH_SINGLE_KIND,
        dispatch_id="mixed:dispatch", project_key=PROJECT_KEY, resolved_schema=PROJECT_SCHEMA,
        registry_revision=REGISTRY_REVISION, scope_incarnation=SCOPE_INCARNATION,
        scope_digest=SCOPE_DIGEST, capability_id=dispatch_contract.owner_capability_id,
        item=c4.AgentBatchSubmissionItem(job_id="mixed:item", channel="source_library", item_key="source:mixed"),
        lane="main", queue="controlled-mixed",
    )
    program = build_batch_task_single_dispatch_program(payload=payload, catalog=catalog, program_id="mixed-program",
        project_key=PROJECT_KEY, project_registry_revision=REGISTRY_REVISION, project_scope_digest=SCOPE_DIGEST)
    payload_ref = program_atoms(program.root)[0].operation.payload_ref
    dummy_ack = c4.BatchTaskSingleDispatchAck(schema_version=c4.DISPATCH_SINGLE_ACK_SCHEMA,
        operation_kind=c4.DISPATCH_SINGLE_KIND, dispatch_id="must-not-consume-static", channel="source_library",
        celery_task_id="must-not-read-static-task", lane="main", queue="controlled-mixed")
    dummy_bytes = canonical_json(c4.build_batch_task_single_dispatch_ack_codec(wait_contract.ref).encode_payload(dummy_ack)).encode()
    ack_ref = ValueRef(value_id="mixed-placeholder", project_key=PROJECT_KEY, object_type=c4.DISPATCH_SINGLE_ACK_TYPE,
        codec_id=c4.DISPATCH_SINGLE_ACK_TYPE.codec_id, content_digest=content_digest(dummy_ack),
        storage_kind="project_value_ref", store_id="successor_values", store_version="1",
        storage_ref="project-value:mixed-placeholder", byte_size=len(dummy_bytes), provenance_digest=_digest("mixed-input"))
    wait = atom_node(OperationSpec(operation_id=business.BUSINESS_WAIT_KIND, contract_ref=wait_contract.ref,
        input_refs=(ack_ref,), payload_ref=ack_ref, allowed_overrides=freeze_json_object({})),
        input_type=wait_contract.input_type, output_type=wait_contract.output_type,
        return_contract=ReturnContract(success_modes=("SUCCEEDED",), failure_modes=("FAILED",),
            wait_modes=("WAIT",), cancel_modes=("CANCELED",), admission_required=False))
    program = replace(program, root=then_node(program.root, wait), output_type=wait.output_type, program_digest="").with_digest()
    plan = compile_program(program, catalog, operation_contracts=registry)
    bindings = {step.step_id: (0, "mixed-incarnation") for step in plan.ordered_steps if step.step_kind == "EFFECT"}
    with live_database.engine.begin() as connection:
        _seed_run(connection)
        install_runtime_authority(connection,
            administrator=RequestActorContext("deployment-admin", "deployment", True, "localdev-installation"),
            project_scope=live_database.project_scope,
            capability=CapabilityAuthority(dispatch_contract.owner_capability_id, "on", 1, True, False,
                _digest("mixed-allow"), _digest("mixed-config"), now, "deployment:mixed", "deployment:mixed-disabled"),
            resource=ResourcePolicySnapshot(PROJECT_KEY, dispatch_contract.owner_capability_id, ResourceClass.NETWORK_IO,
                1, _digest("mixed-policy"), 1, 1, 1, 1),
            grant=AuthorityGrant("mixed-grant", live_database.runtime_scope.actor_id, dispatch_contract.owner_capability_id,
                AuthorityOperationScope.from_content(operation_kinds=(dispatch_contract.ref.kind, wait_contract.ref.kind), project_scope_digest=SCOPE_DIGEST),
                AuthorityResourceCeiling.from_content(limits=(AuthorityResourceLimit(resource_class="NETWORK_IO", units=1),), max_active=1),
                None, 1, now + timedelta(hours=1)), installed=registry)
        activation, deployment = build_program_activation(connection, live_database.runtime_scope, program)
        assert len(activation.entries) == 2
        assert {entry.interpreter_binding.deployment_catalog_digest for entry in activation.entries} == {deployment.catalog_digest}
        assert activation.encode_value(
            c4.DISPATCH_SINGLE_PAYLOAD_TYPE, payload
        ) == canonical_json(payload).encode("utf-8")
        ordered_merges = build_ordered_dispatch_merge_registry()
        dispatch_sequence = ordered_merges.resolve_merge(
            ordered_merges.merge_refs()[0]
        ).output_type
        assert activation.encode_value(
            dispatch_sequence, [dummy_ack]
        ) == canonical_bytes([dummy_ack])
        with pytest.raises(ValueError, match="no exact installed endpoint"):
            activation.encode_value(c4.BATCH_TASK_TYPE, payload)
        submit_compiled_program(connection, live_database.runtime_scope, program=program, operation_catalog=catalog,
            operation_contracts=registry, activation_catalog=activation,
            values=((payload_ref, canonical_json(payload).encode()), (ack_ref, dummy_bytes)),
            idempotency=IdempotencyBinding("mixed-idem", dispatch_contract.owner_capability_id, "mixed-request",
                dispatch_contract.ref.kind, compiled_submission_request_digest(program, live_database.runtime_scope, bindings, {}), "mixed-run"),
            incarnation="mixed-incarnation", canonical_bindings=bindings, approvals_by_step={},
            trigger=ActivationTrigger(now, "mixed-trace", now))
        work_id = connection.scalar(sa.select(PUBLIC_TABLES["runtime_work_items"].c.work_item_id))
    dispatched = []
    class Broker:
        reads = 0
        def read_task(self, task_id):
            self.reads += 1
            assert task_id == "mixed-real-task"
            state = BusinessTaskState.PENDING if pending_first and self.reads == 1 else BusinessTaskState.SUCCESS
            return BusinessTaskObservation(task_id, state, result={"document_id": 731, "nested": [True, 2]})
        def cancel_task(self, task_id):
            raise AssertionError("no cancellation requested")
    broker = Broker()
    def dispatch(actual):
        dispatched.append(actual.dispatch_id)
        return c4.BatchTaskSingleDispatchAck(schema_version=c4.DISPATCH_SINGLE_ACK_SCHEMA,
            operation_kind=c4.DISPATCH_SINGLE_KIND, dispatch_id=actual.dispatch_id, channel=actual.item.channel,
            celery_task_id="mixed-real-task", lane=actual.lane, queue=actual.queue)
    first = execute_successor_work_item(engine=live_database.engine, work_item_id=work_id,
        node_id="mixed-node-1", dispatch=dispatch, business_readback=broker)
    assert first.results[0].committed, first
    frontier = successor_ready_work_ids(live_database.engine, work_id)
    assert len(frontier) == 1 and frontier[0] != work_id
    second = execute_successor_work_item(engine=live_database.engine, work_item_id=frontier[0],
        node_id="mixed-node-rebuilt", dispatch=dispatch, business_readback=broker)
    assert second.results[0].committed, second
    if pending_first:
        assert second.results[0].disposition.value == "OUTCOME_UNKNOWN"
        with live_database.engine.begin() as connection:
            # Advance only the pre-existing recovery schedule for this controlled witness.
            work = PUBLIC_TABLES["runtime_work_items"]
            connection.execute(sa.update(work).where(work.c.run_id == "mixed-run", work.c.state == "READY").values(due_at=now))
        recovery = successor_ready_work_ids(live_database.engine, frontier[0])
        assert len(recovery) == 1
        third = execute_successor_work_item(engine=live_database.engine, work_item_id=recovery[0],
            node_id="mixed-recovery-rebuilt", dispatch=dispatch, business_readback=broker)
        assert third.results[0].committed, third
    assert dispatched == [payload.dispatch_id]
    assert successor_ready_work_ids(live_database.engine, work_id) == ()
    with live_database.engine.connect() as connection:
        state = connection.scalar(sa.select(PUBLIC_TABLES["runtime_runs"].c.state).where(PUBLIC_TABLES["runtime_runs"].c.run_id == "mixed-run"))
        assert state == "COMPLETED"
        values = connection.execute(sa.select(live_database.project_tables.successor_values).where(
            live_database.project_tables.successor_values.c.object_type == business.BUSINESS_WAIT_RESULT_TYPE.type_id)).mappings().all()
        assert len(values) == 1
        assert b"mixed-real-task" in bytes(values[0]["content_bytes"])
        assert json.loads(bytes(values[0]["content_bytes"]))["output"] == {"document_id": 731, "nested": [True, 2]}


@pytest.mark.parametrize("alternate_kind", [False, True], ids=("default", "alternate"))
def test_graph_facade_real_tasks_replay_exact_upstream_outputs(
    live_database: LiveDatabase, monkeypatch: pytest.MonkeyPatch, alternate_kind: bool,
) -> None:
    from app.models import base
    from app.services import tasks, workflow_graph
    from app.services.workflow_graph.executors import llm_call
    from app.services.workflow_graph.store import InMemoryCompiledGraphStore
    from app.successor_runtime.capabilities import workflow_native_contribution as workflow_native
    from app.successor_runtime.capabilities.workflow_native_contribution import (
        WORKFLOW_RUNTIME_OWNER,
    )
    from app.successor_runtime.substrate.postgres import session as runtime_session

    kinds = dict(workflow_native.WORKFLOW_RUNTIME_NODE_KINDS)
    if alternate_kind:
        kinds["llm_call"] = "workflow.runtime.llm-call.nondefault.v1"
    definition = workflow_native.build_workflow_runtime_definition(kinds if alternate_kind else None)
    if alternate_kind:
        monkeypatch.setattr(workflow_native, "build_workflow_runtime_definition", lambda: definition)
    operation = definition.operation_for_node_type("llm_call")
    now = datetime.now(UTC)
    actor_id = live_database.runtime_scope.actor_id
    with live_database.engine.begin() as connection:
        _seed_run(connection)
        install_runtime_authority(
            connection,
            administrator=RequestActorContext("deployment-admin", "deployment", True, "localdev-installation"),
            project_scope=live_database.project_scope,
            capability=CapabilityAuthority(
                WORKFLOW_RUNTIME_OWNER, "on", 1, True, False,
                _digest("graph-allow"), _digest("graph-config"), now,
                "deployment:graph", "deployment:graph-disabled",
            ),
            resource=ResourcePolicySnapshot(
                PROJECT_KEY, WORKFLOW_RUNTIME_OWNER, ResourceClass.NETWORK_IO,
                1, _digest("graph-policy"), 1, 1, 1, 1,
            ),
            grant=AuthorityGrant(
                "graph-grant", actor_id, WORKFLOW_RUNTIME_OWNER,
                AuthorityOperationScope.from_content(
                    operation_kinds=(operation.contract.ref.kind,), project_scope_digest=SCOPE_DIGEST,
                ),
                AuthorityResourceCeiling.from_content(
                    limits=(AuthorityResourceLimit(resource_class="NETWORK_IO", units=1),), max_active=1,
                ),
                None, 1, now + timedelta(hours=1),
            ),
            installed=definition.registry,
        )

    queued: deque[str] = deque()
    prompts: list[str] = []

    def capture_next(args: tuple[object, ...] = (), **_kwargs: object) -> object:
        queued.append(str(args[0]))
        return object()

    def provider(prompt: str, **_kwargs: object) -> str:
        prompts.append(prompt)
        return f"answer:{prompt}"

    monkeypatch.setattr(base, "engine", live_database.engine)
    monkeypatch.setattr(runtime_session, "create_runtime_engine", lambda *_args, **_kwargs: live_database.engine)
    monkeypatch.setattr(sa.engine.Engine, "dispose", lambda _engine: None)
    monkeypatch.setattr(tasks.task_successor_runtime, "apply_async", capture_next)
    monkeypatch.setattr(llm_call, "_invoke_llm", provider)
    compiler = workflow_graph.WorkflowGraphCompilerService(store=InMemoryCompiledGraphStore())
    monkeypatch.setattr(workflow_graph, "compiler", compiler)
    compiler.compile({"graph_id": "graph-pg", "dsl": {
        "version": "1.0", "options": {},
        "nodes": [
            {"node_id": "first", "node_type": "llm_call", "config": {"prompt": "first"}},
            {"node_id": "second", "node_type": "llm_call", "config": {
                "prompt_template": "continue {prior_text}",
                "input_vars": [{"name": "prior_text", "source": "node_output", "from_node": "first",
                                "from_key": "text", "required": True}],
            }},
        ],
        "edges": [{"from": "first", "to": "second"}],
    }})
    facade = workflow_graph.WorkflowGraphRuntimeService()
    submitted = facade.run({"graph_id": "graph-pg", "run_id": "graph-pg-run",
                            "project_key": PROJECT_KEY, "actor_id": actor_id})
    assert submitted["status"] == "queued"
    assert len(queued) == 1
    work_ids: list[str] = []
    while queued:
        assert len(work_ids) < 2, "two-node graph must not repeat effects"
        work_id = queued.popleft()
        work_ids.append(work_id)
        result = tasks.task_successor_runtime.run(work_id)
        assert result["results"] and all(item["committed"] and item["executed"] for item in result["results"]), result
    assert len(work_ids) == len(set(work_ids)) == 2
    assert successor_ready_work_ids(live_database.engine, work_ids[0]) == ()
    assert prompts == ["first", "continue answer:first"]
    detail = facade.get_run("graph-pg-run", project_key=PROJECT_KEY, actor_id=actor_id)
    assert detail["status"] == "succeeded"
    replay = facade.replay_run("graph-pg-run", "stateful", project_key=PROJECT_KEY, actor_id=actor_id)
    assert replay["node_statuses"] == {"first": "succeeded", "second": "succeeded"}
    assert replay["replay_consistency"]["consistent"] is True
    assert replay["results"]["first"]["text"] == "answer:first"
    assert replay["results"]["second"]["text"] == "answer:continue answer:first"
    assert prompts == ["first", "continue answer:first"]
