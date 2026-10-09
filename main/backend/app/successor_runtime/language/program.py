"""Serializable, typed initial Program AST.

The AST keeps complete child programs; node digests are derived projections and
are never a substitute for the full tree.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Literal, NoReturn, Protocol, TypeAlias, TypeGuard, runtime_checkable
from collections.abc import Iterable, Mapping, Sequence



from app.successor_runtime.research.object_types import ObjectType

from functorial_kit import Failure
from .algebra import (
    FrozenJsonObject,
    FrozenJsonValue,
    OperationSpec,
    ReturnContract,
    ValueRef,
    canonical_digest,
    canonical_json_bytes,
    default_return_contract,
    freeze_json_value,
    is_frozen_json_object,
    sha256_digest_bytes,
)
from .object_contracts import (
    OperationContractRef,
    build_first_specimen_return_contract_registry,
)

if TYPE_CHECKING:
    from .algebra import AlgebraRef
    from .object_contracts import OperationContractResolver
    from .transforms import DiscriminatorRef, MergeRef, TransformRef, TransformReference

ALLOWED_NODE_KINDS = (
    "identity",
    "pure",
    "atom",
    "then",
    "map_output",
    "zip_ordered",
    "traverse_ordered",
    "decide",
)
PROGRAM_AST_CODEC_V1_ID = "mrw.functorial-successor.program-ast.codec.v1"
PROGRAM_AST_CODEC_ID = "mrw.functorial-successor.program-ast.codec.v2"
OBJECT_TYPE_PLACEHOLDER_CODEC_ID = "mrw.invalid.unresolved"
OBJECT_TYPE_PLACEHOLDER_VERSION = "0"

@runtime_checkable
class _FailureFamilyLike(Protocol):
    def fail(
        self,
        code: str,
        message: str,
        context: Mapping[str, object] | None = None,
    ) -> Failure: ...

    def matches(self, value: object) -> bool: ...


@runtime_checkable
class _FailureFamilyFactory(Protocol):
    def __call__(
        self, name: str, codes: "tuple[str, ...]"
    ) -> _FailureFamilyLike: ...


def _load_failure_family() -> _FailureFamilyLike:
    import importlib

    module = importlib.import_module("functorial_kit.core.failure")
    factory: object = getattr(module, "define_failure_family", None)
    if not isinstance(factory, _FailureFamilyFactory):
        # kit:boundary owner=successor.language.program.failure_family class=PROGRAMMER_DEFECT failure_family=none witness=test:test_language_failure_family_loader_rejects_missing_factory
        raise TypeError("functorial_kit failure family factory is unavailable")
    return factory("successor.language.failure", _LANGUAGE_FAILURE_CODES)


ProgramResult: TypeAlias = "ProgramNode | Failure"
ProgramSpecResult: TypeAlias = "ProgramSpec | Failure"


_LANGUAGE_FAILURE_CODES: "tuple[str, ...]" = (
    "PROGRAM_CODEC_INVALID",
    "PROGRAM_DIGEST_MISMATCH",
    "PROGRAM_MATERIALIZATION_INVALID",
    "PROGRAM_TYPE_INVALID",
    "UNKNOWN_NODE_KIND",
)
_LANGUAGE_FAILURES = _load_failure_family()


def _program_failure(
    code: str,
    message: object,
    exception_type: type[Exception],
    *,
    site: str,
) -> Failure:
    public_message = str(exception_type(message))
    return _LANGUAGE_FAILURES.fail(
        code,
        public_message,
        {
            "public_exception": exception_type.__name__,
            "public_argument": message,
            "public_message": public_message,
            "site": site,
            "witness": "test:test_w07_language_research_failure_boundary",
        },
    )


def _lift_program_failure(
    failure: Failure,
    exception_type: type[Exception],
) -> NoReturn:
    context = failure.context or {}
    if (
        not _LANGUAGE_FAILURES.matches(failure)
        or context.get("public_exception") != exception_type.__name__
        or not context.get("public_message")
    ):
        # kit:boundary owner=successor.language.failure_lift class=PROGRAMMER_DEFECT failure_family=none witness=test:test_program_failure_lift_rejects_mismatched_context
        raise TypeError("language failure lift context is incomplete")
    # kit:boundary owner=successor.language.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.language.failure witness=test:test_program_try_failures_and_legacy_lift
    raise exception_type(context.get("public_argument", context["public_message"]))


def _exception_type_from_failure(
    failure: Failure,
    default: type[Exception] = ValueError,
) -> type[Exception]:
    name = str((failure.context or {}).get("public_exception") or "")
    return {
        "TypeError": TypeError,
        "KeyError": KeyError,
        "ProgramTypeError": ProgramTypeError,
        "ProgramCodecError": ProgramCodecError,
    }.get(name, default)


class ProgramTypeError(ValueError):
    """Raised when a program composition violates typed boundaries."""


class ProgramCodecError(ValueError):
    """Raised when an AST payload cannot be decoded."""


def placeholder_object_type(endpoint: str) -> ObjectType:
    """Build the explicit construction-time placeholder for one endpoint.

    A placeholder is a valid AST object, but it is not a resolved runtime type.
    ``normalize_program`` rejects placeholders before planning or compilation.
    """

    return ObjectType(
        type_id=f"placeholder:{endpoint}",
        schema_version=OBJECT_TYPE_PLACEHOLDER_VERSION,
        codec_id=OBJECT_TYPE_PLACEHOLDER_CODEC_ID,
        canonical_codec_version=OBJECT_TYPE_PLACEHOLDER_VERSION,
    )


def is_placeholder_object_type(object_type: object) -> bool:
    return (
        getattr(object_type, "schema_version", None)
        == OBJECT_TYPE_PLACEHOLDER_VERSION
        and getattr(object_type, "codec_id", None)
        == OBJECT_TYPE_PLACEHOLDER_CODEC_ID
        and getattr(object_type, "canonical_codec_version", None)
        == OBJECT_TYPE_PLACEHOLDER_VERSION
    )


@runtime_checkable
class ProgramNode(Protocol):
    @property
    def node_kind(self) -> str: ...

    @property
    def input_type(self) -> ObjectType: ...

    @property
    def output_type(self) -> ObjectType: ...

    @property
    def return_contract(self) -> ReturnContract: ...

    def encode_ast(self) -> "dict[str, object]": ...

    def ast_digest(self) -> str: ...

    def normalized(self) -> "ProgramNode": ...


@dataclass(frozen=True, slots=True)
class Identity:

    @property
    def node_kind(self) -> str:
        return "identity"
    object_type: ObjectType

    @property
    def input_type(self) -> ObjectType:
        return self.object_type

    @property
    def output_type(self) -> ObjectType:
        return self.object_type

    @property
    def return_contract(self) -> ReturnContract:
        return default_return_contract()

    def encode_ast(self) -> "dict[str, object]":
        return {
            "node_kind": self.node_kind,
            "object_type": _encode_tagged(self.object_type, "object_type"),
        }

    def ast_digest(self) -> str:
        return canonical_digest(self.encode_ast())

    def normalized(self) -> "ProgramNode":
        from .normalize import normalize_node

        return normalize_node(self)


@dataclass(frozen=True, slots=True, init=False)
class Pure:

    def __init__(
        self,
        *,
        input_type_ref: ObjectType,
        output_type_ref: ObjectType,
        literal_codec: str,
        literal_digest: str,
        literal_value: FrozenJsonValue,
    ) -> None:
        object.__setattr__(self, "input_type_ref", input_type_ref)
        object.__setattr__(self, "output_type_ref", output_type_ref)
        object.__setattr__(self, "literal_codec", literal_codec)
        object.__setattr__(self, "literal_digest", literal_digest)
        object.__setattr__(self, "literal_value", literal_value)

    @property
    def node_kind(self) -> str:
        return "pure"
    input_type_ref: ObjectType
    output_type_ref: ObjectType
    literal_codec: str
    literal_digest: str
    literal_value: FrozenJsonValue

    @property
    def input_type(self) -> ObjectType:
        return self.input_type_ref

    @property
    def output_type(self) -> ObjectType:
        return self.output_type_ref

    @property
    def return_contract(self) -> ReturnContract:
        return default_return_contract()

    def encode_ast(self) -> "dict[str, object]":
        return {
            "node_kind": self.node_kind,
            "input_type_ref": _encode_tagged(self.input_type_ref, "object_type"),
            "output_type_ref": _encode_tagged(self.output_type_ref, "object_type"),
            "literal_codec": self.literal_codec,
            "literal_digest": self.literal_digest,
            "literal_value": self.literal_value,
        }

    def ast_digest(self) -> str:
        return canonical_digest(self.encode_ast())

    def normalized(self) -> "ProgramNode":
        from .normalize import normalize_node

        return normalize_node(self)


@dataclass(frozen=True, slots=True)
class Atom:

    @property
    def node_kind(self) -> str:
        return "atom"
    operation: OperationSpec
    input_type: ObjectType
    output_type: ObjectType
    return_contract: ReturnContract

    @property
    def _typed_input(self) -> ObjectType:
        return self.input_type

    def encode_ast(self) -> "dict[str, object]":
        return {
            "node_kind": self.node_kind,
            "operation": _encode_tagged(_operation_payload(self.operation), "operation_spec"),
            "input_type": _encode_tagged(self.input_type, "object_type"),
            "output_type": _encode_tagged(self.output_type, "object_type"),
            "return_contract": _encode_tagged(self.return_contract, "return_contract"),
        }

    def ast_digest(self) -> str:
        return canonical_digest(self.encode_ast())

    def normalized(self) -> "ProgramNode":
        from .normalize import normalize_node

        return normalize_node(self)


def _operation_payload(operation: OperationSpec) -> "dict[str, object]":
    return {
        "operation_id": operation.operation_id,
        "contract_ref": _encode_plain(operation.contract_ref),
        "input_refs": [_encode_plain(ref) for ref in operation.input_refs],
        "payload_ref": _encode_plain(operation.payload_ref),
        "allowed_overrides": operation.allowed_overrides,
    }


def program_atoms(node: ProgramNode) -> tuple[Atom, ...]:
    """Return atoms in static source order, including every Decide branch."""

    if isinstance(node, Atom):
        return (node,)
    if isinstance(node, Then):
        return program_atoms(node.first) + program_atoms(node.second)
    if isinstance(node, MapOutput):
        return program_atoms(node.source)
    if isinstance(node, ZipOrdered):
        return program_atoms(node.left) + program_atoms(node.right)
    if isinstance(node, TraverseOrdered):
        return program_atoms(node.element_program)
    if isinstance(node, Decide):
        return tuple(
            atom for branch in node.branches for atom in program_atoms(branch.program)
        )
    return ()


@dataclass(frozen=True, slots=True)
class Then:

    @property
    def node_kind(self) -> str:
        return "then"
    first: "ProgramNode"
    second: "ProgramNode"

    @property
    def input_type(self) -> ObjectType:
        return self.first.input_type

    @property
    def output_type(self) -> ObjectType:
        return self.second.output_type

    @property
    def return_contract(self) -> ReturnContract:
        return self.second.return_contract

    def encode_ast(self) -> "dict[str, object]":
        return {
            "node_kind": self.node_kind,
            "first": self.first.encode_ast(),
            "second": self.second.encode_ast(),
        }

    def ast_digest(self) -> str:
        return canonical_digest(self.encode_ast())

    def normalized(self) -> "ProgramNode":
        from .normalize import normalize_node

        return normalize_node(self)


@dataclass(frozen=True, slots=True, init=False)
class MapOutput:

    def __init__(
        self,
        *,
        source: ProgramNode,
        transform_ref: TransformRef,
        target_type: ObjectType,
    ) -> None:
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "transform_ref", transform_ref)
        object.__setattr__(self, "target_type", target_type)

    @property
    def node_kind(self) -> str:
        return "map_output"
    source: "ProgramNode"
    transform_ref: "TransformRef"
    target_type: ObjectType

    @property
    def input_type(self) -> ObjectType:
        return self.source.input_type

    @property
    def output_type(self) -> ObjectType:
        return self.target_type

    @property
    def return_contract(self) -> ReturnContract:
        return self.source.return_contract

    def encode_ast(self) -> "dict[str, object]":
        return {
            "node_kind": self.node_kind,
            "source": self.source.encode_ast(),
            "transform_ref": _encode_tagged(self.transform_ref, "transform_ref"),
            "target_type": _encode_tagged(self.target_type, "object_type"),
        }

    def ast_digest(self) -> str:
        return canonical_digest(self.encode_ast())

    def normalized(self) -> "ProgramNode":
        from .normalize import normalize_node

        return normalize_node(self)


@dataclass(frozen=True, slots=True, init=False)
class ZipOrdered:

    def __init__(
        self,
        *,
        left: ProgramNode,
        right: ProgramNode,
        merge_ref: MergeRef,
        output_type: ObjectType,
    ) -> None:
        object.__setattr__(self, "left", left)
        object.__setattr__(self, "right", right)
        object.__setattr__(self, "merge_ref", merge_ref)
        object.__setattr__(self, "output_type", output_type)

    @property
    def node_kind(self) -> str:
        return "zip_ordered"
    left: "ProgramNode"
    right: "ProgramNode"
    merge_ref: "MergeRef"
    output_type: ObjectType

    @property
    def input_type(self) -> ObjectType:
        return self.left.input_type

    @property
    def return_contract(self) -> ReturnContract:
        return default_return_contract()

    def encode_ast(self) -> "dict[str, object]":
        return {
            "node_kind": self.node_kind,
            "left": self.left.encode_ast(),
            "right": self.right.encode_ast(),
            "merge_ref": _encode_tagged(self.merge_ref, "merge_ref"),
            "output_type": _encode_tagged(self.output_type, "object_type"),
        }

    def ast_digest(self) -> str:
        return canonical_digest(self.encode_ast())

    def normalized(self) -> "ProgramNode":
        from .normalize import normalize_node

        return normalize_node(self)


@dataclass(frozen=True, slots=True)
class TraverseOrdered:

    @property
    def node_kind(self) -> str:
        return "traverse_ordered"
    element_program: "ProgramNode"
    traversal_policy: str
    sequence_codec_version: str = "1"

    def __post_init__(self) -> None:
        sequence_object_type(self.element_program.input_type, version=self.sequence_codec_version)

    @property
    def input_type(self) -> "ObjectType":
        return sequence_object_type(self.element_program.input_type, version=self.sequence_codec_version)

    @property
    def output_type(self) -> "ObjectType":
        return sequence_object_type(self.element_program.output_type, version=self.sequence_codec_version)

    @property
    def return_contract(self) -> ReturnContract:
        return default_return_contract()

    def encode_ast(self) -> "dict[str, object]":
        encoded: dict[str, object] = {
            "node_kind": self.node_kind,
            "element_program": self.element_program.encode_ast(),
            "traversal_policy": self.traversal_policy,
        }
        if self.sequence_codec_version != "1":
            encoded["sequence_codec_version"] = self.sequence_codec_version
        return encoded

    def ast_digest(self) -> str:
        return canonical_digest(self.encode_ast())

    def normalized(self) -> "ProgramNode":
        from .normalize import normalize_node

        return normalize_node(self)


@dataclass(frozen=True, slots=True)
class DecisionBranch:
    branch_id: str
    guard: str
    program: "ProgramNode"

    def encode_ast(self) -> "dict[str, object]":
        return {
            "branch_id": self.branch_id,
            "guard": self.guard,
            "program": self.program.encode_ast(),
        }

    def ast_digest(self) -> str:
        return canonical_digest(self.encode_ast())


@dataclass(frozen=True, slots=True)
class Decide:

    @property
    def node_kind(self) -> str:
        return "decide"
    discriminator_ref: "DiscriminatorRef"
    branches: "tuple[DecisionBranch, ...]"

    @property
    def input_type(self) -> ObjectType:
        return self.branches[0].program.input_type

    @property
    def output_type(self) -> ObjectType:
        return self.branches[0].program.output_type

    @property
    def return_contract(self) -> ReturnContract:
        return default_return_contract()

    def encode_ast(self) -> "dict[str, object]":
        return {
            "node_kind": self.node_kind,
            "discriminator_ref": _encode_tagged(
                self.discriminator_ref, "discriminator_ref"
            ),
            "branches": [branch.encode_ast() for branch in self.branches],
        }

    def ast_digest(self) -> str:
        return canonical_digest(self.encode_ast())

    def normalized(self) -> "ProgramNode":
        from .normalize import normalize_node

        return normalize_node(self)


def _mapping_items(value: Mapping[object, object]) -> "list[tuple[object, object]]":
    return [(key, item) for key, item in value.items()]


def _sequence_items(value: Iterable[object]) -> "list[object]":
    return [item for item in value]


def _is_sequence(value: object) -> TypeGuard[Sequence[object]]:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _is_mapping(value: object) -> TypeGuard[Mapping[object, object]]:
    return isinstance(value, Mapping)


def _json_object(value: object) -> FrozenJsonObject:
    frozen = freeze_json_value(value)
    if not is_frozen_json_object(frozen):
        # kit:boundary owner=successor.language.program.codec class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.language.failure witness=test:test_program_metadata_codec_rejects_malformed_objects_as_typed_failure
        raise TypeError("expected a JSON object value")
    return frozen


def _json_dict(value: object, message: str) -> "dict[str, object]":
    if not _is_mapping(value):
        # kit:boundary owner=successor.language.program.codec class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.language.failure witness=test:test_program_codec_shape_guards_return_typed_failure
        raise ProgramCodecError(message)
    mapping = value
    result: "dict[str, object]" = {}
    for key_object, item in _mapping_items(mapping):
        result[str(key_object)] = item
    return result




def _json_array(value: object, message: str) -> "list[object]":
    if not _is_sequence(value):
        # kit:boundary owner=successor.language.program.codec class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.language.failure witness=test:test_program_codec_shape_guards_return_typed_failure
        raise ProgramCodecError(message)
    return _sequence_items(value)


def _json_text(value: object, message: str) -> str:
    if not isinstance(value, str):
        # kit:boundary owner=successor.language.program.codec class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.language.failure witness=test:test_program_codec_shape_guards_return_typed_failure
        raise ProgramCodecError(message)
    return value


def _json_text_tuple(value: object, message: str) -> "tuple[str, ...]":
    if not _is_sequence(value):
        # kit:boundary owner=successor.language.program.codec class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.language.failure witness=test:test_program_codec_shape_guards_return_typed_failure
        raise ProgramCodecError(message)
    items: "list[str]" = []
    for item in _sequence_items(value):
        if not isinstance(item, str):
            # kit:boundary owner=successor.language.program.codec class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.language.failure witness=test:test_program_codec_shape_guards_return_typed_failure
            raise ProgramCodecError(message)
        items.append(item)
    return tuple(items)


def _json_bool(value: object, message: str) -> bool:
    if not isinstance(value, bool):
        # kit:boundary owner=successor.language.program.codec class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.language.failure witness=test:test_program_codec_shape_guards_return_typed_failure
        raise ProgramCodecError(message)
    return value


def _json_int(value: object, message: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        # kit:boundary owner=successor.language.program.codec class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.language.failure witness=test:test_program_codec_shape_guards_return_typed_failure
        raise ProgramCodecError(message)
    return value


def _parse_json(text: str) -> object:
    import json

    parsed: object = json.loads(text)
    return parsed


def _encode_tagged(value: Any, tag: str) -> "dict[str, object]":
    encoded = canonical_json_bytes(_encode_plain(value)).decode("utf-8")
    return {"$tag": tag, "$json": encoded}



def _encode_plain(value: object) -> object:
    if is_frozen_json_object(value):
        return json.loads(canonical_json_bytes(value))
    if _is_mapping(value):
        if "$tag" in value and "$json" in value:
            return value
        encoded: "dict[str, object]" = {}
        for key_object, item in _mapping_items(value):
            key = str(key_object)
            encoded[key] = _encode_plain(item)
        return encoded
    if _is_sequence(value) and not isinstance(value, (str, bytes, bytearray)):
        items: "list[object]" = []
        for item in _sequence_items(value):
            items.append(_encode_plain(item))
        return items
    return _parse_json(canonical_json_bytes(value).decode("utf-8"))


def _metadata_plain(value: "FrozenJsonObject") -> "dict[str, object]":
    return {key: item for key, item in sorted(value, key=lambda pair: pair[0])}


def _check_then_types(first: "ProgramNode", second: "ProgramNode") -> None:
    if canonical_digest(first.output_type) != canonical_digest(second.input_type):
        # kit:boundary owner=successor.language.program class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.language.failure witness=test:test_program_try_failures_and_legacy_lift
        raise ProgramTypeError(
            f"Then type mismatch: {first.output_type.type_id} -> "
            f"{second.input_type.type_id}"
        )


def _check_runtime_object_type(object_type: object, endpoint: str) -> None:
    type_id = getattr(object_type, "type_id", None)
    schema_version = getattr(object_type, "schema_version", None)
    codec_id = getattr(object_type, "codec_id", None)
    canonical_codec_version = getattr(object_type, "canonical_codec_version", None)
    if (
        not isinstance(type_id, str)
        or not type_id
        or not isinstance(schema_version, str)
        or not schema_version
        or not isinstance(codec_id, str)
        or not codec_id
        or not isinstance(canonical_codec_version, str)
        or not canonical_codec_version
    ):
        # kit:boundary owner=successor.language.program class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.language.failure witness=test:test_atom_node_rejects_malformed_object_types_as_typed_failure
        raise ProgramTypeError(f"{endpoint} must be a complete ObjectType")
    if is_placeholder_object_type(object_type):
        if type_id not in {
            "placeholder:atom.input",
            "placeholder:atom.output",
        }:
            # kit:boundary owner=successor.language.program class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.language.failure witness=test:test_atom_node_rejects_foreign_placeholder_endpoint_as_typed_failure
            raise ProgramTypeError(f"malformed placeholder ObjectType at {endpoint}")
    try:
        canonical_digest(object_type)
    except (TypeError, ValueError) as error:
        # kit:boundary owner=successor.language.program class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.language.failure witness=test:test_atom_node_rejects_malformed_object_types_as_typed_failure
        raise ProgramTypeError(f"{endpoint} is not canonically encodable") from error


def _check_zip_types(left: "ProgramNode", right: "ProgramNode") -> None:
    if canonical_digest(left.input_type) != canonical_digest(right.input_type):
        # kit:boundary owner=successor.language.program class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.language.failure witness=test:test_program_try_failures_and_legacy_lift
        raise ProgramTypeError("ZipOrdered requires equal input types")


def _check_decide_branches(branches: "tuple[DecisionBranch, ...]") -> None:
    if not branches:
        # kit:boundary owner=successor.language.program class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.language.failure witness=test:test_program_try_failures_and_legacy_lift
        raise ProgramTypeError("Decide requires at least one branch")
    input_digest = canonical_digest(branches[0].program.input_type)
    output_digest = canonical_digest(branches[0].program.output_type)
    return_digest = canonical_digest(branches[0].program.return_contract)
    branch_ids: "set[str]" = set()
    for branch in branches:
        if not branch.branch_id:
            # kit:boundary owner=successor.language.program class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.language.failure witness=test:test_program_try_failures_and_legacy_lift
            raise ProgramTypeError("Decide branch requires a branch_id")
        if branch.branch_id in branch_ids:
            # kit:boundary owner=successor.language.program class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.language.failure witness=test:test_program_try_failures_and_legacy_lift
            raise ProgramTypeError(f"duplicate branch_id {branch.branch_id!r}")
        branch_ids.add(branch.branch_id)
        if canonical_digest(branch.program.input_type) != input_digest:
            # kit:boundary owner=successor.language.program class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.language.failure witness=test:test_program_try_failures_and_legacy_lift
            raise ProgramTypeError("Decide branch input types must agree")
        if canonical_digest(branch.program.output_type) != output_digest:
            # kit:boundary owner=successor.language.program class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.language.failure witness=test:test_program_try_failures_and_legacy_lift
            raise ProgramTypeError("Decide branch output types must agree")
        if canonical_digest(branch.program.return_contract) != return_digest:
            # kit:boundary owner=successor.language.program class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.language.failure witness=test:test_decide_node_rejects_branch_return_contract_drift_as_typed_failure
            raise ProgramTypeError("Decide branch return contracts must agree")


def tuple_object_type(types: "tuple[ObjectType, ...]") -> ObjectType:
    return ObjectType(
        type_id="tuple:" + ",".join(t.type_id for t in types),
        schema_version="1",
        codec_id="mrw.successor.tuple_codec.v1",
        canonical_codec_version="1",
    )


def sequence_object_type(element_type: ObjectType, *, version: str = "1") -> ObjectType:
    """Preserve v1 sequences; v2 codec identity binds the complete element type."""
    if version not in {"1", "2"}:
        _lift_program_failure(_program_failure(
            "PROGRAM_TYPE_INVALID", "unsupported sequence codec version", ValueError,
            site="sequence_object_type",
        ), ValueError)
    if version == "2":
        _check_runtime_object_type(element_type, "sequence.element_type")
        return ObjectType(
            type_id="sequence:" + element_type.type_id,
            schema_version="2",
            codec_id="mrw.successor.sequence_codec.v2:" + canonical_digest(element_type),
            canonical_codec_version="2",
        )
    return ObjectType(
        type_id="sequence:" + element_type.type_id,
        schema_version="1",
        codec_id="mrw.successor.sequence_codec.v1",
        canonical_codec_version="1",
    )


def try_identity_node(object_type: ObjectType) -> Identity:
    return Identity(object_type=object_type)


def identity_node(object_type: ObjectType) -> Identity:
    result = try_identity_node(object_type)
    if isinstance(result, Failure):
        _lift_program_failure(result, ValueError)
    return result


def try_pure_node(
    input_type: ObjectType,
    output_type: ObjectType,
    literal_value: object,
    literal_codec: str,
) -> Pure | Failure:
    try:
        frozen_literal = freeze_json_value(literal_value)
        return Pure(
            input_type_ref=input_type,
            output_type_ref=output_type,
            literal_codec=literal_codec,
            literal_digest=canonical_digest(frozen_literal),
            literal_value=frozen_literal,
        )
    except (AttributeError, TypeError, ValueError) as exc:
        return _program_failure(
            "PROGRAM_CODEC_INVALID", str(exc), type(exc), site="pure_node.literal"
        )


def pure_node(
    input_type: ObjectType,
    output_type: ObjectType,
    literal_value: object,
    literal_codec: str,
) -> Pure:
    result = try_pure_node(input_type, output_type, literal_value, literal_codec)
    if isinstance(result, Failure):
        _lift_program_failure(result, _exception_type_from_failure(result))
    return result


def content_addressed_literal(value: "dict[str, Any]") -> "dict[str, object]":
    """Bind a literal's ``content_digest`` to its canonical content bytes.

    The digest excludes its own field.  Callers cannot supply a sentinel or a
    stale digest because this constructor derives the field after copying the
    complete literal payload.
    """

    content = {key: item for key, item in value.items() if key != "content_digest"}
    return {**content, "content_digest": canonical_digest(content)}


def try_atom_node(
    operation: OperationSpec,
    input_type: "ObjectType | None" = None,
    output_type: "ObjectType | None" = None,
    return_contract: "ReturnContract | None" = None,
) -> Atom | Failure:
    try:
        resolved_input = input_type or _placeholder_type("atom.input")
        resolved_output = output_type or _placeholder_type("atom.output")
        _check_runtime_object_type(resolved_input, "atom.input")
        _check_runtime_object_type(resolved_output, "atom.output")
        resolved_return = return_contract or default_return_contract()
        _check_return_contract(resolved_return)
        return Atom(
            operation=operation,
            input_type=resolved_input,
            output_type=resolved_output,
            return_contract=resolved_return,
        )
    except (AttributeError, TypeError, ValueError) as exc:
        return _program_failure(
            "PROGRAM_TYPE_INVALID", str(exc), type(exc), site="atom_node"
        )


def atom_node(
    operation: OperationSpec,
    input_type: "ObjectType | None" = None,
    output_type: "ObjectType | None" = None,
    return_contract: "ReturnContract | None" = None,
) -> Atom:
    result = try_atom_node(operation, input_type, output_type, return_contract)
    if isinstance(result, Failure):
        _lift_program_failure(result, _exception_type_from_failure(result))
    return result


def try_then_node(first: "ProgramNode", second: "ProgramNode") -> Then | Failure:
    try:
        _check_then_types(first, second)
        return Then(first=first, second=second)
    except (AttributeError, TypeError, ValueError) as exc:
        return _program_failure(
            "PROGRAM_TYPE_INVALID", str(exc), type(exc), site="then_node"
        )


def then_node(first: "ProgramNode", second: "ProgramNode") -> Then:
    result = try_then_node(first, second)
    if isinstance(result, Failure):
        _lift_program_failure(result, ProgramTypeError)
    return result


def try_map_output_node(
    source: "ProgramNode",
    transform_ref: "TransformRef",
    target_type: ObjectType,
) -> MapOutput | Failure:
    try:
        _check_runtime_object_type(target_type, "map_output.target_type")
        if is_placeholder_object_type(target_type):
            # kit:boundary owner=successor.language.program class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.language.failure witness=test:test_map_output_and_zip_ordered_reject_unresolved_target_as_typed_failure
            raise ProgramTypeError("MapOutput target_type cannot be unresolved")
        return MapOutput(
            source=source,
            transform_ref=transform_ref,
            target_type=target_type,
        )
    except (AttributeError, TypeError, ValueError) as exc:
        return _program_failure(
            "PROGRAM_TYPE_INVALID", str(exc), type(exc), site="map_output_node"
        )


def map_output_node(
    source: "ProgramNode",
    transform_ref: "TransformRef",
    target_type: ObjectType,
) -> MapOutput:
    result = try_map_output_node(source, transform_ref, target_type)
    if isinstance(result, Failure):
        _lift_program_failure(result, ValueError)
    return result


def try_zip_ordered_node(
    left: "ProgramNode",
    right: "ProgramNode",
    merge_ref: "MergeRef",
    output_type: "ObjectType | None" = None,
) -> ZipOrdered | Failure:
    try:
        _check_zip_types(left, right)
        if output_type is None:
            output_type = tuple_object_type((left.output_type, right.output_type))
        _check_runtime_object_type(output_type, "zip_ordered.output_type")
        if is_placeholder_object_type(output_type):
            # kit:boundary owner=successor.language.program class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.language.failure witness=test:test_map_output_and_zip_ordered_reject_unresolved_target_as_typed_failure
            raise ProgramTypeError("ZipOrdered output_type cannot be unresolved")
        return ZipOrdered(
            left=left,
            right=right,
            merge_ref=merge_ref,
            output_type=output_type,
        )
    except (AttributeError, TypeError, ValueError) as exc:
        return _program_failure(
            "PROGRAM_TYPE_INVALID", str(exc), type(exc), site="zip_ordered_node"
        )


def zip_ordered_node(
    left: "ProgramNode",
    right: "ProgramNode",
    merge_ref: "MergeRef",
    output_type: "ObjectType | None" = None,
) -> ZipOrdered:
    result = try_zip_ordered_node(left, right, merge_ref, output_type)
    if isinstance(result, Failure):
        _lift_program_failure(result, ProgramTypeError)
    return result


def try_traverse_ordered_node(
    element_program: "ProgramNode",
    traversal_policy: str,
    *, sequence_codec_version: str = "1",
) -> TraverseOrdered | Failure:
    try:
        node = TraverseOrdered(
            element_program=element_program,
            traversal_policy=traversal_policy,
            sequence_codec_version=sequence_codec_version,
        )
        _check_runtime_object_type(node.input_type, "traverse_ordered.input_type")
        _check_runtime_object_type(node.output_type, "traverse_ordered.output_type")
        return node
    except (AttributeError, TypeError, ValueError) as exc:
        return _program_failure(
            "PROGRAM_TYPE_INVALID", str(exc), type(exc), site="traverse_ordered_node"
        )


def traverse_ordered_node(
    element_program: "ProgramNode",
    traversal_policy: str,
    *, sequence_codec_version: str = "1",
) -> TraverseOrdered:
    result = try_traverse_ordered_node(element_program, traversal_policy, sequence_codec_version=sequence_codec_version)
    if isinstance(result, Failure):
        _lift_program_failure(result, ValueError)
    return result


def try_decide_node(
    discriminator_ref: "DiscriminatorRef",
    branches: "tuple[DecisionBranch, ...]",
) -> Decide | Failure:
    try:
        _check_decide_branches(branches)
        return Decide(
            discriminator_ref=discriminator_ref,
            branches=branches,
        )
    except (AttributeError, TypeError, ValueError) as exc:
        return _program_failure(
            "PROGRAM_TYPE_INVALID", str(exc), type(exc), site="decide_node"
        )


def decide_node(
    discriminator_ref: "DiscriminatorRef",
    branches: "tuple[DecisionBranch, ...]",
) -> Decide:
    result = try_decide_node(discriminator_ref, branches)
    if isinstance(result, Failure):
        _lift_program_failure(result, ProgramTypeError)
    return result


def _placeholder_type(type_id: str) -> ObjectType:
    return placeholder_object_type(type_id.removeprefix("placeholder:"))


def _string_modes(value: "tuple[object, ...]", field_name: str) -> None:
    if type(value) is not tuple:
        # kit:boundary owner=successor.language.program.return_contract class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.language.failure witness=test:test_atom_node_rejects_invalid_return_contract_shapes_as_typed_failure
        raise ProgramTypeError(f"ReturnContract.{field_name} must be a string tuple")
    for mode in value:
        if not isinstance(mode, str):
            # kit:boundary owner=successor.language.program.return_contract class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.language.failure witness=test:test_atom_node_rejects_invalid_return_contract_shapes_as_typed_failure
            raise ProgramTypeError(f"ReturnContract.{field_name} must be a string tuple")


def _check_return_contract(return_contract: ReturnContract) -> None:
    _string_modes(return_contract.success_modes, "success_modes")
    _string_modes(return_contract.failure_modes, "failure_modes")
    _string_modes(return_contract.wait_modes, "wait_modes")
    _string_modes(return_contract.cancel_modes, "cancel_modes")
    if type(return_contract.admission_required) is not bool:
        # kit:boundary owner=successor.language.program class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.language.failure witness=test:test_atom_node_rejects_invalid_return_contract_shapes_as_typed_failure
        raise ProgramTypeError("ReturnContract.admission_required must be boolean")
    if not return_contract.success_modes or not return_contract.failure_modes:
        # kit:boundary owner=successor.language.program class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.language.failure witness=test:test_atom_node_rejects_invalid_return_contract_shapes_as_typed_failure
        raise ProgramTypeError("ReturnContract requires success and failure modes")

@dataclass(frozen=True, slots=True)
class ProgramSpec:
    program_id: str
    contract_version: str
    project_key: str
    project_registry_revision: int
    project_scope_digest: str
    semantic_identity: str
    input_type: ObjectType
    output_type: ObjectType
    root: "ProgramNode"
    algebra_refs: "tuple[AlgebraRef, ...]"
    transform_refs: "tuple[TransformReference, ...]"
    observation_profile: str
    metadata: FrozenJsonObject
    program_digest: str

    def payload_dict(self) -> "dict[str, object]":
        return {
            "codec": PROGRAM_AST_CODEC_ID,
            "program_id": self.program_id,
            "contract_version": self.contract_version,
            "project_key": self.project_key,
            "project_registry_revision": self.project_registry_revision,
            "project_scope_digest": self.project_scope_digest,
            "semantic_identity": self.semantic_identity,
            "input_type": _encode_tagged(self.input_type, "object_type"),
            "output_type": _encode_tagged(self.output_type, "object_type"),
            "root": self.root.encode_ast(),
            "algebra_refs": [
                _encode_tagged(ref, "algebra_ref") for ref in self.algebra_refs
            ],
            "transform_refs": [
                _encode_tagged(ref, "transform_ref") for ref in self.transform_refs
            ],
            "observation_profile": self.observation_profile,
            "metadata": _metadata_plain(self.metadata),
        }

    def canonical_json(self) -> bytes:
        return canonical_json_bytes(self.payload_dict())

    def digest(self) -> str:
        return sha256_digest_bytes(self.canonical_json())

    def with_digest(self) -> "ProgramSpec":
        return ProgramSpec(
            program_id=self.program_id,
            contract_version=self.contract_version,
            project_key=self.project_key,
            project_registry_revision=self.project_registry_revision,
            project_scope_digest=self.project_scope_digest,
            semantic_identity=self.semantic_identity,
            input_type=self.input_type,
            output_type=self.output_type,
            root=self.root,
            algebra_refs=self.algebra_refs,
            transform_refs=self.transform_refs,
            observation_profile=self.observation_profile,
            metadata=self.metadata,
            program_digest=self.digest(),
        )


def try_bind_program_contracts(
    program: ProgramSpec,
    operation_contract_resolver: "OperationContractResolver",
) -> ProgramSpecResult:
    """Bind construction-time Atom placeholders to exact operation contracts.

    Explicit endpoint and ReturnContract witnesses are checked, never silently
    overwritten. Placeholders are replaced only on the endpoint to which they
    were issued, after the exact contract ref resolves.
    """

    try:
        _check_binding_endpoint(
            program.input_type, program.root.input_type, "program.input_type"
        )
        _check_binding_endpoint(
            program.output_type, program.root.output_type, "program.output_type"
        )
        root = _bind_node_contracts(program.root, operation_contract_resolver, "root")
        return replace(program, input_type=root.input_type,
                       output_type=root.output_type, root=root,
                       program_digest="").with_digest()
    except (AttributeError, TypeError, ValueError, KeyError) as exc:
        return _program_failure(
            "PROGRAM_TYPE_INVALID",
            str(exc),
            type(exc),
            site="bind_program_contracts",
        )


def bind_program_contracts(
    program: ProgramSpec,
    operation_contract_resolver: "OperationContractResolver",
) -> ProgramSpec:
    result = try_bind_program_contracts(program, operation_contract_resolver)
    if isinstance(result, Failure):
        _lift_program_failure(result, _exception_type_from_failure(result))
    return result


_RETURN_CONTRACT_REGISTRY = build_first_specimen_return_contract_registry()


def _bind_node_contracts(
    node: ProgramNode,
    resolver: "OperationContractResolver",
    path: str,
) -> ProgramNode:
    if isinstance(node, Atom):
        return _bind_atom_contracts(node, resolver, path)
    if isinstance(node, Then):
        return Then(
            first=_bind_node_contracts(node.first, resolver, f"{path}.first"),
            second=_bind_node_contracts(node.second, resolver, f"{path}.second"),
        )
    if isinstance(node, MapOutput):
        if is_placeholder_object_type(node.target_type):
            # kit:boundary owner=successor.language.program class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.language.failure witness=test:test_bind_contracts_rejects_unresolved_node_placeholders_as_typed_failure
            raise ProgramTypeError(f"unresolved target placeholder at {path}")
        return MapOutput(
            source=_bind_node_contracts(node.source, resolver, f"{path}.source"),
            transform_ref=node.transform_ref,
            target_type=node.target_type,
        )
    if isinstance(node, ZipOrdered):
        if is_placeholder_object_type(node.output_type):
            # kit:boundary owner=successor.language.program class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.language.failure witness=test:test_bind_contracts_rejects_unresolved_node_placeholders_as_typed_failure
            raise ProgramTypeError(f"unresolved output placeholder at {path}")
        return ZipOrdered(
            left=_bind_node_contracts(node.left, resolver, f"{path}.left"),
            right=_bind_node_contracts(node.right, resolver, f"{path}.right"),
            merge_ref=node.merge_ref,
            output_type=node.output_type,
        )
    if isinstance(node, TraverseOrdered):
        return traverse_ordered_node(
            _bind_node_contracts(
                node.element_program, resolver, f"{path}.element_program"
            ),
            node.traversal_policy,
            sequence_codec_version=node.sequence_codec_version,
        )
    if isinstance(node, Decide):
        return decide_node(
            node.discriminator_ref,
            tuple(
                DecisionBranch(
                    branch_id=branch.branch_id,
                    guard=branch.guard,
                    program=_bind_node_contracts(
                        branch.program,
                        resolver,
                        f"{path}.branches[{branch.branch_id}]",
                    ),
                )
                for branch in node.branches
            ),
        )
    if is_placeholder_object_type(node.input_type) or is_placeholder_object_type(
        node.output_type
    ):
        # kit:boundary owner=successor.language.program class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.language.failure witness=test:test_bind_contracts_rejects_unresolved_node_placeholders_as_typed_failure
        raise ProgramTypeError(f"unresolved placeholder at {path}")
    return node


def _bind_atom_contracts(
    node: Atom,
    resolver: "OperationContractResolver",
    path: str,
) -> Atom:
    contract = resolver.resolve(node.operation.contract_ref)
    if contract is None:
        # kit:boundary owner=successor.language.program class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.language.failure witness=test:test_bind_contracts_rejects_unresolved_operation_contract_as_typed_failure
        raise KeyError(
            f"unresolved operation contract at {path}: "
            f"{node.operation.contract_ref.kind}"
        )
    input_type = _bind_endpoint(
        node.input_type, contract.input_type, "placeholder:atom.input", f"{path}.input_type"
    )
    output_type = _bind_endpoint(
        node.output_type,
        contract.output_type,
        "placeholder:atom.output",
        f"{path}.output_type",
    )
    expected_return = _RETURN_CONTRACT_REGISTRY.resolve(contract.return_contract_ref)
    if expected_return is None:
        # kit:boundary owner=successor.language.program class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.language.failure witness=test:test_bind_contracts_rejects_unresolved_return_contract_as_typed_failure
        raise KeyError(
            f"unresolved return contract at {path}: {contract.return_contract_ref}"
        )
    if (
        node.return_contract.success_modes != expected_return.success_modes
        or node.return_contract.failure_modes != expected_return.failure_modes
        or node.return_contract.wait_modes != expected_return.wait_modes
        or node.return_contract.cancel_modes != expected_return.cancel_modes
    ):
        # kit:boundary owner=successor.language.program class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.language.failure witness=test:test_contract_binding_rejects_wrong_endpoint_and_return_witness
        raise ProgramTypeError(f"ReturnContract mismatch at {path}")
    bound_inputs: "list[ValueRef]" = []
    for index, value_ref in enumerate(node.operation.input_refs):
        object_type = value_ref.object_type
        if is_placeholder_object_type(object_type):
            _check_placeholder_endpoint(
                object_type, "placeholder:atom.input", f"{path}.input_refs[{index}]"
            )
            object_type = contract.input_type
        bound_inputs.append(replace(value_ref, object_type=object_type))
    payload_object_type = node.operation.payload_ref.object_type
    if is_placeholder_object_type(payload_object_type):
        _check_placeholder_endpoint(
            payload_object_type,
            "placeholder:atom.input",
            f"{path}.payload_ref",
        )
        payload_object_type = contract.input_type
    payload_ref = replace(
        node.operation.payload_ref,
        object_type=payload_object_type,
    )
    operation = OperationSpec(
        operation_id=node.operation.operation_id,
        contract_ref=node.operation.contract_ref,
        input_refs=tuple(bound_inputs),
        payload_ref=payload_ref,
        allowed_overrides=node.operation.allowed_overrides,
    )
    return Atom(
        operation=operation,
        input_type=input_type,
        output_type=output_type,
        return_contract=expected_return,
    )


def _bind_endpoint(
    current: ObjectType,
    authoritative: ObjectType,
    placeholder_type_id: str,
    path: str,
) -> ObjectType:
    if is_placeholder_object_type(current):
        if current.type_id != placeholder_type_id:
            # kit:boundary owner=successor.language.program class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.language.failure witness=test:test_bind_contracts_rejects_placeholder_issued_for_other_endpoint_as_typed_failure
            raise ProgramTypeError(f"placeholder issued for another endpoint at {path}")
        return authoritative
    if current != authoritative:
        # kit:boundary owner=successor.language.program class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.language.failure witness=test:test_contract_binding_rejects_wrong_endpoint_and_return_witness
        raise ProgramTypeError(f"ObjectType does not match OperationContract at {path}")
    return current


def _check_placeholder_endpoint(
    object_type: ObjectType, expected_type_id: str, path: str
) -> None:
    if object_type.type_id != expected_type_id:
        # kit:boundary owner=successor.language.program class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.language.failure witness=test:test_bind_contracts_rejects_placeholder_issued_for_other_endpoint_as_typed_failure
        raise ProgramTypeError(f"placeholder issued for another endpoint at {path}")


def _check_binding_endpoint(
    declared: ObjectType, root: ObjectType, path: str
) -> None:
    if declared == root:
        return
    if is_placeholder_object_type(declared) and is_placeholder_object_type(root):
        return
    # kit:boundary owner=successor.language.program class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.language.failure witness=test:test_bind_contracts_rejects_endpoint_mismatch_with_root_as_typed_failure
    raise ProgramTypeError(f"{path} does not match the root endpoint")


@dataclass(frozen=True, slots=True)
class SuccessorMaterialization:
    """Frozen post-run record for one deterministic successor ProgramSpec.

    This is a language-level value only.  Persistence and enforcement through
    ``runtime_idempotency`` belong to the P0-B runtime substrate.
    """

    materialization_id: str
    predecessor_run_id: str
    predecessor_step_id: str
    predecessor_plan_digest: str
    source_value_ref: ValueRef
    materializer_id: str
    materializer_version: str
    authority_digest: str
    idempotency_key: str
    successor_program: ProgramSpec
    successor_program_digest: str
    state: Literal["PREPARED", "MATERIALIZED", "REJECTED"]
    reason: str

    def __post_init__(self) -> None:
        required = (
            self.materialization_id,
            self.predecessor_run_id,
            self.predecessor_step_id,
            self.predecessor_plan_digest,
            self.materializer_id,
            self.materializer_version,
            self.authority_digest,
            self.idempotency_key,
            self.successor_program_digest,
        )
        if any(not value for value in required):
            # kit:boundary owner=successor.language.materialization class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.language.failure witness=test:test_program_try_failures_and_legacy_lift
            raise ValueError("successor materialization identities must be non-empty")
        if self.state not in {"PREPARED", "MATERIALIZED", "REJECTED"}:
            # kit:boundary owner=successor.language.materialization class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.language.failure witness=test:test_program_try_failures_and_legacy_lift
            raise ValueError(f"unsupported successor materialization state {self.state!r}")
        expected_digest = self.successor_program.digest()
        if self.successor_program.program_digest != expected_digest:
            # kit:boundary owner=successor.language.materialization class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.language.failure witness=test:test_program_try_failures_and_legacy_lift
            raise ValueError("successor ProgramSpec carries a stale program_digest")
        if self.successor_program_digest != expected_digest:
            # kit:boundary owner=successor.language.materialization class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.language.failure witness=test:test_program_try_failures_and_legacy_lift
            raise ValueError("successor_program_digest does not match successor ProgramSpec")


def try_successor_materialization(
    *,
    materialization_id: str,
    predecessor_run_id: str,
    predecessor_step_id: str,
    predecessor_plan_digest: str,
    source_value_ref: ValueRef,
    materializer_id: str,
    materializer_version: str,
    authority_digest: str,
    idempotency_key: str,
    successor_program: ProgramSpec,
    successor_program_digest: str,
    state: Literal["PREPARED", "MATERIALIZED", "REJECTED"],
    reason: str,
) -> SuccessorMaterialization | Failure:
    try:
        return SuccessorMaterialization(
            materialization_id=materialization_id,
            predecessor_run_id=predecessor_run_id,
            predecessor_step_id=predecessor_step_id,
            predecessor_plan_digest=predecessor_plan_digest,
            source_value_ref=source_value_ref,
            materializer_id=materializer_id,
            materializer_version=materializer_version,
            authority_digest=authority_digest,
            idempotency_key=idempotency_key,
            successor_program=successor_program,
            successor_program_digest=successor_program_digest,
            state=state,
            reason=reason,
        )
    except (TypeError, ValueError) as exc:
        message = str(exc)
        code = (
            "PROGRAM_DIGEST_MISMATCH"
            if "stale program_digest" in message
            or "successor_program_digest does not match" in message
            else "PROGRAM_MATERIALIZATION_INVALID"
        )
        return _program_failure(code, message, type(exc), site="SuccessorMaterialization")

def encode_program_spec(spec: ProgramSpec) -> "dict[str, object]":
    payload = json.loads(spec.canonical_json())
    return {
        "schema": "mrw.functorial_successor.program_spec.v1",
        "program": payload,
        "program_digest": spec.digest(),
    }


def program_digest(spec: ProgramSpec) -> str:
    return spec.digest()


def _decode_program_spec_impl(payload: "dict[str, object]") -> ProgramSpec:
    from .algebra import AlgebraRef
    from .transforms import DiscriminatorRef, MergeRef, TransformRef

    try:
        declared_digest = _json_text(payload.get("program_digest"), "program_digest must be text")
        program = _json_dict(payload.get("program"), "program must be an object")
        codec = _json_text(program.get("codec"), "codec must be text")
        if codec != PROGRAM_AST_CODEC_ID:
            # kit:boundary owner=successor.language.program class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.language.failure witness=test:test_program_try_failures_and_legacy_lift
            raise ProgramCodecError(f"unsupported AST codec {codec!r}")
        root = _decode_ast_impl(program.get("root"))
        input_type = _decode_type(program.get("input_type"))
        output_type = _decode_type(program.get("output_type"))
        metadata_value = _unwrap_tags(program.get("metadata"))
        metadata = _json_object(metadata_value)
        algebra_refs: "list[AlgebraRef]" = []
        for item in _decode_array(program.get("algebra_refs")):
            fields = _decode_tagged(item, "algebra_ref")
            algebra_refs.append(
                AlgebraRef(
                    algebra_id=_json_text(fields.get("algebra_id"), "algebra_id must be text"),
                    algebra_version=_json_text(fields.get("algebra_version"), "algebra_version must be text"),
                )
            )
        transform_refs: "list[TransformReference]" = []
        for item in _decode_array(program.get("transform_refs")):
            fields = _decode_tagged(item, "transform_ref")
            name = _json_text(fields.get("name"), "transform name must be text")
            version = _json_text(fields.get("version"), "transform version must be text")
            digest = _json_text(fields.get("digest"), "transform digest must be text")
            transform_kind = _json_text(
                fields.get("transform_kind", "transform"),
                "transform_kind must be text",
            )
            if transform_kind == "merge":
                transform_ref: TransformReference = MergeRef(
                    name=name,
                    version=version,
                    digest=digest,
                )
            elif transform_kind == "discriminator":
                transform_ref = DiscriminatorRef(
                    name=name,
                    version=version,
                    digest=digest,
                )
            elif transform_kind == "transform":
                transform_ref = TransformRef(
                    name=name,
                    version=version,
                    digest=digest,
                )
            else:
                # kit:boundary owner=successor.language.program.codec class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.language.failure witness=test:test_program_codec_rejects_unknown_transform_kind_as_typed_failure_and_legacy_lift
                raise ProgramCodecError(
                    f"unsupported transform reference kind {transform_kind!r}"
                )
            transform_refs.append(transform_ref)
        observation_profile = _json_text(program.get("observation_profile"), "observation_profile must be text")
        spec = ProgramSpec(
            program_id=_json_text(program.get("program_id"), "program_id must be text"),
            contract_version=_json_text(program.get("contract_version"), "contract_version must be text"),
            project_key=_json_text(program.get("project_key"), "project_key must be text"),
            project_registry_revision=_json_int(program.get("project_registry_revision"), "project_registry_revision must be an integer"),
            project_scope_digest=_json_text(program.get("project_scope_digest"), "project_scope_digest must be text"),
            semantic_identity=_json_text(program.get("semantic_identity"), "semantic_identity must be text"),
            input_type=input_type,
            output_type=output_type,
            root=root,
            algebra_refs=tuple(algebra_refs),
            transform_refs=tuple(transform_refs),
            observation_profile=observation_profile,
            metadata=metadata,
            program_digest="",
        )
        decoded = spec.with_digest()
        if declared_digest != decoded.program_digest:
            # kit:boundary owner=successor.language.program class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.language.failure witness=test:test_decode_rejects_tampered_canonical_program_bytes
            raise ProgramCodecError(
                "program_digest does not bind canonical ProgramSpec bytes"
            )
        return decoded
    except KeyError as exc:
        # kit:boundary owner=successor.language.program class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.language.failure witness=test:test_program_try_failures_and_legacy_lift
        raise ProgramCodecError(f"malformed program spec payload: {exc}") from exc


def try_decode_program_spec(payload: "dict[str, object]") -> ProgramSpec | Failure:
    try:
        return _decode_program_spec_impl(payload)
    except ProgramCodecError as exc:
        message = str(exc)
        if "node_kind" in message:
            code = "UNKNOWN_NODE_KIND"
        elif "program_digest does not bind" in message:
            code = "PROGRAM_DIGEST_MISMATCH"
        else:
            code = "PROGRAM_CODEC_INVALID"
        return _program_failure(
            code, message, ProgramCodecError, site="decode_program_spec"
        )
    except (TypeError, ValueError, KeyError) as exc:
        return _program_failure(
            "PROGRAM_CODEC_INVALID", str(exc), type(exc), site="decode_program_spec"
        )


def decode_program_spec(payload: "dict[str, object]") -> ProgramSpec:
    result = try_decode_program_spec(payload)
    if isinstance(result, Failure):
        _lift_program_failure(result, _exception_type_from_failure(result))
    return result


def _decode_type(value: object) -> ObjectType:
    from .algebra import ObjectType as _ObjectType

    fields = _json_dict(value, "expected object_type value")
    if fields.get("$tag") == "object_type":
        fields = _decode_tagged(value, "object_type")
    elif "type_id" not in fields:
        # kit:boundary owner=successor.language.program class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.language.failure witness=test:test_program_try_failures_and_legacy_lift
        raise ProgramCodecError("expected object_type value")
    return _ObjectType(
        type_id=_json_text(fields.get("type_id"), "type_id must be text"),
        schema_version=_json_text(fields.get("schema_version"), "schema_version must be text"),
        codec_id=_json_text(fields.get("codec_id"), "codec_id must be text"),
        canonical_codec_version=_json_text(fields.get("canonical_codec_version"), "canonical_codec_version must be text"),
    )


def _decode_tagged(value: object, tag: str) -> "dict[str, object]":
    fields = _json_dict(value, f"expected tagged value {tag!r}")
    if fields.get("$tag") != tag:
        # kit:boundary owner=successor.language.program class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.language.failure witness=test:test_program_try_failures_and_legacy_lift
        raise ProgramCodecError(f"expected tagged value {tag!r}")
    encoded = _json_text(fields.get("$json"), f"expected encoded value {tag!r}")
    decoded = _unwrap_tags(_parse_json(encoded))
    unwrapped = _json_dict(decoded, f"expected tagged object {tag!r}")
    if set(unwrapped) == {tag}:
        return _json_dict(unwrapped[tag], f"expected tagged object {tag!r}")
    return unwrapped


def _unwrap_tags(value: object) -> object:
    if _is_mapping(value):
        fields = _json_dict(value, "JSON object keys must be text")
        if "$tag" in fields and "$json" in fields:
            encoded = _json_text(fields.get("$json"), "expected encoded JSON text")
            return _unwrap_tags(_parse_json(encoded))
        result: "dict[str, object]" = {}
        for key, item in fields.items():
            result[key] = _unwrap_tags(item)
        return result
    if _is_sequence(value) and not isinstance(value, (str, bytes, bytearray)):
        items = _sequence_items(value)
        if items and items[0] == "$array":
            return _unwrap_tags(items[1])
        result_list: "list[object]" = []
        for item in items:
            result_list.append(_unwrap_tags(item))
        return result_list
    return value


def _decode_array(value: object) -> "list[object]":
    if _is_sequence(value):
        items = _sequence_items(value)
        if items and items[0] == "$array":
            return _json_array(items[1], "expected encoded array")
        return items
    # kit:boundary owner=successor.language.program class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.language.failure witness=test:test_program_try_failures_and_legacy_lift
    raise ProgramCodecError("expected encoded array")


def _decode_json_object(value: object) -> "dict[str, object]":
    if _is_mapping(value):
        return _json_dict(value, "expected encoded object")
    # kit:boundary owner=successor.language.program class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.language.failure witness=test:test_program_try_failures_and_legacy_lift
    raise ProgramCodecError("expected encoded object")


def _decode_ast_impl(value: object) -> ProgramNode:
    from .transforms import DiscriminatorRef, MergeRef, TransformRef

    fields = _json_dict(value, "AST node must be an object")
    node_kind = _json_text(fields.get("node_kind"), "node_kind must be text")
    if node_kind not in ALLOWED_NODE_KINDS:
        # kit:boundary owner=successor.language.program class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.language.failure witness=test:test_program_try_failures_and_legacy_lift
        raise ProgramCodecError(f"unknown node_kind {node_kind!r}")
    if node_kind == "identity":
        return Identity(object_type=_decode_type(fields.get("object_type")))
    if node_kind == "pure":
        literal_value = _unwrap_tags(fields.get("literal_value"))
        return Pure(
            input_type_ref=_decode_type(fields.get("input_type_ref")),
            output_type_ref=_decode_type(fields.get("output_type_ref")),
            literal_codec=_json_text(fields.get("literal_codec"), "literal_codec must be text"),
            literal_digest=_json_text(fields.get("literal_digest"), "literal_digest must be text"),
            literal_value=freeze_json_value(literal_value),
        )
    if node_kind == "atom":
        operation_fields = _decode_tagged(fields.get("operation"), "operation_spec")
        contract_ref_value = operation_fields.get("contract_ref")
        contract_ref_fields = _json_dict(contract_ref_value, "contract_ref must be an object")
        if set(contract_ref_fields) == {"operation_contract_ref"}:
            contract_ref_value = contract_ref_fields["operation_contract_ref"]
        contract_fields = _json_dict(contract_ref_value, "contract_ref must be an object")
        input_refs: "list[ValueRef]" = []
        for item in _decode_array(operation_fields.get("input_refs")):
            input_refs.append(_decode_value_ref(item))
        operation = OperationSpec(
            operation_id=_json_text(operation_fields.get("operation_id"), "operation_id must be text"),
            contract_ref=OperationContractRef(
                kind=_json_text(contract_fields.get("kind"), "kind must be text"),
                contract_version=_json_text(contract_fields.get("contract_version"), "contract_version must be text"),
                contract_digest=_json_text(contract_fields.get("contract_digest"), "contract_digest must be text"),
            ),
            input_refs=tuple(input_refs),
            payload_ref=_decode_value_ref(operation_fields.get("payload_ref")),
            allowed_overrides=_json_object(_decode_json_object(operation_fields.get("allowed_overrides"))),
        )
        rc_fields = _decode_tagged(fields.get("return_contract"), "return_contract")
        return Atom(
            operation=operation,
            input_type=_decode_type(fields.get("input_type")),
            output_type=_decode_type(fields.get("output_type")),
            return_contract=ReturnContract(
                success_modes=_json_text_tuple(rc_fields.get("success_modes"), "success_modes must be a tuple"),
                failure_modes=_json_text_tuple(rc_fields.get("failure_modes"), "failure_modes must be a tuple"),
                admission_required=_json_bool(rc_fields.get("admission_required"), "admission_required must be boolean"),
                wait_modes=_json_text_tuple(rc_fields.get("wait_modes", ()), "wait_modes must be a tuple"),
                cancel_modes=_json_text_tuple(rc_fields.get("cancel_modes", ()), "cancel_modes must be a tuple"),
            ),
        )
    if node_kind == "then":
        return Then(
            first=_decode_ast_impl(fields.get("first")),
            second=_decode_ast_impl(fields.get("second")),
        )
    if node_kind == "map_output":
        tf = _decode_tagged(fields.get("transform_ref"), "transform_ref")
        return MapOutput(
            source=_decode_ast_impl(fields.get("source")),
            transform_ref=TransformRef(
                name=_json_text(tf.get("name"), "transform name must be text"),
                version=_json_text(tf.get("version"), "transform version must be text"),
                digest=_json_text(tf.get("digest"), "transform digest must be text"),
                transform_kind=_json_text(tf.get("transform_kind", "transform"), "transform_kind must be text"),
            ),
            target_type=_decode_type(fields.get("target_type")),
        )
    if node_kind == "zip_ordered":
        mf = _decode_tagged(fields.get("merge_ref"), "merge_ref")
        return ZipOrdered(
            left=_decode_ast_impl(fields.get("left")),
            right=_decode_ast_impl(fields.get("right")),
            merge_ref=MergeRef(
                name=_json_text(mf.get("name"), "merge name must be text"),
                version=_json_text(mf.get("version"), "merge version must be text"),
                digest=_json_text(mf.get("digest"), "merge digest must be text"),
                transform_kind=_json_text(mf.get("transform_kind", "merge"), "transform_kind must be text"),
            ),
            output_type=_decode_type(fields.get("output_type")),
        )
    if node_kind == "traverse_ordered":
        return TraverseOrdered(
            element_program=_decode_ast_impl(fields.get("element_program")),
            traversal_policy=_json_text(fields.get("traversal_policy"), "traversal_policy must be text"),
            sequence_codec_version=_json_text(fields.get("sequence_codec_version", "1"), "sequence_codec_version must be text"),
        )
    df = _decode_tagged(fields.get("discriminator_ref"), "discriminator_ref")
    branches: "list[DecisionBranch]" = []
    for item in _decode_array(fields.get("branches")):
        branch = _json_dict(item, "decision branch must be an object")
        branches.append(
            DecisionBranch(
                branch_id=_json_text(branch.get("branch_id"), "branch_id must be text"),
                guard=_json_text(branch.get("guard"), "guard must be text"),
                program=_decode_ast_impl(branch.get("program")),
            )
        )
    return Decide(
        discriminator_ref=DiscriminatorRef(
            name=_json_text(df.get("name"), "discriminator name must be text"),
            version=_json_text(df.get("version"), "discriminator version must be text"),
            digest=_json_text(df.get("digest"), "discriminator digest must be text"),
            transform_kind=_json_text(df.get("transform_kind", "discriminator"), "transform_kind must be text"),
        ),
        branches=tuple(branches),
    )


def try_decode_ast(value: object) -> ProgramNode | Failure:
    try:
        return _decode_ast_impl(value)
    except ProgramCodecError as exc:
        message = str(exc)
        code = "UNKNOWN_NODE_KIND" if "node_kind" in message else "PROGRAM_CODEC_INVALID"
        return _program_failure(code, message, ProgramCodecError, site="decode_ast")
    except (TypeError, ValueError, KeyError) as exc:
        return _program_failure(
            "PROGRAM_CODEC_INVALID", str(exc), type(exc), site="decode_ast"
        )


def decode_ast(value: object) -> ProgramNode:
    result = try_decode_ast(value)
    if isinstance(result, Failure):
        _lift_program_failure(result, _exception_type_from_failure(result))
    return result


def _decode_value_ref(value: object) -> ValueRef:
    from .algebra import ValueRef as _ValueRef

    fields = _json_dict(value, "value ref must be an object")
    return _ValueRef(
        value_id=_json_text(fields.get("value_id"), "value_id must be text"),
        project_key=_json_text(fields.get("project_key"), "project_key must be text"),
        object_type=_decode_type(fields.get("object_type")),
        codec_id=_json_text(fields.get("codec_id"), "codec_id must be text"),
        content_digest=_json_text(fields.get("content_digest"), "content_digest must be text"),
        storage_kind=_decode_storage_kind(fields.get("storage_kind")),
        store_id=_json_text(fields.get("store_id"), "store_id must be text"),
        store_version=_json_text(fields.get("store_version"), "store_version must be text"),
        storage_ref=_json_text(fields.get("storage_ref"), "storage_ref must be text"),
        byte_size=_json_int(fields.get("byte_size"), "byte_size must be an integer"),
        provenance_digest=_json_text(fields.get("provenance_digest"), "provenance_digest must be text"),
    )


def _decode_storage_kind(value: object) -> Literal[
    "project_value_ref", "runtime_blob_ref", "artifact_ref", "canonical_ref"
]:
    if value == "project_value_ref":
        return "project_value_ref"
    if value == "runtime_blob_ref":
        return "runtime_blob_ref"
    if value == "artifact_ref":
        return "artifact_ref"
    if value == "canonical_ref":
        return "canonical_ref"
    # kit:boundary owner=successor.language.program.codec class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.language.failure witness=test:test_program_codec_rejects_unsupported_storage_kind_as_typed_failure
    raise ProgramCodecError("unsupported storage_kind")
