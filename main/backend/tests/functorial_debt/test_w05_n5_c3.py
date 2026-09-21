"""Focused witnesses for the W05-N5 C3 typed contract boundary."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
from functorial_kit import Failure

from app.successor_runtime.capabilities import collect_c3 as c3
from app.successor_runtime.capabilities import collect_c3_program as cp
from app.successor_runtime.capabilities.collect_c3_interpreters import (
    CollectBindingMismatch,
)
from mrw_functorial_kit.core.w05_capability_semantics import (
    successor_capability_contract_failures,
)


REPO_ROOT = Path(__file__).resolve().parents[4]
C3_FILES = (
    REPO_ROOT / "main/backend/app/successor_runtime/capabilities/collect_c3.py",
    REPO_ROOT
    / "main/backend/app/successor_runtime/capabilities/collect_c3_interpreters.py",
    REPO_ROOT / "main/backend/app/successor_runtime/capabilities/collect_c3_program.py",
)
CONTRACT_WITNESS = "test:test_w05_n5_c3_contract_failures_use_canonical_value"


def _request_ref() -> c3.CollectRequestRef:
    return c3.build_collect_request_ref(
        request_id="req.w05.n5",
        project_key="demo_proj",
        channel="search.market",
    )


def _snapshot() -> c3.CollectLegacyRequestSnapshot:
    return c3.CollectLegacyRequestSnapshot(
        schema_version=c3.COLLECT_REQUEST_SNAPSHOT_SCHEMA_REF,
        flow="search",
        channel="search.market",
        project_key="demo_proj",
        query_terms=("a", "b", "c", "d", "e", "f", "g", "h"),
        urls=(),
        limit=80,
        options={},
        source_context={},
        snapshot_digest="",
    )


def _policy() -> c3.CollectResourcePolicy:
    return c3.CollectResourcePolicy(
        schema_ref=c3.COLLECT_RESOURCE_POLICY_SCHEMA_REF,
        max_parallelism=2,
        deadline_seconds=60,
        cancellation="COORDINATED",
        backpressure=True,
        provider_concurrency_key="search.market",
        policy_digest="",
    )


def _static_elements_with_wrong_shape() -> tuple[c3.CollectBatchElement, ...]:
    return (
        c3.CollectBatchElement(
            schema_version=c3.COLLECT_BATCH_ELEMENT_SCHEMA_REF,
            element_id="plan.wrong:element:0",
            input_index=0,
            query_terms=("different",),
            per_batch_limit=40,
            traversal_policy="STATIC_SHAPE",
            failure_policy="ACCUMULATE",
            element_digest="",
        ),
    )


def _valid_plan() -> c3.CollectBatchPlan:
    return c3.build_collect_batch_plan(
        request_ref=_request_ref(),
        snapshot=_snapshot(),
        plan_id="plan.w05.n5",
        resource_policy=_policy(),
        authority_scope_ref="project:demo_proj",
    )


def _element_payload(element: c3.CollectBatchElement) -> c3.CollectBatchElementPayload:
    return c3.CollectBatchElementPayload(
        schema_version=c3.COLLECT_C3_1_PAYLOAD_SCHEMA,
        operation_kind=c3.COLLECT_C3_1_KIND,
        parent_request_ref=_request_ref(),
        request_snapshot=_snapshot(),
        element=element,
        resource_policy=_policy(),
        authority_scope_ref="project:demo_proj",
        payload_digest="",
    )


def test_w05_n5_c3_contract_failures_use_canonical_value() -> None:
    failure = c3.collect_contract_failure(
        code="schema_contract_invalid",
        message="exact rejection",
        operation="collect.test",
        site="test",
        domain_outcome="INVALID_INPUT",
    )

    assert isinstance(failure, Failure)
    assert successor_capability_contract_failures.matches(failure)
    assert failure.family == "successor.capability.contract_failure"
    assert failure.context is not None
    assert failure.context["witness"] == CONTRACT_WITNESS


def test_w05_n5_c3_total_boundaries_preserve_failure_outcomes() -> None:
    plan_result = c3.try_build_collect_batch_plan(
        request_ref=_request_ref(),
        snapshot=_snapshot(),
        plan_id="plan.w05.n5",
        resource_policy=_policy(),
        authority_scope_ref="project:demo_proj",
        traversal_policy="STATIC_SHAPE",
        static_elements=_static_elements_with_wrong_shape(),
    )
    assert isinstance(plan_result, Failure)
    assert plan_result.code == "schema_contract_invalid"
    assert plan_result.context is not None
    assert plan_result.context["domain_outcome"] == "INVALID_INPUT"

    bundle = c3.build_collect_c3_bundle()
    codec_result = c3.try_decode_c3_payload(bundle.payload_codec_c3_2(), [])
    assert isinstance(codec_result, Failure)
    assert codec_result.code == "codec_contract_invalid"
    assert codec_result.context is not None
    assert codec_result.context["domain_outcome"] == "FOLD_CONTRACT_FAILURE"

    program_result = cp.try_build_declared_traversal_program(
        element_payload=None,
        catalog=c3.build_collect_c3_catalog(bundle),
        program_id="program.w05.n5",
        project_key="demo_proj",
        project_registry_revision=7,
        project_scope_digest="scope",
        traversal_policy="UNSUPPORTED_SHAPE",
    )
    assert isinstance(program_result, Failure)
    assert program_result.code == "program_binding_invalid"
    assert program_result.context is not None
    assert program_result.context["domain_outcome"] == "INVALID_INPUT"


def test_w05_n5_c3_legacy_compatibility_lift_preserves_exception_abi() -> None:
    with pytest.raises(
        ValueError,
        match="^STATIC_SHAPE elements do not match the derived finite ordered shape$",
    ):
        c3.build_collect_batch_plan(
            request_ref=_request_ref(),
            snapshot=_snapshot(),
            plan_id="plan.w05.n5",
            resource_policy=_policy(),
            authority_scope_ref="project:demo_proj",
            traversal_policy="STATIC_SHAPE",
            static_elements=_static_elements_with_wrong_shape(),
        )

    fold_codec = c3.build_collect_c3_bundle().payload_codec_c3_2()
    with pytest.raises(TypeError, match="^payload codec requires a JSON object$"):
        fold_codec.decode_payload([])

    binding_failure = c3.collect_contract_failure(
        code="program_binding_invalid",
        message="C3 binding drift",
        operation="collect.require_exact_binding",
        site="test",
        domain_outcome="INVALID_INPUT",
        public_exception="CollectBindingMismatch",
    )
    with pytest.raises(CollectBindingMismatch, match="^C3 binding drift$"):
        c3.raise_collect_contract_failure(
            binding_failure,
            CollectBindingMismatch,
        )


def test_w05_n5_c3_programmer_defect_lift_preserves_exception_abi() -> None:
    incomplete = Failure(
        family=successor_capability_contract_failures.name,
        code="schema_contract_invalid",
        message="incomplete",
    )

    with pytest.raises(TypeError, match="^C3 contract lift context is invalid$"):
        c3.raise_collect_contract_failure(incomplete, ValueError)


def test_w05_n5_c3_ordered_composition_and_wire_abi() -> None:
    plan = _valid_plan()
    assert tuple(element.input_index for element in plan.elements) == tuple(
        range(len(plan.elements))
    )
    assert tuple(term for element in plan.elements for term in element.query_terms) == (
        _snapshot().query_terms
    )

    payloads = tuple(_element_payload(element) for element in plan.elements)
    bundle = c3.build_collect_c3_bundle()
    codec = bundle.payload_codec_c3_1()
    for payload in payloads:
        encoded = codec.encode_payload(payload)
        assert codec.decode_payload(encoded).to_plain() == payload.to_plain()

    program = cp.build_collect_c3_composed_program(
        element_payloads=payloads,
        catalog=c3.build_collect_c3_catalog(bundle),
        program_id="program.w05.n5.composed",
        project_key="demo_proj",
        project_registry_revision=7,
        project_scope_digest="scope",
    )
    assert dict(program.metadata)["composition"] == (
        "Then(TraverseOrdered, MapOutput(sequence_to_fold_payload), FoldAtom)"
    )
    assert tuple(ref.name for ref in program.transform_refs) == (
        cp.COLLECT_SEQUENCE_TO_FOLD_PAYLOAD_TRANSFORM_NAME,
        cp.COLLECT_FOLD_TRANSFORM_NAME,
    )


def test_w05_n5_c3_retained_boundaries_are_narrow_and_witnessed() -> None:
    sources = {path: path.read_text(encoding="utf-8") for path in C3_FILES}
    assert all("class=DOMAIN_CONTRACT" not in source for source in sources.values())

    boundaries = [
        line.strip()
        for source in sources.values()
        for line in source.splitlines()
        if "# kit:boundary " in line
    ]
    assert len(boundaries) == 2
    assert any("class=PROGRAMMER_DEFECT" in line for line in boundaries)
    assert any("class=LEGACY_COMPATIBILITY_EXCEPTION" in line for line in boundaries)

    test_names = {
        node.name
        for path in (REPO_ROOT / "main/backend/tests").rglob("test_*.py")
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    }
    witness_pattern = re.compile(r"witness=test:(test_[A-Za-z0-9_]+)")
    witnesses = {
        match.group(1)
        for source in sources.values()
        for match in witness_pattern.finditer(source)
    }
    assert witnesses <= test_names
