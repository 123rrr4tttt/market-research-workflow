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
    C8AssemblyOptions,
    ProjectorSourceKey,
    local_assembly_scope_digest,
)
from app.successor_runtime.assembly.c8_assembly import build_c8_assembly
from app.successor_runtime.capabilities.c8_graph_projection_contribution import (
    C8_4_FAILURE_CODES,
    C8_GRAPH_PROJECTION_DEFINITION,
    C8GraphProjectionAssemblyContext,
    C8GraphProjectionRuntimeBinding,
    assemble_c8_graph_projection_definition,
    define_c8_graph_projection_cell,
    project_c8_graph_projection_definition,
    validate_c8_graph_projection_binding,
)
from app.successor_runtime.capabilities.c8_program import (
    C8GraphProjectInput,
    build_c8_bundle,
    build_c8_catalog,
    build_c8_program,
    build_c8_registry,
    compose_default_c8_graph_projection_contributions,
    validate_c8_graph_projection_contributions,
)
from app.successor_runtime.capabilities.checksum import content_digest
from app.successor_runtime.specification import c8_p4
from app.successor_runtime.research.object_types import ObjectType
from functorial_kit.contributions import compose_contributions
from functorial_kit.core.failure import Failure
from functorial_kit.law_witness import LawWitness, law_witness_reference
from functorial_kit.native_contribution import (
    BindingRejected,
    NativeContributionSpec,
    define_native_contribution,
)
from mrw_functorial_kit.contributions.c8_graph_projection import (
    c8_graph_projection_law_witness_references,
    c8_graph_projection_law_witnesses,
    c8_graph_projection_native_contribution,
    contribution_catalog,
)
from mrw_functorial_kit.core.c8_semantics import c8_graph_failures

EXTRA_KIND = "c8.graph.project.test.v1"
EXTRA_INPUT = ObjectType("C8GraphProjectionTestInput.v1")
EXTRA_RESULT = ObjectType("C8GraphProjectionTestResult.v1")
EXTRA_OWNER = "graph.c8.4.test.v1"
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
        context: C8GraphProjectionAssemblyContext,
    ) -> C8GraphProjectionRuntimeBinding:
        if calls is not None:
            calls.append(1)
        return assemble_c8_graph_projection_definition(native_definition, context)

    native = define_native_contribution(
        NativeContributionSpec(
            definition=definition,
            project=project_c8_graph_projection_definition,
            assemble=assemble,
            validate_binding=validate_c8_graph_projection_binding,
        )
    )
    _not_failure(native)
    return native


def _extra_native() -> Any:
    definition = define_c8_graph_projection_cell(
        cell_id="C8.4.test",
        owner=EXTRA_OWNER,
        operation_id="c8.graph.project.test",
        kind=EXTRA_KIND,
        payload_codec_id="mrw.successor.c8.c8-4.test.payload.codec.v1",
        input_type=EXTRA_INPUT,
        output_type=EXTRA_RESULT,
        payload_type=_ExtraInput,
        projector_wiring=None,
        rollback_refs=("test:graph-projection-extension",),
    )
    return _native(definition)


def test_default_runtime_uses_single_catalog_contribution() -> None:
    assert C8_4_FAILURE_CODES is c8_graph_failures.codes
    natives = compose_default_c8_graph_projection_contributions()
    assert [native.projection.id for native in natives] == ["mrw.successor.c8.graph-projection.v1"]
    assert natives[0] is c8_graph_projection_native_contribution
    assert contribution_catalog.contributions == tuple(native.projection for native in natives)
    assert all(contribution.factory is None for contribution in contribution_catalog.contributions)
    bundle = build_c8_bundle()
    registry = build_c8_registry(bundle)
    graph_ref = registry.catalog.lookup("c8.graph.project.v1")
    assert graph_ref is not None
    contract = registry.resolve(graph_ref)
    assert contract is not None
    assert contract.owner_capability_id == "graph.c8.4.v1"

    assembly = build_c8_assembly(
        engine=create_engine("sqlite:///:memory:"),  # type: ignore[arg-type]
        project_scope_digest=local_assembly_scope_digest(),
    )
    assert assembly.coverage()["C8.4"] == "PROJECTOR_WIRING_DECLARED"


