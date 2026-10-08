from __future__ import annotations

import unittest
from copy import deepcopy
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.services import workflow_graph as workflow_graph_module
from app.services.workflow_graph import WorkflowGraphRuntimeService
from app.services.workflow_graph.governance_contract import build_graph_rollback_contract
from app.services.workflow_graph.runtime import (
    WorkflowNodeSettledFailure,
    invoke_workflow_runtime_node,
)
from app.services.workflow_graph.store import (
    InMemoryCompiledGraphStore,
    InMemoryHistoricalWorkflowRunReader,
)
from app.successor_runtime.capabilities.workflow_native_contribution import (
    WORKFLOW_RUNTIME_CONTEXT_TYPE,
    WORKFLOW_RUNTIME_CONTEXT_CODEC_ID,
    WorkflowExecutionContext,
    build_workflow_runtime_definition,
    build_workflow_runtime_program,
    decode_workflow_runtime_output,
)
from app.successor_runtime.capabilities.checksum import canonical_json, content_digest, sha256_hex
from app.successor_runtime.language.algebra import ValueRef
from app.successor_runtime.language.compile import compile_program
from app.successor_runtime.runtime.ports import ProjectScopeRef
from app.successor_runtime.runtime.replay import ReplayEvent, replay_runtime_events
from app.successor_runtime.substrate.projections.agent_session import fold_agent_session


pytestmark = pytest.mark.unit


def _dsl() -> dict[str, Any]:
    return {
        "version": "1.0",
        "options": {},
        "nodes": [
            {
                "node_id": "n1",
                "node_type": "vector_search",
                "config": {"query": "ai", "top_k": 2},
            },
            {
                "node_id": "n2",
                "node_type": "llm_call",
                "config": {
                    "input_vars": [{
                        "name": "prompt",
                        "source": "node_output",
                        "from_node": "n1",
                        "from_key": "text",
                        "required": True,
                    }]
                },
            },
        ],
        "edges": [{"from": "n1", "to": "n2"}],
    }


def _context(*, cursor: int = 0, results: dict[str, Any] | None = None) -> WorkflowExecutionContext:
    return WorkflowExecutionContext(
        schema="mrw.workflow.runtime.context.v1",
        workflow_id="wf-runtime",
        project_key="demo_proj",
        trace_id="trace-runtime",
        inputs={"query": "ai"},
        nodes=(
            {
                "node_id": "n1",
                "node_type": "vector_search",
                "params": {"query": "ai"},
                "depends_on": [],
            },
            {
                "node_id": "n2",
                "node_type": "llm_call",
                "params": _dsl()["nodes"][1]["config"],
                "depends_on": ["n1"],
            },
        ),
        cursor=cursor,
        results=dict(results or {}),
    )


