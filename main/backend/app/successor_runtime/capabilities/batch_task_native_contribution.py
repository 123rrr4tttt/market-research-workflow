"""Authored C4 native-contribution rule over the existing agent-batch C4 bundle.

The rule owns only the C4 family-local declaration: plan, retry and submit stay
as three explicit typed slots in the exact business order.  The existing
``BatchTaskCapabilityBundle`` remains authoritative for contracts and codecs;
the Program, reducer, submission store handler and quality-promotion handler
remain the authoritative behavior and effect boundaries.
"""

from __future__ import annotations

from collections.abc import Callable
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from functorial_kit.contribution_compiler import NativeContributionRule
from functorial_kit.contribution_verification import (
    ContributionVerification,
    VerificationCheck,
)
from functorial_kit.contributions import (
    ContributionObject,
    contribution_failures,
)
from functorial_kit.core.failure import Failure
from functorial_kit.law_witness import define_law_witness
from functorial_kit.native_contribution import (
    BindingAccepted,
    BindingRejected,
    NativeBindingIssue,
    ProjectedContributionSpec,
)

from app.successor_runtime.capabilities import batch_task as batch_task

if TYPE_CHECKING:
    from app.successor_runtime.assembly.base import FamilyAssembly

__all__ = [
    "ASSEMBLY_CELL_IDS",
    "BatchTaskNativeDefinition",
    "BatchTaskNativeOperationDefinition",
    "BatchTaskNativeOperationSource",
    "BatchTaskNativeQualityPromotionSource",
    "BatchTaskNativeSource",
    "BatchTaskAssemblyContext",
    "DEFAULT_BATCH_TASK_NATIVE_SOURCE",
    "BATCH_TASK_NATIVE_RULE_ID",
    "BATCH_TASK_NATIVE_VERIFICATION_INPUTS",
    "BATCH_TASK_FAILURES",
    "lower_batch_task_native_source",
    "project_batch_task_native_definition",
    "verify_batch_task_native_definition",
    "BATCH_TASK_NATIVE_CONTRIBUTION_RULE",
    "compile_batch_task_native_contribution",
]


BATCH_TASK_NATIVE_RULE_ID = "mrw.batch.task.native-rule.v2"
BatchTaskNativeSlot = Literal["PLAN", "RETRY", "SUBMIT"]
BatchTaskQualityPromotionEffectBoundary = Literal["READBACK_ONLY"]
_BATCH_TASK_SLOTS: tuple[BatchTaskNativeSlot, ...] = ("PLAN", "RETRY", "SUBMIT")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")

BATCH_TASK_NATIVE_VERIFICATION_INPUTS = (
    "mrw.batch.task.definition",
    "mrw.batch.task.order",
    "mrw.batch.task.codec",
    "mrw.batch.task.quality-promotion-boundary",
)

BATCH_TASK_FAILURES = batch_task.BATCH_TASK_FAILURES
_CURRENT_OPERATION_IDS = batch_task.BATCH_TASK_ASSEMBLY_CELL_IDS
_CURRENT_CODEC_IDS = (
    batch_task.BATCH_PLAN_PAYLOAD_CODEC_ID,
    batch_task.RETRY_REDUCER_PAYLOAD_CODEC_ID,
    batch_task.SUBMISSION_PAYLOAD_CODEC_ID,
)


@dataclass(frozen=True, slots=True)
class BatchTaskNativeOperationSource:
    """One authored C4 semantic slot backed by the existing typed contract."""

    operation_id: str
    slot: BatchTaskNativeSlot
    kind: str
    owner: str
    payload_codec_id: str
    receipt_codec_id: str | None = None
    receipt_provenance_schema: str | None = None


@dataclass(frozen=True, slots=True)
class BatchTaskNativeQualityPromotionSource:
    """The C4 quality-promotion boundary, separate from C4.3 live submission."""

    operation_digest: str
    interpreter_digest: str
    authority_digest: str
    effect_boundary: BatchTaskQualityPromotionEffectBoundary = "READBACK_ONLY"


