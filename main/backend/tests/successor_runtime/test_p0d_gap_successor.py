from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from app.successor_runtime.capabilities import (
    build_first_specimen_bundle,
    build_first_specimen_catalog,
)
from app.successor_runtime.capabilities.catalog import build_first_specimen_registry
from app.successor_runtime.capabilities.first_specimen_successor import (
    GapSuccessorRejected,
    build_gap_successor_closure,
)
from app.successor_runtime.language.algebra import ValueRef
from app.successor_runtime.language.combinators import (
    build_first_specimen_program,
    default_registries,
)
from app.successor_runtime.language.compile import compile_program
from app.successor_runtime.language.program import Pure, Then
from app.successor_runtime.research.claims import Gap
from app.successor_runtime.research.codec import canonical_bytes
from app.successor_runtime.research.identities import ResearchObjectRef
from app.successor_runtime.research.object_types import (
    GAP_TYPE,
    RESEARCH_INTENT_TYPE,
)
from app.successor_runtime.research.sources import SourceRef
from app.successor_runtime.runtime.assignments import MaterializerBinding

pytestmark = pytest.mark.unit


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _source(label: str) -> SourceRef:
    return SourceRef(
        source_ref_id=f"source:{label}",
        owner_id="legacy_document_store",
        locator=f"document://p0d/{label}",
        source_class="existing_project_document",
        observed_at=datetime(2030, 8, 31, tzinfo=UTC),
        access_profile_ref="DocumentCanonicalReadPort",
    )


def _fixture() -> dict[str, object]:
    bundle = build_first_specimen_bundle()
    catalog = build_first_specimen_catalog(bundle.operations)
    registry = build_first_specimen_registry(bundle.operations)
    predecessor = build_first_specimen_program(
        catalog=catalog,
        program_id="program:p0d:predecessor",
        project_key="p0d",
        project_scope_digest=_digest("scope"),
        registries=default_registries(),
        source_refs=(_source("a"), _source("b")),
    )
    predecessor_plan = compile_program(
        predecessor,
        catalog,
        operation_contracts=registry,
    )
    gap = Gap(
        gap_id="gap:p0d:001",
        inquiry_ref="inquiry:p0d:predecessor",
        requirement="two-source support",
        reason="the second qualification is insufficient",
        closure_condition="two exact supporting qualifications",
        reopen_policy={"mode": "open_gap"},
        missing_evidence_or_decision="second supporting qualification",
    )
    assert gap.content_digest is not None
    provenance = _digest("gap-provenance")
    gap_value = ValueRef(
        value_id=gap.gap_id,
        project_key="p0d",
        object_type=GAP_TYPE,
        codec_id=GAP_TYPE.codec_id,
        content_digest=gap.content_digest,
        storage_kind="project_value_ref",
        store_id="successor_values",
        store_version="1",
        storage_ref=f"project-value:{gap.gap_id}",
        byte_size=len(canonical_bytes(gap)),
        provenance_digest=provenance,
    )
    gap_ref = ResearchObjectRef(
        object_id=gap.gap_id,
        object_type=GAP_TYPE,
        project_key="p0d",
        incarnation="gap-inc:001",
        owner_binding_ref="ResearchLedger",
        content_ref=gap_value.storage_ref,
        content_digest=gap.content_digest,
        provenance_closure_digest=provenance,
        lifecycle_state="ADMITTED",
    )
    intent_ref = ResearchObjectRef(
        object_id="intent:p0d:predecessor",
        object_type=RESEARCH_INTENT_TYPE,
        project_key="p0d",
        incarnation="intent-inc:001",
        owner_binding_ref="ResearchLedger",
        content_ref="project-value:intent:p0d:predecessor",
        content_digest=_digest("intent-content"),
        provenance_closure_digest=_digest("intent-provenance"),
        lifecycle_state="ADMITTED",
    )
    binding = MaterializerBinding.from_content(
        materializer_id="mrw.first_specimen.gap-successor",
        materializer_version="1.0.0",
        predecessor_plan_digest=predecessor_plan.plan_digest,
        source_value_digest=gap.content_digest,
        target_domain_contract_snapshot_digest=_digest("domain-contract"),
    )
    return {
        "predecessor_program": predecessor,
        "predecessor_plan": predecessor_plan,
        "predecessor_run_id": "run:p0d:predecessor",
        "predecessor_step_id": "step:p0d:gap",
        "gap": gap,
        "gap_ref": gap_ref,
        "source_value_ref": gap_value,
        "successor_intent_ref": intent_ref,
        "predecessor_plan_digest": binding.predecessor_plan_digest,
        "source_value_digest": binding.source_value_digest,
        "materializer_binding_digest": binding.binding_digest,
        "materializer_id": binding.materializer_id,
        "materializer_version": binding.materializer_version,
        "authority_digest": _digest("authority"),
        "catalog": catalog,
        "operation_contracts": registry,
    }