def _replay_state(*, failed_node: str | None = None):
    context = _context()
    runtime = build_workflow_runtime_program(
        workflow_id=context.workflow_id,
        nodes=context.nodes,
        topo_order=("n1", "n2"),
        inputs=context.inputs,
        program_id="workflow-program:run-1",
        project_key=context.project_key,
        project_registry_revision=3,
        project_scope_digest=content_digest({"project": context.project_key}),
        incarnation="workflow:run-1",
        trace_id=context.trace_id,
    )
    plan = compile_program(runtime.program, runtime.catalog, operation_contracts=runtime.registry)
    effects = tuple(step for step in plan.ordered_steps if step.step_kind == "EFFECT")
    journal: list[ReplayEvent] = []

    def append(event_type, schema, *, step_id=None, attempt_id=None, metadata=None):
        event = ReplayEvent.from_content(
            project_key=context.project_key,
            run_id="run-1",
            run_incarnation="workflow:run-1",
            seq=len(journal) + 1,
            event_type=event_type,
            schema_version=f"mrw.runtime.event.{schema}.v1",
            step_id=step_id,
            attempt_id=attempt_id,
            metadata={} if metadata is None else metadata,
            payload_ref=None,
            payload_digest=None,
            authority_digest=content_digest({"actor": "trusted-actor"}),
        )
        journal.append(event)
        return event

    append("ProgramAccepted", "program_accepted", metadata={
        "program_id": runtime.program.program_id, "program_digest": runtime.program.program_digest,
    })
    append("PlanCompiled", "plan_compiled", metadata={
        "plan_id": plan.plan_id, "plan_digest": plan.plan_digest,
    })
    append("QualificationActivated", "qualification_activated", metadata={
        "qualification_digest": content_digest({"qualified_plan": plan.plan_digest}),
        "decision": "QUALIFIED",
    })
    for step in effects:
        node_id = step.operation_id.split(":", 2)[2]
        attempt_id = f"attempt:{step.step_id}"
        append("StepActivated", "step_activated", step_id=step.step_id, metadata={
            "assignment_digest": content_digest({"assignment_step": step.step_id}),
            "activation_digest": content_digest({"activated_step": step.step_id}),
            "input_closure_digest": content_digest({"input_step": step.step_id}),
        })
        append("StepClaimed", "step_claimed", step_id=step.step_id, attempt_id=attempt_id,
               metadata={"assignment_kind": "INTERPRET", "reconciliation_attempt_id": None})
        append("EffectStarted", "effect_started", step_id=step.step_id, attempt_id=attempt_id)
        if node_id == failed_node:
            policy_digest = content_digest({"required_failure": step.step_id})
            failed = append("EffectFailed", "effect_failed", step_id=step.step_id, attempt_id=attempt_id,
                            metadata={"status": "FAILED", "failure_policy_decision_digest": policy_digest,
                                      "required_step_failed": True,
                                      "required_step_failed_event_revision": len(journal) + 2})
            append("RequiredStepFailed", "required_step_failed", step_id=step.step_id, attempt_id=attempt_id,
                   metadata={"status": "FAILED", "source_revision": failed.seq,
                             "source_event_digest": failed.event_digest,
                             "failure_policy_decision_digest": policy_digest})
            break
        append("RuntimeValueProduced", "effect_succeeded", step_id=step.step_id, attempt_id=attempt_id)
    else:
        append("RunCompletionDerived", "run_completion_derived",
               metadata={"required_step_ids": [step.step_id for step in effects]})

    snapshot = fold_agent_session(replay_runtime_events(journal))
    projected_states = {task.step_id: task.step_state.value for task in snapshot.tasks}
    steps = tuple({"step_id": step.step_id, "operation_id": step.operation_id,
                   "state": projected_states.get(step.step_id, "PENDING")} for step in effects)
    events = tuple({"seq": event.seq, "event_type": event.event_type, "step_id": event.step_id,
                    "event_metadata_json": dict(event.metadata)} for event in journal)
    run = {"state": "COMPLETED" if failed_node is None else "FAILED", "incarnation": "workflow:run-1"}
    return plan, run, steps, events, snapshot


