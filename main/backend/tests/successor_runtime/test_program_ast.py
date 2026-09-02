from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.successor_runtime.capabilities import (
    build_first_specimen_bundle,
    build_first_specimen_catalog,
)
from app.successor_runtime.language.algebra import (
    ObjectType,
    OperationContractCatalogSnapshot,
    OperationContractRef,
    OperationSpec,
    ValueRef,
    build_catalog_snapshot,
    canonical_digest,
    freeze_json_object,
)
from app.successor_runtime.language.catalog import OperationContractRegistry
from app.successor_runtime.language.combinators import (
    Registries,
    build_first_specimen_program,
    default_registries,
    materialize_first_specimen_gap_successor,
)
from app.successor_runtime.language.normalize import (
    normalize_node,
    normalize_program,
    normalized_equivalent,
)
from app.successor_runtime.language.program import (
    Decide,
    Identity,
    MapOutput,
    ProgramSpec,
    ProgramTypeError,
    Pure,
    Then,
    ZipOrdered,
    atom_node,
    decide_node,
    decode_ast,
    decode_program_spec,
    encode_program_spec,
    identity_node,
    map_output_node,
    pure_node,
    then_node,
    zip_ordered_node,
)
from app.successor_runtime.language.transforms import (
    DiscriminatorRef,
    MergeRef,
    TransformRef,
    TransformRegistry,
)
from app.successor_runtime.language.validate import validate_program
from app.successor_runtime.research.object_types import GAP_TYPE
from app.successor_runtime.research.claims import Gap
from app.successor_runtime.research.sources import SourceRef


def _type(
    type_id: str,
    schema_version: str = "1",
    codec_id: str = "mrw.first-specimen.codec.v1",
    canonical_codec_version: str = "1",
) -> ObjectType:
    return ObjectType(
        type_id=type_id,
        schema_version=schema_version,
        codec_id=codec_id,
        canonical_codec_version=canonical_codec_version,
    )


INTENT = _type("ResearchIntent.v1")
MATERIAL_REF = _type("MaterialRef.v1")
EVIDENCE_BUNDLE = _type("evidence.bundle.v1")
OUTCOME = _type("claim_or_gap.outcome.v1")
PROGRAM_OUTPUT = _type("program.output.v1")
SOURCE_REF = _type("SourceRef.v1")


def _document_source(document_id: int) -> SourceRef:
    return SourceRef(
        source_ref_id=f"source:document:{document_id}",
        owner_id="legacy_document_store",
        locator=f"document://p0/{document_id}",
        source_class="existing_project_document",
        observed_at=datetime(2026, 8, 30, tzinfo=timezone.utc),
        access_profile_ref="DocumentCanonicalReadPort",
    )


DOCUMENT_SOURCES = (_document_source(101), _document_source(102))


def specimen_catalog() -> OperationContractCatalogSnapshot:
    bundle = build_first_specimen_bundle()
    return build_first_specimen_catalog(bundle.operations)


def specimen_registry() -> OperationContractRegistry:
    bundle = build_first_specimen_bundle()
    return OperationContractRegistry(
        catalog=build_first_specimen_catalog(bundle.operations),
        contracts=bundle.operations,
    )


def _value_ref(value_id: str, object_type: ObjectType) -> ValueRef:
    return ValueRef(
        value_id=value_id,
        project_key="p0",
        object_type=object_type,
        codec_id=object_type.codec_id,
        content_digest="0" * 64,
        storage_kind="project_value_ref",
        store_id="successor_values",
        store_version="1",
        storage_ref=value_id,
        byte_size=0,
        provenance_digest="0" * 64,
    )


def _op(
    operation_id: str,
    kind: str,
    input_type: ObjectType,
    output_type: ObjectType,
    catalog: OperationContractCatalogSnapshot,
) -> OperationSpec:
    entry = catalog.find(kind)
    assert entry is not None
    return OperationSpec(
        operation_id=operation_id,
        contract_ref=OperationContractRef(
            kind=kind,
            contract_version=entry[1],
            contract_digest=entry[2],
        ),
        input_refs=(_value_ref(operation_id + ".in", input_type),),
        payload_ref=_value_ref(operation_id + ".payload", input_type),
        allowed_overrides=freeze_json_object({}),
    )


def _specimen_program() -> ProgramSpec:
    catalog = specimen_catalog()
    registries = default_registries()
    return build_first_specimen_program(
        catalog=catalog,
        program_id="first-specimen.p0a",
        project_key="p0",
        project_scope_digest="0" * 64,
        observation_profile="mrw.successor.first-specimen.observation.v1",
        registries=registries,
        source_refs=DOCUMENT_SOURCES,
    )


