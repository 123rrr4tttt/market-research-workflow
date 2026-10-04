"""P4 C8.1 typed read handles and demand-read contract tests."""

from __future__ import annotations

import dataclasses
import re

import pytest

from app.successor_runtime.capabilities.c8_typed_knowledge import (
    AmbiguousProjection,
    C8ProjectionError,
    ReadHandleRegistry,
    UnavailableProjection,
    c8_canonical_digest,
    canonical_identity_for,
    demand_read,
    item_digest,
    validate_canonical_ref,
)

from .p4_c8_fixture import PROJECT_KEY, captured_item, new_registry


def test_demand_read_returns_only_requested_fields_with_bound_handle() -> None:
    item = captured_item()
    registry = new_registry()
    read = demand_read(
        (item,),
        item_key=item.key,
        fields=("canonical_statement", "evidence_refs"),
        project_key=PROJECT_KEY,
        registry=registry,
    )

    assert set(read.fields) == {"canonical_statement", "evidence_refs"}
    assert read.fields["canonical_statement"] == item.canonical_statement
    assert re.fullmatch(r"[0-9a-f]{64}", read.handle.handle_id)
    assert read.handle.canonical_identity == (f"knowledge:{PROJECT_KEY}:{item.key}")
    assert read.handle.canonical_digest == item.canonical_ref.content_digest
    assert read.handle.canonical_revision == item.canonical_ref.revision
    assert read.handle.canonical_incarnation == item.canonical_ref.incarnation
    assert read.provenance.projection_name == "demand_read.typed_knowledge"
    assert read.provenance.canonical_revision == item.canonical_ref.revision
    assert read.provenance.canonical_incarnation == item.canonical_ref.incarnation
    assert read.handle.handle_id in registry._handles


def test_demand_read_rejects_missing_and_ambiguous_facts() -> None:
    item = captured_item()
    with pytest.raises(UnavailableProjection, match="unavailable"):
        demand_read(
            (item,),
            item_key="ki:missing",
            fields=("canonical_statement",),
            project_key=PROJECT_KEY,
        )
    duplicate = captured_item(key=item.key)
    with pytest.raises(AmbiguousProjection, match="ambiguous"):
        demand_read(
            (item, duplicate),
            item_key=item.key,
            fields=("canonical_statement",),
            project_key=PROJECT_KEY,
        )


def test_demand_read_rejects_missing_requested_field() -> None:
    item = captured_item()
    with pytest.raises(UnavailableProjection, match="demanded field"):
        demand_read(
            (item,),
            item_key=item.key,
            fields=("canonical_statement", "not_a_field"),
            project_key=PROJECT_KEY,
        )


def test_digest_is_stable_and_binds_canonical_content() -> None:
    item = captured_item()
    first = c8_canonical_digest(
        {"key": item.key, "statement": item.canonical_statement}
    )
    second = c8_canonical_digest(
        {"key": item.key, "statement": item.canonical_statement}
    )
    changed = c8_canonical_digest(
        {"key": item.key, "statement": item.canonical_statement + " changed"}
    )
    assert first == second
    assert first != changed

    registry = ReadHandleRegistry()
    read = demand_read(
        (item,),
        item_key=item.key,
        fields=("canonical_statement",),
        project_key=PROJECT_KEY,
        registry=registry,
    )
    mutated = captured_item(statement="mutated statement")
    resolution = registry.resolve(
        read.handle,
        items=(mutated,),
    )
    assert resolution.available is False
    assert resolution.reason == (
        "canonical content, revision or incarnation changed since handle issuance"
    )


def test_derived_canonical_identity_and_body_digest_are_fail_closed() -> None:
    item = captured_item()
    assert canonical_identity_for(item) == f"knowledge:{PROJECT_KEY}:{item.key}"
    assert item.canonical_ref.content_digest == item_digest(item)
    assert validate_canonical_ref(item, project_key=PROJECT_KEY) is item.canonical_ref

    with pytest.raises(C8ProjectionError, match="project scope"):
        validate_canonical_ref(item, project_key="other-project")

    wrong_body = captured_item(statement="different statement")
    wrong_body = dataclasses.replace(
        wrong_body,
        canonical_ref=dataclasses.replace(
            wrong_body.canonical_ref,
            content_digest=item_digest(item),
        ),
    )
    with pytest.raises(C8ProjectionError, match="body digest"):
        validate_canonical_ref(wrong_body)


def test_aba_content_return_is_detected_by_revision_bump() -> None:
    item = captured_item()
    registry = ReadHandleRegistry()
    read = demand_read(
        (item,),
        item_key=item.key,
        fields=("canonical_statement",),
        project_key=PROJECT_KEY,
        registry=registry,
    )
    original_digest = item_digest(item)
    changed = captured_item(statement="mutated statement")
    changed = dataclasses.replace(
        changed,
        canonical_ref=dataclasses.replace(
            changed.canonical_ref,
            revision=2,
            content_digest=item_digest(changed),
        ),
    )
    resolution_after_change = registry.resolve(read.handle, items=(changed,))
    assert resolution_after_change.available is False

    reverted_body = captured_item(statement=item.canonical_statement)
    reverted_body = dataclasses.replace(
        reverted_body,
        canonical_ref=dataclasses.replace(
            reverted_body.canonical_ref,
            revision=2,
            content_digest=original_digest,
        ),
    )
    resolution_after_aba = registry.resolve(read.handle, items=(reverted_body,))
    assert resolution_after_aba.available is False
    assert "revision or incarnation" in resolution_after_aba.reason
