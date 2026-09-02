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
from typing import Literal

from app.successor_runtime.capabilities.checksum import content_digest, require_hex64
from app.successor_runtime.language.plan import ExecutionPlan, with_plan_digest
from app.successor_runtime.language.program import ProgramSpec

__all__ = [
    "C1AcceptanceError",
    "C1NamedStepObservation",
    "C1RollbackBeforeAfter",
    "C1RuntimeEvidenceRefs",
    "C1SliceAcceptance",
    "C1SliceId",
    "C1StepStatus",
    "accept_c1_slice",
]

C1SliceId = Literal["A", "B", "C"]


class C1AcceptanceError(ValueError):
    """The exact Program/Plan or bounded C1 slice shape is invalid."""


class C1StepStatus(StrEnum):
    SUCCESS = "success"
    DEGRADED = "degraded"
    BLOCKED = "blocked"
    FAILURE = "failure"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class C1NamedStepObservation:
    """One already-captured observation for one exact compiled step."""

    name: str
    step_id: str
    status: C1StepStatus
    result_digest: str
    evidence_ref: str

    def __post_init__(self) -> None:
        if not self.name or not self.step_id or not self.evidence_ref:
            raise C1AcceptanceError(
                "named step observation identities must be non-empty"
            )
        require_hex64(self.result_digest, "C1NamedStepObservation.result_digest")


@dataclass(frozen=True, slots=True)
class C1RuntimeEvidenceRefs:
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
                raise C1AcceptanceError(f"{field_name} must contain opaque refs")
            if len(set(refs)) != len(refs):
                raise C1AcceptanceError(f"{field_name} must not contain duplicates")


@dataclass(frozen=True, slots=True)
class C1RollbackBeforeAfter:
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
            raise C1AcceptanceError("rollback_ref must be non-empty")
        if self.before_authority_epoch < 0:
            raise C1AcceptanceError("before_authority_epoch must be non-negative")
        if self.after_authority_epoch != self.before_authority_epoch + 1:
            raise C1AcceptanceError(
                "rollback may only advance the future owner authority epoch once"
            )
        if not self.before_journal_refs or not self.before_readback_refs:
            raise C1AcceptanceError("rollback requires retained journal/readback refs")
        if self.after_journal_refs != self.before_journal_refs:
            raise C1AcceptanceError("rollback must retain exact journal refs")
        if self.after_readback_refs != self.before_readback_refs:
            raise C1AcceptanceError("rollback must retain exact readback refs")


@dataclass(frozen=True, slots=True)
class C1SliceAcceptance:
    """Content-addressed, effect-free acceptance closure for one C1 slice."""

    schema: str
    slice_id: C1SliceId
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
            require_hex64(getattr(self, name), f"C1SliceAcceptance.{name}")
        expected = content_digest(self, omit_fields=("acceptance_digest",))
        if not self.acceptance_digest:
            object.__setattr__(self, "acceptance_digest", expected)
        elif self.acceptance_digest != expected:
            raise C1AcceptanceError("acceptance_digest does not bind the closure")

    @property
    def accepted(self) -> bool:
        return self.observational_compatibility and not self.blocking_findings


_SLICE_OPERATION_KINDS: dict[C1SliceId, tuple[str, ...]] = {
    "A": ("ingest_index.stage_candidate.v1",),
    "B": ("c8.writing.compose.v1", "c8.writing.stage.v1"),
    "C": (
        "c8.report.stage.v1",
        "c8.report.verify.v1",
        "c8.report.admission.v1",
        "c8.delivery_intent_prepare.v1",
        "delivery.internal_export.v1",
    ),
}

