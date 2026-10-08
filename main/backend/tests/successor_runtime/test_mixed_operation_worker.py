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
from app.successor_runtime.capabilities import workflow_native_contribution as workflow_native
from app.composition import installed_operation as installed_operation_module
from app.successor_runtime.capabilities.batch_task_program import (
    build_batch_task_single_dispatch_program,
    build_ordered_dispatch_merge_registry,
)
from app.successor_runtime.capabilities.catalog import build_operation_catalog
from app.successor_runtime.capabilities.checksum import canonical_json, content_digest
from app.successor_runtime.language.checksum import canonical_bytes
from app.successor_runtime.language.algebra import ObjectType, OperationSpec, ValueRef, freeze_json_object
from app.successor_runtime.language.catalog import OperationContractRegistry
from app.successor_runtime.language.compile import compile_program
from app.successor_runtime.language.object_contracts import ReturnContract
from app.successor_runtime.language.program import atom_node, program_atoms, then_node
from app.successor_runtime.runtime.authority_grants import AuthorityOperationScope, AuthorityResourceCeiling, AuthorityResourceLimit
from app.successor_runtime.runtime.resources import ResourceClass, ResourcePolicySnapshot
from app.successor_runtime.substrate.postgres.authority import AuthorityGrant, CapabilityAuthority
from app.successor_runtime.substrate.postgres.runtime_activation import ActivationTrigger, compiled_submission_request_digest, submit_compiled_program
from app.successor_runtime.substrate.postgres.idempotency import IdempotencyBinding
from app.successor_runtime.substrate.postgres.models import PUBLIC_TABLES
from app.successor_runtime.substrate.postgres.runtime_journal import ExactBindingConflict
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
            activation.encode_value(ObjectType("RetiredBatchTask.v1"), payload)
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


def _workflow_authority_installation(
    live_database: LiveDatabase, definition: workflow_native.WorkflowRuntimeDefinition, now: datetime,
) -> dict:
    operations = tuple(definition.operation_for_node_type(kind) for kind in ("llm_call", "join"))
    resources = tuple(
        ResourcePolicySnapshot(
            PROJECT_KEY, operation.contract.owner_capability_id,
            ResourceClass(operation.profiles.resource.resource_classes[0]),
            1, _digest(f"graph-policy:{operation.node_type}"), 2, capacity, 2, capacity,
        )
        for operation, capacity in zip(operations, (2, 1), strict=True)
    )
    return dict(
        administrator=RequestActorContext("deployment-admin", "deployment", True, "localdev-installation"),
        project_scope=live_database.project_scope,
        capability=CapabilityAuthority(
            workflow_native.WORKFLOW_RUNTIME_OWNER, "on", 1, True, False,
            _digest("graph-allow"), _digest("graph-config"), now,
            "deployment:graph", "deployment:graph-disabled",
        ),
        resource=resources,
        grant=AuthorityGrant(
            "graph-grant", live_database.runtime_scope.actor_id, workflow_native.WORKFLOW_RUNTIME_OWNER,
            AuthorityOperationScope.from_content(
                operation_kinds=tuple(operation.contract.ref.kind for operation in operations),
                project_scope_digest=SCOPE_DIGEST,
            ),
            AuthorityResourceCeiling.from_content(
                limits=tuple(AuthorityResourceLimit(resource_class=resource.resource_class.value, units=1)
                             for resource in resources), max_active=1,
            ),
            None, 1, now + timedelta(hours=1),
        ),
        installed=definition.registry,
    )


