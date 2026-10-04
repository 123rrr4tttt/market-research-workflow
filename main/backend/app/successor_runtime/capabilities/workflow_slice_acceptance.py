"""Pure horizontal acceptance for C1 Slice A/B/C.

C1 does not own an execution graph.  The exact ``ProgramSpec`` and
``ExecutionPlan`` remain the only executable description; this module only
binds their structural closure to already-captured, named observations.
Nothing here selects an interpreter, executes an effect, reads a projector, or
grants authority.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from hashlib import sha256
from typing import Literal, NoReturn, TypeAlias

from functorial_kit import Failure
from app.successor_runtime.capabilities.checksum import content_digest, require_hex64
from app.successor_runtime.capabilities.workflow_common import (
    HISTORICAL_C1_ACCEPTANCE_SCHEMA,
    WORKFLOW_ACCEPTANCE_DIGEST_INVALID,
    WORKFLOW_ACCEPTANCE_INPUT_INVALID,
    WORKFLOW_ACCEPTANCE_SCHEMA,
    WORKFLOW_DEFINITION_FAILURES,
    WORKFLOW_OBSERVATION_SHAPE_INVALID,
    WORKFLOW_PROGRAM_PLAN_BINDING_INVALID,
    WORKFLOW_ROLLBACK_BINDING_INVALID,
    WORKFLOW_SLICE_SHAPE_INVALID,
)
from app.successor_runtime.language.plan import ExecutionPlan, with_plan_digest
from app.successor_runtime.language.program import ProgramSpec

__all__ = [
    "WorkflowAcceptanceError",
    "WorkflowNamedStepObservation",
    "WorkflowRollbackBeforeAfter",
    "WorkflowRuntimeEvidenceRefs",
    "WorkflowSliceAcceptance",
    "WorkflowSliceResult",
    "WorkflowSliceId",
    "WorkflowStepStatus",
    "HISTORICAL_C1_ACCEPTANCE_SCHEMA",
    "WORKFLOW_ACCEPTANCE_SCHEMA",
    "WorkflowAcceptanceArtifactRead",
    "WorkflowAcceptanceSchemaIdentity",
    "accept_workflow_slice",
    "decode_workflow_acceptance_schema",
    "read_workflow_acceptance_artifact",
    "replay_workflow_acceptance_artifact",
    "try_accept_workflow_slice",
]

WorkflowSliceId = Literal["A", "B", "C"]
WorkflowSliceResult: TypeAlias = "WorkflowSliceAcceptance | Failure"
WORKFLOW_FAILURE_OWNER = "workflow.runtime.observe.v2"
WORKFLOW_FAILURE_WITNESS = "test:test_w06_c2_total_core_failure_lifts"


class WorkflowAcceptanceError(ValueError):
    """The exact Program/Plan or bounded workflow slice shape is invalid."""

    def __init__(self, message: str, failure: Failure | None = None) -> None:
        super().__init__(message)
        self.failure = failure


@dataclass(frozen=True, slots=True)
class WorkflowAcceptanceSchemaIdentity:
    """Explicit identity for current or historical workflow acceptance bytes."""

    schema: str
    era: Literal["current", "historical_c1"]


@dataclass(frozen=True, slots=True)
class WorkflowAcceptanceArtifactRead:
    """Exact workflow acceptance bytes retained across versioned readback."""

    identity: WorkflowAcceptanceSchemaIdentity
    raw_bytes: bytes
    sha256: str


def decode_workflow_acceptance_schema(
    schema: str,
) -> WorkflowAcceptanceSchemaIdentity:
    if schema == WORKFLOW_ACCEPTANCE_SCHEMA:
        return WorkflowAcceptanceSchemaIdentity(schema=schema, era="current")
    if schema == HISTORICAL_C1_ACCEPTANCE_SCHEMA:
        return WorkflowAcceptanceSchemaIdentity(schema=schema, era="historical_c1")
    _raise_acceptance_failure(
        _acceptance_failure(
            WORKFLOW_ACCEPTANCE_INPUT_INVALID,
            f"unsupported workflow acceptance schema: {schema}",
            site="schema",
        )
    )


def read_workflow_acceptance_artifact(
    *,
    schema: str,
    raw_bytes: bytes,
) -> WorkflowAcceptanceArtifactRead:
    """Read acceptance bytes without normalizing or re-encoding them."""

    if not isinstance(raw_bytes, bytes):
        _raise_acceptance_failure(
            _acceptance_failure(
                WORKFLOW_ACCEPTANCE_INPUT_INVALID,
                "workflow acceptance artifact raw_bytes must be bytes",
                site="raw_bytes",
            )
        )
    return WorkflowAcceptanceArtifactRead(
        identity=decode_workflow_acceptance_schema(schema),
        raw_bytes=raw_bytes,
        sha256=sha256(raw_bytes).hexdigest(),
    )


def replay_workflow_acceptance_artifact(
    artifact: WorkflowAcceptanceArtifactRead,
) -> bytes:
    """Replay exact acceptance bytes after verifying their retained hash."""

    if sha256(artifact.raw_bytes).hexdigest() != artifact.sha256:
        _raise_acceptance_failure(
            _acceptance_failure(
                WORKFLOW_ACCEPTANCE_DIGEST_INVALID,
                "workflow acceptance artifact hash mismatch",
                site="sha256",
            )
        )
    return artifact.raw_bytes


def _acceptance_failure(code: str, message: str, *, site: str) -> Failure:
    return WORKFLOW_DEFINITION_FAILURES.fail(
        code,
        message,
        {
            "owner": WORKFLOW_FAILURE_OWNER,
            "operation": "accept_workflow_slice",
            "site": site,
            "public_exception": "WorkflowAcceptanceError",
            "public_message": message,
            "witness": WORKFLOW_FAILURE_WITNESS,
        },
    )


def _raise_acceptance_failure(failure: Failure) -> NoReturn:
    context = failure.context or {}
    if (
        failure.family != WORKFLOW_DEFINITION_FAILURES.name
        or context.get("public_exception") != WorkflowAcceptanceError.__name__
        or not context.get("public_message")
    ):
        # kit:boundary owner=workflow_slice_acceptance.py class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w06_c2_total_core_failure_lifts
        raise TypeError("workflow acceptance lift context is incomplete")
    # kit:boundary owner=workflow_slice_acceptance.py class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=workflow.definition.failure witness=test:test_historical_acceptance_readback_preserves_bytes_and_rejects_unknown_schema
    raise WorkflowAcceptanceError(str(context["public_message"]), failure)


def _reject(
    message: str,
    *,
    code: str = WORKFLOW_ACCEPTANCE_INPUT_INVALID,
    site: str = "accept_workflow_slice",
) -> NoReturn:
    _raise_acceptance_failure(_acceptance_failure(code, message, site=site))


class WorkflowStepStatus(StrEnum):
    SUCCESS = "success"
    DEGRADED = "degraded"
    BLOCKED = "blocked"
    FAILURE = "failure"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class WorkflowNamedStepObservation:
    """One already-captured observation for one exact compiled step."""

    name: str
    step_id: str
    status: WorkflowStepStatus
    result_digest: str
    evidence_ref: str

    def __post_init__(self) -> None:
        if not self.name or not self.step_id or not self.evidence_ref:
            return _reject(
                "named step observation identities must be non-empty"
            )
        require_hex64(self.result_digest, "WorkflowNamedStepObservation.result_digest")


@dataclass(frozen=True, slots=True)
class WorkflowRuntimeEvidenceRefs:
    """Opaque refs to evidence captured outside this pure acceptance surface."""

    runtime_evidence_refs: tuple[str, ...]
    journal_refs: tuple[str, ...]
    readback_refs: tuple[str, ...]
    replay_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        for field_name, refs in (
            ("runtime_evidence_refs", self.runtime_evidence_refs),
            ("journal_refs", self.journal_refs),
            ("readback_refs", self.readback_refs),
            ("replay_refs", self.replay_refs),
        ):
            if not refs or any(not ref for ref in refs):
                return _reject(f"{field_name} must contain opaque refs", code=WORKFLOW_ACCEPTANCE_INPUT_INVALID, site=field_name)
            if len(set(refs)) != len(refs):
                return _reject(f"{field_name} must not contain duplicates", code=WORKFLOW_ACCEPTANCE_INPUT_INVALID, site=field_name)


@dataclass(frozen=True, slots=True)
class WorkflowRollbackBeforeAfter:
    """Future-owner rollback evidence that preserves journal/readback identity."""

    rollback_ref: str
    before_authority_epoch: int
    after_authority_epoch: int
    before_journal_refs: tuple[str, ...]
    after_journal_refs: tuple[str, ...]
    before_readback_refs: tuple[str, ...]
    after_readback_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.rollback_ref:
            return _reject("rollback_ref must be non-empty", code=WORKFLOW_ROLLBACK_BINDING_INVALID, site="rollback_ref")
        if self.before_authority_epoch < 0:
            return _reject("before_authority_epoch must be non-negative", code=WORKFLOW_ROLLBACK_BINDING_INVALID, site="before_authority_epoch")
        if self.after_authority_epoch != self.before_authority_epoch + 1:
            return _reject(
                "rollback may only advance the future owner authority epoch once"
            )
        if not self.before_journal_refs or not self.before_readback_refs:
            return _reject("rollback requires retained journal/readback refs", code=WORKFLOW_ROLLBACK_BINDING_INVALID, site="rollback_refs")
        if self.after_journal_refs != self.before_journal_refs:
            return _reject("rollback must retain exact journal refs", code=WORKFLOW_ROLLBACK_BINDING_INVALID, site="journal_refs")
        if self.after_readback_refs != self.before_readback_refs:
            return _reject("rollback must retain exact readback refs", code=WORKFLOW_ROLLBACK_BINDING_INVALID, site="readback_refs")


@dataclass(frozen=True, slots=True)
class WorkflowSliceAcceptance:
    """Content-addressed, effect-free acceptance closure for one workflow slice."""

    schema: str
    slice_id: WorkflowSliceId
    program_id: str
    program_digest: str
    plan_digest: str
    catalog_digest: str
    control_root_digest: str
    source_map_digest: str
    dependency_index_digest: str
    ordered_operation_kinds: tuple[str, ...]
    ordered_step_kinds: tuple[str, ...]
    ordered_assignment_kinds: tuple[str, ...]
    observation_profile: str
    legacy_observation_digest: str
    successor_observation_digest: str
    observational_compatibility: bool
    compatibility_claim: str
    declared_differences: tuple[str, ...]
    runtime_evidence_refs: tuple[str, ...]
    journal_refs: tuple[str, ...]
    readback_refs: tuple[str, ...]
    replay_refs: tuple[str, ...]
    rollback_refs: tuple[str, ...]
    rollback_before_authority_epoch: int
    rollback_after_authority_epoch: int
    blocking_findings: tuple[str, ...]
    acceptance_digest: str = field(default="")

    def __post_init__(self) -> None:
        if self.schema != WORKFLOW_ACCEPTANCE_SCHEMA:
            return _reject(
                f"unsupported current workflow acceptance schema: {self.schema}",
                code=WORKFLOW_ACCEPTANCE_INPUT_INVALID,
                site="schema",
            )
        for name in (
            "program_digest",
            "plan_digest",
            "catalog_digest",
            "control_root_digest",
            "source_map_digest",
            "dependency_index_digest",
            "legacy_observation_digest",
            "successor_observation_digest",
        ):
            require_hex64(getattr(self, name), f"WorkflowSliceAcceptance.{name}")
        expected = content_digest(self, omit_fields=("acceptance_digest",))
        if not self.acceptance_digest:
            object.__setattr__(self, "acceptance_digest", expected)
        elif self.acceptance_digest != expected:
            return _reject("acceptance_digest does not bind the closure", code=WORKFLOW_ACCEPTANCE_DIGEST_INVALID, site="acceptance_digest")

    @property
    def accepted(self) -> bool:
        return self.observational_compatibility and not self.blocking_findings


_SLICE_OPERATION_KINDS: dict[WorkflowSliceId, tuple[str, ...]] = {
    "A": ("ingest_index.stage_candidate.v1",),
    "B": ("knowledge.writing.compose.v2", "knowledge.writing.stage.v2"),
    "C": (
        "knowledge.report.stage.v2",
        "knowledge.report.verify.v2",
        "knowledge.report.admission.v2",
        "knowledge.report.prepare_delivery_intent.v2",
        "delivery.internal_export.v1",
    ),
}

_SLICE_STEP_KINDS: dict[WorkflowSliceId, tuple[str, ...]] = {
    "A": ("EFFECT", "ADMISSION"),
    "B": ("EFFECT", "EFFECT"),
    "C": (
        "EFFECT",
        "EFFECT",
        "EFFECT",
        "ADMISSION",
        "EFFECT",
        "EFFECT",
        "ADMISSION",
    ),
}

_BASE_DECLARED_DIFFERENCES: dict[WorkflowSliceId, tuple[str, ...]] = {
    "A": ("legacy_graph_dsl_is_not_rehydrated_as_a_second_graph_json",),
    "B": ("graph_and_ui_projectors_are_excluded_from_the_program",),
    "C": (
        "api_and_ui_projectors_are_excluded_from_the_program",
        "delivery_requires_separate_current_authority",
    ),
}

_ASSIGNMENT_KIND_BY_STEP_KIND = {
    "PURE": "NO_RUNTIME_ASSIGNMENT",
    "TRANSFORM": "NO_RUNTIME_ASSIGNMENT",
    "MERGE": "NO_RUNTIME_ASSIGNMENT",
    "DECIDE": "NO_RUNTIME_ASSIGNMENT",
    "EFFECT": "INTERPRET",
    "ADMISSION": "VERIFY_ADMIT",
}


def _require_exact_program_plan(
    in_program: ProgramSpec,
    in_plan: ExecutionPlan,
) -> None:
    exact_program_digest = in_program.digest()
    if (
        not in_program.program_digest
        or in_program.program_digest != exact_program_digest
    ):
        return _reject("ProgramSpec carries a stale program_digest", code=WORKFLOW_PROGRAM_PLAN_BINDING_INVALID, site="program_digest")
    if in_plan.program_id != in_program.program_id:
        return _reject("Program/ExecutionPlan program_id mismatch", code=WORKFLOW_PROGRAM_PLAN_BINDING_INVALID, site="program_id")
    if in_plan.program_digest != exact_program_digest:
        return _reject("ExecutionPlan does not bind the exact ProgramSpec", code=WORKFLOW_PROGRAM_PLAN_BINDING_INVALID, site="plan.program_digest")
    if in_plan.plan_digest != with_plan_digest(in_plan).plan_digest:
        return _reject("ExecutionPlan carries a stale plan_digest", code=WORKFLOW_PROGRAM_PLAN_BINDING_INVALID, site="plan_digest")

    def require_control(node: object) -> None:
        node.require_valid_control_digest()
        for child in node.children:
            require_control(child)

    try:
        require_control(in_plan.control_root)
    except ValueError as exc:
        return _reject(str(exc), code=WORKFLOW_PROGRAM_PLAN_BINDING_INVALID, site="control_root")

    step_ids = tuple(step.step_id for step in in_plan.ordered_steps)
    if len(step_ids) != len(set(step_ids)):
        return _reject("ExecutionPlan step IDs must be unique", code=WORKFLOW_PROGRAM_PLAN_BINDING_INVALID, site="step_ids")
    if in_plan.dependency_index.entries != tuple(
        (step.step_id, step.dependencies) for step in in_plan.ordered_steps
    ):
        return _reject("ExecutionPlan dependency index drift", code=WORKFLOW_PROGRAM_PLAN_BINDING_INVALID, site="dependency_index")


def _ordered_operation_refs(in_plan: ExecutionPlan) -> tuple[tuple[str, str, str], ...]:
    refs: list[tuple[str, str, str]] = []
    for step in in_plan.ordered_steps:
        ref = step.operation_contract_ref
        if ref is None or step.step_kind == "ADMISSION":
            continue
        refs.append((ref.kind, ref.contract_version, ref.contract_digest))
    return tuple(refs)


def _require_slice_shape(
    in_slice_id: WorkflowSliceId,
    in_program: ProgramSpec,
    in_plan: ExecutionPlan,
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    if in_slice_id not in _SLICE_OPERATION_KINDS:
        return _reject(f"unsupported workflow slice: {in_slice_id!r}", code=WORKFLOW_SLICE_SHAPE_INVALID, site="slice_id")
    operation_kinds = tuple(ref[0] for ref in _ordered_operation_refs(in_plan))
    step_kinds = tuple(step.step_kind for step in in_plan.ordered_steps)
    if operation_kinds != _SLICE_OPERATION_KINDS[in_slice_id]:
        return _reject(
            f"Slice {in_slice_id} operation shape drift: {operation_kinds!r}"
        )
    if step_kinds != _SLICE_STEP_KINDS[in_slice_id]:
        return _reject(
            f"Slice {in_slice_id} ordered step shape drift: {step_kinds!r}"
        )
    if in_slice_id == "A" and in_program.semantic_identity != (
        "material.ingest.stage-candidate.v2"
    ):
        return _reject("Slice A must use the real C7 ingest semantic identity", code=WORKFLOW_SLICE_SHAPE_INVALID, site="semantic_identity")
    if in_slice_id == "B" and in_program.semantic_identity != (
        "knowledge.read-writing-report-graph.v2"
    ):
        return _reject("Slice B must use the current knowledge composition", code=WORKFLOW_SLICE_SHAPE_INVALID, site="semantic_identity")
    if in_slice_id == "C" and in_program.semantic_identity != (
        "knowledge.report.stage-verify-admission-delivery.v2"
    ):
        return _reject("Slice C must use the knowledge report-delivery bridge", code=WORKFLOW_SLICE_SHAPE_INVALID, site="semantic_identity")

    forbidden_tokens = (".graph.", ".ui.", ".api.", "projector")
    if in_slice_id in {"B", "C"} and any(
        token in kind for kind in operation_kinds for token in forbidden_tokens
    ):
        return _reject(
            f"Slice {in_slice_id} Program must exclude graph/API/UI projector atoms"
        )
    if in_slice_id == "C":
        delivery_step = in_plan.ordered_steps[-2]
        admission_step = in_plan.ordered_steps[-1]
        if not delivery_step.return_contract.admission_required:
            return _reject("Slice C delivery must require separate admission", code=WORKFLOW_SLICE_SHAPE_INVALID, site="delivery_admission")
        if admission_step.dependencies != (delivery_step.step_id,):
            return _reject("Slice C delivery admission dependency drift", code=WORKFLOW_SLICE_SHAPE_INVALID, site="delivery_dependency")
    assignment_kinds = tuple(
        _ASSIGNMENT_KIND_BY_STEP_KIND[step_kind] for step_kind in step_kinds
    )
    return operation_kinds, step_kinds, assignment_kinds


def _require_observation_shape(
    observations: tuple[WorkflowNamedStepObservation, ...],
    in_plan: ExecutionPlan,
    side: str,
) -> None:
    expected_step_ids = tuple(step.step_id for step in in_plan.ordered_steps)
    observed_step_ids = tuple(observation.step_id for observation in observations)
    if observed_step_ids != expected_step_ids:
        return _reject(
            f"{side} observations must cover exact ordered ExecutionPlan steps"
        )
    names = tuple(observation.name for observation in observations)
    if len(names) != len(set(names)):
        return _reject(f"{side} observation names must be unique", code=WORKFLOW_OBSERVATION_SHAPE_INVALID, site=f"{side}.names")


def _compare_observations(
    legacy: tuple[WorkflowNamedStepObservation, ...],
    successor: tuple[WorkflowNamedStepObservation, ...],
) -> tuple[bool, tuple[str, ...], tuple[str, ...]]:
    declared: list[str] = []
    blockers: list[str] = []
    compatible = True
    for legacy_observation, successor_observation in zip(
        legacy, successor, strict=True
    ):
        if legacy_observation.name != successor_observation.name:
            compatible = False
            blockers.append(
                "OBSERVATION_NAME_MISMATCH:"
                f"{legacy_observation.name}!={successor_observation.name}"
            )
            continue
        name = legacy_observation.name
        if (
            legacy_observation.status != successor_observation.status
            or legacy_observation.result_digest != successor_observation.result_digest
        ):
            compatible = False
            declared.append(
                f"{name}:legacy={legacy_observation.status.value}:"
                f"{legacy_observation.result_digest};"
                f"successor={successor_observation.status.value}:"
                f"{successor_observation.result_digest}"
            )
            blockers.append(f"OBSERVATION_MISMATCH:{name}")
            continue
        status = successor_observation.status
        if status == WorkflowStepStatus.DEGRADED:
            declared.append(f"MATCHED_DEGRADED_OBSERVATION:{name}")
        elif status in {
            WorkflowStepStatus.BLOCKED,
            WorkflowStepStatus.FAILURE,
            WorkflowStepStatus.UNKNOWN,
        }:
            blockers.append(f"OBSERVED_{status.value.upper()}:{name}")
    return compatible, tuple(declared), tuple(blockers)


def accept_workflow_slice(
    *,
    in_slice_id: WorkflowSliceId,
    in_program: ProgramSpec,
    in_plan: ExecutionPlan,
    in_legacy_step_observations: tuple[WorkflowNamedStepObservation, ...],
    in_successor_step_observations: tuple[WorkflowNamedStepObservation, ...],
    in_runtime_evidence: WorkflowRuntimeEvidenceRefs,
    in_rollback_before_after: WorkflowRollbackBeforeAfter,
) -> WorkflowSliceAcceptance:
    """Bind one exact Program/Plan to bounded named observational evidence.

    Validation of the immutable Program/Plan and slice shape deliberately
    precedes any observation traversal.  The function executes no callback and
    crosses no effect boundary.
    """

    _require_exact_program_plan(in_program, in_plan)
    operation_kinds, step_kinds, assignment_kinds = _require_slice_shape(
        in_slice_id,
        in_program,
        in_plan,
    )
    _require_observation_shape(in_legacy_step_observations, in_plan, "legacy")
    _require_observation_shape(in_successor_step_observations, in_plan, "successor")
    if in_runtime_evidence.journal_refs != in_rollback_before_after.before_journal_refs:
        return _reject(
            "rollback journal refs must equal runtime evidence refs"
        )
    if (
        in_runtime_evidence.readback_refs
        != in_rollback_before_after.before_readback_refs
    ):
        return _reject(
            "rollback readback refs must equal runtime evidence refs"
        )

    compatible, observed_differences, blockers = _compare_observations(
        in_legacy_step_observations,
        in_successor_step_observations,
    )
    exact_operation_refs = _ordered_operation_refs(in_plan)
    return WorkflowSliceAcceptance(
        schema=WORKFLOW_ACCEPTANCE_SCHEMA,
        slice_id=in_slice_id,
        program_id=in_program.program_id,
        program_digest=in_program.program_digest,
        plan_digest=in_plan.plan_digest,
        catalog_digest=content_digest(
            {
                "schema": "mrw.workflow.runtime.used-operation-catalog-closure.v2",
                "operation_contract_refs": exact_operation_refs,
            }
        ),
        control_root_digest=in_plan.control_root.control_digest,
        source_map_digest=content_digest(in_plan.source_map),
        dependency_index_digest=content_digest(in_plan.dependency_index),
        ordered_operation_kinds=operation_kinds,
        ordered_step_kinds=step_kinds,
        ordered_assignment_kinds=assignment_kinds,
        observation_profile=in_program.observation_profile,
        legacy_observation_digest=content_digest(in_legacy_step_observations),
        successor_observation_digest=content_digest(in_successor_step_observations),
        observational_compatibility=compatible,
        compatibility_claim="NAMED_OBSERVATIONAL_COMPATIBILITY_ONLY",
        declared_differences=(
            _BASE_DECLARED_DIFFERENCES[in_slice_id] + observed_differences
        ),
        runtime_evidence_refs=in_runtime_evidence.runtime_evidence_refs,
        journal_refs=in_runtime_evidence.journal_refs,
        readback_refs=in_runtime_evidence.readback_refs,
        replay_refs=in_runtime_evidence.replay_refs,
        rollback_refs=(in_rollback_before_after.rollback_ref,),
        rollback_before_authority_epoch=(
            in_rollback_before_after.before_authority_epoch
        ),
        rollback_after_authority_epoch=(in_rollback_before_after.after_authority_epoch),
        blocking_findings=blockers,
    )


def try_accept_workflow_slice(
    *,
    in_slice_id: WorkflowSliceId,
    in_program: ProgramSpec,
    in_plan: ExecutionPlan,
    in_legacy_step_observations: tuple[WorkflowNamedStepObservation, ...],
    in_successor_step_observations: tuple[WorkflowNamedStepObservation, ...],
    in_runtime_evidence: WorkflowRuntimeEvidenceRefs,
    in_rollback_before_after: WorkflowRollbackBeforeAfter,
) -> WorkflowSliceResult:
    """Return the typed C1 failure instead of raising the compatibility exception."""

    try:
        return accept_workflow_slice(
            in_slice_id=in_slice_id,
            in_program=in_program,
            in_plan=in_plan,
            in_legacy_step_observations=in_legacy_step_observations,
            in_successor_step_observations=in_successor_step_observations,
            in_runtime_evidence=in_runtime_evidence,
            in_rollback_before_after=in_rollback_before_after,
        )
    except WorkflowAcceptanceError as exc:
        if exc.failure is None:
            # This should only be reachable for an unexpected programmer defect.
            return _acceptance_failure(
                WORKFLOW_ACCEPTANCE_INPUT_INVALID,
                str(exc),
                site="try_accept_workflow_slice",
            )
        return exc.failure