@dataclass(frozen=True, slots=True)
class BatchTaskNativeSource:
    """One authored C4 fact: ordered plan, retry, submit and promotion boundary."""

    contribution_id: str
    bundle_id: str
    owner: str
    deployment_catalog_digest: str
    program_id: str
    operations: tuple[
        BatchTaskNativeOperationSource,
        BatchTaskNativeOperationSource,
        BatchTaskNativeOperationSource,
    ]
    quality_promotion: BatchTaskNativeQualityPromotionSource

    @property
    def slots(self) -> tuple[BatchTaskNativeSlot, ...]:
        return tuple(operation.slot for operation in self.operations)


@dataclass(frozen=True, slots=True)
class BatchTaskNativeOperationDefinition:
    source: BatchTaskNativeOperationSource
    contract: object
    codec: object


@dataclass(frozen=True, slots=True)
class BatchTaskNativeDefinition:
    source: BatchTaskNativeSource
    bundle: batch_task.BatchTaskCapabilityBundle
    catalog: object
    registry: object
    _operations: tuple[BatchTaskNativeOperationDefinition, ...] = ()

    @property
    def contribution_id(self) -> str:
        return self.source.contribution_id

    def operation_by_slot(
        self, slot: BatchTaskNativeSlot
    ) -> BatchTaskNativeOperationDefinition | None:
        for current_operation_id, current_codec_id, operation in zip(
            _CURRENT_OPERATION_IDS, _CURRENT_CODEC_IDS, self.operations
        ):
            if operation.source.slot == slot:
                return operation
        return None

    @property
    def operations(self) -> tuple[BatchTaskNativeOperationDefinition, ...]:
        return self._operations

    def contribution_objects(self) -> tuple[ContributionObject, ...]:
        # The ordered slots form one chain: plan output feeds retry/reducer work
        # and submit terminalizes a fresh attempt.  Declare that chain once.
        merged: dict[tuple[str, str, str], tuple[str, ...]] = {}
        prior_output: str | None = None
        for current_operation_id, current_codec_id, operation in zip(
            _CURRENT_OPERATION_IDS, _CURRENT_CODEC_IDS, self.operations
        ):
            input_type = operation.contract.input_type.type_id
            output_type = operation.contract.output_type.type_id
            declared = (
                (input_type, "ObjectType", () if prior_output is None else (prior_output,)),
                (output_type, "ObjectType", (input_type,)),
                (
                    current_operation_id,
                    "Capability",
                    (input_type, output_type),
                ),
                (
                    current_codec_id,
                    "PayloadCodec",
                    (current_operation_id, input_type),
                ),
            )
            for object_id, kind, references in declared:
                key = (object_id, kind, self.source.owner)
                prior_references = merged.setdefault(key, ())
                merged[key] = prior_references + tuple(
                    reference
                    for reference in references
                    if reference not in prior_references
                )
            prior_output = output_type
        return tuple(
            ContributionObject(object_id, kind, owner, references)
            for (object_id, kind, owner), references in merged.items()
        )

def _issue(checks: tuple[tuple[bool, str, str], ...]) -> tuple[NativeBindingIssue, ...]:
    return tuple(
        NativeBindingIssue(path, message) for valid, path, message in checks if not valid
    )