_SLICE_STEP_KINDS: dict[C1SliceId, tuple[str, ...]] = {
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

_BASE_DECLARED_DIFFERENCES: dict[C1SliceId, tuple[str, ...]] = {
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
        raise C1AcceptanceError("ProgramSpec carries a stale program_digest")
    if in_plan.program_id != in_program.program_id:
        raise C1AcceptanceError("Program/ExecutionPlan program_id mismatch")
    if in_plan.program_digest != exact_program_digest:
        raise C1AcceptanceError("ExecutionPlan does not bind the exact ProgramSpec")
    if in_plan.plan_digest != with_plan_digest(in_plan).plan_digest:
        raise C1AcceptanceError("ExecutionPlan carries a stale plan_digest")

    def require_control(node: object) -> None:
        node.require_valid_control_digest()
        for child in node.children:
            require_control(child)

    try:
        require_control(in_plan.control_root)
    except ValueError as exc:
        raise C1AcceptanceError(str(exc)) from exc

    step_ids = tuple(step.step_id for step in in_plan.ordered_steps)
    if len(step_ids) != len(set(step_ids)):
        raise C1AcceptanceError("ExecutionPlan step IDs must be unique")
    if in_plan.dependency_index.entries != tuple(
        (step.step_id, step.dependencies) for step in in_plan.ordered_steps
    ):
        raise C1AcceptanceError("ExecutionPlan dependency index drift")


def _ordered_operation_refs(in_plan: ExecutionPlan) -> tuple[tuple[str, str, str], ...]:
    refs: list[tuple[str, str, str]] = []
    for step in in_plan.ordered_steps:
        ref = step.operation_contract_ref
        if ref is None or step.step_kind == "ADMISSION":
            continue
        refs.append((ref.kind, ref.contract_version, ref.contract_digest))
    return tuple(refs)


def _require_slice_shape(
    in_slice_id: C1SliceId,
    in_program: ProgramSpec,
    in_plan: ExecutionPlan,
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    if in_slice_id not in _SLICE_OPERATION_KINDS:
        raise C1AcceptanceError(f"unsupported C1 slice: {in_slice_id!r}")
    operation_kinds = tuple(ref[0] for ref in _ordered_operation_refs(in_plan))
    step_kinds = tuple(step.step_kind for step in in_plan.ordered_steps)
    if operation_kinds != _SLICE_OPERATION_KINDS[in_slice_id]:
        raise C1AcceptanceError(
            f"Slice {in_slice_id} operation shape drift: {operation_kinds!r}"
        )
    if step_kinds != _SLICE_STEP_KINDS[in_slice_id]:
        raise C1AcceptanceError(
            f"Slice {in_slice_id} ordered step shape drift: {step_kinds!r}"
        )
    if in_slice_id == "A" and in_program.semantic_identity != (
        "ingest-index.stage-candidate"
    ):
        raise C1AcceptanceError("Slice A must use the real C7 ingest semantic identity")
    if in_slice_id == "B" and in_program.semantic_identity != (
        "c8.knowledge-writing-report-graph"
    ):
        raise C1AcceptanceError("Slice B must use the current C8 composition")
    if in_slice_id == "C" and in_program.semantic_identity != (
        "c8.report.stage-verify-admission-delivery"
    ):
        raise C1AcceptanceError("Slice C must use the C8 report-delivery bridge")

    forbidden_tokens = (".graph.", ".ui.", ".api.", "projector")
    if in_slice_id in {"B", "C"} and any(
        token in kind for kind in operation_kinds for token in forbidden_tokens
    ):
        raise C1AcceptanceError(
            f"Slice {in_slice_id} Program must exclude graph/API/UI projector atoms"
        )
    if in_slice_id == "C":
        delivery_step = in_plan.ordered_steps[-2]
        admission_step = in_plan.ordered_steps[-1]
        if not delivery_step.return_contract.admission_required:
            raise C1AcceptanceError("Slice C delivery must require separate admission")
        if admission_step.dependencies != (delivery_step.step_id,):
            raise C1AcceptanceError("Slice C delivery admission dependency drift")
    assignment_kinds = tuple(
        _ASSIGNMENT_KIND_BY_STEP_KIND[step_kind] for step_kind in step_kinds
    )
    return operation_kinds, step_kinds, assignment_kinds


def _require_observation_shape(
    observations: tuple[C1NamedStepObservation, ...],
    in_plan: ExecutionPlan,
    side: str,
) -> None:
    expected_step_ids = tuple(step.step_id for step in in_plan.ordered_steps)
    observed_step_ids = tuple(observation.step_id for observation in observations)
    if observed_step_ids != expected_step_ids:
        raise C1AcceptanceError(
            f"{side} observations must cover exact ordered ExecutionPlan steps"
        )
    names = tuple(observation.name for observation in observations)
    if len(names) != len(set(names)):
        raise C1AcceptanceError(f"{side} observation names must be unique")


def _compare_observations(
    legacy: tuple[C1NamedStepObservation, ...],
    successor: tuple[C1NamedStepObservation, ...],
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
        if status == C1StepStatus.DEGRADED:
            declared.append(f"MATCHED_DEGRADED_OBSERVATION:{name}")
        elif status in {
            C1StepStatus.BLOCKED,
            C1StepStatus.FAILURE,
            C1StepStatus.UNKNOWN,
        }:
            blockers.append(f"OBSERVED_{status.value.upper()}:{name}")
    return compatible, tuple(declared), tuple(blockers)


def accept_c1_slice(
    *,
    in_slice_id: C1SliceId,
    in_program: ProgramSpec,
    in_plan: ExecutionPlan,
    in_legacy_step_observations: tuple[C1NamedStepObservation, ...],
    in_successor_step_observations: tuple[C1NamedStepObservation, ...],
    in_runtime_evidence: C1RuntimeEvidenceRefs,
    in_rollback_before_after: C1RollbackBeforeAfter,
) -> C1SliceAcceptance:
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
        raise C1AcceptanceError(
            "rollback journal refs must equal runtime evidence refs"
        )
    if (
        in_runtime_evidence.readback_refs
        != in_rollback_before_after.before_readback_refs
    ):
        raise C1AcceptanceError(
            "rollback readback refs must equal runtime evidence refs"
        )

    compatible, observed_differences, blockers = _compare_observations(
        in_legacy_step_observations,
        in_successor_step_observations,
    )
    exact_operation_refs = _ordered_operation_refs(in_plan)
    return C1SliceAcceptance(
        schema="mrw.functorial-successor.c1-slice-acceptance.v1",
        slice_id=in_slice_id,
        program_id=in_program.program_id,
        program_digest=in_program.program_digest,
        plan_digest=in_plan.plan_digest,
        catalog_digest=content_digest(
            {
                "schema": "mrw.c1.used-operation-catalog-closure.v1",
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