def test_gap_materializes_schema_valid_successor_and_opens_relation() -> None:
    inputs = _fixture()
    first = build_gap_successor_closure(**inputs)
    repeated = build_gap_successor_closure(**inputs)

    assert repeated == first
    assert first.inquiry.intent_ref == "intent:p0d:predecessor"
    assert first.research_plan.inquiry_ref == first.inquiry.inquiry_id
    assert first.opens_relation.source_ref == inputs["gap_ref"]
    assert first.opens_relation.target_ref == first.inquiry_ref
    assert first.opens_relation.relation_type == "opens"
    assert (
        first.successor_plan.program_digest
        == first.materialization.successor_program_digest
    )
    assert first.successor_run_id.startswith("run:successor:sha256:")
    root = first.materialization.successor_program.root
    assert isinstance(root, Then)
    assert isinstance(root.first, Pure)
    assert isinstance(root.second, Pure)
    assert "source_gap_ref" not in dict(root.first.literal_value)
    assert "source_gap_ref" not in dict(root.second.literal_value)
    assert dict(dict(root.second.literal_value)["replan_policy"])["source_gap_ref"] == (
        inputs["gap"].gap_id
    )


def test_gap_successor_identity_changes_for_authority_or_source_digest() -> None:
    inputs = _fixture()
    first = build_gap_successor_closure(**inputs)
    changed_authority = build_gap_successor_closure(
        **{**inputs, "authority_digest": _digest("authority-v2")}
    )
    source = inputs["source_value_ref"]
    gap_ref = inputs["gap_ref"]
    assert isinstance(source, ValueRef)
    assert isinstance(gap_ref, ResearchObjectRef)
    changed_digest = _digest("changed-gap-content")
    changed_source = replace(source, content_digest=changed_digest)
    changed_gap_ref = replace(gap_ref, content_digest=changed_digest)
    changed_binding = MaterializerBinding.from_content(
        materializer_id=inputs["materializer_id"],
        materializer_version=inputs["materializer_version"],
        predecessor_plan_digest=inputs["predecessor_plan_digest"],
        source_value_digest=changed_digest,
        target_domain_contract_snapshot_digest=_digest("domain-contract"),
    )
    with pytest.raises(GapSuccessorRejected, match="Gap/value"):
        build_gap_successor_closure(
            **{
                **inputs,
                "source_value_ref": changed_source,
                "gap_ref": changed_gap_ref,
                "source_value_digest": changed_binding.source_value_digest,
                "materializer_binding_digest": changed_binding.binding_digest,
            }
        )
    assert changed_authority.request_digest != first.request_digest
    assert changed_authority.successor_run_id != first.successor_run_id


@pytest.mark.parametrize(
    "field,value,match",
    (
        ("authority_digest", "0" * 64, "authority"),
        ("predecessor_run_id", "", "run/step"),
    ),
)
def test_gap_successor_fails_closed_on_invalid_closure(
    field: str,
    value: str,
    match: str,
) -> None:
    inputs = _fixture()
    with pytest.raises(GapSuccessorRejected, match=match):
        build_gap_successor_closure(**{**inputs, field: value})