class WorkflowRuntimeKernelUnitTest(unittest.TestCase):
    def test_durable_output_is_decoded_by_the_matching_operation_codec(self) -> None:
        context = _context(cursor=1, results={"n1": {"text": "found"}})
        operation = build_workflow_runtime_definition().operation_for_node_type("vector_search")
        exact = canonical_json(operation.context_codec.encode_payload(context)).encode()
        value_ref = ValueRef(
            value_id="workflow-output-1",
            project_key="demo_proj",
            object_type=WORKFLOW_RUNTIME_CONTEXT_TYPE,
            codec_id=WORKFLOW_RUNTIME_CONTEXT_CODEC_ID,
            content_digest=sha256_hex(exact),
            storage_kind="runtime_blob_ref",
            store_id="successor_values",
            store_version="1",
            storage_ref="runtime-output:workflow-output-1",
            byte_size=len(exact),
            provenance_digest=content_digest({"output": "workflow-output-1"}),
        )

        decoded = decode_workflow_runtime_output(value_ref, exact)

        self.assertEqual(decoded.cursor, 1)
        self.assertEqual(decoded.results, {"n1": {"text": "found"}})

    def test_current_occurrence_invokes_one_kernel_and_advances_typed_context(self) -> None:
        from app.services.workflow_graph.executors.kernel import node_success

        def execute(context):
            self.assertEqual(context.node_id, "n1")
            self.assertEqual(context.inputs["query"], "ai")
            return node_success(context, {"text": "found"})

        with patch(
            "app.services.workflow_graph.runtime.execute_node",
            side_effect=execute,
        ) as kernel:
            advanced = invoke_workflow_runtime_node(_context())

        self.assertEqual(kernel.call_count, 1)
        self.assertEqual(advanced.cursor, 1)
        self.assertEqual(advanced.results["n1"]["text"], "found")

    def test_upstream_result_projection_is_preserved_at_runtime_leaf(self) -> None:
        from app.services.workflow_graph.executors.kernel import node_success

        def execute(context):
            self.assertEqual(context.node_id, "n2")
            self.assertEqual(context.inputs["prompt"], "found")
            return node_success(context, {"text": "summary"})

        with patch("app.services.workflow_graph.runtime.execute_node", side_effect=execute):
            advanced = invoke_workflow_runtime_node(
                _context(cursor=1, results={"n1": {"text": "found"}}),
            )

        self.assertEqual(advanced.cursor, 2)
        self.assertEqual(advanced.results["n2"]["text"], "summary")

    def test_typed_kernel_failure_lifts_without_running_a_private_loop(self) -> None:
        from app.services.workflow_graph.executors.kernel import node_failed

        def execute(context):
            return node_failed(
                context,
                "required_input_missing",
                "missing prompt",
                owner="workflow_graph.kernel.llm_call",
                details={},
            )

        with patch("app.services.workflow_graph.runtime.execute_node", side_effect=execute):
            with self.assertRaisesRegex(WorkflowNodeSettledFailure, "missing prompt") as raised:
                invoke_workflow_runtime_node(
                    _context(cursor=1, results={"n1": {"text": "found"}}),
                )
        self.assertEqual(raised.exception.failure_code, "required_input_missing")

    def test_unknown_kernel_exception_remains_unclassified(self) -> None:
        with patch(
            "app.services.workflow_graph.runtime.execute_node",
            side_effect=RuntimeError("unknown kernel fault"),
        ):
            with self.assertRaisesRegex(RuntimeError, "unknown kernel fault"):
                invoke_workflow_runtime_node(_context())


