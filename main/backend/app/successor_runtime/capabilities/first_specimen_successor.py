"""Pure Gap-to-successor materialization for the frozen first specimen.

The capability derives one immutable successor closure.  It neither opens a
transaction nor treats a Gap as a ResearchIntent.  The Gap remains the source
of an explicit ``opens`` relation; the new Inquiry keeps the predecessor
Inquiry's admitted ResearchIntent binding.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.successor_runtime.language.algebra import (
    OperationContractCatalogSnapshot,
    ValueRef,
    canonical_digest,
)
from app.successor_runtime.language.combinators import (
    materialize_first_specimen_gap_successor,
)
from app.successor_runtime.language.compile import compile_program
from app.successor_runtime.language.object_contracts import OperationContractResolver
from app.successor_runtime.language.plan import ExecutionPlan
from app.successor_runtime.language.program import (
    ProgramSpec,
    Pure,
    SuccessorMaterialization,
    Then,
)
from app.successor_runtime.research.claims import Gap
from app.successor_runtime.research.codec import (
    canonical_bytes,
    is_sha256_hex,
    sha256_hex,
)
from app.successor_runtime.research.identities import ResearchObjectRef
from app.successor_runtime.research.inquiries import Inquiry, PlanWorkItem, ResearchPlan
from app.successor_runtime.research.object_types import (
    CANONICAL_CODEC_ID,
    GAP_TYPE,
    INQUIRY_TYPE,
    RESEARCH_INTENT_TYPE,
    RESEARCH_PLAN_TYPE,
)
from app.successor_runtime.research.relations import ResearchRelation

GAP_SUCCESSOR_CAPABILITY_ID = "mrw.first-specimen.gap-successor"
GAP_SUCCESSOR_VALUE_CODEC = CANONICAL_CODEC_ID


class GapSuccessorRejected(ValueError):
    """The supplied predecessor/materializer closure is not exact."""


@dataclass(frozen=True, slots=True)
class GapSuccessorClosure:
    """Complete pure closure written by the PostgreSQL interpreter."""

    request_digest: str
    materializer_binding_digest: str
    materializer_id: str
    materializer_version: str
    materialization: SuccessorMaterialization
    inquiry: Inquiry
    research_plan: ResearchPlan
    inquiry_value_ref: ValueRef
    research_plan_value_ref: ValueRef
    inquiry_ref: ResearchObjectRef
    research_plan_ref: ResearchObjectRef
    opens_relation: ResearchRelation
    successor_plan: ExecutionPlan
    successor_run_id: str
    successor_run_incarnation: str

    def __post_init__(self) -> None:
        for name in (
            "request_digest",
            "successor_run_id",
            "successor_run_incarnation",
        ):
            if not getattr(self, name):
                raise ValueError(f"{name} is required")
        if not is_sha256_hex(self.request_digest):
            raise ValueError("request_digest must be canonical sha256 hex")
        if (
            self.successor_plan.program_digest
            != self.materialization.successor_program_digest
        ):
            raise ValueError("successor Plan/Program digest drift")
        if self.opens_relation.source_ref.object_type != GAP_TYPE:
            raise ValueError("opens source must remain the admitted Gap")
        if self.opens_relation.target_ref != self.inquiry_ref:
            raise ValueError("opens target must be the exact successor Inquiry")


def build_gap_successor_closure(
    *,
    predecessor_program: ProgramSpec,
    predecessor_plan: ExecutionPlan,
    predecessor_run_id: str,
    predecessor_step_id: str,
    gap: Gap,
    gap_ref: ResearchObjectRef,
    source_value_ref: ValueRef,
    successor_intent_ref: ResearchObjectRef,
    predecessor_plan_digest: str,
    source_value_digest: str,
    materializer_binding_digest: str,
    materializer_id: str,
    materializer_version: str,
    authority_digest: str,
    catalog: OperationContractCatalogSnapshot,
    operation_contracts: OperationContractResolver,
) -> GapSuccessorClosure:
    """Derive one deterministic, schema-valid successor closure.

    Identity closes over the exact predecessor Program/Plan/run/step, admitted
    Gap/value, MaterializerBinding and current authority.  Node identity is not
    included: two isomorphic RuntimeNodes materialize the same logical request.
    """

    _require_predecessor(
        predecessor_program=predecessor_program,
        predecessor_plan=predecessor_plan,
        predecessor_run_id=predecessor_run_id,
        predecessor_step_id=predecessor_step_id,
    )
    _require_gap(
        gap=gap,
        gap_ref=gap_ref,
        source_value_ref=source_value_ref,
        predecessor_program=predecessor_program,
    )
    _require_intent(successor_intent_ref, predecessor_program.project_key)
    if not is_sha256_hex(authority_digest) or authority_digest == "0" * 64:
        raise GapSuccessorRejected("current materialization authority is required")
    if (
        predecessor_plan_digest != predecessor_plan.plan_digest
        or source_value_digest != source_value_ref.content_digest
        or not is_sha256_hex(materializer_binding_digest)
        or not materializer_id
        or not materializer_version
    ):
        raise GapSuccessorRejected("MaterializerBinding predecessor/source drift")

    materialization = materialize_first_specimen_gap_successor(
        predecessor_program=predecessor_program,
        predecessor_run_id=predecessor_run_id,
        predecessor_step_id=predecessor_step_id,
        predecessor_plan_digest=predecessor_plan.plan_digest,
        source_value_ref=source_value_ref,
        gap=gap,
        successor_intent_ref=successor_intent_ref.object_id,
        authority_digest=authority_digest,
        materializer_id=materializer_id,
        materializer_version=materializer_version,
    )
    inquiry, research_plan = _decode_materialized_literals(materialization)
    successor_plan = compile_program(
        materialization.successor_program,
        catalog,
        operation_contracts=operation_contracts,
    )
    request_digest = canonical_digest(
        {
            "schema": "mrw.first-specimen.gap-successor-request.v1",
            "materialization_id": materialization.materialization_id,
            "materializer_binding_digest": materializer_binding_digest,
            "gap_ref": _object_ref_identity(gap_ref),
            "intent_ref": _object_ref_identity(successor_intent_ref),
            "successor_program_digest": materialization.successor_program_digest,
            "successor_plan_digest": successor_plan.plan_digest,
        }
    )
    provenance_digest = canonical_digest(
        {
            "schema": "mrw.first-specimen.gap-successor-provenance.v1",
            "request_digest": request_digest,
            "predecessor_program_digest": predecessor_program.program_digest,
            "predecessor_plan_digest": predecessor_plan.plan_digest,
            "predecessor_run_id": predecessor_run_id,
            "predecessor_step_id": predecessor_step_id,
            "source_gap_digest": gap_ref.content_digest,
            "authority_digest": authority_digest,
        }
    )
    inquiry_value_ref = _value_ref(
        project_key=predecessor_program.project_key,
        value_id=inquiry.inquiry_id,
        object_type=INQUIRY_TYPE,
        content=inquiry,
        provenance_digest=provenance_digest,
    )
    research_plan_value_ref = _value_ref(
        project_key=predecessor_program.project_key,
        value_id=research_plan.plan_id,
        object_type=RESEARCH_PLAN_TYPE,
        content=research_plan,
        provenance_digest=provenance_digest,
    )
    inquiry_ref = _ledger_ref(
        object_id=inquiry.inquiry_id,
        value_ref=inquiry_value_ref,
        materialization_digest=request_digest,
    )
    research_plan_ref = _ledger_ref(
        object_id=research_plan.plan_id,
        value_ref=research_plan_value_ref,
        materialization_digest=request_digest,
    )
    relation_seed = canonical_digest(
        {
            "relation_type": "opens",
            "source": _object_ref_identity(gap_ref),
            "target": _object_ref_identity(inquiry_ref),
            "provenance": provenance_digest,
        }
    )
    opens_relation = ResearchRelation(
        relation_id=f"relation:opens:sha256:{relation_seed}",
        relation_type="opens",
        project_key=predecessor_program.project_key,
        source_ref=gap_ref,
        target_ref=inquiry_ref,
        provenance_closure_digest=provenance_digest,
        direction="OPENS",
        scope_ref=f"gap:{gap.gap_id}",
        uncertainty_profile_ref="uncertainty:explicit",
        incarnation=f"relation-inc:sha256:{relation_seed}",
    )
    run_seed = canonical_digest(
        {
            "schema": "mrw.first-specimen.gap-successor-run.v1",
            "request_digest": request_digest,
            "program_digest": materialization.successor_program_digest,
            "plan_digest": successor_plan.plan_digest,
        }
    )
    return GapSuccessorClosure(
        request_digest=request_digest,
        materializer_binding_digest=materializer_binding_digest,
        materializer_id=materializer_id,
        materializer_version=materializer_version,
        materialization=materialization,
        inquiry=inquiry,
        research_plan=research_plan,
        inquiry_value_ref=inquiry_value_ref,
        research_plan_value_ref=research_plan_value_ref,
        inquiry_ref=inquiry_ref,
        research_plan_ref=research_plan_ref,
        opens_relation=opens_relation,
        successor_plan=successor_plan,
        successor_run_id=f"run:successor:sha256:{run_seed}",
        successor_run_incarnation=f"run-inc:successor:sha256:{run_seed}",
    )


def _require_predecessor(
    *,
    predecessor_program: ProgramSpec,
    predecessor_plan: ExecutionPlan,
    predecessor_run_id: str,
    predecessor_step_id: str,
) -> None:
    if not predecessor_run_id or not predecessor_step_id:
        raise GapSuccessorRejected("predecessor run/step identity is required")
    if (
        predecessor_plan.program_id != predecessor_program.program_id
        or predecessor_plan.program_digest != predecessor_program.program_digest
        or predecessor_program.program_digest != predecessor_program.digest()
    ):
        raise GapSuccessorRejected("predecessor Program/Plan closure drift")


def _require_gap(
    *,
    gap: Gap,
    gap_ref: ResearchObjectRef,
    source_value_ref: ValueRef,
    predecessor_program: ProgramSpec,
) -> None:
    if gap.content_digest is None:
        raise GapSuccessorRejected("Gap has no canonical content digest")
    if (
        gap_ref.object_type != GAP_TYPE
        or source_value_ref.object_type != GAP_TYPE
        or gap_ref.lifecycle_state != "ADMITTED"
        or gap_ref.object_id != gap.gap_id
        or gap_ref.project_key != predecessor_program.project_key
        or source_value_ref.project_key != predecessor_program.project_key
        or gap_ref.content_ref != source_value_ref.storage_ref
        or gap_ref.content_digest != gap.content_digest
        or source_value_ref.content_digest != gap.content_digest
        or gap_ref.provenance_closure_digest != source_value_ref.provenance_digest
    ):
        raise GapSuccessorRejected("admitted Gap/value exact binding drift")


def _require_intent(ref: ResearchObjectRef, project_key: str) -> None:
    if (
        ref.object_type != RESEARCH_INTENT_TYPE
        or ref.project_key != project_key
        or ref.lifecycle_state != "ADMITTED"
    ):
        raise GapSuccessorRejected(
            "successor intent must be an admitted ResearchIntent"
        )


def _decode_materialized_literals(
    materialization: SuccessorMaterialization,
) -> tuple[Inquiry, ResearchPlan]:
    root = materialization.successor_program.root
    if (
        not isinstance(root, Then)
        or not isinstance(root.first, Pure)
        or not isinstance(root.second, Pure)
    ):
        raise GapSuccessorRejected(
            "successor Program is not the frozen Inquiry/Plan shape"
        )
    inquiry_raw = dict(root.first.literal_value)
    plan_raw = dict(root.second.literal_value)
    inquiry = Inquiry(
        inquiry_id=inquiry_raw["inquiry_id"],
        intent_ref=inquiry_raw["intent_ref"],
        question_or_hypothesis=inquiry_raw["question_or_hypothesis"],
        acceptance_conditions=tuple(inquiry_raw["acceptance_conditions"]),
        stop_conditions=tuple(inquiry_raw["stop_conditions"]),
        uncertainty_ceiling=inquiry_raw["uncertainty_ceiling"],
        content_digest=inquiry_raw["content_digest"],
    )
    work_items = tuple(
        PlanWorkItem(
            work_id=dict(item)["work_id"],
            operator=dict(item)["operator"],
            depends_on=tuple(dict(item).get("depends_on", ())),
        )
        for item in plan_raw["work_items"]
    )
    research_plan = ResearchPlan(
        plan_id=plan_raw["plan_id"],
        inquiry_ref=plan_raw["inquiry_ref"],
        work_items=work_items,
        budget=dict(plan_raw["budget"]),
        deadline=None,
        replan_policy=dict(plan_raw["replan_policy"]),
        content_digest=plan_raw["content_digest"],
    )
    return inquiry, research_plan


def _value_ref(
    *,
    project_key: str,
    value_id: str,
    object_type: object,
    content: object,
    provenance_digest: str,
) -> ValueRef:
    exact = canonical_bytes(content)
    return ValueRef(
        value_id=value_id,
        project_key=project_key,
        object_type=object_type,
        codec_id=GAP_SUCCESSOR_VALUE_CODEC,
        content_digest=sha256_hex(content),
        storage_kind="project_value_ref",
        store_id="successor_values",
        store_version="1",
        storage_ref=f"project-value:{value_id}",
        byte_size=len(exact),
        provenance_digest=provenance_digest,
    )


def _ledger_ref(
    *,
    object_id: str,
    value_ref: ValueRef,
    materialization_digest: str,
) -> ResearchObjectRef:
    incarnation = canonical_digest(
        {
            "schema": "mrw.first-specimen.gap-successor-object-incarnation.v1",
            "object_id": object_id,
            "materialization_digest": materialization_digest,
        }
    )
    return ResearchObjectRef(
        object_id=object_id,
        object_type=value_ref.object_type,
        project_key=value_ref.project_key,
        revision=1,
        incarnation=f"object-inc:sha256:{incarnation}",
        owner_binding_ref="ResearchLedger",
        content_ref=value_ref.storage_ref,
        content_digest=value_ref.content_digest,
        provenance_closure_digest=value_ref.provenance_digest,
        lifecycle_state="ADMITTED",
    )


def _object_ref_identity(ref: ResearchObjectRef) -> dict[str, object]:
    return {
        "object_id": ref.object_id,
        "object_type": ref.object_type.type_id,
        "project_key": ref.project_key,
        "revision": ref.revision,
        "incarnation": ref.incarnation,
        "content_ref": ref.content_ref,
        "content_digest": ref.content_digest,
        "provenance_closure_digest": ref.provenance_closure_digest,
        "lifecycle_state": ref.lifecycle_state,
    }


__all__ = [
    "GAP_SUCCESSOR_CAPABILITY_ID",
    "GAP_SUCCESSOR_VALUE_CODEC",
    "GapSuccessorClosure",
    "GapSuccessorRejected",
    "build_gap_successor_closure",
]