def _definition_issues(
    source: BatchTaskNativeSource, bundle: batch_task.BatchTaskCapabilityBundle
) -> tuple[NativeBindingIssue, ...]:
    expected = (
        batch_task.BATCH_PLAN_KIND,
        batch_task.RETRY_REDUCE_KIND,
        batch_task.SUBMISSION_KIND,
    )
    issues = _issue(
        (
            (bundle.bundle_id == source.bundle_id, "$.source.bundle_id", "bundle identity drift"),
            (len(source.operations) == 3, "$.source.operations", "C4 has exactly plan/retry/submit"),
            (source.slots == _BATCH_TASK_SLOTS, "$.source.slots", "C4 slot order drift"),
            (
                tuple(operation.ref.kind for operation in bundle.operations) == expected,
                "$.bundle.operations",
                "bundle operation order drift",
            ),
            (
                source.quality_promotion.effect_boundary == "READBACK_ONLY",
                "$.source.quality_promotion.effect_boundary",
                "quality promotion must remain readback-only",
            ),
        )
    )
    expected_ids = (
        batch_task.BATCH_PLAN_OPERATION_ID,
        batch_task.RETRY_REDUCE_OPERATION_ID,
        batch_task.SUBMISSION_OPERATION_ID,
    )
    expected_owners = tuple(operation.owner_capability_id for operation in bundle.operations)
    for index, operation in enumerate(source.operations):
        contract = bundle.operations[index]
        codec = bundle.codecs[index]
        issues += _issue(
            (
                (
                    operation.operation_id == expected_ids[index],
                    f"$.source.operations[{index}].operation_id",
                    "operation identity drift",
                ),
                (
                    operation.kind == contract.ref.kind,
                    f"$.source.operations[{index}].kind",
                    "operation kind drift",
                ),
                (
                    operation.owner == contract.owner_capability_id == expected_owners[index],
                    f"$.source.operations[{index}].owner",
                    "operation owner drift",
                ),
                (
                    operation.payload_codec_id == codec.codec_id,
                    f"$.source.operations[{index}].payload_codec_id",
                    "payload codec drift",
                ),
                (
                    codec.contract_ref.contract_digest == contract.ref.contract_digest,
                    f"$.source.operations[{index}].codec_contract",
                    "codec contract digest drift",
                ),
            )
        )
        if operation.slot == "SUBMIT":
            issues += _issue(
                (
                    (
                        operation.receipt_codec_id
                        == batch_task.SUBMISSION_RECEIPT_CODEC_ID,
                        f"$.source.operations[{index}].receipt_codec_id",
                        "submission receipt codec drift",
                    ),
                    (
                        operation.receipt_provenance_schema
                        == batch_task.SUBMISSION_RECEIPT_PROVENANCE_SCHEMA,
                        f"$.source.operations[{index}].receipt_provenance_schema",
                        "submission receipt provenance drift",
                    ),
                )
            )
        else:
            issues += _issue(
                (
                    (
                        operation.receipt_codec_id is None,
                        f"$.source.operations[{index}].receipt_codec_id",
                        "non-submit slot cannot own a receipt codec",
                    ),
                    (
                        operation.receipt_provenance_schema is None,
                        f"$.source.operations[{index}].receipt_provenance_schema",
                        "non-submit slot cannot own receipt provenance",
                    ),
                )
            )
    return issues


def lower_batch_task_native_source(source: BatchTaskNativeSource) -> BatchTaskNativeDefinition | Failure:
    bundle = batch_task.build_batch_task_bundle()
    issues = _definition_issues(source, bundle)
    if issues:
        return contribution_failures.fail(
            "CONTRIBUTION_INVALID",
            "native C4 definition is invalid",
            {
                "issues": tuple(
                    {"code": "invalid_spec", "path": issue.path, "message": issue.message}
                    for issue in issues
                )
            },
        )
    return BatchTaskNativeDefinition(
        source=source,
        bundle=bundle,
        catalog=batch_task.build_batch_task_catalog(bundle),
        registry=batch_task.build_batch_task_registry(bundle),
        _operations=tuple(
            BatchTaskNativeOperationDefinition(operation, contract, codec)
            for operation, contract, codec in zip(
                source.operations, bundle.operations, bundle.codecs
            )
        ),
    )


def project_batch_task_native_definition(
    definition: BatchTaskNativeDefinition,
) -> ProjectedContributionSpec | Failure:
    return ProjectedContributionSpec(
        id=definition.contribution_id,
        owner=definition.source.owner,
        objects=definition.contribution_objects(),
        failures=(BATCH_TASK_FAILURES,),
    )


@dataclass(frozen=True, slots=True)
class BatchTaskAssemblyContext:
    """Runtime inputs for inert native assembly; no provider or live submit."""

    uow_factory: Callable[[], object]
    project_scope_digest: str
    definition: "BatchTaskNativeDefinition"
    options: object = field(default_factory=lambda: None)


@dataclass(frozen=True, slots=True)
class BatchTaskNativeBinding:
    definition: BatchTaskNativeDefinition
    family_assembly: "FamilyAssembly"
    assembly_context: BatchTaskAssemblyContext


def _verify(definition: BatchTaskNativeDefinition) -> Failure | None:
    issues = _definition_issues(definition.source, definition.bundle)
    if not issues:
        return None
    return contribution_failures.fail(
        "CONTRIBUTION_INVALID",
        "; ".join(f"{issue.path}: {issue.message}" for issue in issues),
    )