class WorkflowGraphServiceUnitTest(unittest.TestCase):
    def test_compiler_keeps_domain_binding_for_durable_lowering(self) -> None:
        store = InMemoryCompiledGraphStore()
        service = workflow_graph_module.WorkflowGraphCompilerService(store=store)
        response = service.compile({"graph_id": "wf-platform", "dsl": _dsl()})

        compiled = service.get_compiled("wf-platform")
        self.assertEqual(response["checksum"], compiled["checksum"])
        self.assertEqual(compiled["binding_version"], "workflow-graph.domain.v1")
        self.assertEqual(compiled["dsl_content_digest"], content_digest(_dsl()))
        self.assertEqual(compiled["topo_order"], ["n1", "n2"])

    def test_service_rejects_old_unknown_and_tampered_bindings_before_any_effect(self) -> None:
        store = InMemoryCompiledGraphStore()
        compiler_service = workflow_graph_module.WorkflowGraphCompilerService(store=store)
        compiler_service.compile({"graph_id": "bound", "dsl": _dsl()})
        current = compiler_service.get_compiled("bound")

        cases: list[tuple[str, dict[str, Any], str]] = []

        old = deepcopy(current)
        old.pop("binding_version")
        old.pop("dsl_content_digest")
        old["platform"] = {"program_digest": "a", "plan_digest": "b", "catalog_digest": "c"}
        cases.append(("old", old, "missing or unsupported binding version"))

        unknown = deepcopy(current)
        unknown["binding_version"] = "workflow-graph.domain.v999"
        cases.append(("unknown", unknown, "missing or unsupported binding version"))

        dsl_only = deepcopy(current)
        dsl_only["dsl"]["nodes"][0]["config"]["top_k"] = 99
        cases.append(("dsl-only", dsl_only, "DSL content digest is stale"))

        dsl_rehashed_only = deepcopy(current)
        dsl_rehashed_only["dsl"]["nodes"][0]["config"]["top_k"] = 99
        dsl_rehashed_only["dsl_content_digest"] = content_digest(
            dsl_rehashed_only["dsl"]
        )
        cases.append(("dsl-rehashed-only", dsl_rehashed_only, "domain projection is stale"))

        nodes_only = deepcopy(current)
        nodes_only["nodes"]["n1"]["params"]["top_k"] = 99
        cases.append(("nodes-only", nodes_only, "domain projection is stale"))

        dsl_and_nodes = deepcopy(current)
        dsl_and_nodes["dsl"]["nodes"][0]["config"]["top_k"] = 99
        dsl_and_nodes["nodes"]["n1"]["params"]["top_k"] = 99
        cases.append(("dsl-and-nodes", dsl_and_nodes, "DSL content digest is stale"))

        edges = deepcopy(current)
        edges["outgoing_edges"]["n1"] = []
        cases.append(("edges", edges, "domain projection is stale"))

        topo = deepcopy(current)
        topo["topo_order"] = ["n2", "n1"]
        cases.append(("topo", topo, "domain projection is stale"))

        wrong_identity = deepcopy(current)
        wrong_identity["graph_id"] = "different"
        cases.append(("identity", wrong_identity, "identity does not match"))

        service = WorkflowGraphRuntimeService()
        for label, compiled, message in cases:
            with self.subTest(label=label):
                with (
                    patch.object(workflow_graph_module, "compiler") as compiler,
                    patch("app.models.base.engine") as runtime_engine,
                    patch("app.composition.production.submit_installed_program") as submit,
                ):
                    compiler.get_compiled.return_value = compiled
                    with self.assertRaisesRegex(ValueError, message):
                        service.run({
                            "graph_id": "bound",
                            "project_key": "demo_proj",
                            "actor_id": "trusted-actor",
                            "input": {},
                        })
                    runtime_engine.connect.assert_not_called()
                    submit.assert_not_called()

    def test_service_submits_compiled_graph_to_canonical_runtime(self) -> None:
        store = InMemoryCompiledGraphStore()
        compiler = workflow_graph_module.WorkflowGraphCompilerService(store=store)
        compiler.compile({"graph_id": "wf-submit", "dsl": _dsl()})
        scope = ProjectScopeRef(
            project_key="demo_proj",
            resolved_schema="project_demo_proj",
            project_registry_revision=3,
            incarnation="project-incarnation",
            scope_digest="a" * 64,
        )
        fake_engine = MagicMock()
        fake_engine.connect.return_value.__enter__.return_value = MagicMock()
        resolver = MagicMock()
        resolver.resolve.return_value = scope

        with (
            patch.object(workflow_graph_module, "compiler", compiler),
            patch("app.models.base.engine", fake_engine),
            patch(
                "app.successor_runtime.substrate.postgres.session.ServerProjectScopeResolver",
                return_value=resolver,
            ),
            patch(
                "app.composition.production.submit_installed_program",
                return_value=({"run_id": "run-submit", "state": "RUNNING"}, ("work-1",)),
            ) as submit,
            patch.object(
                WorkflowGraphRuntimeService,
                "_read_runtime",
                return_value=(
                    {"run_id": "run-submit", "state": "RUNNING"},
                    (
                        {"operation_id": "workflow-node:0:n1", "state": "READY"},
                        {"operation_id": "workflow-node:1:n2", "state": "PENDING"},
                    ),
                    (),
                ),
            ),
        ):
            result = WorkflowGraphRuntimeService().run({
                "graph_id": "wf-submit",
                "project_key": "demo_proj",
                "actor_id": "trusted-actor",
                "run_id": "run-submit",
                "input": {"query": "ai"},
            })

        self.assertEqual(result["status"], "running")
        self.assertEqual(result["node_statuses"], {"n1": "queued", "n2": "queued"})
        submitted = submit.call_args.kwargs
        self.assertEqual(submitted["project_key"], "demo_proj")
        self.assertEqual(submitted["actor_id"], "trusted-actor")
        self.assertEqual(dict(submitted["program"].metadata)["workflow_id"], "wf-submit")
        self.assertEqual(len(submitted["values"]), 2)

    def test_idempotency_key_without_run_id_uses_one_stable_runtime_identity(self) -> None:
        store = InMemoryCompiledGraphStore()
        compiler = workflow_graph_module.WorkflowGraphCompilerService(store=store)
        compiler.compile({"graph_id": "wf-idempotent", "dsl": _dsl()})
        scope = ProjectScopeRef(
            project_key="demo_proj",
            resolved_schema="project_demo_proj",
            project_registry_revision=3,
            incarnation="project-incarnation",
            scope_digest="a" * 64,
        )
        fake_engine = MagicMock()
        fake_engine.connect.return_value.__enter__.return_value = MagicMock()
        resolver = MagicMock()
        resolver.resolve.return_value = scope

        def readback(*, run_id: str, **_kwargs: object):
            return (
                {"run_id": run_id, "state": "READY"},
                (
                    {"operation_id": "workflow-node:0:n1", "state": "READY"},
                    {"operation_id": "workflow-node:1:n2", "state": "PENDING"},
                ),
                (),
            )

        with (
            patch.object(workflow_graph_module, "compiler", compiler),
            patch("app.models.base.engine", fake_engine),
            patch(
                "app.successor_runtime.substrate.postgres.session.ServerProjectScopeResolver",
                return_value=resolver,
            ),
            patch(
                "app.composition.production.submit_installed_program",
                return_value=({}, ()),
            ) as submit,
            patch.object(
                WorkflowGraphRuntimeService,
                "_read_runtime",
                side_effect=readback,
            ),
        ):
            service = WorkflowGraphRuntimeService()
            payload = {
                "graph_id": "wf-idempotent",
                "project_key": "demo_proj",
                "actor_id": "trusted-actor",
                "idempotency_key": "same-request",
                "input": {"query": "ai"},
            }
            first = service.run(payload)
            second = service.run(payload)

        first_run_id = submit.call_args_list[0].kwargs["run_id"]
        second_run_id = submit.call_args_list[1].kwargs["run_id"]
        self.assertEqual(first["run_id"], second["run_id"])
        self.assertEqual(first_run_id, second_run_id)
        self.assertEqual(first["node_statuses"], {"n1": "queued", "n2": "queued"})

    def test_readback_maps_only_canonical_runtime_facts(self) -> None:
        service = WorkflowGraphRuntimeService()
        run = {
            "run_id": "run-1",
            "state": "RUNNING",
            "project_key": "demo_proj",
            "program_id": "program-1",
            "program_digest": "a" * 64,
            "plan_id": "plan-1",
            "plan_digest": "b" * 64,
        }
        steps = (
            {"step_id": "s1", "operation_id": "workflow-node:0:n1", "state": "SUCCEEDED"},
            {"step_id": "s2", "operation_id": "workflow-node:1:n2", "state": "RUNNING"},
        )
        with patch.object(service, "_read_runtime", return_value=(run, steps, ())):
            detail = service.get_run(
                "run-1", project_key="demo_proj", actor_id="trusted-actor",
            )

        self.assertEqual(detail["status"], "running")
        self.assertEqual(detail["node_statuses"], {"n1": "succeeded", "n2": "running"})
        self.assertNotIn("session_id", detail)

    def test_historical_read_requires_explicit_source_and_matching_project(self) -> None:
        historical_reader = InMemoryHistoricalWorkflowRunReader({
            "legacy-run": {
                "run": {
                    "run_id": "legacy-run",
                    "status": "succeeded",
                    "created_at": "2026-09-01T00:00:00+00:00",
                    "updated_at": "2026-09-01T00:01:00+00:00",
                    "node_statuses": {"n1": "succeeded"},
                    "metadata": {
                        "project_key": "demo_proj",
                        "workflow_id": "legacy-workflow",
                    },
                },
                "events": [],
                "results": {"n1": {"text": "legacy"}},
            },
        })
        service = WorkflowGraphRuntimeService(historical_reader=historical_reader)

        detail = service.get_run(
            "legacy-run",
            project_key="demo_proj",
            actor_id="trusted-actor",
            source="historical",
        )
        events = service.get_run_events(
            "legacy-run",
            project_key="demo_proj",
            actor_id="trusted-actor",
            source="historical",
        )

        self.assertEqual(detail["metadata"]["workflow_id"], "legacy-workflow")
        self.assertEqual(events, {"items": [], "session_id": None})
        with self.assertRaisesRegex(KeyError, "not available in this project"):
            service.get_run(
                "legacy-run",
                project_key="other_proj",
                actor_id="trusted-actor",
                source="historical",
            )

    def test_agent_session_projection_is_folded_read_only_from_runtime_journal(self) -> None:
        service = WorkflowGraphRuntimeService()
        scope = ProjectScopeRef(
            project_key="demo_proj",
            resolved_schema="project_demo_proj",
            project_registry_revision=3,
            incarnation="project-incarnation",
            scope_digest="a" * 64,
        )
        fake_engine = MagicMock()
        fake_engine.connect.return_value.__enter__.return_value = MagicMock()
        resolver = MagicMock()
        resolver.resolve.return_value = scope
        task = MagicMock()
        task.model_dump.return_value = {"task_id": "step-1", "status": "completed"}
        snapshot = MagicMock()
        snapshot.model_dump.return_value = {
            "session_id": "run-1",
            "run_id": "run-1",
            "run_incarnation": "workflow:run-1",
            "status": "completed",
        }
        snapshot.tasks = (task,)
        adapter = MagicMock()
        adapter.load.return_value = snapshot
        with (
            patch.object(
                service,
                "_read_runtime",
                return_value=({"incarnation": "workflow:run-1"}, (), ()),
            ),
            patch.object(
                service,
                "get_run_events",
                return_value={"items": [{"event_type": "RunCompletionDerived"}]},
            ),
            patch("app.models.base.engine", fake_engine),
            patch(
                "app.successor_runtime.substrate.postgres.session.ServerProjectScopeResolver",
                return_value=resolver,
            ),
            patch(
                "app.successor_runtime.substrate.projections.agent_session.PostgresAgentSessionReadAdapter",
                return_value=adapter,
            ),
        ):
            bundle = service.get_run_agent_session(
                "run-1", project_key="demo_proj", actor_id="trusted-actor",
            )

        self.assertEqual(bundle["session"]["session_id"], "run-1")
        self.assertEqual(bundle["tasks"], [{"task_id": "step-1", "status": "completed"}])
        self.assertEqual(bundle["artifacts"], [])
        adapter.load.assert_called_once()

    def test_replay_consistency_is_derived_from_journal_projection(self) -> None:
        service = WorkflowGraphRuntimeService()
        plan, run, steps, events, snapshot = _replay_state()
        with (
            patch.object(service, "_read_runtime", return_value=(run, steps, events)),
            patch.object(service, "_read_runtime_plan", return_value=plan),
            patch.object(service, "_load_agent_session_snapshot", return_value=snapshot),
            patch.object(service, "get_run_events", return_value={"items": []}),
            patch.object(
                service,
                "_read_runtime_outputs",
                return_value=(
                    (steps[0]["step_id"], _context(cursor=1, results={"n1": {"text": "found"}})),
                    (steps[1]["step_id"], _context(cursor=2, results={
                        "n1": {"text": "found"}, "n2": {"text": "answer"},
                    })),
                ),
            ),
        ):
            replay = service.replay_run(
                "run-1", "stateful",
                project_key="demo_proj", actor_id="trusted-actor",
            )

        self.assertEqual(replay["status"], "succeeded")
        self.assertEqual(replay["node_statuses"], {"n1": "succeeded", "n2": "succeeded"})
        self.assertTrue(replay["replay_consistency"]["consistent"])
        self.assertEqual(replay["results"], {"n1": {"text": "found"}, "n2": {"text": "answer"}})

    def test_stateful_replay_returns_latest_partial_results_after_failure(self) -> None:
        service = WorkflowGraphRuntimeService()
        plan, run, steps, events, snapshot = _replay_state(failed_node="n2")
        with (
            patch.object(service, "_read_runtime", return_value=(run, steps, events)),
            patch.object(service, "_read_runtime_plan", return_value=plan),
            patch.object(service, "_load_agent_session_snapshot", return_value=snapshot),
            patch.object(service, "get_run_events", return_value={"items": []}),
            patch.object(
                service,
                "_read_runtime_outputs",
                return_value=((steps[0]["step_id"], _context(
                    cursor=1, results={"n1": {"text": "partial"}},
                )),),
            ),
        ):
            replay = service.replay_run(
                "run-1", "stateful",
                project_key="demo_proj", actor_id="trusted-actor",
            )

        self.assertEqual(replay["status"], "failed")
        self.assertEqual(replay["node_statuses"], {"n1": "succeeded", "n2": "failed"})
        self.assertTrue(replay["replay_consistency"]["consistent"])
        self.assertEqual(replay["results"], {"n1": {"text": "partial"}})


