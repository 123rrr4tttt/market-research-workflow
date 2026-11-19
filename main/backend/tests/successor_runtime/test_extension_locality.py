"""An independent capability can compile through the shared compiler unchanged."""

from __future__ import annotations

import hashlib
import inspect
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.successor_runtime.capabilities import (
    FIXTURE_OPERATION_KIND,
    build_first_specimen_bundle,
    build_first_specimen_catalog,
    build_fixture_capability_bundle,
)
from app.successor_runtime.language.algebra import (
    AlgebraRef,
    OperationContractRef,
    OperationSpec,
    ReturnContract,
    ValueRef,
    freeze_json_object,
)
from app.successor_runtime.language.catalog import (
    OperationContractRegistry,
)
from app.successor_runtime.language.compile import compile_program
from app.successor_runtime.language.program import ProgramSpec, atom_node

SHARED_ROOT_RELATIVES: tuple[str, ...] = (
    "language/program.py",
    "language/compile.py",
    "language/plan.py",
    "runtime/activation.py",
    "runtime/reducer.py",
    "runtime/transitions.py",
    "runtime/assignments.py",
    "runtime/work_items.py",
)

def _digest(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _fixture_program(contract: object) -> ProgramSpec:
    input_type = contract.input_type
    output_type = contract.output_type
    value = ValueRef(
        value_id="fixture:input:001",
        project_key="specimen",
        object_type=input_type,
        codec_id=input_type.codec_id,
        content_digest=_digest("fixture-input"),
        storage_kind="project_value_ref",
        store_id="successor-values",
        store_version="1",
        storage_ref="fixture-input",
        byte_size=1,
        provenance_digest=_digest("fixture-provenance"),
    )
    atom = atom_node(
        OperationSpec(
            operation_id="fixture-echo",
            contract_ref=OperationContractRef(
                contract.ref.kind,
                contract.ref.contract_version,
                contract.ref.contract_digest,
            ),
            input_refs=(value,),
            payload_ref=value,
            allowed_overrides=freeze_json_object({}),
        ),
        input_type=input_type,
        output_type=output_type,
        return_contract=ReturnContract(
            success_modes=("SUCCEEDED",),
            failure_modes=("FAILED",),
            admission_required=True,
            wait_modes=("WAIT",),
            cancel_modes=("CANCELED",),
        ),
    )
    return ProgramSpec(
        program_id="fixture-echo-program",
        contract_version="mrw.functorial-successor.program-spec.v1",
        project_key="specimen",
        project_registry_revision=1,
        project_scope_digest=_digest("scope"),
        semantic_identity="fixture-echo",
        input_type=input_type,
        output_type=output_type,
        root=atom,
        algebra_refs=(AlgebraRef("first-specimen", "1"),),
        transform_refs=(),
        observation_profile="fixture.echo_hex_digest.v1.observation",
        metadata=freeze_json_object({}),
        program_digest="",
    ).with_digest()


def _shared_root_digests() -> dict[str, str]:
    root = _BACKEND_ROOT / "app" / "successor_runtime"
    return {
        relative: hashlib.sha256((root / relative).read_bytes()).hexdigest()
        for relative in SHARED_ROOT_RELATIVES
    }


def test_fixture_compiles_through_shared_compiler_without_modifying_shared_roots() -> (
    None
):
    before = _shared_root_digests()

    first_specimen = build_first_specimen_bundle()
    fixture = build_fixture_capability_bundle()
    catalog = build_first_specimen_catalog(first_specimen.operations, fixture.operation)
    registry = OperationContractRegistry(
        catalog,
        first_specimen.operations + (fixture.operation,),
    )

    program = _fixture_program(fixture.operation)
    plan = compile_program(
        program,
        catalog,
        operation_contracts=registry,
    )

    fixture_steps = [
        step
        for step in plan.ordered_steps
        if step.operation_contract_ref is not None
        and step.operation_contract_ref.kind == FIXTURE_OPERATION_KIND
        and step.step_kind == "EFFECT"
    ]
    assert len(fixture_steps) == 1
    step = fixture_steps[0]
    assert (
        step.operation_contract_ref.contract_digest
        == fixture.operation.ref.contract_digest
    )
    assert step.effect_profile_ref == fixture.operation.effect_profile_ref
    assert step.authority_profile_ref == fixture.operation.authority_profile_ref
    assert plan.plan_digest

    assert _shared_root_digests() == before


def test_fixture_capability_is_independent_of_first_specimen() -> None:
    fixture_module = sys.modules[type(build_fixture_capability_bundle()).__module__]
    source = inspect.getsource(fixture_module)
    assert "make_operation_contract" in source
    assert "from .first_specimen" not in source
    assert "first_specimen import" not in source
    for shared_import in (
        "from successor_runtime.language.program",
        "import successor_runtime.language.program",
        "from successor_runtime.language.compile",
        "from successor_runtime.runtime.reducer",
        "from successor_runtime.runtime.assignments",
        "from successor_runtime.runtime.work_items",
        "from successor_runtime.substrate.postgres.work_items",
    ):
        assert shared_import not in source
