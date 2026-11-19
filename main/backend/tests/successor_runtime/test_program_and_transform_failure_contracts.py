"""Program and transform failure contracts."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from functorial_kit import Failure

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.successor_runtime.language.algebra import ValueRef
from app.successor_runtime.language.program import (
    ProgramSpec,
    ProgramTypeError,
    decode_ast,
    identity_node,
    then_node,
    try_decode_ast,
    try_successor_materialization,
    try_then_node,
)
from app.successor_runtime.language.transforms import (
    RegistryError,
    TransformRef,
    TransformRegistry,
    merge_output_type,
    try_merge_output_type,
)
from app.successor_runtime.research.object_types import ObjectType


LEFT = ObjectType("test.language.left")
RIGHT = ObjectType("test.language.right")


def _merge_value(left: object, right: object) -> tuple[object, object]:
    return left, right


def test_program_try_failures_and_legacy_lift() -> None:
    failure = try_then_node(identity_node(LEFT), identity_node(RIGHT))
    assert isinstance(failure, Failure)
    assert failure.code == "PROGRAM_TYPE_INVALID"
    with pytest.raises(ProgramTypeError, match=r"Then type mismatch"):
        then_node(identity_node(LEFT), identity_node(RIGHT))

    unknown = try_decode_ast({"node_kind": "unknown"})
    assert isinstance(unknown, Failure)
    assert unknown.code == "UNKNOWN_NODE_KIND"
    with pytest.raises(ValueError, match=r"unknown node_kind"):
        decode_ast({"node_kind": "unknown"})

    successor_program = ProgramSpec(
        program_id="test.materialization",
        contract_version="1",
        project_key="test-project",
        project_registry_revision=1,
        project_scope_digest="0" * 64,
        semantic_identity="test.materialization",
        input_type=LEFT,
        output_type=LEFT,
        root=identity_node(LEFT),
        algebra_refs=(),
        transform_refs=(),
        observation_profile="test.materialization",
        metadata=(),
        program_digest="",
    ).with_digest()
    source_value_ref = ValueRef(
        value_id="source",
        project_key="test-project",
        object_type=LEFT,
        codec_id=LEFT.codec_id,
        content_digest="0" * 64,
        storage_kind="project_value_ref",
        store_id="test",
        store_version="1",
        storage_ref="source",
        byte_size=0,
        provenance_digest="0" * 64,
    )
    materialization = try_successor_materialization(
        materialization_id="",
        predecessor_run_id="run",
        predecessor_step_id="step",
        predecessor_plan_digest="0" * 64,
        source_value_ref=source_value_ref,
        materializer_id="materializer",
        materializer_version="1",
        authority_digest="0" * 64,
        idempotency_key="idempotency",
        successor_program=successor_program,
        successor_program_digest=successor_program.digest(),
        state="PREPARED",
        reason="",
    )
    assert isinstance(materialization, Failure)
    assert materialization.code == "PROGRAM_MATERIALIZATION_INVALID"


def test_transform_try_failures_and_legacy_lift() -> None:
    registry = TransformRegistry()
    callable_failure = registry.try_register_transform(
        name="bad",
        version="1",
        input_type=LEFT,
        output_type=RIGHT,
        func=object(),  # type: ignore[arg-type]
    )
    assert isinstance(callable_failure, Failure)
    assert callable_failure.code == "TRANSFORM_CALLABLE_INVALID"
    with pytest.raises(RegistryError, match=r"only plain functions"):
        registry.register_transform(
            name="bad-legacy",
            version="1",
            input_type=LEFT,
            output_type=RIGHT,
            func=object(),  # type: ignore[arg-type]
        )

    missing = registry.try_resolve_transform(TransformRef("missing", "1", "0" * 64))
    assert isinstance(missing, Failure)
    assert missing.code == "TRANSFORM_BINDING_MISSING"

    merge_ref = registry.register_merge(
        name="pair",
        version="1",
        left_type=LEFT,
        right_type=LEFT,
        output_type=RIGHT,
        func=_merge_value,
    )
    mismatch = try_merge_output_type(registry, merge_ref, LEFT, RIGHT)
    assert isinstance(mismatch, Failure)
    assert mismatch.code == "TRANSFORM_TYPE_INVALID"
    with pytest.raises(RegistryError, match=r"type mismatch"):
        merge_output_type(registry, merge_ref, LEFT, RIGHT)