def test_catalog_composition_is_pure_and_extra_entry_reaches_native_registries() -> None:
    calls: list[int] = []
    observed = _native(C8_GRAPH_PROJECTION_DEFINITION, calls=calls)
    extra = _extra_native()
    natives = (observed, extra)
    composition = compose_contributions(tuple(native.projection for native in natives))
    _not_failure(composition)
    assert calls == []

    bundle = build_c8_bundle(graph_projection_composition=natives)
    registry = build_c8_registry(bundle)
    extra_ref = registry.catalog.lookup(EXTRA_KIND)
    assert extra_ref is not None
    assert registry.resolve(extra_ref) is not None

    assembly = build_c8_assembly(
        engine=create_engine("sqlite:///:memory:"),  # type: ignore[arg-type]
        project_scope_digest=local_assembly_scope_digest(),
        options=C8AssemblyOptions(graph_projection_composition=natives),
    )
    assert assembly.cell("C8.4.test").operation_contract_refs == (EXTRA_KIND,)
    assert assembly.cell("C8.4.test").status == "PROJECTOR_WIRING_DECLARED"
    object_kinds = {obj.id: obj.kind for obj in composition.objects}
    assert object_kinds[EXTRA_INPUT.type_id] == "ObjectType"
    assert object_kinds["c8.graph.project.test"] == "Capability"
    assert calls

    payload = _ExtraInput(
        project_key="project-a",
        graph_id="graph-extra",
        node_keys=("ki:a",),
        node_types=("Topic",),
    )
    program = build_c8_program(
        cell_id="C8.4.test",
        payload=payload,
        catalog=build_c8_catalog(bundle),
        program_id="program:c8-4-test",
        project_key="project-a",
        project_registry_revision=1,
        project_scope_digest="0" * 64,
        graph_projection_composition=natives,
    )
    assert program.root.operation.operation_id == "c8.graph.project.test"
    assert dict(program.metadata)["canonical_owner"] == EXTRA_OWNER
    assert [entry["operation_kind"] for entry in c8_p4._operation_bindings(natives)["c8_4"]] == [
        "c8.graph.project.v1",
        EXTRA_KIND,
    ]


def test_definition_consistency_and_duplicate_cell_ids_fail_closed() -> None:
    bad_definition = dataclasses.replace(
        C8_GRAPH_PROJECTION_DEFINITION,
        program_atom=dataclasses.replace(
            C8_GRAPH_PROJECTION_DEFINITION.program_atom,
            payload_codec_id="wrong.codec",
        ),
    )
    candidate = assemble_c8_graph_projection_definition(
        bad_definition,
        C8GraphProjectionAssemblyContext(),
    )
    decision = validate_c8_graph_projection_binding(bad_definition, candidate)
    assert isinstance(decision, BindingRejected)
    assert [issue.path for issue in decision.issues] == ["$.definition.program_atom.payload_codec_id"]
    projection = project_c8_graph_projection_definition(bad_definition)
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
            project=project_c8_graph_projection_definition,
            assemble=assemble_c8_graph_projection_definition,
            validate_binding=validate_c8_graph_projection_binding,
        )
    )
    assert isinstance(rejected_native, Failure)
    assert rejected_native.context == projection.context

    duplicate_cell_definition = define_c8_graph_projection_cell(
        cell_id="C8.4",
        contribution_id="mrw.test.c8.duplicate-cell.v1",
        owner=EXTRA_OWNER,
        operation_id="c8.graph.project.test",
        kind=EXTRA_KIND,
        payload_codec_id="mrw.successor.c8.c8-4.test.payload.codec.v1",
        input_type=EXTRA_INPUT,
        output_type=EXTRA_RESULT,
        payload_type=_ExtraInput,
        projector_wiring=None,
        rollback_refs=("test:graph-projection-extension",),
    )
    duplicate_cell = _native(duplicate_cell_definition)
    with pytest.raises(ValueError, match="duplicate native graph cell id C8.4"):
        validate_c8_graph_projection_contributions((c8_graph_projection_native_contribution, duplicate_cell))