def _specimen_program_with_registries() -> "tuple[ProgramSpec, Registries]":
    registries = default_registries()
    spec = build_first_specimen_program(
        catalog=specimen_catalog(),
        program_id="first-specimen.p0a",
        project_key="p0",
        project_scope_digest="0" * 64,
        observation_profile="mrw.successor.first-specimen.observation.v1",
        registries=registries,
        source_refs=DOCUMENT_SOURCES,
    )
    return spec, registries


def test_full_ast_round_trip_keeps_complete_child_programs() -> None:
    spec = _specimen_program()
    encoded = encode_program_spec(spec)
    decoded = decode_program_spec(encoded)
    assert decoded.program_digest == spec.program_digest
    assert decode_ast(encoded["program"]["root"]).ast_digest() == spec.root.ast_digest()
    # Complete child programs survive serialization: no digest-only placeholder.
    assert isinstance(decoded.root, Then)
    kinds = _operation_kinds(decoded.root)
    assert kinds == (
        "material.capture_document_snapshot.v1",
        "material.read_canonical_ref.v1",
        "evidence.qualify.v1",
        "material.capture_document_snapshot.v1",
        "material.read_canonical_ref.v1",
        "evidence.qualify.v1",
        "claim.form_or_open_gap.v1",
        "artifact.compose_markdown.v1",
        "delivery.internal_export.v1",
    )


def test_persisted_canonical_json_round_trip_keeps_decision_branches() -> None:
    spec = _specimen_program()
    persisted = json.loads(spec.canonical_json())
    decoded = decode_program_spec(
        {"program": persisted, "program_digest": spec.program_digest}
    )

    assert decoded.program_digest == spec.program_digest
    assert _operation_kinds(decoded.root) == _operation_kinds(spec.root)


def test_node_kind_fixed_discriminators() -> None:
    spec = _specimen_program()
    encoded = encode_program_spec(spec)
    assert encoded["program"]["root"]["node_kind"] == "then"
    assert "zip_ordered" in _node_kinds(spec.root)
    assert "decide" in _node_kinds(spec.root)
    assert (
        _operation_kinds(spec.root).count("material.capture_document_snapshot.v1") == 2
    )
    assert _operation_kinds(spec.root).count("material.read_canonical_ref.v1") == 2
    assert _operation_kinds(spec.root).count("evidence.qualify.v1") == 2


def test_first_specimen_binds_real_document_sources_and_literal_digests() -> None:
    spec = _specimen_program()
    literals = [_thaw(node.literal_value) for node in _pure_nodes(spec.root)]
    addressed = [value for value in literals if "content_digest" in value]
    assert addressed
    for literal in addressed:
        digest = literal.pop("content_digest")
        assert digest == canonical_digest(literal)
        assert digest != "0" * 64

    sources = [value for value in literals if "source_ref_id" in value]
    assert [source["locator"] for source in sources] == [
        "document://p0/101",
        "document://p0/102",
    ]
    assert all("first-specimen/a" not in source["locator"] for source in sources)


def test_normalization_identity_and_associativity_laws() -> None:
    node = identity_node(INTENT)
    atom = atom_node(
        _op(
            "read.a",
            "material.read_canonical_ref.v1",
            INTENT,
            MATERIAL_REF,
            specimen_catalog(),
        ),
        input_type=INTENT,
        output_type=MATERIAL_REF,
    )
    compose = pure_node(
        input_type=INTENT,
        output_type=INTENT,
        literal_value={"step": "compose"},
        literal_codec="mrw.first-specimen.literal.v1",
    )
    left_id = then_node(identity_node(INTENT), atom)
    right_id = then_node(atom, identity_node(MATERIAL_REF))
    assert normalized_equivalent(left_id, atom)
    assert normalized_equivalent(right_id, atom)

    left_assoc = then_node(then_node(compose, compose), compose)
    right_assoc = then_node(compose, then_node(compose, compose))
    assert normalized_equivalent(left_assoc, right_assoc)
    assert (
        normalize_node(left_assoc).ast_digest()
        == normalize_node(normalize_node(left_assoc)).ast_digest()
    )


def test_composition_is_ordered_not_commutative() -> None:
    first = pure_node(
        input_type=INTENT,
        output_type=INTENT,
        literal_value={"step": "first"},
        literal_codec="mrw.first-specimen.literal.v1",
    )
    second = pure_node(
        input_type=INTENT,
        output_type=INTENT,
        literal_value={"step": "second"},
        literal_codec="mrw.first-specimen.literal.v1",
    )
    assert (
        then_node(first, second).ast_digest() != then_node(second, first).ast_digest()
    )
    assert isinstance(first, Pure)