def verify_batch_task_native_definition(
    definition: BatchTaskNativeDefinition,
    native: object,
) -> ContributionVerification | Failure:
    del native

    def _run() -> Failure | None:
        return _verify(definition)

    witness = define_law_witness(
        f"test_batch_native_definition_law:{definition.contribution_id}", _run
    )
    if isinstance(witness, Failure):
        return witness
    return ContributionVerification(
        rule_id=BATCH_TASK_NATIVE_RULE_ID,
        inputs=BATCH_TASK_NATIVE_VERIFICATION_INPUTS,
        checks=(VerificationCheck(witness=witness, inputs=BATCH_TASK_NATIVE_VERIFICATION_INPUTS),),
        complete=True,
    )


def validate_batch_task_native_binding(
    definition: BatchTaskNativeDefinition,
    candidate: object,
) -> BindingAccepted[BatchTaskNativeBinding] | BindingRejected:
    if not isinstance(candidate, BatchTaskNativeBinding):
        return BindingRejected(
            (NativeBindingIssue("$.binding", "expected BatchTaskNativeBinding"),)
        )
    assembly = candidate.family_assembly
    source = definition.source
    checks: tuple[tuple[bool, str, str], ...] = (
        (candidate.definition == definition, "$.binding.definition", "definition drift"),
        (
            candidate.assembly_context.definition == definition,
            "$.binding.assembly_context.definition",
            "assembly context definition drift",
        ),
        (
            _HEX64.fullmatch(candidate.assembly_context.project_scope_digest) is not None,
            "$.binding.assembly_context.project_scope_digest",
            "invalid assembly context scope digest",
        ),
        (
            assembly.family_id == batch_task.BATCH_TASK_FAMILY_ID,
            "$.binding.family_assembly.family_id",
            "family id drift",
        ),
        (
            tuple(cell.cell_id for cell in assembly.cells)
            == tuple(operation.operation_id for operation in source.operations),
            "$.binding.family_assembly.cells",
            "C4 cell order drift",
        ),
        (
            tuple(
                cell.operation_contract_refs[0] if cell.operation_contract_refs else None
                for cell in assembly.cells
            )
            == tuple(operation.kind for operation in source.operations),
            "$.binding.family_assembly.cells.operation_refs",
            "operation order drift",
        ),
        (
            assembly.cells[2].status == "INSTALLED",
            "$.binding.family_assembly.cells[2].status",
            "submit terminal must install",
        ),
        (
            bool(assembly.handlers)
            and all(
                getattr(handler, "deployment_catalog_digest", None)
                == source.deployment_catalog_digest
                for handler in assembly.handlers
            ),
            "$.binding.handlers.deployment_catalog_digest",
            "handler deployment catalog digest drift",
        ),
    )
    quality_handlers = tuple(
        handler
        for handler in assembly.handlers
        if getattr(handler, "gate_calls", None) is not None
        and getattr(handler, "evidence", None) is not None
    )
    submission_handler = next(
        (
            handler
            for handler in assembly.handlers
            if getattr(handler, "receipt_codec_id", None) is not None
        ),
        None,
    )
    submission_source = definition.operation_by_slot("SUBMIT")
    checks += (
        (
            submission_handler is not None
            and submission_source is not None
            and submission_handler.receipt_codec_id
            == submission_source.source.receipt_codec_id
            and submission_handler.receipt_provenance_schema
            == submission_source.source.receipt_provenance_schema,
            "$.binding.submission_receipt",
            "submission receipt binding drift",
        ),
    )
    if quality_handlers:
        quality = source.quality_promotion
        quality_handler = quality_handlers[0]
        checks += (
            (
                len(quality_handlers) == 1
                and quality.effect_boundary == "READBACK_ONLY"
                and getattr(quality_handler, "operation_contract_digest", None)
                == quality.operation_digest
                and getattr(quality_handler, "interpreter_profile_digest", None)
                == quality.interpreter_digest
                and getattr(quality_handler, "deployment_catalog_digest", None)
                == source.deployment_catalog_digest,
                "$.binding.quality_promotion",
                "quality promotion binding drift or boundary change",
            ),
        )
    issues = _issue(checks)
    return BindingRejected(issues) if issues else BindingAccepted(candidate)

