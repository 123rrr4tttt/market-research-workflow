"""C8.4 contribution catalog runtime and projection integration tests."""

from __future__ import annotations

import dataclasses
import importlib.util
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine

from app.successor_runtime.assembly.base import (
    KnowledgeAssemblyOptions,
    ProjectorSourceKey,
    local_assembly_scope_digest,
)
from app.successor_runtime.assembly.knowledge_assembly import build_knowledge_assembly
from app.successor_runtime.capabilities.knowledge_graph_projection_contribution import (
    KNOWLEDGE_GRAPH_PROJECTION_FAILURE_CODES,
    KNOWLEDGE_GRAPH_PROJECTION_DEFINITION,
    KNOWLEDGE_GRAPH_PROJECTION_NATIVE_RULE,
    KnowledgeGraphProjectionAssemblyContext,
    KnowledgeGraphProjectionAuthorSource,
    KnowledgeGraphProjectionRuntimeBinding,
    assemble_knowledge_graph_projection_definition,
    define_knowledge_graph_projection_cell,
    lower_knowledge_graph_projection_author_source,
    project_knowledge_graph_projection_definition,
    validate_knowledge_graph_projection_binding,
)
from app.successor_runtime.capabilities.knowledge_program import (
    KnowledgeGraphProjectInput,
    build_knowledge_bundle,
    build_knowledge_catalog,
    build_knowledge_program,
    GraphProjectionNativeContribution,
    build_knowledge_registry,
    compose_default_knowledge_graph_projection_contributions,
    validate_knowledge_graph_projection_contributions,
)
from app.successor_runtime.capabilities.checksum import content_digest
from app.successor_runtime.specification import c8_p4
from app.successor_runtime.research.object_types import ObjectType
from functorial_kit.contribution_compiler import compile_native_contribution
from functorial_kit.contributions import compose_contributions
from functorial_kit.core.failure import Failure
from functorial_kit.law_witness import LawWitness, law_witness_reference
from functorial_kit.native_contribution import (
    BindingRejected,
    NativeContributionSpec,
    define_native_contribution,
)
from mrw_functorial_kit.contributions.knowledge_graph_projection import knowledge_graph_projection_law_witness_references, knowledge_graph_projection_law_witnesses, knowledge_graph_projection_native_contribution, contribution_catalog
from mrw_functorial_kit.core.knowledge_semantics import knowledge_graph_failures

EXTRA_KIND = "knowledge.graph.project.test.v2"
EXTRA_INPUT = ObjectType("KnowledgeGraphProjectionTestInput.v2")
EXTRA_RESULT = ObjectType("KnowledgeGraphProjectionTestResult.v2")
EXTRA_OWNER = "knowledge.graph-projection.test.v2"
GOLDEN_PATH = (
    Path(__file__).resolve().parents[1] / "fixtures/successor_runtime/c8_graph_projection_pre_contribution_golden.json"
)


@dataclass(frozen=True, slots=True)
class _ExtraInput:
    project_key: str
    graph_id: str
    node_keys: tuple[str, ...]
    node_types: tuple[str, ...]
    payload_digest: str = ""

    def __post_init__(self) -> None:
        expected = content_digest(
            {key: value for key, value in dataclasses.asdict(self).items() if key != "payload_digest"}
        )
        if self.payload_digest == "":
            object.__setattr__(self, "payload_digest", expected)


def _not_failure(value: object) -> None:
    assert not isinstance(value, Failure)


def _golden() -> dict[str, Any]:
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def _json_observation(value: object) -> object:
    return json.loads(json.dumps(value, ensure_ascii=False))


def _native(definition: Any, *, calls: list[int] | None = None) -> Any:
    def assemble(
        native_definition: Any,
        context: KnowledgeGraphProjectionAssemblyContext,
    ) -> KnowledgeGraphProjectionRuntimeBinding:
        if calls is not None:
            calls.append(1)
        return assemble_knowledge_graph_projection_definition(native_definition, context)

    native = define_native_contribution(
        NativeContributionSpec(
            definition=definition,
            project=project_knowledge_graph_projection_definition,
            assemble=assemble,
            validate_binding=validate_knowledge_graph_projection_binding,
        )
    )
    _not_failure(native)
    return native