def test_type_mismatch_is_rejected_at_composition() -> None:
    catalog = specimen_catalog()
    atom = atom_node(
        _op("read.a", "material.read_canonical_ref.v1", INTENT, MATERIAL_REF, catalog),
        input_type=INTENT,
        output_type=MATERIAL_REF,
    )
    with pytest.raises(ProgramTypeError):
        then_node(atom, identity_node(INTENT))


def test_validation_catalog_membership_and_registry_refs() -> None:
    spec, registries = _specimen_program_with_registries()
    catalog = specimen_catalog()
    valid = validate_program(
        spec,
        catalog,
        transform_registry=registries.transforms,
        merge_registry=registries.merges,
        discriminator_registry=registries.discriminators,
        operation_contract_resolver=specimen_registry(),
    )
    assert valid.valid, valid.failures

    stale_catalog = build_catalog_snapshot(
        catalog_id="stale",
        catalog_version="1",
        contracts=(build_first_specimen_bundle().operations[1],),
    )
    invalid = validate_program(spec, stale_catalog)
    assert not invalid.valid
    assert "UNKNOWN_OPERATION_CONTRACT" in invalid.failure_codes()


def test_validation_rejects_bad_transform_ref() -> None:
    spec = _specimen_program()
    bad_registry = TransformRegistry()
    result = validate_program(
        spec,
        specimen_catalog(),
        transform_registry=bad_registry,
        merge_registry=bad_registry,
        discriminator_registry=bad_registry,
        operation_contract_resolver=specimen_registry(),
    )
    assert not result.valid
    assert "MISSING_MERGE" in result.failure_codes()


def test_registry_rejects_lambda_and_closure() -> None:
    registry = TransformRegistry()
    with pytest.raises(Exception):
        registry.register_transform(
            name="bad",
            version="1",
            input_type=INTENT,
            output_type=MATERIAL_REF,
            func=lambda value: value,
        )
    captured = MATERIAL_REF

    def closure(value: object) -> object:
        return captured

    with pytest.raises(Exception):
        registry.register_transform(
            name="bad-closure",
            version="1",
            input_type=INTENT,
            output_type=MATERIAL_REF,
            func=closure,
        )


def test_decide_keeps_branch_order_and_guards() -> None:
    atom = atom_node(
        _op(
            "read.a",
            "material.read_canonical_ref.v1",
            INTENT,
            MATERIAL_REF,
            specimen_catalog(),
        ),
        input_type=INTENT,
        output_type=MATERIAL_REF,
    )
    discriminator = DiscriminatorRef(
        name="d",
        version="1",
        digest="0" * 64,
        transform_kind="discriminator",
    )
    from app.successor_runtime.language.program import DecisionBranch

    decide = decide_node(
        discriminator,
        (
            DecisionBranch(
                branch_id="claim",
                guard="outcome.kind == 'claim'",
                program=atom,
            ),
            DecisionBranch(
                branch_id="gap",
                guard="outcome.kind == 'gap'",
                program=atom,
            ),
        ),
    )
    assert isinstance(decide, Decide)
    assert [branch.branch_id for branch in decide.branches] == ["claim", "gap"]


