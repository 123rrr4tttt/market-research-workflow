"""Typed validation for the Program AST."""

from __future__ import annotations

from dataclasses import dataclass

from .algebra import (
    OperationContractCatalogSnapshot,
    OperationContractRef,
    OperationSpec,
    canonical_digest,
)
from .object_contracts import (
    OperationContract,
    OperationContractResolver,
    build_first_specimen_return_contract_registry,
)
from .program import (
    ALLOWED_NODE_KINDS,
    Atom,
    Decide,
    Identity,
    MapOutput,
    ProgramNode,
    ProgramSpec,
    Pure,
    Then,
    TraverseOrdered,
    ZipOrdered,
)
from .transforms import TransformRegistry


@dataclass(frozen=True, slots=True)
class ValidationFailure:
    code: str
    path: str
    message: str
    detail: "str | None" = None


@dataclass(frozen=True, slots=True)
class ValidateResult:
    valid: bool
    failures: "tuple[ValidationFailure, ...]"

    def failure_codes(self) -> "tuple[str, ...]":
        return tuple(failure.code for failure in self.failures)


class _Validator:
    def __init__(
        self,
        catalog: OperationContractCatalogSnapshot,
        transform_registry: "TransformRegistry | None",
        merge_registry: "TransformRegistry | None",
        discriminator_registry: "TransformRegistry | None",
        require_contract_digest_match: bool,
        operation_contract_resolver: "OperationContractResolver | None",
    ) -> None:
        self.catalog = catalog
        self.transform_registry = transform_registry
        self.merge_registry = merge_registry
        self.discriminator_registry = discriminator_registry
        self.require_contract_digest_match = require_contract_digest_match
        self.operation_contract_resolver = operation_contract_resolver
        self.failures: "list[ValidationFailure]" = []

    def fail(
        self,
        code: str,
        path: str,
        message: str,
        detail: "str | None" = None,
    ) -> None:
        self.failures.append(
            ValidationFailure(code=code, path=path, message=message, detail=detail)
        )

    def validate(self, program: ProgramSpec) -> ValidateResult:
        self._walk(program.root, "root")
        return ValidateResult(valid=not self.failures, failures=tuple(self.failures))

    def _walk(self, node: ProgramNode, path: str) -> None:
        kind = getattr(node, "node_kind", None)
        if kind not in ALLOWED_NODE_KINDS:
            self.fail(
                "UNKNOWN_NODE_KIND",
                path,
                f"unknown node_kind {kind!r}",
            )
            return
        if isinstance(node, Identity):
            self._check_type(node.input_type, path)
            return
        if isinstance(node, Pure):
            self._check_type(node.input_type, path)
            self._check_type(node.output_type, path)
            if not node.literal_codec:
                self.fail("MISSING_LITERAL_CODEC", path, "Pure requires literal_codec")
            return
        if isinstance(node, Atom):
            self._validate_atom(node, path)
            return
        if isinstance(node, Then):
            self._walk(node.first, path + ".first")
            self._walk(node.second, path + ".second")
            if (
                canonical_digest(node.first.output_type)
                != canonical_digest(node.second.input_type)
            ):
                self.fail(
                    "TYPE_MISMATCH",
                    path,
                    "Then composition is not type-compatible",
                )
            return
        if isinstance(node, MapOutput):
            self._walk(node.source, path + ".source")
            self._check_type(node.target_type, path + ".target_type")
            if self.transform_registry is not None:
                if not self.transform_registry.has_transform(node.transform_ref):
                    self.fail(
                        "MISSING_TRANSFORM",
                        path,
                        f"transform {node.transform_ref.label()} is not registered",
                    )
            return
        if isinstance(node, ZipOrdered):
            self._walk(node.left, path + ".left")
            self._walk(node.right, path + ".right")
            if (
                canonical_digest(node.left.input_type)
                != canonical_digest(node.right.input_type)
            ):
                self.fail(
                    "TYPE_MISMATCH",
                    path,
                    "ZipOrdered inputs must agree",
                )
            if self.merge_registry is not None:
                if not self.merge_registry.has_merge(node.merge_ref):
                    self.fail(
                        "MISSING_MERGE",
                        path,
                        f"merge {node.merge_ref.label()} is not registered",
                    )
            return
        if isinstance(node, TraverseOrdered):
            self._walk(node.element_program, path + ".element_program")
            if node.traversal_policy not in ("STATIC_SHAPE", "MATERIALIZED_SHAPE"):
                self.fail(
                    "UNSUPPORTED_TRAVERSAL",
                    path,
                    f"unsupported traversal policy {node.traversal_policy!r}",
                )
            return
        if isinstance(node, Decide):
            if self.discriminator_registry is not None:
                if not self.discriminator_registry.has_discriminator(
                    node.discriminator_ref
                ):
                    self.fail(
                        "MISSING_DISCRIMINATOR",
                        path,
                        f"discriminator {node.discriminator_ref.label()} is not registered",
                    )
            branch_ids: "set[str]" = set()
            for index, branch in enumerate(node.branches):
                branch_path = f"{path}.branches[{index}]"
                if not branch.branch_id:
                    self.fail("EMPTY_BRANCH_ID", branch_path, "branch_id is empty")
                if branch.branch_id in branch_ids:
                    self.fail(
                        "DUPLICATE_BRANCH_ID",
                        branch_path,
                        f"duplicate branch_id {branch.branch_id!r}",
                    )
                branch_ids.add(branch.branch_id)
                if not branch.guard:
                    self.fail(
                        "EMPTY_BRANCH_GUARD",
                        branch_path,
                        "branch guard must be explicit",
                    )
                self._walk(branch.program, branch_path + ".program")
            return
        self.fail(
            "UNKNOWN_NODE_KIND",
            path,
            f"unsupported AST node {kind!r}",
        )

    def _check_type(self, object_type: "object", path: str) -> None:
        type_id = getattr(object_type, "type_id", None)
        codec_id = getattr(object_type, "codec_id", None)
        if not isinstance(type_id, str) or not type_id:
            self.fail("INVALID_OBJECT_TYPE", path, "type_id must be non-empty")
        if not isinstance(codec_id, str) or not codec_id:
            self.fail("INVALID_OBJECT_TYPE", path, "codec_id must be non-empty")
        try:
            digest = canonical_digest(object_type)
        except (TypeError, ValueError):
            digest = ""
        if not _is_hex64(digest):
            self.fail("INVALID_DIGEST", path, "object type digest must be sha256 hex")

    def _validate_atom(self, node: Atom, path: str) -> None:
        operation = node.operation
        if not operation.operation_id:
            self.fail("EMPTY_OPERATION_ID", path, "Atom operation_id must be non-empty")
        self._validate_operation_contract_ref(operation.contract_ref, path)
        self._check_type(node.input_type, path + ".input_type")
        self._check_type(node.output_type, path + ".output_type")
        if not operation.input_refs:
            self.fail("MISSING_INPUT_REFS", path, "Atom requires input refs")
        for index, value_ref in enumerate(operation.input_refs):
            self._check_type(value_ref.object_type, f"{path}.input_refs[{index}]")
        if self.operation_contract_resolver is None:
            self.fail(
                "MISSING_OPERATION_CONTRACT_RESOLVER",
                path,
                "Atom validation requires a full OperationContract resolver",
            )
            return
        contract = self.operation_contract_resolver.resolve(operation.contract_ref)
        if contract is None:
            self.fail(
                "UNRESOLVED_OPERATION_CONTRACT",
                path,
                f"full contract {operation.contract_ref.kind} is not resolvable by exact ref",
            )
            return
        self._validate_atom_contract(node, contract, path)

    def _validate_atom_contract(
        self, node: Atom, contract: OperationContract, path: str
    ) -> None:
        if not hasattr(contract, "input_type") or not hasattr(contract, "output_type"):
            self.fail(
                "INCOMPLETE_OPERATION_CONTRACT",
                path,
                "resolver returned a partial contract without input/output types",
            )
            return
        if canonical_digest(node.input_type) != canonical_digest(contract.input_type):
            self.fail(
                "CONTRACT_INPUT_TYPE_MISMATCH",
                path,
                "Atom input_type does not match the frozen OperationContract",
            )
        if canonical_digest(node.output_type) != canonical_digest(contract.output_type):
            self.fail(
                "CONTRACT_OUTPUT_TYPE_MISMATCH",
                path,
                "Atom output_type does not match the frozen OperationContract",
            )
        expected_return = frozen_return_contract(contract)
        if expected_return is None:
            self.fail(
                "UNKNOWN_RETURN_CONTRACT",
                path,
                f"return contract {contract.return_contract_ref!r} is not frozen",
            )
        else:
            reported = node.return_contract
            if (
                reported.success_modes != expected_return.success_modes
                or reported.failure_modes != expected_return.failure_modes
                or reported.wait_modes != expected_return.wait_modes
                or reported.cancel_modes != expected_return.cancel_modes
            ):
                self.fail(
                    "RETURN_CONTRACT_MISMATCH",
                    path,
                    "Atom return modes do not match the frozen OperationContract return contract",
                )
        profile_fields = (
            "semantic_profile_ref",
            "effect_profile_ref",
            "resource_profile_ref",
            "failure_profile_ref",
            "authority_profile_ref",
            "interpreter_compatibility_ref",
            "observation_profile_ref",
        )
        missing_profiles = tuple(
            name for name in profile_fields if not getattr(contract, name, "")
        )
        if missing_profiles:
            self.fail(
                "INCOMPLETE_OPERATION_CONTRACT_PROFILES",
                path,
                f"full OperationContract is missing profile refs: {missing_profiles}",
            )

    def _validate_operation_contract_ref(
        self, ref: OperationContractRef, path: str
    ) -> None:
        if not ref.kind or not ref.contract_version:
            self.fail("INVALID_CONTRACT_REF", path, "contract kind/version required")
        if not _is_hex64(ref.contract_digest):
            self.fail("INVALID_DIGEST", path, "contract digest must be sha256 hex")
        entry = self.catalog.lookup(ref.kind)
        if entry is None:
            self.fail(
                "UNKNOWN_OPERATION_CONTRACT",
                path,
                f"contract {ref.kind} not in catalog {self.catalog.catalog_id}",
            )
            return
        if entry.contract_version != ref.contract_version:
            self.fail(
                "CONTRACT_VERSION_MISMATCH",
                path,
                f"contract {ref.kind} version {ref.contract_version} "
                f"not in catalog",
            )
        if (
            self.require_contract_digest_match
            and entry.contract_digest != ref.contract_digest
        ):
            self.fail(
                "DIGEST_MISMATCH",
                path,
                f"contract {ref.kind} digest does not match catalog",
            )