def _extra_source() -> KnowledgeGraphProjectionAuthorSource:
    return KnowledgeGraphProjectionAuthorSource(
        cell_id="knowledge.graph-projection.test.v2",
        owner=EXTRA_OWNER,
        operation_id="knowledge.graph.project.test",
        kind=EXTRA_KIND,
        payload_codec_id="mrw.knowledge.graph-project.test.codec.v2",
        input_type=EXTRA_INPUT,
        output_type=EXTRA_RESULT,
        payload_type=_ExtraInput,
        projector_wiring=None,
        rollback_refs=("test:graph-projection-extension",),
    )


def _compile_extra_native(source: KnowledgeGraphProjectionAuthorSource) -> GraphProjectionNativeContribution:
    native = compile_native_contribution(source, KNOWLEDGE_GRAPH_PROJECTION_NATIVE_RULE)
    assert not isinstance(native, Failure)
    return native


def test_default_runtime_uses_single_catalog_contribution() -> None:
    assert KNOWLEDGE_GRAPH_PROJECTION_FAILURE_CODES is knowledge_graph_failures.codes
    assert KNOWLEDGE_GRAPH_PROJECTION_DEFINITION is knowledge_graph_projection_native_contribution.definition
    natives = compose_default_knowledge_graph_projection_contributions()
    assert [native.projection.id for native in natives] == ["mrw.knowledge.graph-projection.native.v2"]
    assert natives[0] is knowledge_graph_projection_native_contribution
    assert contribution_catalog.contributions == tuple(native.projection for native in natives)
    assert all(contribution.factory is None for contribution in contribution_catalog.contributions)
    bundle = build_knowledge_bundle()
    registry = build_knowledge_registry(bundle)
    graph_ref = registry.catalog.lookup("knowledge.graph.project.v2")
    assert graph_ref is not None
    contract = registry.resolve(graph_ref)
    assert contract is not None
    assert contract.owner_capability_id == "knowledge.graph-projection.v2"

    assembly = build_knowledge_assembly(
        engine=create_engine("sqlite:///:memory:"),  # type: ignore[arg-type]
        project_scope_digest=local_assembly_scope_digest(),
    )
    assert assembly.coverage()["knowledge.graph-projection.v2"] == "PROJECTOR_WIRING_DECLARED"


def test_legacy_cell_constructor_lowers_the_same_author_source() -> None:
    source = _extra_source()
    legacy = define_knowledge_graph_projection_cell(
        cell_id=source.cell_id,
        contribution_id=source.contribution_id,
        owner=source.owner,
        operation_id=source.operation_id,
        kind=source.kind,
        payload_codec_id=source.payload_codec_id,
        input_type=source.input_type,
        output_type=source.output_type,
        payload_type=source.payload_type,
        projector_wiring=source.projector_wiring,
        rollback_refs=source.rollback_refs,
        failure_codes=source.failure_codes,
        return_contract_ref=source.return_contract_ref,
    )
    lowered = lower_knowledge_graph_projection_author_source(source)
    assert legacy == dataclasses.replace(lowered, payload_codec=legacy.payload_codec)
    assert legacy.cell_id == "knowledge.graph-projection.test.v2"
    assert legacy.payload_codec.codec_id == source.payload_codec_id