@pytest.mark.parametrize("alternate_kind", [False, True], ids=("default", "alternate"))
def test_graph_facade_real_tasks_replay_exact_upstream_outputs(
    live_database: LiveDatabase, monkeypatch: pytest.MonkeyPatch, alternate_kind: bool,
) -> None:
    from app.models import base
    from app.services import tasks, workflow_graph
    from app.services.workflow_graph.executors import llm_call
    from app.services.workflow_graph.store import InMemoryCompiledGraphStore
    from app.successor_runtime.substrate.postgres import session as runtime_session

    kinds = dict(workflow_native.WORKFLOW_RUNTIME_NODE_KINDS)
    if alternate_kind:
        kinds["llm_call"] = "workflow.runtime.llm-call.nondefault.v1"
    definition = workflow_native.build_workflow_runtime_definition(kinds if alternate_kind else None)
    if alternate_kind:
        monkeypatch.setattr(workflow_native, "build_workflow_runtime_definition", lambda: definition)
        monkeypatch.setattr(
            installed_operation_module,
            "installed_operation_catalog",
            (
                *installed_operation_module.workflow_installed_operation_catalog(definition),
                *installed_operation_module.nonworkflow_installed_operations,
            ),
        )
    now = datetime.now(UTC)
    actor_id = live_database.runtime_scope.actor_id
    with live_database.engine.begin() as connection:
        _seed_run(connection)
        installation = _workflow_authority_installation(live_database, definition, now)
        install_runtime_authority(connection, **installation)
        install_runtime_authority(connection, **installation)
        assert connection.scalar(sa.select(sa.func.count()).select_from(PUBLIC_TABLES["runtime_authority_grants"])) == 1
        policy_classes = connection.scalars(sa.select(PUBLIC_TABLES["runtime_resource_policies"].c.resource_class)).all()
        assert sorted(policy_classes) == ["CPU_LIGHT", "NETWORK_IO"]

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
            {"node_id": "combine", "node_type": "join", "config": {"field": "text"}},
        ],
        "edges": [{"from": "first", "to": "second"},
                  {"from": "first", "to": "combine"}, {"from": "second", "to": "combine"}],
    }})
    facade = workflow_graph.WorkflowGraphRuntimeService()
    submitted = facade.run({"graph_id": "graph-pg", "run_id": "graph-pg-run",
                            "project_key": PROJECT_KEY, "actor_id": actor_id})
    assert submitted["status"] == "queued"
    assert len(queued) == 1
    work_ids: list[str] = []
    while queued:
        assert len(work_ids) < 3, "three-node graph must not repeat effects"
        work_id = queued.popleft()
        work_ids.append(work_id)
        result = tasks.task_successor_runtime.run(work_id)
        assert result["results"] and all(item["committed"] and item["executed"] for item in result["results"]), result
    assert len(work_ids) == len(set(work_ids)) == 3
    assert successor_ready_work_ids(live_database.engine, work_ids[0]) == ()
    assert prompts == ["first", "continue answer:first"]
    detail = facade.get_run("graph-pg-run", project_key=PROJECT_KEY, actor_id=actor_id)
    assert detail["status"] == "succeeded"
    replay = facade.replay_run("graph-pg-run", "stateful", project_key=PROJECT_KEY, actor_id=actor_id)
    assert replay["node_statuses"] == {"first": "succeeded", "second": "succeeded", "combine": "succeeded"}
    assert replay["replay_consistency"]["consistent"] is True
    assert replay["results"]["first"]["text"] == "answer:first"
    assert replay["results"]["second"]["text"] == "answer:continue answer:first"
    join_payload = {
        "node_type": "join", "field": "text", "sources": ["first", "second"],
        "values": ["answer:first", "answer:continue answer:first"], "count": 2,
    }
    assert replay["results"]["combine"] == {
        **join_payload, "data": join_payload, "error": None,
        "meta": {"node_id": "combine", "node_type": "join"}, "io_trace": {},
    }
    assert prompts == ["first", "continue answer:first"]


