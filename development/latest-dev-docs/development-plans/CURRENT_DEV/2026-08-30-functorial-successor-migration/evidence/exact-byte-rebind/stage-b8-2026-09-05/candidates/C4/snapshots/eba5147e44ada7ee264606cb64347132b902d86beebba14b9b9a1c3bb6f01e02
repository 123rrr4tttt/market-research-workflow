"""Serializable, typed initial Program AST.

The AST keeps complete child programs; node digests are derived projections and
are never a substitute for the full tree.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

from app.successor_runtime.research.object_types import ObjectType

from .algebra import (
    FrozenJsonObject,
    FrozenJsonValue,
    OperationSpec,
    ReturnContract,
    ValueRef,
    canonical_digest,
    canonical_json_bytes,
    default_return_contract,
    freeze_json_object,
    freeze_json_value,
    sha256_digest_bytes,
)

if TYPE_CHECKING:
    from .algebra import AlgebraRef
    from .transforms import DiscriminatorRef, MergeRef, TransformRef

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
PROGRAM_AST_CODEC_ID = "mrw.functorial-successor.program-ast.codec.v1"


class ProgramTypeError(ValueError):
    """Raised when a program composition violates typed boundaries."""


class ProgramCodecError(ValueError):
    """Raised when an AST payload cannot be decoded."""


@runtime_checkable
class ProgramNode(Protocol):
    node_kind: str

    @property
    def input_type(self) -> ObjectType: ...

    @property
    def output_type(self) -> ObjectType: ...

    @property
    def return_contract(self) -> ReturnContract: ...

    def encode_ast(self) -> "dict[str, Any]": ...

    def ast_digest(self) -> str: ...

    def normalized(self) -> "ProgramNode": ...


@dataclass(frozen=True, slots=True)
class Identity:
    node_kind: str
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

    def encode_ast(self) -> "dict[str, Any]":
        return {
            "node_kind": self.node_kind,
            "object_type": _encode_tagged(self.object_type, "object_type"),
        }

    def ast_digest(self) -> str:
        return canonical_digest(self.encode_ast())

    def normalized(self) -> "ProgramNode":
        from .normalize import normalize_node

        return normalize_node(self)


@dataclass(frozen=True, slots=True)
class Pure:
    node_kind: str
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

    def encode_ast(self) -> "dict[str, Any]":
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
    node_kind: str
    operation: OperationSpec
    input_type: ObjectType
    output_type: ObjectType
    return_contract: ReturnContract

    @property
    def _typed_input(self) -> ObjectType:
        return self.input_type

    def encode_ast(self) -> "dict[str, Any]":
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


def _operation_payload(operation: OperationSpec) -> "dict[str, Any]":
    return {
        "operation_id": operation.operation_id,
        "contract_ref": _encode_plain(operation.contract_ref),
        "input_refs": [_encode_plain(ref) for ref in operation.input_refs],
        "payload_ref": _encode_plain(operation.payload_ref),
        "allowed_overrides": operation.allowed_overrides,
    }


@dataclass(frozen=True, slots=True)
class Then:
    node_kind: str
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

    def encode_ast(self) -> "dict[str, Any]":
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


@dataclass(frozen=True, slots=True)
class MapOutput:
    node_kind: str
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

    def encode_ast(self) -> "dict[str, Any]":
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


@dataclass(frozen=True, slots=True)
class ZipOrdered:
    node_kind: str
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

    def encode_ast(self) -> "dict[str, Any]":
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
    node_kind: str
    element_program: "ProgramNode"
    traversal_policy: str

    @property
    def input_type(self) -> "ObjectType":
        return _sequence_object_type(self.element_program.input_type)

    @property
    def output_type(self) -> "ObjectType":
        return _sequence_object_type(self.element_program.output_type)

    @property
    def return_contract(self) -> ReturnContract:
        return default_return_contract()

    def encode_ast(self) -> "dict[str, Any]":
        return {
            "node_kind": self.node_kind,
            "element_program": self.element_program.encode_ast(),
            "traversal_policy": self.traversal_policy,
        }

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

    def encode_ast(self) -> "dict[str, Any]":
        return {
            "branch_id": self.branch_id,
            "guard": self.guard,
            "program": self.program.encode_ast(),
        }

    def ast_digest(self) -> str:
        return canonical_digest(self.encode_ast())


@dataclass(frozen=True, slots=True)
class Decide:
    node_kind: str
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

    def encode_ast(self) -> "dict[str, Any]":
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


def _encode_tagged(value: Any, tag: str) -> "dict[str, Any]":
    encoded = canonical_json_bytes(_encode_plain(value)).decode("utf-8")
    return {"$tag": tag, "$json": encoded}


def _encode_plain(value: Any) -> Any:
    import json

    if isinstance(value, dict):
        if "$tag" in value and "$json" in value:
            return value
        return {key: _encode_plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_encode_plain(item) for item in value]
    if hasattr(value, "to_plain"):
        return _encode_plain(value.to_plain())
    return json.loads(canonical_json_bytes(value).decode("utf-8"))


def _metadata_plain(value: "FrozenJsonObject") -> "dict[str, Any]":
    return {key: item for key, item in sorted(value, key=lambda pair: pair[0])}


def _check_then_types(first: "ProgramNode", second: "ProgramNode") -> None:
    if first is None or second is None:
        raise ProgramTypeError("Then requires first and second programs")
    if canonical_digest(first.output_type) != canonical_digest(second.input_type):
        raise ProgramTypeError(
            f"Then type mismatch: {first.output_type.type_id} -> "
            f"{second.input_type.type_id}"
        )


def _check_zip_types(left: "ProgramNode", right: "ProgramNode") -> None:
    if left is None or right is None:
        raise ProgramTypeError("ZipOrdered requires left and right programs")
    if canonical_digest(left.input_type) != canonical_digest(right.input_type):
        raise ProgramTypeError("ZipOrdered requires equal input types")


def _check_decide_branches(branches: "tuple[DecisionBranch, ...]") -> None:
    if not branches:
        raise ProgramTypeError("Decide requires at least one branch")
    input_digest = canonical_digest(branches[0].program.input_type)
    output_digest = canonical_digest(branches[0].program.output_type)
    branch_ids: "set[str]" = set()
    for branch in branches:
        if not branch.branch_id:
            raise ProgramTypeError("Decide branch requires a branch_id")
        if branch.branch_id in branch_ids:
            raise ProgramTypeError(f"duplicate branch_id {branch.branch_id!r}")
        branch_ids.add(branch.branch_id)
        if canonical_digest(branch.program.input_type) != input_digest:
            raise ProgramTypeError("Decide branch input types must agree")
        if canonical_digest(branch.program.output_type) != output_digest:
            raise ProgramTypeError("Decide branch output types must agree")


def _tuple_object_type(types: "tuple[ObjectType, ...]") -> ObjectType:
    return ObjectType(
        type_id="tuple:" + ",".join(t.type_id for t in types),
        schema_version="1",
        codec_id="mrw.successor.tuple_codec.v1",
        canonical_codec_version="1",
    )


def _sequence_object_type(element_type: ObjectType) -> ObjectType:
    return ObjectType(
        type_id="sequence:" + element_type.type_id,
        schema_version="1",
        codec_id="mrw.successor.sequence_codec.v1",
        canonical_codec_version="1",
    )


def identity_node(object_type: ObjectType) -> Identity:
    return Identity(node_kind="identity", object_type=object_type)


def pure_node(
    input_type: ObjectType,
    output_type: ObjectType,
    literal_value: FrozenJsonValue,
    literal_codec: str,
) -> Pure:
    frozen_literal = freeze_json_value(literal_value)
    return Pure(
        node_kind="pure",
        input_type_ref=input_type,
        output_type_ref=output_type,
        literal_codec=literal_codec,
        literal_digest=canonical_digest(frozen_literal),
        literal_value=frozen_literal,
    )


def content_addressed_literal(value: "dict[str, Any]") -> "dict[str, Any]":
    """Bind a literal's ``content_digest`` to its canonical content bytes.

    The digest excludes its own field.  Callers cannot supply a sentinel or a
    stale digest because this constructor derives the field after copying the
    complete literal payload.
    """

    content = {key: item for key, item in value.items() if key != "content_digest"}
    return {**content, "content_digest": canonical_digest(content)}


def atom_node(
    operation: OperationSpec,
    input_type: "ObjectType | None" = None,
    output_type: "ObjectType | None" = None,
    return_contract: "ReturnContract | None" = None,
) -> Atom:
    return Atom(
        node_kind="atom",
        operation=operation,
        input_type=input_type or _placeholder_type("atom.input"),
        output_type=output_type or _placeholder_type("atom.output"),
        return_contract=return_contract or default_return_contract(),
    )


def then_node(first: "ProgramNode", second: "ProgramNode") -> Then:
    _check_then_types(first, second)
    return Then(node_kind="then", first=first, second=second)


def map_output_node(
    source: "ProgramNode",
    transform_ref: "TransformRef",
    target_type: ObjectType,
) -> MapOutput:
    return MapOutput(
        node_kind="map_output",
        source=source,
        transform_ref=transform_ref,
        target_type=target_type,
    )


def zip_ordered_node(
    left: "ProgramNode",
    right: "ProgramNode",
    merge_ref: "MergeRef",
    output_type: "ObjectType | None" = None,
) -> ZipOrdered:
    _check_zip_types(left, right)
    if output_type is None:
        output_type = _tuple_object_type((left.output_type, right.output_type))
    return ZipOrdered(
        node_kind="zip_ordered",
        left=left,
        right=right,
        merge_ref=merge_ref,
        output_type=output_type,
    )


def traverse_ordered_node(
    element_program: "ProgramNode",
    traversal_policy: str,
) -> TraverseOrdered:
    return TraverseOrdered(
        node_kind="traverse_ordered",
        element_program=element_program,
        traversal_policy=traversal_policy,
    )


def decide_node(
    discriminator_ref: "DiscriminatorRef",
    branches: "tuple[DecisionBranch, ...]",
) -> Decide:
    _check_decide_branches(branches)
    return Decide(
        node_kind="decide",
        discriminator_ref=discriminator_ref,
        branches=branches,
    )


def _placeholder_type(type_id: str) -> ObjectType:
    return ObjectType(
        type_id=type_id,
        schema_version="0",
        codec_id="mrw.invalid.unresolved",
        canonical_codec_version="0",
    )


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
    transform_refs: "tuple[TransformRef, ...]"
    observation_profile: str
    metadata: FrozenJsonObject
    program_digest: str

    def payload_dict(self) -> "dict[str, Any]":
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
            raise ValueError("successor materialization identities must be non-empty")
        if self.state not in {"PREPARED", "MATERIALIZED", "REJECTED"}:
            raise ValueError(f"unsupported successor materialization state {self.state!r}")
        expected_digest = self.successor_program.digest()
        if self.successor_program.program_digest != expected_digest:
            raise ValueError("successor ProgramSpec carries a stale program_digest")
        if self.successor_program_digest != expected_digest:
            raise ValueError("successor_program_digest does not match successor ProgramSpec")


def encode_program_spec(spec: ProgramSpec) -> "dict[str, Any]":
    payload = spec.payload_dict()
    return {
        "schema": "mrw.functorial_successor.program_spec.v1",
        "program": payload,
        "program_digest": spec.digest(),
    }


def program_digest(spec: ProgramSpec) -> str:
    return spec.digest()


def decode_program_spec(payload: "dict[str, Any]") -> ProgramSpec:
    from .algebra import AlgebraRef
    from .transforms import TransformRef

    try:
        program = payload["program"]
        codec = program["codec"]
        if codec != PROGRAM_AST_CODEC_ID:
            raise ProgramCodecError(f"unsupported AST codec {codec!r}")
        root = decode_ast(program["root"])
        input_type = _decode_type(program["input_type"])
        output_type = _decode_type(program["output_type"])
        metadata_value = _unwrap_tags(program["metadata"])
        if not isinstance(metadata_value, dict):
            raise ProgramCodecError("Program metadata must decode to an object")
        metadata = freeze_json_object(metadata_value)
        algebra_refs = tuple(
            AlgebraRef(
                algebra_id=_decode_tagged(item, "algebra_ref")["algebra_id"],
                algebra_version=_decode_tagged(item, "algebra_ref")["algebra_version"],
            )
            for item in _decode_array(program["algebra_refs"])
        )
        transform_refs = tuple(
            TransformRef(
                name=_decode_tagged(item, "transform_ref")["name"],
                version=_decode_tagged(item, "transform_ref")["version"],
                digest=_decode_tagged(item, "transform_ref")["digest"],
                transform_kind=_decode_tagged(item, "transform_ref").get(
                    "transform_kind", "transform"
                ),
            )
            for item in _decode_array(program["transform_refs"])
        )
        spec = ProgramSpec(
            program_id=program["program_id"],
            contract_version=program["contract_version"],
            project_key=program["project_key"],
            project_registry_revision=program["project_registry_revision"],
            project_scope_digest=program["project_scope_digest"],
            semantic_identity=program["semantic_identity"],
            input_type=input_type,
            output_type=output_type,
            root=root,
            algebra_refs=algebra_refs,
            transform_refs=transform_refs,
            observation_profile=program["observation_profile"],
            metadata=metadata,
            program_digest="",
        )
        return spec.with_digest()
    except KeyError as exc:
        raise ProgramCodecError(f"malformed program spec payload: {exc}") from exc


def _decode_type(value: Any) -> ObjectType:
    from .algebra import ObjectType as _ObjectType

    if isinstance(value, dict) and value.get("$tag") == "object_type":
        fields = _decode_tagged(value, "object_type")
    elif isinstance(value, dict) and "type_id" in value:
        fields = value
    else:
        raise ProgramCodecError("expected object_type value")
    return _ObjectType(
        type_id=fields["type_id"],
        schema_version=fields["schema_version"],
        codec_id=fields["codec_id"],
        canonical_codec_version=fields["canonical_codec_version"],
    )


def _decode_tagged(value: Any, tag: str) -> Any:
    import json

    if not isinstance(value, dict) or value.get("$tag") != tag:
        raise ProgramCodecError(f"expected tagged value {tag!r}")
    decoded = _unwrap_tags(json.loads(value["$json"]))
    if isinstance(decoded, dict) and set(decoded) == {tag}:
        decoded = decoded[tag]
    return decoded


def _unwrap_tags(value: Any) -> Any:
    import json

    if isinstance(value, dict):
        if "$tag" in value and "$json" in value:
            return _unwrap_tags(json.loads(value["$json"]))
        return {key: _unwrap_tags(item) for key, item in value.items()}
    if isinstance(value, list):
        if value and value[0] == "$array":
            return _unwrap_tags(value[1])
        return [_unwrap_tags(item) for item in value]
    return value


def _decode_array(value: Any) -> "list[Any]":
    if isinstance(value, list) and value and value[0] == "$array":
        return list(value[1])
    if isinstance(value, list):
        return value
    raise ProgramCodecError("expected encoded array")


def _decode_json_object(value: Any) -> "dict[str, Any]":
    if isinstance(value, list) and value and value[0] == "$array":
        return {}
    if isinstance(value, list) and not value:
        return {}
    if isinstance(value, dict):
        return value
    raise ProgramCodecError("expected encoded object")


def decode_ast(value: Any) -> "ProgramNode":
    from .algebra import OperationContractRef
    from .transforms import DiscriminatorRef, MergeRef, TransformRef

    if not isinstance(value, dict):
        raise ProgramCodecError("AST node must be an object")
    node_kind = value.get("node_kind")
    if node_kind not in ALLOWED_NODE_KINDS:
        raise ProgramCodecError(f"unknown node_kind {node_kind!r}")
    if node_kind == "identity":
        return Identity(
            node_kind="identity",
            object_type=_decode_type(value["object_type"]),
        )
    if node_kind == "pure":
        return Pure(
            node_kind="pure",
            input_type_ref=_decode_type(value["input_type_ref"]),
            output_type_ref=_decode_type(value["output_type_ref"]),
            literal_codec=value["literal_codec"],
            literal_digest=value["literal_digest"],
            literal_value=freeze_json_value(_unwrap_tags(value["literal_value"])),
        )
    if node_kind == "atom":
        operation_value = _decode_tagged(value["operation"], "operation_spec")
        contract_ref_value = operation_value["contract_ref"]
        if (
            isinstance(contract_ref_value, dict)
            and set(contract_ref_value) == {"operation_contract_ref"}
        ):
            contract_ref_value = contract_ref_value["operation_contract_ref"]
        input_refs_value = _decode_array(operation_value["input_refs"])
        operation = OperationSpec(
            operation_id=operation_value["operation_id"],
            contract_ref=OperationContractRef(
                kind=contract_ref_value["kind"],
                contract_version=contract_ref_value["contract_version"],
                contract_digest=contract_ref_value["contract_digest"],
            ),
            input_refs=tuple(_decode_value_ref(item) for item in input_refs_value),
            payload_ref=_decode_value_ref(operation_value["payload_ref"]),
            allowed_overrides=freeze_json_object(
                _decode_json_object(operation_value["allowed_overrides"])
            ),
        )
        rc_value = _decode_tagged(value["return_contract"], "return_contract")
        return Atom(
            node_kind="atom",
            operation=operation,
            input_type=_decode_type(value["input_type"]),
            output_type=_decode_type(value["output_type"]),
            return_contract=ReturnContract(
                success_modes=tuple(rc_value["success_modes"]),
                failure_modes=tuple(rc_value["failure_modes"]),
                admission_required=rc_value["admission_required"],
                wait_modes=tuple(rc_value.get("wait_modes", [])),
                cancel_modes=tuple(rc_value.get("cancel_modes", [])),
            ),
        )
    if node_kind == "then":
        return Then(
            node_kind="then",
            first=decode_ast(value["first"]),
            second=decode_ast(value["second"]),
        )
    if node_kind == "map_output":
        tf = _decode_tagged(value["transform_ref"], "transform_ref")
        return MapOutput(
            node_kind="map_output",
            source=decode_ast(value["source"]),
            transform_ref=TransformRef(
                name=tf["name"],
                version=tf["version"],
                digest=tf["digest"],
                transform_kind=tf.get("transform_kind", "transform"),
            ),
            target_type=_decode_type(value["target_type"]),
        )
    if node_kind == "zip_ordered":
        mf = _decode_tagged(value["merge_ref"], "merge_ref")
        return ZipOrdered(
            node_kind="zip_ordered",
            left=decode_ast(value["left"]),
            right=decode_ast(value["right"]),
            merge_ref=MergeRef(
                name=mf["name"],
                version=mf["version"],
                digest=mf["digest"],
                transform_kind=mf.get("transform_kind", "merge"),
            ),
            output_type=_decode_type(value["output_type"]),
        )
    if node_kind == "traverse_ordered":
        return TraverseOrdered(
            node_kind="traverse_ordered",
            element_program=decode_ast(value["element_program"]),
            traversal_policy=value["traversal_policy"],
        )
    if node_kind == "decide":
        df = _decode_tagged(value["discriminator_ref"], "discriminator_ref")
        branches = tuple(
            DecisionBranch(
                branch_id=item["branch_id"],
                guard=item["guard"],
                program=decode_ast(item["program"]),
            )
            for item in _decode_array(value["branches"])
        )
        return Decide(
            node_kind="decide",
            discriminator_ref=DiscriminatorRef(
                name=df["name"],
                version=df["version"],
                digest=df["digest"],
                transform_kind=df.get("transform_kind", "discriminator"),
            ),
            branches=branches,
        )
    raise ProgramCodecError(f"unsupported node_kind {node_kind!r}")


def _decode_value_ref(value: Any) -> Any:
    from .algebra import ValueRef

    fields = value
    return ValueRef(
        value_id=fields["value_id"],
        project_key=fields["project_key"],
        object_type=_decode_type(fields["object_type"]),
        codec_id=fields["codec_id"],
        content_digest=fields["content_digest"],
        storage_kind=fields["storage_kind"],
        store_id=fields["store_id"],
        store_version=fields["store_version"],
        storage_ref=fields["storage_ref"],
        byte_size=fields["byte_size"],
        provenance_digest=fields["provenance_digest"],
    )


def _check_same_type(left: ObjectType, right: ObjectType) -> bool:
    return canonical_digest(left) == canonical_digest(right)