def test_catalog_composition_is_pure_and_extra_entry_reaches_native_registries() -> None:
    calls: list[int] = []
    observed = _native(KNOWLEDGE_GRAPH_PROJECTION_DEFINITION, calls=calls)
    extra_source = _extra_source()
    extra = _compile_extra_native(extra_source)
    relowered = lower_knowledge_graph_projection_author_source(extra_source)
    # PayloadCodec dataclasses contain generated encode/decode closures; structural identity
    # is exercised through the bundle/Program checks below rather than function object equality.
    assert extra.definition == dataclasses.replace(
        relowered,
        payload_codec=extra.definition.payload_codec,
    )
    assert extra.projection.id == "mrw.knowledge.graph-projection.test.native.v2"
    natives = (observed, extra)
    composition = compose_contributions(tuple(native.projection for native in natives))
    _not_failure(composition)
    assert calls == []

    bundle = build_knowledge_bundle(graph_projection_composition=natives)
    registry = build_knowledge_registry(bundle)
    extra_ref = registry.catalog.lookup(EXTRA_KIND)
    assert extra_ref is not None
    assert registry.resolve(extra_ref) is not None

    assembly = build_knowledge_assembly(
        engine=create_engine("sqlite:///:memory:"),  # type: ignore[arg-type]
        project_scope_digest=local_assembly_scope_digest(),
        options=KnowledgeAssemblyOptions(graph_projection_composition=natives),
    )
    assert assembly.cell("knowledge.graph-projection.test.v2").operation_contract_refs == (EXTRA_KIND,)
    assert assembly.cell("knowledge.graph-projection.test.v2").status == "PROJECTOR_WIRING_DECLARED"
    object_kinds = {obj.id: obj.kind for obj in composition.objects}
    assert object_kinds[EXTRA_INPUT.type_id] == "ObjectType"
    assert object_kinds["knowledge.graph.project.test"] == "Capability"
    assert calls

    payload = _ExtraInput(
        project_key="project-a",
        graph_id="graph-extra",
        node_keys=("ki:a",),
        node_types=("Topic",),
    )
    program = build_knowledge_program(
        cell_id="knowledge.graph-projection.test.v2",
        payload=payload,
        catalog=build_knowledge_catalog(bundle),
        program_id="program:c8-4-test",
        project_key="project-a",
        project_registry_revision=1,
        project_scope_digest="0" * 64,
        graph_projection_composition=natives,
    )
    assert program.root.operation.operation_id == "knowledge.graph.project.test"
    assert dict(program.metadata)["canonical_owner"] == EXTRA_OWNER
    assert [entry["operation_kind"] for entry in c8_p4._operation_bindings(natives)["c8_4"]] == [
        "knowledge.graph.project.v2",
        EXTRA_KIND,
    ]


def test_definition_consistency_and_duplicate_cell_ids_fail_closed() -> None:
    bad_definition = dataclasses.replace(
        KNOWLEDGE_GRAPH_PROJECTION_DEFINITION,
        program_atom=dataclasses.replace(
            KNOWLEDGE_GRAPH_PROJECTION_DEFINITION.program_atom,
            payload_codec_id="wrong.codec",
        ),
    )
    candidate = assemble_knowledge_graph_projection_definition(
        bad_definition,
        KnowledgeGraphProjectionAssemblyContext(),
    )
    decision = validate_knowledge_graph_projection_binding(bad_definition, candidate)
    assert isinstance(decision, BindingRejected)
    assert [issue.path for issue in decision.issues] == ["$.definition.program_atom.payload_codec_id"]
    projection = project_knowledge_graph_projection_definition(bad_definition)
    assert isinstance(projection, Failure)
    assert projection.family == "kit.contribution"
    assert projection.code == "CONTRIBUTION_INVALID"
    assert projection.context == {
        "issues": (
            {
                "code": "invalid_spec",
                "path": "$.definition.program_atom.payload_codec_id",
                "message": "atom codec drift",
            },
        )
    }
    rejected_native = define_native_contribution(
        NativeContributionSpec(
            definition=bad_definition,
            project=project_knowledge_graph_projection_definition,
            assemble=assemble_knowledge_graph_projection_definition,
            validate_binding=validate_knowledge_graph_projection_binding,
        )
    )
    assert isinstance(rejected_native, Failure)
    assert rejected_native.context == projection.context

    invalid_source = dataclasses.replace(_extra_source(), contribution_id="")
    invalid_native = compile_native_contribution(invalid_source, KNOWLEDGE_GRAPH_PROJECTION_NATIVE_RULE)
    assert isinstance(invalid_native, Failure)
    assert invalid_native.code == "CONTRIBUTION_INVALID"

    duplicate_cell = _compile_extra_native(
        dataclasses.replace(
            _extra_source(),
            cell_id="knowledge.graph-projection.v2",
            contribution_id="mrw.test.c8.duplicate-cell.v1",
        )
    )
    with pytest.raises(ValueError, match="duplicate native graph cell id knowledge.graph-projection.v2"):
        validate_knowledge_graph_projection_contributions((knowledge_graph_projection_native_contribution, duplicate_cell))