def test_gap_successor_materialization_is_post_run_and_deterministic() -> None:
    predecessor = _specimen_program()
    source = _value_ref("gap:value:001", GAP_TYPE)
    inputs = {
        "predecessor_program": predecessor,
        "predecessor_run_id": "run:predecessor:001",
        "predecessor_step_id": "step:claim-or-gap:001",
        "predecessor_plan_digest": "1" * 64,
        "source_value_ref": source,
        "gap": Gap(
            gap_id="gap:001",
            inquiry_ref="inquiry:predecessor:001",
            requirement="two-source support",
            reason="evidence missing",
            closure_condition="two exact qualifications",
            reopen_policy={"mode": "open_gap"},
            missing_evidence_or_decision="second source qualification",
        ),
        "successor_intent_ref": "intent:predecessor:001",
        "authority_digest": "2" * 64,
    }
    first = materialize_first_specimen_gap_successor(**inputs)
    repeated = materialize_first_specimen_gap_successor(**inputs)

    assert repeated == first
    assert first.state == "MATERIALIZED"
    assert first.successor_program.program_id != predecessor.program_id
    assert first.successor_program_digest != predecessor.program_digest
    assert first.successor_program.input_type == GAP_TYPE
    assert first.successor_program.output_type.type_id == "ResearchPlan.v1"
    assert first.successor_program_digest == first.successor_program.program_digest
    assert (
        decode_program_spec(encode_program_spec(first.successor_program)).program_digest
        == first.successor_program_digest
    )
    metadata = dict(first.successor_program.metadata)
    assert metadata["predecessor_program_id"] == predecessor.program_id
    assert metadata["predecessor_program_digest"] == predecessor.program_digest
    assert metadata["materialization_id"] == first.materialization_id
    root = first.successor_program.root
    assert isinstance(root, Then)
    assert isinstance(root.first, Pure)
    assert isinstance(root.second, Pure)
    inquiry_literal = dict(root.first.literal_value)
    plan_literal = dict(root.second.literal_value)
    assert inquiry_literal["intent_ref"] == "intent:predecessor:001"
    assert "source_gap_ref" not in inquiry_literal
    assert "source_gap_ref" not in plan_literal
    assert dict(plan_literal["replan_policy"])["source_gap_ref"] == "gap:001"

    changed_authority = materialize_first_specimen_gap_successor(
        **{**inputs, "authority_digest": "3" * 64}
    )
    changed_source = materialize_first_specimen_gap_successor(
        **{
            **inputs,
            "source_value_ref": ValueRef(
                value_id=source.value_id,
                project_key=source.project_key,
                object_type=source.object_type,
                codec_id=source.codec_id,
                content_digest="4" * 64,
                storage_kind=source.storage_kind,
                store_id=source.store_id,
                store_version=source.store_version,
                storage_ref=source.storage_ref,
                byte_size=source.byte_size,
                provenance_digest=source.provenance_digest,
            ),
        }
    )
    assert changed_authority.materialization_id != first.materialization_id
    assert changed_authority.idempotency_key != first.idempotency_key
    assert changed_source.materialization_id != first.materialization_id
    assert changed_source.idempotency_key != first.idempotency_key


def test_current_gap_branch_contains_no_hidden_successor_round_trip() -> None:
    spec = _specimen_program()
    assert all(
        ref.name != "mrw.first_specimen.MaterializeSuccessor"
        and ref.name != "mrw.first_specimen.successor_inquiry_ref_to_gap"
        for ref in spec.transform_refs
    )
    gap_refs = [ref for ref in spec.transform_refs if ref.name.endswith(".gap_branch")]
    assert len(gap_refs) == 1
    assert "InquiryRef.v1" not in str(encode_program_spec(spec)["program"]["root"])


def test_normalize_program_keeps_spec_digest_contract() -> None:
    spec = _specimen_program()
    normalized = normalize_program(spec)
    assert normalized.program_digest == spec.program_digest
    assert normalized.root.ast_digest() == normalize_node(normalized.root).ast_digest()


def _operation_kinds(node) -> tuple[str, ...]:
    from app.successor_runtime.language.program import (
        Atom,
        Decide,
        MapOutput,
        Then,
        ZipOrdered,
    )

    if isinstance(node, Atom):
        return (node.operation.contract_ref.kind,)
    if isinstance(node, Then):
        return _operation_kinds(node.first) + _operation_kinds(node.second)
    if isinstance(node, ZipOrdered):
        return _operation_kinds(node.left) + _operation_kinds(node.right)
    if isinstance(node, MapOutput):
        return _operation_kinds(node.source)
    if isinstance(node, Decide):
        return tuple(
            kind
            for branch in node.branches
            for kind in _operation_kinds(branch.program)
        )
    return ()


def _node_kinds(node) -> tuple[str, ...]:
    from app.successor_runtime.language.program import (
        Decide,
        MapOutput,
        Then,
        ZipOrdered,
    )

    children = ()
    if isinstance(node, Then):
        children = _node_kinds(node.first) + _node_kinds(node.second)
    elif isinstance(node, ZipOrdered):
        children = _node_kinds(node.left) + _node_kinds(node.right)
    elif isinstance(node, MapOutput):
        children = _node_kinds(node.source)
    elif isinstance(node, Decide):
        children = tuple(
            kind for branch in node.branches for kind in _node_kinds(branch.program)
        )
    return (node.node_kind,) + children


def _pure_nodes(node) -> tuple[Pure, ...]:
    if isinstance(node, Pure):
        return (node,)
    if isinstance(node, Then):
        return _pure_nodes(node.first) + _pure_nodes(node.second)
    if isinstance(node, ZipOrdered):
        return _pure_nodes(node.left) + _pure_nodes(node.right)
    if isinstance(node, MapOutput):
        return _pure_nodes(node.source)
    if isinstance(node, Decide):
        return tuple(
            pure for branch in node.branches for pure in _pure_nodes(branch.program)
        )
    return ()


def _thaw(value):
    if isinstance(value, tuple):
        if value and all(
            isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], str)
            for item in value
        ):
            return {key: _thaw(item) for key, item in value}
        return [_thaw(item) for item in value]
    return value
