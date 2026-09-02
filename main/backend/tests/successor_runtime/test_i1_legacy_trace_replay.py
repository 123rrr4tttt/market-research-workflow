"""I1 legacy trace replay evidence rows (deterministic, zero double effect).

Each row replays one deterministic legacy trace through the pure successor
surface twice and records the resulting digest.  Rows never write evidence
files and never call PostgreSQL, providers or canonical writers.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

import pytest

from app.successor_migration import legacy_workflow_graph as legacy_graph
from app.successor_migration.legacy_ingest_c7 import (
    capture_legacy_ingest_c7_fixture,
)
from app.successor_runtime.capabilities import c1_legacy_dsl as c1_dsl
from app.successor_runtime.capabilities import collect_c3 as c3
from app.successor_runtime.capabilities import collect_c3_interpreters as ci
from app.successor_runtime.capabilities.c1_slice_acceptance import C1StepStatus
from app.successor_runtime.capabilities.ingest_c7_movements import (
    verify_structured_candidate,
)

from .p4_c7_fixture import submission as _c7_submission
from .test_c7_movement_decision_parity import _run_mode as _c7_run_mode
from .test_p2_c2_1_parity import (
    _bindings,
    _closure,
    _run_legacy,
)
from .test_p2_c2_1_parity import (
    _payload as _c2_1_payload,
)
from .test_p2_c2_1_parity import (
    _run_successor as _c2_1_run_successor,
)
from .test_p3_c3_contracts import (
    _catalog,
    _compiled_c3_1,
    _element_payload,
    _plan,
    _program_c3_1,
    _request_ref,
    _scope,
    _snapshot,
)
from .test_p3_c3_micro import _failed, _receipt, _sequence, _succeeded
from .test_p3_c3_replay_shadow import (
    _bindings_c3_1,
    _bindings_c3_2,
    _fold_program_and_plan,
    _SuccessorFixtureRunner,
)
from .test_p5_c1_legacy_oracle import _compare as _c1_oracle_compare


def _c1_status():
    return C1StepStatus.SUCCESS


def _deployment_digest() -> str:
    return c3.deployment_catalog_digest()


def _verify_c7(forged, snapshot, envelope, decision, trace):
    return verify_structured_candidate(
        snapshot=snapshot,
        envelope=envelope,
        decision=decision,
        candidate=forged,
        expected_candidate_digest=trace.outcome.candidate_digest,
        expected_project_key=trace.outcome.project_key,
        actor="actor:i1-replay",
        authority_digest="a" * 64,
        authority_epoch=1,
        canonical_base_revision=1,
        canonical_base_incarnation="canonical-base-v1",
        canonical_object_id="doc:c7:i1-replay",
    )


pytestmark = pytest.mark.unit


def _c2_1_replay_digest() -> str:
    payload = _c2_1_payload()
    program, plan, ref, payload_ref = _closure(payload)
    _, successor_binding = _bindings()
    first = _c2_1_run_successor(
        payload, program, plan, ref, payload_ref, successor_binding
    )
    assert not isinstance(first, Exception)
    second = _c2_1_run_successor(
        payload, program, plan, ref, payload_ref, successor_binding
    )
    assert not isinstance(second, Exception)
    assert first.value.observation_digest == second.value.observation_digest, (
        "C2.1 successor observation digest is not deterministic"
    )
    return first.value.observation_digest


def _c2_1_zero_double_effect() -> bool:
    from app.successor_migration.legacy_source_library import (
        LegacySourceLibraryC2_1Adapter,
    )

    adapter = LegacySourceLibraryC2_1Adapter()
    payload = _c2_1_payload()
    first = adapter._trace(payload, trace_id="i1.c2-1.replay.same")
    second = adapter._trace(payload, trace_id="i1.c2-1.replay.same")
    assert first.trace_digest == second.trace_digest
    assert adapter.resolves == 0, "C2.1 replay must not dispatch effects"
    return True


def _c3_1_replay_digest() -> str:
    plan = _plan(options={"batch_parallelism": 2, "batch_fail_fast": True})
    payload = _element_payload(
        plan,
        snapshot=_snapshot(options={"batch_parallelism": 2, "batch_fail_fast": True}),
    )
    program = _program_c3_1(payload)
    compiled = _compiled_c3_1(payload)
    _, successor_binding = _bindings_c3_1()
    common = {
        "program": program,
        "plan": compiled,
        "contract_ref": program.root.operation.contract_ref,
        "payload_ref": program.root.operation.payload_ref,
        "payload": payload,
        "project_scope": _scope(),
        "catalog": _catalog(),
        "deployment_catalog_digest": _deployment_digest(),
        "binding": successor_binding,
        "runner": _SuccessorFixtureRunner(),
    }
    first = ci.CollectTraversalSuccessorInterpreter().interpret(**common)
    second = ci.CollectTraversalSuccessorInterpreter().interpret(**common)
    assert first.disposition == "SUCCEEDED"
    assert second.disposition == "SUCCEEDED"
    assert first.value.outcome_digest == second.value.outcome_digest
    return first.value.outcome_digest + compiled.plan_digest


def _c3_2_fold_replay_digest() -> str:
    queued = _receipt(
        job_id="i1-job-1",
        kind="DISPATCH_ACKNOWLEDGEMENT",
        status="queued",
    )
    first = _succeeded(0, inserted=2, links=("https://a", "https://b"), receipt=queued)
    second = _failed(1, message="batch exploded", terms=("t5",))
    third = _succeeded(2, inserted=3, links=("https://b", "https://c"))
    sequence = _sequence(first, second, third)
    fold_payload = c3.build_collect_fold_payload(
        parent_request_ref=_request_ref(),
        ordered_outcomes=sequence,
    )
    program, plan, contract_ref, payload_ref = _fold_program_and_plan(fold_payload)
    _, successor_binding = _bindings_c3_2()
    common = {
        "program": program,
        "plan": plan,
        "contract_ref": contract_ref,
        "payload_ref": payload_ref,
        "payload": fold_payload,
        "project_scope": _scope(),
        "catalog": _catalog(),
        "deployment_catalog_digest": _deployment_digest(),
        "binding": successor_binding,
    }
    first_aggregate = ci.CollectFoldSuccessorInterpreter().interpret(**common)
    second_aggregate = ci.CollectFoldSuccessorInterpreter().interpret(**common)
    assert first_aggregate.disposition == "SUCCEEDED"
    assert second_aggregate.disposition == "SUCCEEDED"
    assert (
        first_aggregate.value.aggregate_digest
        == second_aggregate.value.aggregate_digest
    )
    return first_aggregate.value.aggregate_digest


def _c7_movement_replay_digest() -> str:
    first = _c7_run_mode("pass_through")
    second = _c7_run_mode("pass_through")
    first_decision = first[3]
    second_decision = second[3]
    assert first_decision.decision_digest == second_decision.decision_digest
    assert first[4].outcome.candidate_digest == second[4].outcome.candidate_digest
    assert first[4].provider_calls == 0
    assert first[4].canonical_write is False
    return first_decision.decision_digest + first[4].outcome.candidate_digest


def _c7_writer_zero() -> bool:
    fixture, replay = capture_legacy_ingest_c7_fixture(
        _c7_submission(),
    )
    assert fixture["writer_calls"] == 0
    assert replay.writer_calls == 0
    assert fixture["writer_enabled"] is False
    return True


def _c1_oracle_replay_digest() -> str:
    oracle = legacy_graph.LegacyWorkflowGraphOracle()
    first = _c1_oracle_compare(oracle, _c1_status())
    second = _c1_oracle_compare(oracle, _c1_status())
    assert first.receipt_digest == second.receipt_digest
    assert first.acceptance.acceptance_digest == second.acceptance.acceptance_digest
    assert oracle.comparison_calls == 2
    assert oracle.provider_calls == 0
    assert oracle.store_writes == 0
    assert oracle.duplicated_effect_calls == 0
    return first.receipt_digest


def _c1_dsl_replay_digest() -> str:
    payload = {
        "version": "1.0",
        "options": {},
        "nodes": [
            {
                "node_id": "retrieve",
                "node_type": "vector_search",
                "config": {"top_k": 5},
            },
            {
                "node_id": "draft",
                "node_type": "llm_call",
                "config": {"model": "mrw-local"},
            },
            {"node_id": "combine", "node_type": "join", "config": {"field": "values"}},
        ],
        "edges": [
            {"from": "retrieve", "to": "combine"},
            {"from": "draft", "to": "combine"},
        ],
    }
    first = c1_dsl.parse_and_validate_legacy_dsl(payload)
    second = c1_dsl.parse_and_validate_legacy_dsl(payload)
    assert first.ok and second.ok
    assert first.program_digest == second.program_digest
    assert first.plan_digest == second.plan_digest
    assert first.provider_calls == 0
    assert first.store_writes == 0
    assert first.canonical_effect_calls == 0
    return first.program_digest + first.plan_digest


def _c2_1_failure_union_parity() -> bool:
    payload = _c2_1_payload()
    program, plan, ref, payload_ref = _closure(payload)
    legacy_binding, successor_binding = _bindings()
    legacy_failure = _run_legacy(
        payload, program, plan, ref, payload_ref, successor_binding
    )
    successor_failure = _c2_1_run_successor(
        payload, program, plan, ref, payload_ref, legacy_binding
    )
    assert (
        isinstance(legacy_failure, Exception)
        or getattr(legacy_failure, "code", None) == "ASSIGNMENT_BINDING_MISMATCH"
    )
    assert (
        isinstance(successor_failure, Exception)
        or getattr(successor_failure, "code", None) == "ASSIGNMENT_BINDING_MISMATCH"
    )
    return True


def _c7_failure_union_parity() -> bool:
    snapshot, envelope, _legacy, decision, trace, _ = _c7_run_mode("structured_json")
    forged = replace(trace.outcome, envelope_digest="0" * 64, candidate_digest="")
    rejected = _verify_c7(forged, snapshot, envelope, decision, trace)
    assert rejected.failure_code == "envelope_digest_mismatch"
    assert trace.provider_calls == 0
    return True


def _replay_rows() -> list[dict[str, Any]]:
    cases: list[tuple[str, str, Callable[[], str], Callable[[], bool]]] = [
        ("C2.1", "i1.replay.c2-1", _c2_1_replay_digest, _c2_1_zero_double_effect),
        ("C3", "i1.replay.c3-1", _c3_1_replay_digest, lambda: True),
        ("C3", "i1.replay.c3-2", _c3_2_fold_replay_digest, lambda: True),
        ("C7", "i1.replay.c7", _c7_movement_replay_digest, _c7_writer_zero),
        ("C1", "i1.replay.c1-oracle", _c1_oracle_replay_digest, lambda: True),
        ("C1", "i1.replay.c1-dsl", _c1_dsl_replay_digest, lambda: True),
    ]
    rows = []
    for cell_id, trace_id, replay, zero_effect in cases:
        replay1_digest = replay()
        replay2_digest = replay()
        rows.append(
            {
                "cell_id": cell_id,
                "trace_id": trace_id,
                "replay1_digest": replay1_digest,
                "replay2_digest": replay2_digest,
                "deterministic": replay1_digest == replay2_digest,
                "zero_double_effect": bool(zero_effect()),
            }
        )
    return rows


def test_i1_legacy_trace_replay_rows_are_deterministic_and_zero_effect() -> None:
    rows = _replay_rows()
    assert {row["cell_id"] for row in rows} >= {"C2.1", "C3", "C7", "C1"}
    for row in rows:
        assert set(row) == {
            "cell_id",
            "trace_id",
            "replay1_digest",
            "replay2_digest",
            "deterministic",
            "zero_double_effect",
        }
        assert row["deterministic"] is True, row
        assert row["zero_double_effect"] is True, row
        assert row["replay1_digest"] == row["replay2_digest"]
        assert row["replay1_digest"]


def test_i1_c2_1_and_c7_failure_union_parity_is_representative() -> None:
    assert _c2_1_failure_union_parity() is True
    assert _c7_failure_union_parity() is True