def test_default_and_installed_c8_4_assembly_preserve_exact_declarations() -> None:
    scope = local_assembly_scope_digest()
    source_key = {
        "knowledge.graph-projection.v2": ProjectorSourceKey(
            source_ref="run:c8-graph-contribution:before-after",
            source_incarnation="incarnation:c8-graph-contribution:before-after",
        )
    }
    unbound = build_knowledge_assembly(
        engine=create_engine("sqlite:///:memory:"),  # type: ignore[arg-type]
        project_scope_digest=scope,
    )
    installed = build_knowledge_assembly(
        engine=create_engine("sqlite:///:memory:"),  # type: ignore[arg-type]
        project_scope_digest=scope,
        projector_source_keys=source_key,
    )
    assert unbound.projector_registry is None
    wiring = unbound.projector_wiring[-1].to_dict()
    assert wiring == installed.projector_wiring[-1].to_dict()
    assert wiring["cell_id"] == "knowledge.graph-projection.v2"
    assert wiring["projector_id"] == "knowledge.graph.projector"
    assert wiring["source_kind"] == "knowledge_value"
    assert wiring["projection_schema_ref"] == "mrw.knowledge.graph-projection.v2"
    assert unbound.cell("knowledge.graph-projection.v2").status == "PROJECTOR_WIRING_DECLARED"
    assert installed.cell("knowledge.graph-projection.v2").status == "INSTALLED"
    assert installed.projector_registry is not None
    assert any(
        binding.cell_id == "knowledge.graph-projection.v2"
        for binding in installed.rollback_bindings
    )


def test_default_bundle_preserves_native_payload_codec_behavior() -> None:
    bundle = build_knowledge_bundle()
    codec = bundle.codec_by_kind("knowledge.graph.project.v2")
    operation = next(
        operation
        for operation in bundle.operations
        if operation.ref.kind == "knowledge.graph.project.v2"
    )
    assert [entry.ref.kind for entry in bundle.operations] == [
        "knowledge.read.demand.v2",
        "knowledge.writing.compose.v2",
        "knowledge.writing.stage.v2",
        "knowledge.report.stage.v2",
        "knowledge.graph.project.v2",
    ]
    assert operation.owner_capability_id == "knowledge.graph-projection.v2"
    assert operation.input_type.type_id == "KnowledgeGraphProjectInput.v2"
    assert operation.output_type.type_id == "KnowledgeGraphContext.v2"
    assert set(bundle.profiles) == {
        "knowledge.read.v2",
        "knowledge.writing.v2",
        "knowledge.report.v2",
        "knowledge.graph-projection.v2",
    }
    fields = {
        "project_key": "project-a",
        "graph_id": "graph-a",
        "node_keys": ("ki:a",),
        "node_types": ("Topic",),
    }
    payload = KnowledgeGraphProjectInput(**fields)
    wire = codec.encode_payload(payload)
    assert "kind" not in wire
    assert dataclasses.asdict(codec.decode_payload(wire)) == dataclasses.asdict(payload)
    assert codec.codec_id == "mrw.knowledge.graph-project.codec.v2"
    assert codec.codec_version == "1"
    assert codec.payload_type_id == "KnowledgeGraphProjectInput.v2"
    assert codec.contract_ref == operation.ref


@pytest.mark.parametrize(
    "law_witness",
    knowledge_graph_projection_law_witnesses,
    ids=law_witness_reference,
)
def test_c8_graph_projection_native_catalog_law(law_witness: LawWitness) -> None:
    assert knowledge_graph_projection_law_witness_references == tuple(
        law_witness_reference(witness) for witness in knowledge_graph_projection_law_witnesses
    )
    law_witness.run()


def test_project_catalog_contains_graph_projection_runtime_entry() -> None:
    from contributions.project_catalog import project_contribution_catalog

    assert knowledge_graph_projection_native_contribution.projection in project_contribution_catalog