def validate_program(
    program: ProgramSpec,
    catalog: OperationContractCatalogSnapshot,
    transform_registry: "TransformRegistry | None" = None,
    merge_registry: "TransformRegistry | None" = None,
    discriminator_registry: "TransformRegistry | None" = None,
    require_contract_digest_match: bool = False,
    operation_contract_resolver: "OperationContractResolver | None" = None,
) -> ValidateResult:
    return _Validator(
        catalog=catalog,
        transform_registry=transform_registry,
        merge_registry=merge_registry,
        discriminator_registry=discriminator_registry,
        require_contract_digest_match=require_contract_digest_match,
        operation_contract_resolver=operation_contract_resolver,
    ).validate(program)


def validate_operation_spec(
    operation: OperationSpec,
    catalog: OperationContractCatalogSnapshot,
    path: str,
) -> "tuple[ValidationFailure, ...]":
    validator = _Validator(
        catalog=catalog,
        transform_registry=None,
        merge_registry=None,
        discriminator_registry=None,
        require_contract_digest_match=False,
        operation_contract_resolver=None,
    )
    if not operation.operation_id:
        validator.fail("EMPTY_OPERATION_ID", path, "operation_id must be non-empty")
    validator._validate_operation_contract_ref(operation.contract_ref, path)
    for index, value_ref in enumerate(operation.input_refs):
        validator._check_type(value_ref.object_type, f"{path}.input_refs[{index}]")
    return tuple(validator.failures)


def _is_hex64(value: str) -> bool:
    if len(value) != 64:
        return False
    return all(character in "0123456789abcdef" for character in value)


_RETURN_CONTRACTS = build_first_specimen_return_contract_registry()


def frozen_return_contract(contract: OperationContract):
    """Resolve P0-A's immutable return-contract vocabulary.

    The AST copy of ``admission_required`` is deliberately not consulted: the
    capability-owned OperationContract ref is the authority for this bit.
    """
    return _RETURN_CONTRACTS.resolve(contract.return_contract_ref)