def test_default_and_installed_c8_4_assembly_preserve_exact_declarations() -> None:
    golden = _golden()
    scope = local_assembly_scope_digest()
    source_key = {
        "C8.4": ProjectorSourceKey(
            source_ref="run:c8-graph-contribution:before-after",
            source_incarnation="incarnation:c8-graph-contribution:before-after",
        )
    }
    unbound = build_c8_assembly(
        engine=create_engine("sqlite:///:memory:"),  # type: ignore[arg-type]
        project_scope_digest=scope,
    )
    installed = build_c8_assembly(
        engine=create_engine("sqlite:///:memory:"),  # type: ignore[arg-type]
        project_scope_digest=scope,
        projector_source_keys=source_key,
    )
    assert unbound.projector_registry is None
    assert unbound.projector_wiring[-1].to_dict() == golden["projector_wiring"]
    assert installed.projector_wiring[-1].to_dict() == golden["projector_wiring"]
    assert unbound.cell("C8.4").to_dict() == golden["unbound_cell"]
    assert installed.cell("C8.4").to_dict() == golden["installed_cell"]
    assert _json_observation(dataclasses.asdict(installed.projector_registry)) == golden["installed_projector_registry"]
    assert [binding.to_dict() for binding in installed.rollback_bindings] == golden["rollback_bindings"]


def test_default_bundle_preserves_native_payload_codec_behavior() -> None:
    golden = _golden()
    bundle = build_c8_bundle()
    codec = bundle.codec_by_kind("c8.graph.project.v1")
    operation = next(operation for operation in bundle.operations if operation.ref.kind == "c8.graph.project.v1")
    assert [entry.ref.kind for entry in bundle.operations] == golden["operation_order"]
    assert _json_observation(dataclasses.asdict(operation)) == golden["operation_contract"]
    assert {name: profile.profile_digest for name, profile in bundle.profiles["C8.4"].items()} == golden[
        "profile_digests"
    ]
    for family, expected in golden["profile_observations"].items():
        profile = dataclasses.asdict(bundle.profiles["C8.4"][family])
        assert {key: _json_observation(profile[key]) for key in expected} == expected
    fields = {
        "project_key": "project-a",
        "graph_id": "graph-a",
        "node_keys": ("ki:a",),
        "node_types": ("Topic",),
    }
    payload = C8GraphProjectInput(**fields)
    wire = codec.encode_payload(payload)
    assert wire == golden["payload_codec"]["sample_wire"]
    assert "kind" not in wire
    assert dataclasses.asdict(codec.decode_payload(wire)) == dataclasses.asdict(payload)
    assert codec.codec_id == golden["payload_codec"]["codec_id"]
    assert codec.codec_version == golden["payload_codec"]["codec_version"]
    assert codec.payload_type_id == golden["payload_codec"]["payload_type_id"]
    assert codec.codec_digest == golden["payload_codec"]["codec_digest"]
    assert _json_observation(dataclasses.asdict(codec.contract_ref)) == golden["operation_contract"]["ref"]


@pytest.mark.parametrize(
    "law_witness",
    c8_graph_projection_law_witnesses,
    ids=law_witness_reference,
)
def test_c8_graph_projection_native_catalog_law(law_witness: LawWitness) -> None:
    assert c8_graph_projection_law_witness_references == tuple(
        law_witness_reference(witness) for witness in c8_graph_projection_law_witnesses
    )
    law_witness.run()


def test_explicit_catalog_module_reexports_the_runtime_entry() -> None:
    path = Path(__file__).resolve().parents[4] / "contributions/c8_graph_projection_catalog.py"
    spec = importlib.util.spec_from_file_location("mrw_explicit_c8_catalog", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.contribution_catalog is contribution_catalog
    assert module.c8_graph_projection_law_witnesses is c8_graph_projection_law_witnesses
    assert module.c8_graph_projection_law_witness_references is c8_graph_projection_law_witness_references
