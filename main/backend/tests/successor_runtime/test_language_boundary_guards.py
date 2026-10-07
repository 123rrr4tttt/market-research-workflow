"""Boundary witnesses for successor program/normalize construction guards.

Each guard below is an internal construction invariant whose public boundary is
the typed ``Failure`` returned by the ``try_*`` entry points.  The tests trigger
the guard with malformed input and assert the typed rejection, so the
``kit:boundary`` witness strings refer to behaviour that is actually exercised.
"""

from __future__ import annotations

import dataclasses
import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from functorial_kit import Failure

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.successor_runtime.capabilities import (
    build_first_specimen_bundle,
    build_first_specimen_catalog,
)
from app.successor_runtime.language.algebra import (
    ObjectType,
    OperationContractRef,
    OperationSpec,
    ReturnContract,
    ValueRef,
    default_return_contract,
    freeze_json_value,
    freeze_json_object,
    is_frozen_json_object,
    try_canonical_json_bytes,
    try_freeze_json_object,
    thaw_json_value,
)
from app.successor_runtime.language import algebra as algebra_module
from app.successor_runtime.language import object_contracts as object_contracts_module
from app.successor_runtime.language import program as program_module
from app.successor_runtime.language.catalog import OperationContractRegistry
from app.successor_runtime.language.normalize import normalize_program
from app.successor_runtime.language.program import (
    OBJECT_TYPE_PLACEHOLDER_CODEC_ID,
    Atom,
    DecisionBranch,
    MapOutput,
    ProgramSpec,
    Pure,
    ZipOrdered,
    atom_node,
    encode_program_spec,
    identity_node,
    placeholder_object_type,
    try_atom_node,
    try_bind_program_contracts,
    try_decode_ast,
    try_decode_program_spec,
    try_decide_node,
    try_map_output_node,
    try_pure_node,
    try_then_node,
    try_zip_ordered_node,
)
from app.successor_runtime.language.transforms import (
    DiscriminatorRef,
    MergeRef,
    TransformRef,
)
from app.successor_runtime.research.object_types import (
    CAPTURED_MATERIAL_SNAPSHOT_TYPE,
    MATERIAL_REF_TYPE,
)

