"""Extension-locality gate for capability additions.

The gate registers the independent fixture capability (built only from public
``make_operation_contract``/profile builders), compiles it through the real
shared successor compiler, and binds the shared Program AST/compiler/reducer
RuntimeAssignment root and work-item root schema against a pre-stored
baseline evidence manifest.  The same fixture compile also proves the shared
root hashes are unchanged before and after compilation.  No computed
missing-file placeholder exists: every shared root is pinned by explicit
pre-stored evidence.
"""

from __future__ import annotations

import hashlib
import inspect
import json
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

# Pre-stored baseline evidence for the frozen P0-A shared roots.  All five
# roots exist and are pinned by SHA-256; the P0-A slice does not declare any
# shared root missing.  The gate fails if any recorded state drifts in either
# direction.
SHARED_ROOT_BASELINE: dict[str, object] = {
    "schema": "mrw.successor_runtime.extension_locality.baseline.v1",
    "captured_at": "2026-08-31T18:26:56Z",
    "files": {
        "language/program.py": (
            "eba5147e44ada7ee264606cb64347132b902d86beebba14b9b9a1c3bb6f01e02"
        ),
        "language/compile.py": (
            "91b06329b8476d06193e8030746288be5550f065b6f471b81dce650608d61dd5"
        ),
        "language/plan.py": (
            "a8f5ab8ccc38c56ebfb67b6b7a1b36132bf45e132014f6d2a2ed0ee3ba7cfb82"
        ),
        "runtime/activation.py": (
            "00191b27c57850a5398e34c6d01af7430facf0dcf33b580b606d5b66082034fc"
        ),
        "runtime/reducer.py": (
            "0462576d08ec7748aaf96fabf739707ca44b3b6a4a9c1f85f52574122af31856"
        ),
        "runtime/transitions.py": (
            "5fca6cda9ec554e660ea615ec32a848d819d7be48dc2a32ef5481f4bd5a88b4b"
        ),
        "runtime/assignments.py": (
            "5cf914fbb3c49bc00f929ab184c5c5014f8013a6526af57e3283a12a8b8ca0b0"
        ),
        "runtime/work_items.py": (
            "5acf8ecdfc4c85aec16af6798f7ea24053b7b77a3ab49187a6a3387a4c5d75f2"
        ),
    },
    "declared_not_created": [],
}

SHARED_ROOT_BASELINE_DIGEST = (
    "b13c756ea5693d9c8b3c69af59788386b876c0ea13aec861eedacb789a2c1327"
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


def _baseline_payload() -> dict[str, object]:
    return {
        "schema": SHARED_ROOT_BASELINE["schema"],
        "captured_at": SHARED_ROOT_BASELINE["captured_at"],
        "files": dict(sorted(SHARED_ROOT_BASELINE["files"].items())),
        "declared_not_created": sorted(
            entry["path"] for entry in SHARED_ROOT_BASELINE["declared_not_created"]
        ),
    }


def _canonical_sha256(payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _baseline_state() -> dict[str, object]:
    return {
        "files": dict(sorted(SHARED_ROOT_BASELINE["files"].items())),
        "missing": sorted(
            entry["path"] for entry in SHARED_ROOT_BASELINE["declared_not_created"]
        ),
    }


def _current_shared_state(root: Path) -> dict[str, object]:
    files: dict[str, str] = {}
    missing: list[str] = []
    for relative in SHARED_ROOT_RELATIVES:
        path = root / relative
        if path.exists():
            files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        else:
            missing.append(relative)
    return {"files": files, "missing": missing}


def test_fixture_compiles_through_shared_compiler_without_modifying_shared_roots() -> (
    None
):
    successor_root = _BACKEND_ROOT / "app" / "successor_runtime"
    before = _current_shared_state(successor_root)
    assert before == _baseline_state()

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

    after = _current_shared_state(successor_root)
    assert after == before
    assert after == _baseline_state()
    assert _canonical_sha256(_baseline_payload()) == SHARED_ROOT_BASELINE_DIGEST


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


def test_baseline_evidence_has_no_absent_placeholder() -> None:
    declared_missing = {
        entry["path"] for entry in SHARED_ROOT_BASELINE["declared_not_created"]
    }
    assert set(SHARED_ROOT_BASELINE["files"]) | declared_missing == set(
        SHARED_ROOT_RELATIVES
    )
    forbidden_sentinel = "<" + "absent" + ">"
    assert forbidden_sentinel not in json.dumps(SHARED_ROOT_BASELINE, sort_keys=True)