@pytest.mark.parametrize("stored_downstream_state", ["PENDING", "SUCCEEDED"])
def test_failed_first_node_replay_uses_plan_for_untouched_downstream(stored_downstream_state) -> None:
    service = WorkflowGraphRuntimeService()
    plan, run, steps, events, snapshot = _replay_state(failed_node="n1")
    assert len(snapshot.tasks) == 1
    assert all(event["step_id"] != steps[1]["step_id"] for event in events)
    steps = (steps[0], {**steps[1], "state": stored_downstream_state})
    with (
        patch.object(service, "_read_runtime", return_value=(run, steps, events)),
        patch.object(service, "_read_runtime_plan", return_value=plan),
        patch.object(service, "_load_agent_session_snapshot", return_value=snapshot),
    ):
        replay = service.replay_run("run-1", project_key="demo_proj", actor_id="trusted-actor")

    assert replay["status"] == "failed"
    assert replay["node_statuses"] == {"n1": "failed", "n2": "queued"}
    consistency = replay["replay_consistency"]
    assert consistency["consistent"] is (stored_downstream_state == "PENDING")
    if stored_downstream_state == "SUCCEEDED":
        assert consistency["issues"] == [{
            "code": "node_status_mismatch",
            "message": "stored node status does not match journal replay: n2",
            "details": {"node_id": "n2", "stored": "succeeded", "replayed": "queued"},
        }]


