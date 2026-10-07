"""Current workflow migration contract over exact Program/Plan/interpreter."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

from functorial_kit import Failure
import pytest

from app.services.workflow_graph.runtime import invoke_workflow_runtime_node
from app.successor_runtime.capabilities.workflow_native_contribution import (
    WorkflowExecutionContext,
)
from app.successor_runtime.capabilities.workflow_legacy_dsl import (
    workflow_program_metadata,
)
from app.successor_runtime.capabilities.workflow_legacy_dsl import (
    parse_and_validate_workflow_dsl,
)
from app.successor_runtime.language.program import decode_program_spec, encode_program_spec
from app.successor_runtime.language.plan import ExecutionPlan
from app.successor_runtime.language.program import ProgramSpec
from app.successor_runtime.runtime.activation import activate_plan_result
from app.successor_runtime.language.transforms import TransformRegistry


pytestmark = pytest.mark.unit

_EVIDENCE_ROOT = (
    Path(__file__).resolve().parents[4]
    / "development/latest-dev-docs/development-plans/CURRENT_DEV"
    / "2026-08-30-functorial-successor-migration/evidence/p5-c1-slices"
)


def _workflow_dsl() -> dict[str, Any]:
    return {
        "version": "1.0",
        "options": {},
        "nodes": [
            {"node_id": "retrieve", "node_type": "vector_search", "config": {"top_k": 5}},
            {"node_id": "draft", "node_type": "llm_call", "config": {"model": "mrw-local"}},
            {"node_id": "combine", "node_type": "join", "config": {"field": "values"}},
        ],
        "edges": [
            {"from": "retrieve", "to": "combine"},
            {"from": "draft", "to": "combine"},
            {"from": "retrieve", "to": "draft"},
        ],
    }


def _current_program_plan() -> tuple[ProgramSpec, ExecutionPlan, dict[str, Any]]:
    receipt = parse_and_validate_workflow_dsl(_workflow_dsl())
    assert receipt.ok
    assert receipt.program is not None and receipt.plan is not None
    metadata = workflow_program_metadata(receipt.program)
    return receipt.program, receipt.plan, metadata


def test_workflow_low_once_into_exact_program_and_plan() -> None:
    program, plan, metadata = _current_program_plan()
    effects = [step for step in plan.ordered_steps if step.step_kind == "EFFECT"]
    payload_refs = [step.operation_id for step in effects]

    assert metadata["ordered_composition"] == "THEN_TOPOLOGY_ONCE"
    assert metadata["topo_order"] == ["retrieve", "draft", "combine"]
    assert len(effects) == 3
    assert payload_refs == [
        "workflow.vector_search.v1",
        "workflow.llm_call.v1",
        "workflow.join.v1",
    ]
    assert len({step.operation_id for step in effects}) == 3
    assert program.program_digest == program.digest()
    assert plan.plan_digest
    assert all(
        step.operation_contract_ref is not None
        for step in effects
    )


def test_workflow_metadata_preserves_json_shapes_through_program_persistence() -> None:
    dsl = _workflow_dsl()
    dsl["options"] = {
        "empty_array": [],
        "empty_object": {},
        "pair_array": [["key", 1]],
    }
    dsl["nodes"][0]["config"] = {
        "top_k": 3,
        "nested": {"empty_array": [], "empty_object": {}, "pairs": [["k", 1]]},
    }
    receipt = parse_and_validate_workflow_dsl(dsl)

    assert receipt.ok and receipt.program is not None
    decoded = decode_program_spec(encode_program_spec(receipt.program))
    metadata = workflow_program_metadata(decoded)
    assert metadata["options"] == dsl["options"]
    assert metadata["topo_order"] == ["retrieve", "draft", "combine"]
    assert metadata["nodes"][0]["config"] == dsl["nodes"][0]["config"]
    assert metadata["nodes"][0]["config"]["nested"]["empty_array"] == []
    assert metadata["nodes"][0]["config"]["nested"]["empty_object"] == {}


def test_shared_predecessor_executes_once_through_runtime_leaf_transport() -> None:
    _, _, metadata = _current_program_plan()
    nodes = {
        str(item["node_id"]): {
            "id": str(item["node_id"]),
            "node_type": item["node_type"],
            "params": dict(item["config"]),
        }
        for item in metadata["nodes"]
    }
    for node in nodes.values():
        node["depends_on"] = [
            edge["from"]
            for edge in metadata["edges"]
            if edge["to"] == node["id"]
        ]
    ordered_nodes = tuple(
        {
            "node_id": node_id,
            "node_type": nodes[node_id]["node_type"],
            "params": nodes[node_id]["params"],
            "depends_on": nodes[node_id]["depends_on"],
        }
        for node_id in metadata["topo_order"]
    )
    calls: list[str] = []

    def execute(context):
        from app.services.workflow_graph.executors.kernel import node_success

        calls.append(context.node_id)
        values = {
            "retrieve": {"text": "retrieved"},
            "draft": {"text": "drafted"},
            "combine": {"values": ["retrieved", "drafted"]},
        }
        return node_success(context, values[context.node_id])

    with patch(
        "app.services.workflow_graph.runtime.execute_node",
        side_effect=execute,
    ) as kernel:
        context = WorkflowExecutionContext(
            schema="mrw.workflow.runtime.context.v1",
            workflow_id="current-workflow-boundary",
            project_key="demo_proj",
            trace_id="current-workflow-run",
            inputs={},
            nodes=ordered_nodes,
            cursor=0,
            results={},
        )
        for _ in ordered_nodes:
            context = invoke_workflow_runtime_node(context)

    assert calls == ["retrieve", "draft", "combine"]
    assert kernel.call_count == 3
    assert context.cursor == 3
    assert context.results["combine"]["values"] == ["retrieved", "drafted"]


def test_activation_has_one_ready_effect_per_fixed_point_round() -> None:
    program, plan, _ = _current_program_plan()
    completed: tuple[Any, ...] = ()
    observed: list[str] = []
    registries = (
        TransformRegistry(registry_id="workflow.transforms"),
        TransformRegistry(registry_id="workflow.merges"),
        TransformRegistry(registry_id="workflow.discriminators"),
    )
    for _ in range(4):
        result = activate_plan_result(
            run_id="activation-readback",
            program=program,
            plan=plan,
            completed_outputs=completed,
            transform_registry=registries[0],
            merge_registry=registries[1],
            discriminator_registry=registries[2],
        )
        assert not isinstance(result, Failure)
        if not result.activations:
            break
        assert len(result.activations) == 1
        activation = result.activations[0]
        node_id = activation.payload_ref.value_id.split(":node:", 1)[1]
        node_id = node_id.removesuffix(":payload")
        observed.append(node_id)
        from app.successor_runtime.runtime.activation import BoundStepValue

        completed += (
            BoundStepValue(
                activation.step_id,
                activation.payload_ref,
                {"completed": activation.step_id},
            ),
        )
    assert observed == ["retrieve", "draft", "combine"]


def test_frozen_c1_slice_summaries_remain_byte_readable_history() -> None:
    rows = []
    for slice_id in ("A", "B", "C"):
        path = _EVIDENCE_ROOT / f"C1Slice{slice_id}.v1.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["schema"] == "mrw.functorial-successor.c1-slice-evidence.v1"
        assert payload["slice_id"] == slice_id
        assert len(payload["content_digest"]) == 64
        rows.append((slice_id, payload["content_digest"]))
    assert [row[0] for row in rows] == ["A", "B", "C"]


def _current_replay_digest() -> str:
    program, plan, _ = _current_program_plan()
    return program.program_digest + plan.plan_digest