INTENT = ObjectType(
    type_id="ResearchIntent.v1",
    schema_version="1",
    codec_id="mrw.first-specimen.codec.v1",
    canonical_codec_version="1",
)
MATERIAL_REF = ObjectType(
    type_id="MaterialRef.v1",
    schema_version="1",
    codec_id="mrw.first-specimen.codec.v1",
    canonical_codec_version="1",
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


def _operation_spec(operation_id: str) -> OperationSpec:
    return OperationSpec(
        operation_id=operation_id,
        contract_ref=OperationContractRef(
            kind="material.read_canonical_ref.v1",
            contract_version="1",
            contract_digest="0" * 64,
        ),
        input_refs=(_value_ref(operation_id + ".in", INTENT),),
        payload_ref=_value_ref(operation_id + ".payload", INTENT),
        allowed_overrides=freeze_json_object({}),
    )


def _program_for_root(
    root,
    *,
    input_type: ObjectType | None = None,
    output_type: ObjectType | None = None,
) -> ProgramSpec:
    return ProgramSpec(
        program_id="program.boundary.guard",
        contract_version="mrw.functorial-successor.program-spec.v1",
        project_key="p0",
        project_registry_revision=1,
        project_scope_digest="0" * 64,
        semantic_identity="program.boundary.guard",
        input_type=input_type if input_type is not None else root.input_type,
        output_type=output_type if output_type is not None else root.output_type,
        root=root,
        algebra_refs=(),
        transform_refs=(),
        observation_profile="mrw.successor.program.test.v1",
        metadata=freeze_json_object({}),
        program_digest="",
    )


class _NullResolver:
    def resolve(self, ref: OperationContractRef) -> None:
        return None


@dataclasses.dataclass(frozen=True, slots=True)
class _StubContract:
    input_type: ObjectType
    output_type: ObjectType
    return_contract_ref: str


class _StubResolver:
    def __init__(self, contract: _StubContract) -> None:
        self._contract = contract

    def resolve(self, ref: OperationContractRef) -> _StubContract:
        return self._contract


def _specimen_registry() -> OperationContractRegistry:
    bundle = build_first_specimen_bundle()
    return OperationContractRegistry(
        catalog=build_first_specimen_catalog(bundle.operations),
        contracts=bundle.operations,
    )


def _specimen_operation(operation_id: str) -> OperationSpec:
    catalog = build_first_specimen_catalog(build_first_specimen_bundle().operations)
    entry = catalog.find("material.read_canonical_ref.v1")
    assert entry is not None
    return OperationSpec(
        operation_id=operation_id,
        contract_ref=OperationContractRef(
            kind="material.read_canonical_ref.v1",
            contract_version=entry[1],
            contract_digest=entry[2],
        ),
        input_refs=(
            _value_ref(operation_id + ".in", CAPTURED_MATERIAL_SNAPSHOT_TYPE),
        ),
        payload_ref=_value_ref(
            operation_id + ".payload", CAPTURED_MATERIAL_SNAPSHOT_TYPE
        ),
        allowed_overrides=freeze_json_object({}),
    )


def test_normalize_rejects_spec_type_mismatch() -> None:
    root = identity_node(MATERIAL_REF)
    with pytest.raises(ValueError, match="input_type does not match its root"):
        normalize_program(_program_for_root(root, input_type=INTENT))
    with pytest.raises(ValueError, match="output_type does not match its root"):
        normalize_program(_program_for_root(root, output_type=INTENT))


def test_normalize_rejects_atom_without_input_refs() -> None:
    operation = dataclasses.replace(_operation_spec("guard.no-input-refs"), input_refs=())
    atom = atom_node(operation, input_type=INTENT, output_type=MATERIAL_REF)
    assert isinstance(atom, Atom)
    with pytest.raises(ValueError, match="requires at least one input ValueRef"):
        normalize_program(_program_for_root(atom))


def test_normalize_rejects_unbound_placeholder_endpoint() -> None:
    root = identity_node(placeholder_object_type("atom.input"))
    with pytest.raises(
        ValueError, match="unresolved construction placeholder at program.input_type"
    ):
        normalize_program(_program_for_root(root))


def test_normalize_rejects_incomplete_object_type_identity() -> None:
    incomplete = ObjectType(
        type_id="",
        schema_version="1",
        codec_id="mrw.first-specimen.codec.v1",
        canonical_codec_version="1",
    )
    root = identity_node(MATERIAL_REF)
    with pytest.raises(ValueError, match="incomplete ObjectType identity"):
        normalize_program(_program_for_root(root, input_type=incomplete))


def test_normalize_rejects_incomplete_object_type_codec() -> None:
    incomplete = ObjectType(
        type_id="IncompleteCodec.v1",
        schema_version="1",
        codec_id="",
        canonical_codec_version="1",
    )
    root = identity_node(MATERIAL_REF)
    with pytest.raises(ValueError, match="incomplete ObjectType codec"):
        normalize_program(_program_for_root(root, input_type=incomplete))


def test_atom_node_rejects_malformed_object_types_as_typed_failure() -> None:
    operation = _operation_spec("guard.malformed")
    missing_fields = try_atom_node(operation, input_type=object(), output_type=MATERIAL_REF)
    assert isinstance(missing_fields, Failure)
    assert missing_fields.code == "PROGRAM_TYPE_INVALID"
    assert "must be a complete ObjectType" in missing_fields.message

    non_encodable = SimpleNamespace(
        type_id="NotAnObjectType.v1",
        schema_version="1",
        codec_id="mrw.first-specimen.codec.v1",
        canonical_codec_version="1",
    )
    not_encodable = try_atom_node(
        operation, input_type=non_encodable, output_type=MATERIAL_REF
    )
    assert isinstance(not_encodable, Failure)
    assert not_encodable.code == "PROGRAM_TYPE_INVALID"
    assert "is not canonically encodable" in not_encodable.message


def test_atom_node_rejects_foreign_placeholder_endpoint_as_typed_failure() -> None:
    foreign = ObjectType(
        type_id="placeholder:elsewhere",
        schema_version="0",
        codec_id=OBJECT_TYPE_PLACEHOLDER_CODEC_ID,
        canonical_codec_version="0",
    )
    result = try_atom_node(
        _operation_spec("guard.foreign-placeholder"),
        input_type=foreign,
        output_type=MATERIAL_REF,
    )
    assert isinstance(result, Failure)
    assert result.code == "PROGRAM_TYPE_INVALID"
    assert "malformed placeholder ObjectType" in result.message


def test_decide_node_rejects_branch_return_contract_drift_as_typed_failure() -> None:
    operation = _operation_spec("guard.decide")
    default_branch = DecisionBranch(
        branch_id="a",
        guard="left",
        program=atom_node(
            operation,
            input_type=INTENT,
            output_type=MATERIAL_REF,
            return_contract=default_return_contract(),
        ),
    )
    drifted_branch = DecisionBranch(
        branch_id="b",
        guard="right",
        program=atom_node(
            operation,
            input_type=INTENT,
            output_type=MATERIAL_REF,
            return_contract=ReturnContract(
                success_modes=("DONE",),
                failure_modes=("FAILED",),
                admission_required=False,
            ),
        ),
    )
    result = try_decide_node(
        DiscriminatorRef("guard.discriminator", "1", "0" * 64),
        (default_branch, drifted_branch),
    )
    assert isinstance(result, Failure)
    assert result.code == "PROGRAM_TYPE_INVALID"
    assert "return contracts must agree" in result.message


def test_map_output_and_zip_ordered_reject_unresolved_target_as_typed_failure() -> None:
    unresolved = placeholder_object_type("atom.output")

    map_result = try_map_output_node(
        identity_node(INTENT),
        TransformRef("guard.transform", "1", "0" * 64),
        unresolved,
    )
    assert isinstance(map_result, Failure)
    assert "MapOutput target_type cannot be unresolved" in map_result.message

    zip_result = try_zip_ordered_node(
        identity_node(INTENT),
        identity_node(INTENT),
        MergeRef("guard.merge", "1", "0" * 64),
        output_type=unresolved,
    )
    assert isinstance(zip_result, Failure)
    assert "ZipOrdered output_type cannot be unresolved" in zip_result.message


def test_atom_node_rejects_invalid_return_contract_shapes_as_typed_failure() -> None:
    operation = _operation_spec("guard.return-contract")

    non_tuple_modes = try_atom_node(
        operation,
        input_type=INTENT,
        output_type=MATERIAL_REF,
        return_contract=ReturnContract(
            success_modes=["SUCCEEDED"],  # type: ignore[arg-type]
            failure_modes=("FAILED",),
            admission_required=False,
        ),
    )
    assert isinstance(non_tuple_modes, Failure)
    assert "must be a string tuple" in non_tuple_modes.message

    empty_modes = try_atom_node(
        operation,
        input_type=INTENT,
        output_type=MATERIAL_REF,
        return_contract=ReturnContract(
            success_modes=(),
            failure_modes=("FAILED",),
            admission_required=False,
        ),
    )
    assert isinstance(empty_modes, Failure)
    assert "requires success and failure modes" in empty_modes.message

    non_bool_admission = try_atom_node(
        operation,
        input_type=INTENT,
        output_type=MATERIAL_REF,
        return_contract=ReturnContract(
            success_modes=("SUCCEEDED",),
            failure_modes=("FAILED",),
            admission_required="yes",  # type: ignore[arg-type]
        ),
    )
    assert isinstance(non_bool_admission, Failure)
    assert "admission_required must be boolean" in non_bool_admission.message

    non_string_modes = default_return_contract()
    object.__setattr__(non_string_modes, "success_modes", (1,))
    invalid_mode = try_atom_node(
        operation,
        input_type=INTENT,
        output_type=MATERIAL_REF,
        return_contract=non_string_modes,
    )
    assert isinstance(invalid_mode, Failure)
    assert "must be a string tuple" in invalid_mode.message


def test_bind_contracts_rejects_unresolved_node_placeholders_as_typed_failure() -> None:
    unresolved = placeholder_object_type("atom.output")

    map_root = MapOutput(
        source=identity_node(INTENT),
        transform_ref=TransformRef("guard.transform", "1", "0" * 64),
        target_type=unresolved,
    )
    map_result = try_bind_program_contracts(
        _program_for_root(map_root), _NullResolver()
    )
    assert isinstance(map_result, Failure)
    assert "unresolved target placeholder" in map_result.message

    zip_root = ZipOrdered(
        left=identity_node(INTENT),
        right=identity_node(INTENT),
        merge_ref=MergeRef("guard.merge", "1", "0" * 64),
        output_type=unresolved,
    )
    zip_result = try_bind_program_contracts(
        _program_for_root(zip_root), _NullResolver()
    )
    assert isinstance(zip_result, Failure)
    assert "unresolved output placeholder" in zip_result.message

    pure_root = Pure(
        input_type_ref=unresolved,
        output_type_ref=MATERIAL_REF,
        literal_codec="guard.literal.codec.v1",
        literal_digest="0" * 64,
        literal_value=1,
    )
    pure_result = try_bind_program_contracts(
        _program_for_root(pure_root), _NullResolver()
    )
    assert isinstance(pure_result, Failure)
    assert "unresolved placeholder" in pure_result.message


def test_bind_contracts_rejects_unresolved_operation_contract_as_typed_failure() -> None:
    atom = atom_node(
        _operation_spec("guard.unresolved-operation"),
        input_type=INTENT,
        output_type=MATERIAL_REF,
    )
    result = try_bind_program_contracts(_program_for_root(atom), _NullResolver())
    assert isinstance(result, Failure)
    assert result.code == "PROGRAM_TYPE_INVALID"
    assert "unresolved operation contract" in result.message


def test_bind_contracts_rejects_unresolved_return_contract_as_typed_failure() -> None:
    atom = atom_node(
        _operation_spec("guard.unresolved-return"),
        input_type=INTENT,
        output_type=MATERIAL_REF,
    )
    resolver = _StubResolver(
        _StubContract(
            input_type=INTENT,
            output_type=MATERIAL_REF,
            return_contract_ref="mrw.return.unknown.v1",
        )
    )
    result = try_bind_program_contracts(_program_for_root(atom), resolver)
    assert isinstance(result, Failure)
    assert "unresolved return contract" in result.message


def test_bind_contracts_rejects_placeholder_issued_for_other_endpoint_as_typed_failure() -> (
    None
):
    registry = _specimen_registry()
    operation = _specimen_operation("guard.placeholder-endpoint")

    foreign_endpoint = placeholder_object_type("atom.output")
    endpoint_node = atom_node(
        operation, input_type=foreign_endpoint, output_type=MATERIAL_REF_TYPE
    )
    endpoint_result = try_bind_program_contracts(
        _program_for_root(endpoint_node), registry
    )
    assert isinstance(endpoint_result, Failure)
    assert "placeholder issued for another endpoint" in endpoint_result.message

    foreign_ref = dataclasses.replace(
        _value_ref("guard.placeholder-endpoint.in", CAPTURED_MATERIAL_SNAPSHOT_TYPE),
        object_type=placeholder_object_type("atom.output"),
    )
    ref_node = atom_node(
        dataclasses.replace(operation, input_refs=(foreign_ref,)),
        input_type=CAPTURED_MATERIAL_SNAPSHOT_TYPE,
        output_type=MATERIAL_REF_TYPE,
    )
    ref_result = try_bind_program_contracts(_program_for_root(ref_node), registry)
    assert isinstance(ref_result, Failure)
    assert "placeholder issued for another endpoint" in ref_result.message


def test_bind_contracts_rejects_endpoint_mismatch_with_root_as_typed_failure() -> None:
    root = atom_node(
        _operation_spec("guard.endpoint-mismatch"),
        input_type=MATERIAL_REF,
        output_type=MATERIAL_REF,
    )
    result = try_bind_program_contracts(
        _program_for_root(root, input_type=INTENT), _NullResolver()
    )
    assert isinstance(result, Failure)
    assert "does not match the root endpoint" in result.message


def test_language_failure_family_loader_rejects_missing_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(importlib, "import_module", lambda _name: SimpleNamespace())

    with pytest.raises(TypeError, match="factory is unavailable"):
        program_module._load_failure_family()
    with pytest.raises(TypeError, match="factory is unavailable"):
        object_contracts_module._load_language_failures()


def test_language_failure_family_loader_rejects_missing_family(monkeypatch: pytest.MonkeyPatch) -> None:
    module = SimpleNamespace(
        define_failure_family=lambda _name, _codes: object(),
        language_failures=object(),
    )
    monkeypatch.setattr(importlib, "import_module", lambda _name: module)

    with pytest.raises(TypeError, match="failure family is unavailable"):
        object_contracts_module._load_language_failures()


def test_program_failure_lift_rejects_mismatched_context() -> None:
    failure = try_then_node(identity_node(INTENT), identity_node(MATERIAL_REF))
    assert isinstance(failure, Failure)

    with pytest.raises(TypeError, match="lift context is incomplete"):
        program_module._lift_program_failure(failure, ValueError)


def test_pure_literal_rejects_non_json_values_as_typed_failure() -> None:
    for literal in (float("nan"), {1, 2}, object()):
        result = try_pure_node(INTENT, MATERIAL_REF, literal, "guard.literal.v1")
        assert isinstance(result, Failure)
        assert result.code == "PROGRAM_CODEC_INVALID"


def test_program_metadata_codec_rejects_malformed_objects_as_typed_failure() -> None:
    def encoded() -> dict[str, object]:
        return encode_program_spec(
            _program_for_root(identity_node(INTENT)).with_digest()
        )

    malformed_metadata: tuple[object, ...] = (5, [1, 2], [[1, 2]])
    for metadata in malformed_metadata:
        payload = encoded()
        program = payload.get("program")
        assert isinstance(program, dict)
        program["metadata"] = metadata
        result = try_decode_program_spec(payload)
        assert isinstance(result, Failure)
        assert result.code == "PROGRAM_CODEC_INVALID"


def test_program_codec_shape_guards_return_typed_failure() -> None:
    def encoded() -> dict[str, object]:
        return encode_program_spec(
            _program_for_root(identity_node(INTENT)).with_digest()
        )

    bad_payloads: list[dict[str, object]] = []
    non_object = encoded()
    non_object["program"] = 5
    bad_payloads.append(non_object)

    non_text_digest = encoded()
    non_text_digest["program_digest"] = 5
    bad_payloads.append(non_text_digest)

    program = encoded()
    program_fields = program.get("program")
    assert isinstance(program_fields, dict)
    program_fields["algebra_refs"] = ["$array", 5]
    bad_payloads.append(program)

    non_integer_revision = encoded()
    revision_fields = non_integer_revision.get("program")
    assert isinstance(revision_fields, dict)
    revision_fields["project_registry_revision"] = True
    bad_payloads.append(non_integer_revision)

    for payload in bad_payloads:
        result = try_decode_program_spec(payload)
        assert isinstance(result, Failure)
        assert result.code == "PROGRAM_CODEC_INVALID"

    ast_failure = try_decode_ast(5)
    assert isinstance(ast_failure, Failure)
    assert ast_failure.code == "PROGRAM_CODEC_INVALID"

    def atom_ast() -> dict[str, object]:
        return atom_node(
            _operation_spec("guard.codec-return-contract"),
            input_type=INTENT,
            output_type=MATERIAL_REF,
        ).encode_ast()

    for changes in (
        {"success_modes": 5},
        {"success_modes": [1]},
        {"admission_required": "yes"},
    ):
        root = atom_ast()
        tagged_contract = root.get("return_contract")
        assert isinstance(tagged_contract, dict)
        contract_json = tagged_contract.get("$json")
        assert isinstance(contract_json, str)
        contract_fields = json.loads(contract_json)
        assert isinstance(contract_fields, dict)
        contract_fields.update(changes)
        tagged_contract["$json"] = json.dumps(
            contract_fields, sort_keys=True, separators=(",", ":")
        )
        result = try_decode_ast(root)
        assert isinstance(result, Failure)
        assert result.code == "PROGRAM_CODEC_INVALID"

    def atom_ast() -> dict[str, object]:
        return atom_node(
            _operation_spec("guard.codec-return-contract"),
            input_type=INTENT,
            output_type=MATERIAL_REF,
        ).encode_ast()

    for changes in (
        {"success_modes": 5},
        {"success_modes": [1]},
        {"admission_required": "yes"},
    ):
        root = atom_ast()
        tagged_contract = root.get("return_contract")
        assert isinstance(tagged_contract, dict)
        contract_json = tagged_contract.get("$json")
        assert isinstance(contract_json, str)
        contract_fields = json.loads(contract_json)
        assert isinstance(contract_fields, dict)
        contract_fields.update(changes)
        tagged_contract["$json"] = json.dumps(
            contract_fields, sort_keys=True, separators=(",", ":")
        )
        result = try_decode_ast(root)
        assert isinstance(result, Failure)
        assert result.code == "PROGRAM_CODEC_INVALID"


def test_program_codec_rejects_unsupported_storage_kind_as_typed_failure() -> None:
    root = atom_node(
        _operation_spec("guard.unsupported-storage-kind"),
        input_type=INTENT,
        output_type=MATERIAL_REF,
    ).encode_ast()
    operation_tag = root.get("operation")
    assert isinstance(operation_tag, dict)
    operation_json = operation_tag.get("$json")
    assert isinstance(operation_json, str)
    operation_fields = json.loads(operation_json)
    assert isinstance(operation_fields, dict)
    refs = operation_fields.get("input_refs")
    assert isinstance(refs, list) and refs
    encoded_refs = refs[1] if refs[0] == "$array" else refs
    assert isinstance(encoded_refs, list) and encoded_refs
    value_ref = encoded_refs[0]
    assert isinstance(value_ref, dict)
    value_ref["storage_kind"] = "unsupported"
    operation_tag["$json"] = json.dumps(
        operation_fields, sort_keys=True, separators=(",", ":")
    )

    result = try_decode_ast(root)
    assert isinstance(result, Failure)
    assert result.code == "PROGRAM_CODEC_INVALID"


def test_operation_contract_resolver_requires_required_resolution() -> None:
    class ResolveOnlyResolver(object_contracts_module.OperationContractResolver):
        def resolve(
            self, ref: OperationContractRef
        ) -> object_contracts_module.OperationContract | None:
            return None

    with pytest.raises(NotImplementedError):
        ResolveOnlyResolver().resolve_required(
            _operation_spec("guard.required-contract").contract_ref
        )


def test_canonical_encoding_rejects_invalid_tag_registration(monkeypatch: pytest.MonkeyPatch) -> None:
    class MisregisteredValue:
        pass

    monkeypatch.setitem(algebra_module._TAG_MAP, MisregisteredValue, "invalid_value")
    result = try_canonical_json_bytes(MisregisteredValue())
    assert isinstance(result, Failure)
    assert result.code == "CANONICAL_VALUE_INVALID"


def test_freeze_json_object_validates_input_and_normalizes_key_order() -> None:
    first = try_freeze_json_object({"b": 2, "a": 1})
    second = try_freeze_json_object({"a": 1, "b": 2})
    invalid = try_freeze_json_object([])

    assert not isinstance(first, Failure)
    assert not isinstance(second, Failure)
    assert first == second
    assert isinstance(invalid, Failure)
    assert invalid.code == "CANONICAL_VALUE_INVALID"


def test_frozen_json_shape_survives_freeze_thaw_and_canonical_encoding() -> None:
    source = {
        "empty_array": [],
        "empty_object": {},
        "pair_array": [["key", 1]],
        "nested": {"array": [["left", "right"]], "object": {"empty_array": []}},
        "scalar": 1.0,
        "boolean": False,
    }
    frozen = freeze_json_value(source)

    assert is_frozen_json_object(frozen)
    assert freeze_json_value(frozen) is frozen
    assert thaw_json_value(frozen) == source
    encoded = json.loads(algebra_module.canonical_json_bytes(frozen))
    assert encoded["empty_array"] == ["$array", []]
    assert encoded["empty_object"] == {}
    assert encoded["pair_array"] == ["$array", [["$array", ["key", 1]]]]
    assert thaw_json_value(freeze_json_value(frozenset({"b", "a"}))) == ["a", "b"]