@pytest.mark.parametrize("drift", [
    "program_digest", "plan_digest", "missing_plan_anchor", "duplicate_program_anchor",
    "unknown_task", "unknown_event_step", "missing_touched_task",
    "journal_sequence", "snapshot_frontier", "snapshot_run", "snapshot_incarnation",
])
def test_replay_rejects_plan_anchor_task_and_frontier_drift(drift) -> None:
    service = WorkflowGraphRuntimeService()
    plan, run, steps, original_events, snapshot = _replay_state(failed_node="n1")
    events = list(deepcopy(original_events))
    if drift in {"program_digest", "plan_digest"}:
        events[0 if drift == "program_digest" else 1]["event_metadata_json"][drift] = "f" * 64
    elif drift == "missing_plan_anchor":
        events[1]["event_type"] = "CompileSucceeded"
    elif drift == "duplicate_program_anchor":
        events[2].update(event_type="ProgramAccepted", event_metadata_json=dict(events[0]["event_metadata_json"]))
    elif drift == "unknown_task":
        task = snapshot.tasks[0].model_copy(update={"step_id": "unknown-step", "task_id": "unknown-step"})
        snapshot = snapshot.model_copy(update={"tasks": (task,)})
    elif drift == "unknown_event_step":
        events[3]["step_id"] = "unknown-step"
    elif drift == "missing_touched_task":
        snapshot = snapshot.model_copy(update={"tasks": ()})
    elif drift == "journal_sequence":
        events[3]["seq"] = events[2]["seq"]
    elif drift == "snapshot_frontier":
        snapshot = snapshot.model_copy(update={"last_seq": snapshot.last_seq - 1})
    elif drift == "snapshot_run":
        snapshot = snapshot.model_copy(update={"run_id": "other-run"})
    else:
        snapshot = snapshot.model_copy(update={"run_incarnation": "other-incarnation"})
    with (
        patch.object(service, "_read_runtime", return_value=(run, steps, tuple(events))),
        patch.object(service, "_read_runtime_plan", return_value=plan),
        patch.object(service, "_load_agent_session_snapshot", return_value=snapshot),
        pytest.raises(ValueError, match="workflow replay") as rejected,
    ):
        service.replay_run("run-1", project_key="demo_proj", actor_id="trusted-actor")
    assert rejected.value.workflow_failure.code == "integrity_invalid"


class WorkflowGraphCompatibilityUnitTest(unittest.TestCase):
    def test_private_graph_interpreter_is_retired(self) -> None:
        with self.assertRaises(ImportError):
            from app.services.workflow_graph.runtime import WorkflowGraphPlatformInterpreter  # noqa: F401

    def test_graph_rollback_contract_is_preserved(self) -> None:
        contract = build_graph_rollback_contract(
            actor_id="ops-user",
            project_key="demo_proj",
            graph_id="cg-1",
            target_version_id="cver-1",
            current_revision=4,
            base_revision=4,
            reason="restore tested snapshot",
        )
        self.assertEqual(contract["contract_version"], "workflow_graph.rollback.v1")


if __name__ == "__main__":
    unittest.main()