def test_graph_bounded_failure_preserves_domain_details_in_persisted_readback(
    live_database: LiveDatabase, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.models import base
    from app.services import tasks, workflow_graph
    from app.services.workflow_graph.executors import llm_call
    from app.services.workflow_graph.store import InMemoryCompiledGraphStore
    from app.successor_runtime.substrate.postgres import session as runtime_session

    with live_database.engine.begin() as connection:
        _seed_run(connection)
        install_runtime_authority(connection, **_workflow_authority_installation(
            live_database, workflow_native.build_workflow_runtime_definition(), datetime.now(UTC),
        ))
    queued: deque[str] = deque()
    provider_calls: list[str] = []

    def capture_next(args: tuple[object, ...] = (), **_kwargs: object) -> object:
        queued.append(str(args[0]))
        return object()

    def forbidden_provider(prompt: str, **_kwargs: object) -> str:
        provider_calls.append(prompt)
        raise AssertionError("missing input must fail before provider invocation")

    monkeypatch.setattr(base, "engine", live_database.engine)
    monkeypatch.setattr(runtime_session, "create_runtime_engine", lambda *_args, **_kwargs: live_database.engine)
    monkeypatch.setattr(sa.engine.Engine, "dispose", lambda _engine: None)
    monkeypatch.setattr(tasks.task_successor_runtime, "apply_async", capture_next)
    monkeypatch.setattr(llm_call, "_invoke_llm", forbidden_provider)
    compiler = workflow_graph.WorkflowGraphCompilerService(store=InMemoryCompiledGraphStore())
    monkeypatch.setattr(workflow_graph, "compiler", compiler)
    compiler.compile({"graph_id": "graph-failure", "dsl": {
        "version": "1.0", "options": {},
        "nodes": [
            {"node_id": "missing_prompt", "node_type": "llm_call", "config": {
                "prompt_template": "Answer this required variable: {required_for_live_failure}",
            }},
            {"node_id": "not_started_join", "node_type": "join", "config": {"field": "text"}},
        ],
        "edges": [{"from": "missing_prompt", "to": "not_started_join"}],
    }})
    facade = workflow_graph.WorkflowGraphRuntimeService()
    actor = live_database.runtime_scope.actor_id
    submitted = facade.run({"graph_id": "graph-failure", "run_id": "graph-failure-run",
                            "project_key": PROJECT_KEY, "actor_id": actor})
    assert submitted["status"] == "queued" and len(queued) == 1
    result = tasks.task_successor_runtime.run(queued.popleft())
    assert result["results"][0]["committed"] and result["results"][0]["executed"], result
    assert not queued and not provider_calls
    detail = facade.get_run("graph-failure-run", project_key=PROJECT_KEY, actor_id=actor)
    assert detail["status"] == "failed"
    assert detail["node_statuses"] == {"missing_prompt": "failed", "not_started_join": "queued"}
    events = facade.get_run_events("graph-failure-run", project_key=PROJECT_KEY, actor_id=actor)["items"]
    assert [event["type"] for event in events] == [
        "ProgramAccepted", "CompileSucceeded", "PlanCompiled", "QualificationActivated",
        "StepActivated", "StepClaimed", "EffectStarted", "EffectFailed", "RequiredStepFailed",
    ]
    failed = next(event for event in events if event["type"] == "EffectFailed")
    assert failed["node_id"] == "missing_prompt"
    payload = failed["payload"]
    assert payload["failure_family"] == "workflow_graph.failure"
    assert payload["failure_code"] == "required_input_missing"
    assert "required_for_live_failure" in payload["error"]
    with live_database.engine.connect() as connection:
        attempt = connection.execute(sa.select(PUBLIC_TABLES["runtime_effect_attempts"]).where(
            PUBLIC_TABLES["runtime_effect_attempts"].c.run_id == "graph-failure-run",
        )).mappings().one()
        assert attempt["disposition"] == "FAILED"
        assert payload["failure_ref"] == attempt["failure_ref"]
        assert payload["failure_digest"] == attempt["failure_digest"]
        values = live_database.project_tables.successor_values
        value = connection.execute(sa.select(values).where(
            values.c.content_digest == attempt["failure_digest"],
        )).mappings().one()
        exact = bytes(value["content_bytes"])
        assert _digest(exact) == attempt["failure_digest"]
        body = json.loads(exact)
        assert value["object_type"] == "RuntimeFailure.v2"
        assert body["schema_version"] == "mrw.runtime.failure.v2"
        assert body["failure_code"] == "required_input_missing"
        assert body["domain_failure"] == {
            "family": payload["failure_family"], "code": payload["failure_code"],
            "message": payload["error"], "context": payload["context"],
        }
        assert body["attempt_id"] == attempt["attempt_id"]
        assert body["run_id"] == "graph-failure-run"
    replay = facade.replay_run("graph-failure-run", "stateful", project_key=PROJECT_KEY, actor_id=actor)
    assert replay["replay_consistency"]["consistent"] is True and replay["results"] == {}
    assert not queued and not provider_calls


@pytest.mark.parametrize("invalid", (
    "empty", "duplicate_class", "missing_policy", "policy_project", "policy_capability",
    "grant_scope", "grant_capability", "units", "max_active",
))
def test_multi_resource_installation_rejects_declarations_before_writes(
    live_database: LiveDatabase, invalid: str,
) -> None:
    definition = workflow_native.build_workflow_runtime_definition()
    installation = _workflow_authority_installation(live_database, definition, datetime.now(UTC))
    resources, grant = installation["resource"], installation["grant"]
    if invalid == "empty":
        installation["resource"] = ()
    elif invalid == "duplicate_class":
        installation["resource"] = (resources[0], replace(resources[0], policy_epoch=2,
                                                        policy_digest=_digest("duplicate-policy")))
    elif invalid == "missing_policy":
        installation["resource"] = resources[:1]
    elif invalid in {"policy_project", "policy_capability"}:
        changed = {"project_key": "other-project"} if invalid == "policy_project" else {"capability_id": "other-capability"}
        installation["resource"] = (resources[0], replace(resources[1], **changed))
    elif invalid == "grant_scope":
        installation["grant"] = replace(grant, operation_scope_json=AuthorityOperationScope.from_content(
            operation_kinds=grant.operation_scope_json.operation_kinds, project_scope_digest=_digest("wrong-scope"),
        ))
    elif invalid == "grant_capability":
        installation["grant"] = replace(grant, capability_id="other-capability")
    else:
        limits = grant.resource_ceiling_json.limits
        installation["grant"] = replace(grant, resource_ceiling_json=AuthorityResourceCeiling.from_content(
            limits=(limits[0], AuthorityResourceLimit(resource_class="CPU_LIGHT", units=2)) if invalid == "units" else limits,
            max_active=2 if invalid == "max_active" else 1,
        ))
    with live_database.engine.begin() as connection:
        _seed_run(connection)
        with pytest.raises(ExactBindingConflict):
            install_runtime_authority(connection, **installation)
        for name in ("runtime_capability_authority", "runtime_resource_policies", "runtime_authority_grants"):
            assert connection.scalar(sa.select(sa.func.count()).select_from(PUBLIC_TABLES[name])) == 0


def test_multi_resource_installation_conflict_rolls_back_caller_savepoint(
    live_database: LiveDatabase,
) -> None:
    definition = workflow_native.build_workflow_runtime_definition()
    installation = _workflow_authority_installation(live_database, definition, datetime.now(UTC))
    resource = installation["resource"][1]
    policies = PUBLIC_TABLES["runtime_resource_policies"]
    with live_database.engine.begin() as connection:
        _seed_run(connection)
        connection.execute(sa.insert(policies).values(
            resource_policy_id="preexisting-policy", project_key=resource.project_key,
            capability_id=resource.capability_id, resource_class=resource.resource_class.value,
            concurrency_limit=resource.max_capability_active, max_project_active=resource.max_project_active,
            max_capability_active=resource.max_capability_active, max_resource_active=resource.max_resource_active,
            units_ceiling=resource.max_units, policy_epoch=resource.policy_epoch,
            policy_digest=_digest("preexisting-policy"),
        ))
        previous = dict(connection.execute(sa.select(policies)).mappings().one())
        with pytest.raises(ExactBindingConflict, match="existing authority/resource facts"), connection.begin_nested():
            install_runtime_authority(connection, **installation)
        assert [dict(row) for row in connection.execute(sa.select(policies)).mappings()] == [previous]
        for name in ("runtime_capability_authority", "runtime_authority_grants"):
            assert connection.scalar(sa.select(sa.func.count()).select_from(PUBLIC_TABLES[name])) == 0
    with live_database.engine.connect() as connection:
        assert [dict(row) for row in connection.execute(sa.select(policies)).mappings()] == [previous]


def test_installed_extra_policy_does_not_grant_resource_qualification(
    live_database: LiveDatabase,
) -> None:
    from app.successor_runtime.substrate.postgres.authority_provider import CurrentAuthorityGrantUnavailable

    now = datetime.now(UTC)
    definition = workflow_native.build_workflow_runtime_definition()
    installation = _workflow_authority_installation(live_database, definition, now)
    grant = installation["grant"]
    installation["grant"] = replace(grant, resource_ceiling_json=AuthorityResourceCeiling.from_content(
        limits=(grant.resource_ceiling_json.limits[0],), max_active=1,
    ))
    runtime = workflow_native.build_workflow_runtime_program(
        workflow_id="ungranted-join", nodes=({"node_id": "combine", "node_type": "join", "params": {}, "depends_on": []},),
        topo_order=("combine",), inputs={}, program_id="ungranted-join-program", project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION, project_scope_digest=SCOPE_DIGEST,
        incarnation="ungranted-join-incarnation", trace_id="ungranted-join-trace",
    )
    with live_database.engine.begin() as connection:
        _seed_run(connection)
        install_runtime_authority(connection, **installation)
        assert connection.scalar(sa.select(sa.func.count()).select_from(PUBLIC_TABLES["runtime_resource_policies"])) == 2
        activation, _ = build_program_activation(connection, live_database.runtime_scope, runtime.program)
        with pytest.raises(CurrentAuthorityGrantUnavailable, match="no current grant covers"), connection.begin_nested():
            submit_compiled_program(
                connection, live_database.runtime_scope, program=runtime.program, operation_catalog=runtime.catalog,
                operation_contracts=runtime.registry, activation_catalog=activation, values=runtime.values,
                idempotency=IdempotencyBinding(
                    "ungranted-join-idem", grant.capability_id, "ungranted-join-request",
                    definition.operation_for_node_type("join").contract.ref.kind,
                    compiled_submission_request_digest(runtime.program, live_database.runtime_scope, runtime.canonical_bindings, {}),
                    "ungranted-join-run",
                ),
                incarnation="ungranted-join-incarnation", canonical_bindings=runtime.canonical_bindings,
                approvals_by_step={}, trigger=ActivationTrigger(now, "ungranted-join-trace", now),
            )
        assert connection.scalar(sa.select(sa.func.count()).select_from(PUBLIC_TABLES["runtime_authority_grants"])) == 1
        assert connection.scalar(sa.select(sa.func.count()).select_from(PUBLIC_TABLES["runtime_work_items"])) == 0