BATCH_TASK_NATIVE_CONTRIBUTION_RULE = NativeContributionRule[
    BatchTaskNativeSource,
    BatchTaskNativeDefinition,
    object,
    BatchTaskNativeBinding,
](
    lower=lower_batch_task_native_source,
    project=project_batch_task_native_definition,
    assemble=lambda definition, context: _assemble_batch_task_native_definition(definition, context),
    validate_binding=validate_batch_task_native_binding,
    verification=verify_batch_task_native_definition,
)


def _assemble_batch_task_native_definition(
    definition: BatchTaskNativeDefinition,
    context: object,
) -> BatchTaskNativeBinding | Failure:
    from app.successor_runtime.assembly.batch_task_assembly import build_batch_task_assembly

    if not isinstance(context, BatchTaskAssemblyContext):
        return contribution_failures.fail(
            "CONTRIBUTION_INVALID",
            "C4 native assembly requires C4AssemblyContext",
            {
                "issues": (
                    {
                        "code": "invalid_context",
                        "path": "$.context",
                        "message": "expected C4AssemblyContext",
                    },
                )
            },
        )
    family_assembly = build_batch_task_assembly(
        uow_factory=context.uow_factory,
        project_scope_digest=context.project_scope_digest,
        options=context.options,
        native_definition=definition,
    )
    return BatchTaskNativeBinding(
        definition=definition,
        family_assembly=family_assembly,
        assembly_context=context,
    )

def compile_batch_task_native_contribution(
    source: BatchTaskNativeSource,
) -> object:
    from functorial_kit.contribution_compiler import compile_native_contribution

    return compile_native_contribution(source, BATCH_TASK_NATIVE_CONTRIBUTION_RULE)


DEFAULT_BATCH_TASK_NATIVE_SOURCE = BatchTaskNativeSource(
    contribution_id="mrw.batch.task.native.v2",
    bundle_id=batch_task.BATCH_TASK_BUNDLE_ID,
    owner="batch.task.v2",
    deployment_catalog_digest=batch_task.sha256_hex(batch_task.BATCH_TASK_DEPLOYMENT_CATALOG_ID.encode()),
    program_id="program:batch-task.v2",
    operations=(
        BatchTaskNativeOperationSource(
            operation_id=batch_task.BATCH_PLAN_OPERATION_ID,
            slot="PLAN",
            kind=batch_task.BATCH_PLAN_KIND,
            owner=batch_task.BATCH_TASK_OWNER,
            payload_codec_id=batch_task.BATCH_PLAN_PAYLOAD_CODEC_ID,
        ),
        BatchTaskNativeOperationSource(
            operation_id=batch_task.RETRY_REDUCE_OPERATION_ID,
            slot="RETRY",
            kind=batch_task.RETRY_REDUCE_KIND,
            owner=batch_task.BATCH_TASK_OWNER,
            payload_codec_id=batch_task.RETRY_REDUCER_PAYLOAD_CODEC_ID,
        ),
        BatchTaskNativeOperationSource(
            operation_id=batch_task.SUBMISSION_OPERATION_ID,
            slot="SUBMIT",
            kind=batch_task.SUBMISSION_KIND,
            owner=batch_task.SUBMISSION_OWNER,
            payload_codec_id=batch_task.SUBMISSION_PAYLOAD_CODEC_ID,
            receipt_codec_id=batch_task.SUBMISSION_RECEIPT_CODEC_ID,
            receipt_provenance_schema=batch_task.SUBMISSION_RECEIPT_PROVENANCE_SCHEMA,
        ),
    ),
    quality_promotion=BatchTaskNativeQualityPromotionSource(
        operation_digest=batch_task.sha256_hex(
            batch_task.QUALITY_PROMOTION_OPERATION_ID.encode()
        ),
        interpreter_digest=batch_task.sha256_hex(
            batch_task.QUALITY_PROMOTION_INTERPRETER_ID.encode()
        ),
        authority_digest=batch_task.sha256_hex(
            batch_task.QUALITY_PROMOTION_AUTHORITY_ID.encode()
        ),
    ),
)

# Shared assembly/catalog consumers derive the current cells from the authored
# source rather than restating the former C4.1/C4.2/C4.3 development labels.
ASSEMBLY_CELL_IDS = tuple(
    operation.operation_id for operation in DEFAULT_BATCH_TASK_NATIVE_SOURCE.operations
)
