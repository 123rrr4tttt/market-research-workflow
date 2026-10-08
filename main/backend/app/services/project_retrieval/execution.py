"""Bounded execution of a project retrieval plan through registered MRW tools.

Candidates, collected documents, model proposals and validated graph elements
have separate identities. Only the last of these is committed as formal graph.
"""

from __future__ import annotations

from datetime import datetime, UTC
from hashlib import sha256
import json
from dataclasses import dataclass, replace
from functools import partial
from typing import Annotated, Any, Literal, cast
from collections.abc import Callable, Mapping

from functorial_kit import Failure
from sqlalchemy import MetaData, select
from sqlalchemy.engine import Connection, Engine

from app.services.agent_core.query_tools import (
    build_source_candidate_review_decision,
    build_source_discovery_search_queries,
)
from app.services.information_topology.contracts import (
    topology_state_codec,
    TopologyState,
    Element,
    ElementRef,
    BoundRef,
    Endpoint,
)
from app.services.information_topology.io.retrieval import resolve_domain_vocabulary
from app.services.information_topology.modules.retrieval import (
    domain_vocabulary_element,
    make_retrieval_profile,
    profile_from_state_payload,
    validate_evidence_v2,
)
from app.services.information_topology.profiles import ProfileSpec, decode_state, validate_state
from app.services.information_topology.service import InformationTopologyService
from app.services.project_retrieval.contracts import (
    RetrievalJsonObject,
)
from app.services.source_library.source_candidate_trust import (
    build_source_candidate_plan,
)
from app.successor_runtime.capabilities.acquisition_url import (
    URL_SINGLE_URL_OUTCOME_TYPE,
    URL_SINGLE_URL_REQUEST_TYPE,
    UrlSingleUrlOutcome,
    UrlSingleUrlRequest,
    build_url_single_url_contract,
    build_url_single_url_outcome_codec,
    build_url_single_url_program,
    build_url_single_url_request_codec,
)
from app.successor_runtime.capabilities.catalog import build_operation_catalog
from app.successor_runtime.capabilities.checksum import (
    CanonicalJsonObject,
    CanonicalJsonValue,
    canonical_json,
    sha256_hex,
)
from app.successor_runtime.capabilities.retrieval_candidate_native import (
    RETRIEVAL_CANDIDATE_DISCOVER_V3_KIND,
    RETRIEVAL_CANDIDATE_ATTEMPT_OUTCOME_TYPE,
    RETRIEVAL_CANDIDATE_ATTEMPT_SEQUENCE_TYPE,
    RETRIEVAL_BUDGET_STATE_TYPE,
    RETRIEVAL_CANDIDATE_INVOCATION_TYPE,
    build_retrieval_candidate_atom,
    build_retrieval_candidate_prefix,
    build_retrieval_candidate_merge_registry,
    build_retrieval_candidate_runtime_definition,
)
from app.successor_runtime.capabilities.retrieval_common import (
    CandidateSearchRequest,
    RetrievalBudgetState,
    RetrievalCandidateAttemptOutcome,
    RetrievalCandidateInvocation,
    raise_retrieval_contract_error,
    retrieval_budget_id,
)
from app.successor_runtime.capabilities.retrieval_material_native import (
    CANDIDATE_WORK_SEQUENCE_TYPE,
    CANDIDATE_WORK_TYPE,
    RETRIEVAL_CONTROL_TYPE,
    RETRIEVAL_LEAF_KINDS,
    RETRIEVAL_CANDIDATE_REVIEW_KIND,
    RETRIEVAL_FOLLOWUP_PLAN_KIND,
    RETRIEVAL_MATERIAL_FORMALIZE_KIND,
    RETRIEVAL_MATERIAL_READ_BODY_KIND,
    RETRIEVAL_MATERIAL_REVALIDATE_KIND,
    RETRIEVAL_TOPOLOGY_COMMIT_KIND,
    CandidateWork,
    RetrievalControl,
    build_retrieval_leaf_definition,
    build_retrieval_leaf_contract,
    retrieval_payload_value,
    validate_candidate_work_transition,
)
from app.successor_runtime.language.algebra import (
    AlgebraRef,
    OperationSpec,
    ValueRef,
    freeze_json_object,
    freeze_json_value,
)
from app.successor_runtime.language.catalog import (
    OperationContractCatalogSnapshot,
    OperationContractRegistry,
)
from app.successor_runtime.language.object_contracts import OperationContract
from app.successor_runtime.language.compile import compile_program
from app.successor_runtime.language.program import (
    DecisionBranch,
    ProgramNode,
    ProgramSpec,
    atom_node,
    decide_node,
    identity_node,
    map_output_node,
    pure_node,
    program_atoms,
    then_node,
    traverse_ordered_node,
    zip_ordered_node,
)
from app.successor_runtime.language.transforms import (
    DiscriminatorRef,
    MergeRef,
    TransformRef,
    TransformRegistry,
)
from app.successor_runtime.research.object_types import ObjectType
from app.successor_runtime.runtime.activation import TraversalMaterialization
from app.successor_runtime.runtime.ports import RuntimeScope
from app.successor_runtime.substrate.postgres.runtime_activation import (
    ActiveChildMaterializer,
    ActiveChildSubmission,
    ActiveChildMaterializationReceipt,
    ActiveChildTerminalObservation,
    ActivationTrigger,
    OperationActivationCatalog,
    PostgresRuntimeActivationBindingAdapter,
    materialize_active_children,
)
from app.successor_runtime.substrate.postgres.models import (
    PUBLIC_TABLES,
    project_tables,
)
from app.successor_runtime.substrate.postgres.programs import ProgramRepository
from app.successor_runtime.substrate.postgres.research_ledger import one_mapping


def _digest(value: Any) -> str:
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def _now() -> str:
    return datetime.now(UTC).isoformat()


# The formal root now contains one ordered CandidateWork traversal.  The
# Program constructors and its sole active-child materializer are defined below.

RetrievalPlanLoader = Callable[[str, str], Mapping[str, Any]]
RetrievalJournalReader = Callable[[RetrievalControl], Mapping[str, Any]]
RetrievalEffectInputObservation = tuple[str, str, ValueRef, bytes]
RetrievalStaticInputObservation = tuple[ValueRef, bytes]


def _decode_exact_retrieval_value(
    *,
    ref: ValueRef,
    exact: bytes,
    expected_type: ObjectType,
    expected_codec_id: str,
    project_key: str,
    label: str,
) -> CanonicalJsonObject:
    if (
        ref.object_type != expected_type
        or ref.codec_id != expected_codec_id
        or ref.project_key != project_key
        or ref.byte_size != len(exact)
        or ref.content_digest != sha256_hex(exact)
    ):
        raise_retrieval_contract_error(ValueError, f'{label} ValueRef or bytes drift')
    try:
        decoded: object = json.loads(exact)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise_retrieval_contract_error(ValueError, f'{label} bytes are not canonical JSON', cause=exc)
    if not isinstance(decoded, dict):
        raise_retrieval_contract_error(ValueError, f'{label} bytes are not a canonical object')
    canonical = cast(CanonicalJsonObject, decoded)
    if canonical_json(canonical).encode("utf-8") != exact:
        raise_retrieval_contract_error(ValueError, f'{label} bytes are not a canonical object')
    return canonical


def _decode_root_retrieval_budget(
    control: RetrievalControl,
    observations: tuple[RetrievalStaticInputObservation, ...],
) -> RetrievalBudgetState:
    definition = build_retrieval_candidate_runtime_definition()
    matching = tuple(
        (ref, exact)
        for ref, exact in observations
        if ref.object_type == RETRIEVAL_BUDGET_STATE_TYPE
    )
    if len(matching) != 1:
        raise_retrieval_contract_error(ValueError, 'retrieval root requires one exact static budget input')
    ref, exact = matching[0]
    budget = definition.budget_codec.decode_payload(
        _decode_exact_retrieval_value(
            ref=ref,
            exact=exact,
            expected_type=RETRIEVAL_BUDGET_STATE_TYPE,
            expected_codec_id=definition.budget_codec.codec_id,
            project_key=control.project_key,
            label="retrieval budget",
        )
    )
    if (
        budget.budget_id != control.retrieval_budget_id
        or budget.project_key != control.project_key
        or budget.root_run_id != control.root_run_id
        or budget.plan_id != control.plan_id
        or budget.mode_version != control.mode_version
        or budget.queries_attempted != 0
        or budget.materials_accepted != 0
        or budget.followup_rounds_started != 0
    ):
        raise_retrieval_contract_error(ValueError, 'retrieval static budget differs from its root identity')
    return budget


def _decode_started_candidate_invocations(
    control: RetrievalControl,
    started_by_step: Mapping[str, Mapping[str, object]],
    observations: tuple[RetrievalEffectInputObservation, ...],
) -> dict[str, RetrievalCandidateInvocation]:
    definition = build_retrieval_candidate_runtime_definition()
    by_step: dict[str, list[RetrievalEffectInputObservation]] = {}
    for observation in observations:
        by_step.setdefault(observation[0], []).append(observation)
    decoded: dict[str, RetrievalCandidateInvocation] = {}
    query_ids: set[str] = set()
    query_ordinals: set[int] = set()
    for step_id, event in started_by_step.items():
        matching = by_step.get(step_id, [])
        if len(matching) != 1:
            raise_retrieval_contract_error(ValueError, 'begun candidate effect lacks one exact semantic input')
        observed_step_id, observed_attempt_id, ref, exact = matching[0]
        if (
            observed_step_id != step_id
            or observed_attempt_id != str(event.get("attempt_id") or "")
        ):
            raise_retrieval_contract_error(ValueError, 'candidate semantic input attempt identity drift')
        invocation = definition.invocation_codec.decode_payload(
            _decode_exact_retrieval_value(
                ref=ref,
                exact=exact,
                expected_type=RETRIEVAL_CANDIDATE_INVOCATION_TYPE,
                expected_codec_id=definition.invocation_codec.codec_id,
                project_key=control.project_key,
                label="candidate invocation",
            )
        )
        if (
            invocation.budget_id != control.retrieval_budget_id
            or invocation.route_id != control.route_id
            or invocation.request.project_ref != control.project_key
            or invocation.request.source_ref != control.route_id
            or invocation.query_id in query_ids
            or invocation.query_ordinal in query_ordinals
        ):
            raise_retrieval_contract_error(ValueError, 'candidate invocation differs from its retrieval root')
        query_ids.add(invocation.query_id)
        query_ordinals.add(invocation.query_ordinal)
        decoded[step_id] = invocation
    return decoded


def _validate_candidate_outcome_identity(
    invocation: RetrievalCandidateInvocation,
    outcome: RetrievalCandidateAttemptOutcome,
) -> None:
    if (
        outcome.query_id != invocation.query_id
        or outcome.route_id != invocation.route_id
        or outcome.query_kind != invocation.query_kind
        or outcome.query_ordinal != invocation.query_ordinal
        or outcome.followup_round != invocation.followup_round
        or outcome.budget_id != invocation.budget_id
        or (outcome.bundle is not None and outcome.bundle.request != invocation.request)
    ):
        raise_retrieval_contract_error(ValueError, 'candidate outcome identity differs from executed invocation')


def build_retrieval_runtime_journal_reader(
    *,
    engine: Engine,
    actor_id: str,
) -> Annotated[
    RetrievalJournalReader,
    "kit:non-authoritative derived_as=projection fact_source=runtime_journal+exact_started_semantic_inputs+exact_static_budget+typed_outputs+settlement_events witness=test:test_runtime_journal_reader_uses_executed_invocation_for_unknown_attempt",
]:
    """Project canonical Runtime events and typed outputs into retrieval facts.

    The projection has no writer or replay state. Search attempts require an
    ``EffectStarted`` event and its exact semantic input. Budget ceilings come
    from the unique original static budget value. CandidateWork values require
    an exact ``ActiveChildrenSettled`` payload digest from the root run.
    """

    if not actor_id.strip():
        raise_retrieval_contract_error(ValueError, 'retrieval journal reader requires a trusted actor identity')

    def read(control: RetrievalControl) -> Mapping[str, Any]:
        from app.composition.production import (
            read_installed_program,
            read_installed_program_input_bindings,
            read_installed_program_outputs,
        )

        run, steps, events = read_installed_program(
            engine=engine,
            project_key=control.project_key,
            actor_id=actor_id,
            run_id=control.root_run_id,
        )
        if (
            str(run.get("run_id") or "") != control.root_run_id
            or str(run.get("project_key") or "") != control.project_key
        ):
            raise_retrieval_contract_error(ValueError, 'retrieval journal run identity drift')
        outputs = read_installed_program_outputs(
            engine=engine,
            project_key=control.project_key,
            actor_id=actor_id,
            run_id=control.root_run_id,
        )
        static_inputs, effect_inputs = read_installed_program_input_bindings(
            engine=engine,
            project_key=control.project_key,
            actor_id=actor_id,
            run_id=control.root_run_id,
            static_input_type=RETRIEVAL_BUDGET_STATE_TYPE,
        )
        steps_by_id = {str(step.get("step_id") or ""): step for step in steps}
        outputs_by_step = {step_id: (ref, exact) for step_id, ref, exact in outputs}

        started = [
            event
            for event in events
            if event.get("event_type") == "EffectStarted"
            and str(event.get("step_id") or "") in steps_by_id
        ]
        started_by_step: dict[str, Mapping[str, object]] = {}
        for event in started:
            step_id = str(event.get("step_id") or "")
            if step_id in started_by_step:
                raise_retrieval_contract_error(ValueError, 'retrieval effect has more than one begun attempt')
            started_by_step[step_id] = event

        candidate_steps = [
            step
            for step in steps
            if step.get("operation_kind") == RETRIEVAL_CANDIDATE_DISCOVER_V3_KIND
            and str(step.get("step_id") or "") in started_by_step
        ]
        candidate_started_by_step = {
            step_id: started_by_step[step_id]
            for step_id in (str(step.get("step_id") or "") for step in candidate_steps)
        }
        root_budget = _decode_root_retrieval_budget(control, static_inputs)
        candidate_invocations = _decode_started_candidate_invocations(
            control,
            candidate_started_by_step,
            effect_inputs,
        )

        definition = build_retrieval_candidate_runtime_definition()
        candidate_outputs: dict[str, RetrievalCandidateAttemptOutcome] = {}
        final_control: RetrievalControl | None = None
        settled_work_digests = {
            str(event.get("payload_digest") or "")
            for event in events
            if event.get("event_type") == "ActiveChildrenSettled"
        }
        works: list[CandidateWork] = []
        work_ids: set[str] = set()
        work_codec = _candidate_work_codec()
        control_codec = _control_codec()
        for step_id, (ref, exact) in outputs_by_step.items():
            raw = json.loads(exact)
            if ref.object_type == RETRIEVAL_CANDIDATE_ATTEMPT_OUTCOME_TYPE:
                if not isinstance(raw, dict):
                    raise_retrieval_contract_error(TypeError, 'candidate Runtime output must be an object')
                candidate_outputs[step_id] = definition.output_codec.decode_payload(
                    cast(CanonicalJsonObject, raw)
                )
            elif ref.object_type == RETRIEVAL_CONTROL_TYPE:
                if not isinstance(raw, dict):
                    raise_retrieval_contract_error(TypeError, 'retrieval control Runtime output must be an object')
                observed_control = control_codec.decode_payload(cast(CanonicalJsonObject, raw))
                step = steps_by_id.get(step_id) or {}
                if step.get("operation_kind") == RETRIEVAL_TOPOLOGY_COMMIT_KIND:
                    if final_control is not None:
                        raise_retrieval_contract_error(ValueError, 'retrieval Runtime has multiple topology semantic outputs')
                    final_control = observed_control
            elif (
                ref.object_type == CANDIDATE_WORK_SEQUENCE_TYPE
                and ref.content_digest in settled_work_digests
            ):
                if not isinstance(raw, list):
                    raise_retrieval_contract_error(TypeError, 'settled CandidateWork output must be a sequence')
                for item in cast(list[object], raw):
                    if not isinstance(item, dict):
                        raise_retrieval_contract_error(TypeError, 'settled CandidateWork element must be an object')
                    work = work_codec.decode_payload(cast(CanonicalJsonObject, item))
                    if work.root_run_id != control.root_run_id or work.project_key != control.project_key:
                        raise_retrieval_contract_error(ValueError, 'settled CandidateWork crosses retrieval root')
                    if work.candidate_id in work_ids:
                        raise_retrieval_contract_error(ValueError, 'settled CandidateWork identity repeats')
                    work_ids.add(work.candidate_id)
                    works.append(work)

        if any(step_id not in candidate_invocations for step_id in candidate_outputs):
            raise_retrieval_contract_error(ValueError, 'candidate output lacks a begun semantic invocation')
        attempts: list[dict[str, Any]] = []
        for step in candidate_steps:
            step_id = str(step.get("step_id") or "")
            event = started_by_step[step_id]
            invocation = candidate_invocations[step_id]
            outcome = candidate_outputs.get(step_id)
            if outcome is not None:
                _validate_candidate_outcome_identity(invocation, outcome)
                found = tuple(outcome.bundle.candidates) if outcome.bundle is not None else ()
                result = "access_failed" if outcome.state != "completed" else ("hit" if found else "miss")
                note = outcome.error_message or outcome.error_code or ""
            else:
                result = "access_failed"
                note = str(step.get("failure_digest") or "candidate effect ended without a typed outcome")
            attempt_id = str(event.get("attempt_id") or "")
            query_id = invocation.query_id
            actual_query = invocation.request.topic
            if not attempt_id:
                raise_retrieval_contract_error(ValueError, 'begun candidate attempt lacks exact journal/query identity')
            related = [work for work in works if work.query_id == query_id]
            created = event.get("created_at")
            attempts.append(
                {
                    "attempt_id": attempt_id,
                    "query_id": query_id,
                    "round_id": control.root_run_id,
                    "clue_key": control.route_id,
                    "executed_at": created.isoformat() if isinstance(created, datetime) else str(created or ""),
                    "tool": "source.web.search",
                    "actual_query": actual_query,
                    "result": result,
                    "source_ids": [work.candidate_id for work in related],
                    "material_ids": [
                        work.candidate_id
                        for work in related
                        if work.stage in {"ingested", "body_read", "formalized", "revalidated"}
                    ],
                    "next_step": "candidate_review" if result == "hit" else "inspect_provider_diagnostics",
                    "result_note": note,
                    "raw_return_location": f"runtime:{control.root_run_id}:attempt:{attempt_id}",
                }
            )

        encoded_works = [work_codec.encode_payload(work) for work in works]
        accepted = sum(
            1
            for work in works
            if work.stage in {"ingested", "body_read", "formalized", "revalidated"}
        )
        consumed_budget = root_budget.after_settled_events(
            query_attempts=len(attempts),
            accepted_materials=accepted,
            followup_rounds=len({
                invocation.followup_round
                for invocation in candidate_invocations.values()
                if invocation.query_kind == "followup"
            }),
        )
        budget = {
            "queries_attempted": consumed_budget.queries_attempted,
            "materials_accepted": consumed_budget.materials_accepted,
            "followup_rounds_started": consumed_budget.followup_rounds_started,
            "max_queries": consumed_budget.max_queries,
            "max_materials": consumed_budget.max_materials,
            "max_followups": consumed_budget.max_followups,
            "remaining_queries": consumed_budget.remaining_queries,
            "remaining_materials": consumed_budget.remaining_materials,
            "remaining_followups": consumed_budget.remaining_followups,
        }
        candidates = [
            {
                "candidate_id": work.candidate_id,
                "query_id": work.query_id,
                "url": work.candidate.get("url"),
                "title": work.candidate.get("title"),
                "provider": work.candidate.get("provider"),
                "trust": work.candidate.get("trust"),
                "status": work.stage,
                "review_status": work.disposition if work.review is not None else None,
                "review_receipt": work.review,
            }
            for work in works
        ]
        materials = [
            {
                "candidate_id": work.candidate_id,
                "url": work.candidate.get("url"),
                "document_id": (work.ingest or {}).get("document_id"),
                "status": (
                    "body_read"
                    if work.body is not None and work.body.get("status") == "read"
                    else "submitted"
                    if work.disposition != "ingest_failed"
                    else "access_failed"
                ),
                "body_read": work.body,
                "ingest_receipt": work.ingest,
                "formalization": work.formalization,
                "formal_topology_ref": None,
            }
            for work in works
            if work.ingest is not None
        ]
        gaps = [dict(gap) for work in works for gap in work.gaps]
        failures = [
            {"phase": work.stage, "candidate_id": work.candidate_id, "error": work.error}
            for work in works
            if work.error is not None
        ]
        return {
            "run": dict(run),
            "attempts": attempts,
            "works": encoded_works,
            "candidates": candidates,
            "materials": materials,
            "gaps": gaps,
            "failures": failures,
            "budget": budget,
            "final_control": (
                control_codec.encode_payload(final_control) if final_control is not None else None
            ),
        }

    return read


def review_candidate_work(
    work: CandidateWork,
    *,
    approved_prefix_count: int,
) -> CandidateWork:
    """Apply the original review decision kernel without creating a session."""

    if work.stage != "candidate":
        raise_retrieval_contract_error(ValueError, 'candidate review requires candidate-stage work')
    if type(approved_prefix_count) is not int or approved_prefix_count < 0:
        raise_retrieval_contract_error(
            ValueError,
            "candidate review requires an exact nonnegative approved prefix count",
        )
    assessment_plan = build_source_candidate_plan(
        project_key=work.project_key,
        query=str(work.candidate.get("query") or ""),
        urls=[str(work.candidate.get("url") or "")],
        max_candidates=1,
    )
    accepted_rows: object = assessment_plan.get("candidate_urls")
    rejected_rows: object = assessment_plan.get("rejected_urls")
    assessment_row: object = None
    if isinstance(accepted_rows, list) and accepted_rows:
        assessment_row = cast(list[object], accepted_rows)[0]
    elif isinstance(rejected_rows, list) and rejected_rows:
        assessment_row = cast(list[object], rejected_rows)[0]
    assessment = (
        cast(dict[str, Any], assessment_row)
        if isinstance(assessment_row, dict)
        else {
            "status": "rejected",
            "blocked_reason": "candidate trust assessment unavailable",
        }
    )
    trust_status = str(assessment.get("status") or "rejected").strip().lower()
    budget_exhausted = (
        trust_status in {"accepted", "approved"}
        and approved_prefix_count >= work.material_budget_remaining
    )
    decision = (
        "deferred"
        if budget_exhausted
        else "approved"
        if trust_status in {"accepted", "approved"}
        else "deferred"
        if trust_status in {"deferred", "pending", "pending_review"}
        else "rejected"
    )
    if budget_exhausted:
        assessment = {
            **assessment,
            "status": "deferred",
            "blocked_reason": "retrieval material budget exhausted",
        }
        trust_status = "deferred"
    candidate: CanonicalJsonObject = {
        **work.candidate,
        "trust": {
            "status": trust_status,
            "trust_score": assessment.get("trust_score"),
            "trust_level": assessment.get("trust_level"),
            "domain": assessment.get("domain"),
            "blocked_reason": assessment.get("blocked_reason"),
            "url_checksum": assessment.get("url_checksum"),
            "source_policy_action": assessment.get("source_policy_action"),
            "source_policy_reason": assessment.get("source_policy_reason"),
            "pre_ingest_required_checks": assessment.get("pre_ingest_required_checks") or [],
        },
    }
    review = build_source_candidate_review_decision(
        project_key=work.project_key,
        candidate=candidate,
        decision=decision,
        preferred_ingest="url_pool",
        reason=(
            "Bounded project retrieval: collect trust-accepted URL for body review"
            if decision == "approved"
            else "Candidate trust gate did not authorize collection"
        ),
        idempotency_key=work.candidate_id,
        reviewed_at=_now(),
        source_call_id=f"runtime:{work.root_run_id}:{work.candidate_id}:review",
    )
    receipt: dict[str, CanonicalJsonValue] = {
        **cast(dict[str, CanonicalJsonValue], review),
        "contract_version": "project_retrieval.candidate.review.v1",
        "receipt_owner": RETRIEVAL_CANDIDATE_REVIEW_KIND,
        "receipt_reference": {
            "kind": "runtime_step_output",
            "root_run_id": work.root_run_id,
            "candidate_id": work.candidate_id,
        },
        "review_artifact_ref": None,
        "approved_prefix_count": approved_prefix_count,
        "material_budget_remaining": work.material_budget_remaining,
    }
    disposition: Literal["approved", "deferred", "rejected"] = decision
    gaps = work.gaps
    if disposition != "approved":
        gaps += (
            {
                "code": "CANDIDATE_REVIEW_NOT_APPROVED",
                "candidate_id": work.candidate_id,
                "decision": disposition,
                "trust_status": trust_status,
            },
        )
    after = replace(
        work,
        candidate=candidate,
        stage="reviewed",
        disposition=disposition,
        review=receipt,
        gaps=gaps,
    )
    validate_candidate_work_transition(work, after)
    return after


def merge_candidate_work_ingest(work: CandidateWork, outcome: UrlSingleUrlOutcome) -> CandidateWork:
    """Attach the original URL owner's typed receipt to the reviewed work."""

    if work.stage != "reviewed" or work.disposition != "approved":
        raise_retrieval_contract_error(ValueError, 'URL acquisition requires approved reviewed work')
    successful = outcome.status in {"completed", "accepted", "partial"} and bool(outcome.document_id)
    receipt: dict[str, CanonicalJsonValue] = {
        "status": outcome.status,
        "inserted": outcome.inserted,
        "updated": outcome.updated,
        "skipped": outcome.skipped,
        "document_id": outcome.document_id,
        "error": outcome.error,
        "task_id": outcome.task_id,
        "readback": outcome.readback,
        "receipt_owner": "acquisition.url.single_url.v1",
    }
    gaps = work.gaps
    error = work.error
    disposition: Literal["approved", "ingest_failed"] = "approved" if successful else "ingest_failed"
    if not successful:
        error = {"code": "INGEST_FAILED", "status": outcome.status, "message": outcome.error}
        gaps += ({"code": "INGEST_FAILED", "candidate_id": work.candidate_id, "status": outcome.status},)
    after = replace(
        work,
        stage="ingested",
        disposition=disposition,
        ingest=receipt,
        error=error,
        gaps=gaps,
    )
    validate_candidate_work_transition(work, after)
    return after


def read_candidate_work_body(
    topology_service: InformationTopologyService,
    work: CandidateWork,
) -> CandidateWork:
    """Read the exact persisted Document body through its original owner."""

    if work.stage != "ingested" or work.disposition != "approved" or work.ingest is None:
        raise_retrieval_contract_error(ValueError, 'body read requires a successful ingest receipt')
    document_id = work.ingest.get("document_id")
    receipt, body = _read_document_body(topology_service, work.project_key, document_id)
    status = str(receipt.get("status") or "failed")
    disposition: Literal["approved", "body_missing", "body_failed"]
    disposition = "approved" if status == "read" and body is not None else (
        "body_missing" if status == "missing" else "body_failed"
    )
    gaps = work.gaps
    error = work.error
    if disposition != "approved":
        raw_error = receipt.get("error")
        error = (
            {
                str(key): cast(CanonicalJsonValue, value)
                for key, value in cast(Mapping[object, object], raw_error).items()
            }
            if isinstance(raw_error, Mapping)
            else {"code": "DOCUMENT_BODY_READ_FAILED"}
        )
        gaps += (
            {"code": str(error.get("code") or "DOCUMENT_BODY_READ_FAILED"), "candidate_id": work.candidate_id},
        )
    body_receipt = cast(dict[str, CanonicalJsonValue], receipt)
    after = replace(
        work,
        stage="body_read",
        disposition=disposition,
        body=body_receipt,
        body_text=body,
        error=error,
        gaps=gaps,
    )
    validate_candidate_work_transition(work, after)
    return after


def _formalization_payload(work: CandidateWork, plan: Mapping[str, Any]) -> dict[str, Any]:
    if work.body is None or work.body_text is None:
        raise_retrieval_contract_error(ValueError, 'formalization requires a body observation')
    queries = {
        str(item.get("id") or item.get("query_id") or ""): item
        for item in _mapping_list(plan.get("queries"))
    }
    query = queries.get(work.query_id)
    if query is None:
        planned = _mapping(plan.get("planned_query"))
        if planned is not None and str(planned.get("query_id") or "") == work.query_id:
            query = planned
    if query is None and work.query_kind == "followup":
        expression = str(work.candidate.get("query") or "").strip()
        if expression:
            query = {
                "query_id": work.query_id,
                "expression": expression,
                "query_ordinal": work.query_ordinal,
                "followup_round": work.followup_round,
                "source_route_id": work.route_id,
            }
    binding = _mapping(plan.get("binding_snapshot")) or {}
    routes = _mapping_list(binding.get("routes"))
    if not routes:
        routes = _mapping_list((_mapping(plan.get("topology_seed")) or {}).get("source_routes"))
    route = next((item for item in routes if str(item.get("route_id") or "") == work.route_id), None)
    if route is None or query is None:
        raise_retrieval_contract_error(ValueError, 'formalization plan lacks the bound route or query')
    return {
        "project_key": work.project_key,
        "run_id": work.root_run_id,
        "plan_id": work.plan_id,
        "route_id": work.route_id,
        "query_id": work.query_id,
        "candidate_id": work.candidate_id,
        "document_id": work.body.get("document_id"),
        "title": work.body.get("title"),
        "url": work.body.get("uri") or work.candidate.get("url"),
        "body": work.body_text,
        "body_digest": work.body.get("body_digest"),
        "document_updated_at": work.body.get("document_updated_at"),
        "domain_vocabulary": plan.get("domain_vocabulary")
        or (_mapping(plan.get("topology_seed")) or {}).get("domain_vocabulary"),
        "query": dict(query),
        "source_route": dict(route),
    }


def formalize_candidate_work(
    plan_loader: RetrievalPlanLoader,
    work: CandidateWork,
) -> CandidateWork:
    """Run the original bounded provider formalizer on the exact body."""

    if work.stage != "body_read" or work.disposition != "approved":
        raise_retrieval_contract_error(ValueError, 'formalization requires a successful body read')
    from app.services.project_retrieval.formalization import formalize_material

    try:
        plan = plan_loader(work.project_key, work.plan_id)
        result = formalize_material(_formalization_payload(work, plan))
    except Exception as exc:
        result = {"status": "failed", "error": _failure(exc)}
    status = str(result.get("status") or "failed")
    disposition: Literal["proposed", "no_claim", "formalization_failed"] = (
        "proposed" if status == "proposed" else "no_claim" if status == "no_claim" else "formalization_failed"
    )
    gaps = work.gaps
    for detail in _list(result.get("gaps")):
        gaps += ({"code": "FORMALIZATION_REMAINING_GAP", "candidate_id": work.candidate_id, "detail": detail},)
    error = work.error
    if disposition == "formalization_failed":
        raw_error = result.get("error")
        error = (
            {
                str(key): cast(CanonicalJsonValue, value)
                for key, value in cast(Mapping[object, object], raw_error).items()
            }
            if isinstance(raw_error, Mapping)
            else {"code": "FORMALIZATION_FAILED"}
        )
        gaps += ({"code": str(error.get("code") or "FORMALIZATION_FAILED"), "candidate_id": work.candidate_id},)
    receipt = {str(key): cast(CanonicalJsonValue, value) for key, value in result.items()}
    after = replace(
        work,
        stage="formalized",
        disposition=disposition,
        formalization=receipt,
        error=error,
        gaps=gaps,
    )
    validate_candidate_work_transition(work, after)
    return after


def revalidate_candidate_work(
    topology_service: InformationTopologyService,
    work: CandidateWork,
) -> CandidateWork:
    """Re-read the exact source before making a proposal topology-eligible."""

    if work.stage != "formalized":
        raise_retrieval_contract_error(ValueError, 'source revalidation requires formalized work')
    if work.disposition != "proposed":
        after = replace(work, stage="revalidated")
        validate_candidate_work_transition(work, after)
        return after
    if work.body is None or work.body_text is None:
        raise_retrieval_contract_error(ValueError, 'source revalidation requires the original body receipt')
    receipt, body = _read_document_body(
        topology_service,
        work.project_key,
        work.body.get("document_id"),
    )
    consistent = (
        receipt.get("status") == "read"
        and body == work.body_text
        and receipt.get("body_digest") == work.body.get("body_digest")
        and receipt.get("document_updated_at") == work.body.get("document_updated_at")
    )
    gaps = work.gaps
    error = work.error
    disposition: Literal["ready", "source_changed"] = "ready" if consistent else "source_changed"
    if not consistent:
        error = {"code": "SOURCE_CHANGED", "revalidation": cast(CanonicalJsonValue, receipt)}
        gaps += ({"code": "SOURCE_CHANGED", "candidate_id": work.candidate_id},)
    after = replace(work, stage="revalidated", disposition=disposition, error=error, gaps=gaps)
    validate_candidate_work_transition(work, after)
    return after


def _candidate_work_codec():
    return build_retrieval_leaf_definition(RETRIEVAL_CANDIDATE_REVIEW_KIND).input_codec


def _control_codec():
    return build_retrieval_leaf_definition(RETRIEVAL_FOLLOWUP_PLAN_KIND).input_codec


def _retrieval_operation_environment(
    candidate_contract: OperationContract | None = None,
) -> tuple[OperationContractCatalogSnapshot, OperationContractRegistry]:
    contracts = (
        candidate_contract or build_retrieval_candidate_runtime_definition().operation_contract,
        build_url_single_url_contract(),
        *(build_retrieval_leaf_definition(kind).contract for kind in RETRIEVAL_LEAF_KINDS),
    )
    catalog = build_operation_catalog(
        contracts,
        catalog_id="mrw.project-retrieval.runtime.operations",
        catalog_version="1",
    )
    return catalog, OperationContractRegistry(catalog=catalog, contracts=contracts)


def _decode_work(value: object) -> CandidateWork:
    if not isinstance(value, dict):
        raise_retrieval_contract_error(TypeError, 'CandidateWork transform input must be an object')
    return _candidate_work_codec().decode_payload(cast(CanonicalJsonObject, value))


def _encode_work(value: CandidateWork) -> CanonicalJsonObject:
    return _candidate_work_codec().encode_payload(value)


def _decode_control(value: object) -> RetrievalControl:
    if not isinstance(value, dict):
        raise_retrieval_contract_error(TypeError, 'RetrievalControl transform input must be an object')
    return _control_codec().decode_payload(cast(CanonicalJsonObject, value))


def _encode_control(value: RetrievalControl) -> CanonicalJsonObject:
    return _control_codec().encode_payload(value)


def _candidate_work_to_url_request(value: object) -> CanonicalJsonObject:
    work = _decode_work(value)
    if work.review is None:
        raise_retrieval_contract_error(ValueError, 'approved CandidateWork lacks its review receipt')
    ingest = _mapping(work.review.get("ingest_payload"))
    url = str((ingest or {}).get("url") or work.candidate.get("url") or "").strip()
    request = UrlSingleUrlRequest(
        url=url,
        project_key=work.project_key,
        query_terms=tuple(
            dict.fromkeys(
                item
                for item in (
                    str(work.candidate.get("query") or "").strip(),
                    str(work.candidate.get("keyword") or "").strip(),
                )
                if item
            )
        ),
        extra_params={"disable_site_seed_expansion": True},
        enable_extraction=True,
        target={"candidate_id": work.candidate_id, "query_id": work.query_id},
        context={"root_run_id": work.root_run_id, "retrieval_budget_id": work.retrieval_budget_id},
    )
    contract = build_url_single_url_contract()
    return build_url_single_url_request_codec(contract.ref).encode_payload(request)


def _merge_work_url_outcome(left: object, right: object) -> CanonicalJsonObject:
    work = _decode_work(left)
    if not isinstance(right, dict):
        raise_retrieval_contract_error(TypeError, 'URL outcome must be an object')
    contract = build_url_single_url_contract()
    outcome = build_url_single_url_outcome_codec(contract.ref).decode_payload(cast(CanonicalJsonObject, right))
    return _encode_work(merge_candidate_work_ingest(work, outcome))


def _review_branch(value: object) -> str:
    return "approved" if str(cast(Mapping[str, object], value).get("disposition") or "") == "approved" else "stopped"


def _ingest_branch(value: object) -> str:
    raw = cast(Mapping[str, object], value)
    return "body" if raw.get("stage") == "ingested" and raw.get("disposition") == "approved" else "stopped"


def _body_branch(value: object) -> str:
    raw = cast(Mapping[str, object], value)
    return "formalize" if raw.get("stage") == "body_read" and raw.get("disposition") == "approved" else "stopped"


def _control_branch(value: object) -> str:
    return "planned" if str(cast(Mapping[str, object], value).get("state") or "") == "planned" else "skipped"


def _control_to_candidate_invocation(value: object) -> CanonicalJsonObject:
    control = _decode_control(value)
    planned = control.planned_query or {}
    query_id = str(planned.get("query_id") or "").strip()
    expression = str(planned.get("expression") or planned.get("query") or "").strip()
    max_results_raw = planned.get("max_results")
    if type(max_results_raw) is not int or max_results_raw <= 0:
        raise_retrieval_contract_error(ValueError, 'planned follow-up requires a positive max_results budget')
    invocation = RetrievalCandidateInvocation(
        query_id=query_id,
        route_id=control.route_id,
        query_kind="followup",
        query_ordinal=_exact_int(planned.get("query_ordinal"), default=0),
        followup_round=control.round,
        budget_id=control.retrieval_budget_id,
        request=CandidateSearchRequest(
            topic=expression,
            language=str(planned.get("language") or "bi"),
            max_results=max_results_raw,
            project_ref=control.project_key,
            source_ref=control.route_id,
        ),
    )
    return build_retrieval_candidate_runtime_definition().invocation_codec.encode_payload(invocation)


def _decode_candidate_outcomes(value: object) -> tuple[RetrievalCandidateAttemptOutcome, ...]:
    definition = build_retrieval_candidate_runtime_definition()
    items: list[object] = cast(list[object], value) if isinstance(value, list) else [value]
    outcomes: list[RetrievalCandidateAttemptOutcome] = []
    for item in items:
        if not isinstance(item, dict):
            raise_retrieval_contract_error(TypeError, 'candidate outcome must be an object')
        outcomes.append(definition.output_codec.decode_payload(cast(CanonicalJsonObject, item)))
    return tuple(outcomes)


def _merge_candidate_outcomes_control(left: object, right: object) -> list[CanonicalJsonObject]:
    outcomes = _decode_candidate_outcomes(left)
    control = _decode_control(right)
    remaining_raw = control.budget.get("remaining_materials")
    if type(remaining_raw) is not int or remaining_raw < 0:
        raise_retrieval_contract_error(ValueError, 'retrieval control lacks an exact remaining material budget')
    remaining = remaining_raw
    works: list[CanonicalJsonObject] = []
    seen: set[str] = set()
    for outcome in outcomes:
        bundle = outcome.bundle if outcome.state == "completed" else None
        if bundle is None:
            continue
        for candidate in bundle.candidates:
            url = candidate.resource_uri.strip()
            if not url or url in seen:
                continue
            seen.add(url)
            ordinal = len(works) + 1
            work = CandidateWork(
                project_key=control.project_key,
                root_run_id=control.root_run_id,
                retrieval_budget_id=control.retrieval_budget_id,
                plan_id=control.plan_id,
                mode_version=control.mode_version,
                route_id=control.route_id,
                query_id=outcome.query_id,
                query_kind=outcome.query_kind,
                query_ordinal=outcome.query_ordinal,
                followup_round=outcome.followup_round,
                candidate_ordinal=ordinal,
                candidate_id="candidate:" + _digest(
                    (control.retrieval_budget_id, outcome.query_id, candidate.result_rank, url)
                ),
                material_budget_remaining=remaining,
                candidate={
                    "url": url,
                    "title": candidate.title or url,
                    "snippet": candidate.snippet or "",
                    "provider": candidate.source or "",
                    "rank": candidate.result_rank,
                    "keyword": candidate.keyword or "",
                    "query": bundle.request.topic,
                    "trust": {"status": "pending_review"},
                },
            )
            works.append(_encode_work(work))
    return works


def _merge_control_outcome(left: object, right: object) -> list[CanonicalJsonObject]:
    return _merge_candidate_outcomes_control(right, left)


def _merge_work_sequence_control(_left: object, right: object) -> CanonicalJsonObject:
    return cast(CanonicalJsonObject, right)


def _candidate_outcome_to_sequence(value: object) -> list[CanonicalJsonObject]:
    if not isinstance(value, dict):
        raise_retrieval_contract_error(TypeError, 'candidate outcome must be an object')
    return [cast(CanonicalJsonObject, value)]


def _candidate_work_identity(value: object) -> object:
    return value


def _retrieval_control_identity(value: object) -> object:
    return value


def _register_retrieval_transforms(registry: TransformRegistry) -> dict[str, TransformRef]:
    return {
        "work_to_url": registry.register_transform(
            name="project_retrieval.work.to_url_request",
            version="1",
            input_type=CANDIDATE_WORK_TYPE,
            output_type=URL_SINGLE_URL_REQUEST_TYPE,
            func=_candidate_work_to_url_request,
        ),
        "control_to_invocation": registry.register_transform(
            name="project_retrieval.control.to_candidate_invocation",
            version="1",
            input_type=build_retrieval_leaf_contract(RETRIEVAL_FOLLOWUP_PLAN_KIND).input_type,
            output_type=build_retrieval_candidate_runtime_definition().program_atom.input_type,
            func=_control_to_candidate_invocation,
        ),
        "candidate_to_sequence": registry.register_transform(
            name="project_retrieval.candidate.to_sequence",
            version="1",
            input_type=RETRIEVAL_CANDIDATE_ATTEMPT_OUTCOME_TYPE,
            output_type=RETRIEVAL_CANDIDATE_ATTEMPT_SEQUENCE_TYPE,
            func=_candidate_outcome_to_sequence,
        ),
        "work_identity": registry.register_transform(
            name="project_retrieval.work.identity",
            version="1",
            input_type=CANDIDATE_WORK_TYPE,
            output_type=CANDIDATE_WORK_TYPE,
            func=_candidate_work_identity,
            preserves_value_ref=True,
        ),
        "control_identity": registry.register_transform(
            name="project_retrieval.control.identity",
            version="1",
            input_type=build_retrieval_leaf_contract(RETRIEVAL_FOLLOWUP_PLAN_KIND).input_type,
            output_type=build_retrieval_leaf_contract(RETRIEVAL_FOLLOWUP_PLAN_KIND).input_type,
            func=_retrieval_control_identity,
            preserves_value_ref=True,
        ),
    }


def build_retrieval_transform_registry() -> Annotated[
    TransformRegistry,
    "kit:non-authoritative derived_as=program fact_source=retrieval_typed_transforms witness=test:test_root_and_candidate_work_have_one_semantic_return",
]:
    registry = TransformRegistry(registry_id="mrw.project-retrieval.transforms.v1", registry_version="1")
    _register_retrieval_transforms(registry)
    return registry


def _register_retrieval_merges(registry: TransformRegistry) -> dict[str, MergeRef]:
    candidate_output = RETRIEVAL_CANDIDATE_ATTEMPT_SEQUENCE_TYPE
    control_type = build_retrieval_leaf_contract(RETRIEVAL_FOLLOWUP_PLAN_KIND).input_type
    return {
        "work_url": registry.register_merge(
            name="project_retrieval.work.attach_url_outcome",
            version="1",
            left_type=CANDIDATE_WORK_TYPE,
            right_type=URL_SINGLE_URL_OUTCOME_TYPE,
            output_type=CANDIDATE_WORK_TYPE,
            func=_merge_work_url_outcome,
        ),
        "candidates_work": registry.register_merge(
            name="project_retrieval.candidates.to_work",
            version="1",
            left_type=candidate_output,
            right_type=control_type,
            output_type=CANDIDATE_WORK_SEQUENCE_TYPE,
            func=_merge_candidate_outcomes_control,
        ),
        "followup_work": registry.register_merge(
            name="project_retrieval.followup.to_work",
            version="1",
            left_type=control_type,
            right_type=RETRIEVAL_CANDIDATE_ATTEMPT_OUTCOME_TYPE,
            output_type=CANDIDATE_WORK_SEQUENCE_TYPE,
            func=_merge_control_outcome,
        ),
        "work_control": registry.register_merge(
            name="project_retrieval.work.to_control",
            version="1",
            left_type=CANDIDATE_WORK_SEQUENCE_TYPE,
            right_type=control_type,
            output_type=control_type,
            func=_merge_work_sequence_control,
        ),
    }


def _register_candidate_merges(registry: TransformRegistry) -> None:
    candidate_registry = build_retrieval_candidate_merge_registry()
    for merge_ref in candidate_registry.merge_refs():
        entry = candidate_registry.resolve_merge(merge_ref)
        registry.register_merge(
            name=entry.id,
            version=entry.version,
            left_type=entry.left_type,
            right_type=entry.right_type,
            output_type=entry.output_type,
            func=entry.callable,
        )


def build_retrieval_merge_registry() -> Annotated[
    TransformRegistry,
    "kit:non-authoritative derived_as=program fact_source=retrieval_typed_merges+candidate_attempt_merges witness=test:test_root_and_candidate_work_have_one_semantic_return",
]:
    registry = TransformRegistry(registry_id="mrw.project-retrieval.merges.v1", registry_version="1")
    _register_retrieval_merges(registry)
    _register_candidate_merges(registry)
    return registry


def _retrieval_merge_refs(registry: TransformRegistry) -> dict[str, MergeRef]:
    by_name = {ref.name: ref for ref in registry.merge_refs()}
    names = {
        "work_url": "project_retrieval.work.attach_url_outcome",
        "candidates_work": "project_retrieval.candidates.to_work",
        "followup_work": "project_retrieval.followup.to_work",
        "work_control": "project_retrieval.work.to_control",
    }
    try:
        return {key: by_name[name] for key, name in names.items()}
    except KeyError as exc:
        raise_retrieval_contract_error(ValueError, f'retrieval merge registry lacks {exc.args[0]}', cause=exc)


def _register_retrieval_discriminators(
    registry: TransformRegistry,
) -> dict[str, DiscriminatorRef]:
    refs: dict[str, DiscriminatorRef] = {}
    for name, branches, func in (
        ("project_retrieval.review.branch", ("approved", "stopped"), _review_branch),
        ("project_retrieval.ingest.branch", ("body", "stopped"), _ingest_branch),
        ("project_retrieval.body.branch", ("formalize", "stopped"), _body_branch),
    ):
        refs[name] = registry.register_discriminator(
            name=name, version="1", input_type=CANDIDATE_WORK_TYPE, branch_ids=branches, func=func
        )
    refs["project_retrieval.control.branch"] = registry.register_discriminator(
        name="project_retrieval.control.branch",
        version="1",
        input_type=build_retrieval_leaf_contract(RETRIEVAL_FOLLOWUP_PLAN_KIND).input_type,
        branch_ids=("planned", "skipped"),
        func=_control_branch,
    )
    return refs


def build_retrieval_discriminator_registry() -> Annotated[
    TransformRegistry,
    "kit:non-authoritative derived_as=program fact_source=retrieval_typed_branch_rules witness=test:test_root_and_candidate_work_have_one_semantic_return",
]:
    registry = TransformRegistry(registry_id="mrw.project-retrieval.discriminators.v1", registry_version="1")
    _register_retrieval_discriminators(registry)
    return registry


@dataclass(frozen=True, slots=True)
class RetrievalWorkChildProgram:
    element_index: int
    element_digest: str
    program: ProgramSpec
    values: tuple[tuple[ValueRef, bytes], ...]
    invocation_ref: ValueRef
    budget_ref: ValueRef
    canonical_bindings: Mapping[str, tuple[int, str]]
    approvals_by_step: Mapping[str, tuple[str, ...]]
    logical_request_id: str
    idempotency_id: str
    child_run_id: str
    incarnation: str


def _work_leaf_atom(kind: str, work_ref: ValueRef, budget_ref: ValueRef) -> ProgramNode:
    contract = build_retrieval_leaf_contract(kind)
    operation = OperationSpec(
        operation_id=kind,
        contract_ref=contract.ref,
        input_refs=(budget_ref, work_ref),
        payload_ref=work_ref,
        allowed_overrides=freeze_json_object({}),
    )
    return atom_node(operation, input_type=CANDIDATE_WORK_TYPE, output_type=CANDIDATE_WORK_TYPE)


def _url_request_template(work: CandidateWork) -> UrlSingleUrlRequest:
    return UrlSingleUrlRequest(
        url=str(work.candidate.get("url") or ""),
        project_key=work.project_key,
        query_terms=tuple(
            item
            for item in (
                str(work.candidate.get("query") or "").strip(),
                str(work.candidate.get("keyword") or "").strip(),
            )
            if item
        ),
        extra_params={"disable_site_seed_expansion": True},
        enable_extraction=True,
        target={"candidate_id": work.candidate_id, "query_id": work.query_id},
        context={"root_run_id": work.root_run_id, "retrieval_budget_id": work.retrieval_budget_id},
    )


def build_retrieval_work_child_program(
    *,
    work: CandidateWork,
    budget_ref: ValueRef,
    budget_bytes: bytes,
    element_index: int,
    element_digest: str,
    program_id: str,
    child_run_id: str,
    project_registry_revision: int,
    project_scope_digest: str,
) -> Annotated[
    RetrievalWorkChildProgram,
    "kit:prepared-command effect_boundary=successor_program_interpreter witness=test:test_root_and_candidate_work_have_one_semantic_return",
]:
    review_contract = build_retrieval_leaf_contract(RETRIEVAL_CANDIDATE_REVIEW_KIND)
    work_ref, work_bytes = retrieval_payload_value(
        value=work,
        contract_ref=review_contract.ref,
        value_id=f"{program_id}:payload:candidate-work",
        project_key=work.project_key,
    )
    incarnation = f"retrieval-work:{element_digest}"
    url_leaf = build_url_single_url_program(
        request=_url_request_template(work),
        program_id="program:retrieval-url:" + _digest((program_id, work.candidate_id)),
        project_key=work.project_key,
        project_registry_revision=project_registry_revision,
        project_scope_digest=project_scope_digest,
        incarnation=incarnation,
        extra_bound_inputs=((budget_ref, budget_bytes),),
    )
    transform_registry = TransformRegistry(
        registry_id="mrw.project-retrieval.transforms.v1", registry_version="1"
    )
    transform_refs = _register_retrieval_transforms(transform_registry)
    merge_registry = build_retrieval_merge_registry()
    merge_refs = _retrieval_merge_refs(merge_registry)
    discriminator_registry = TransformRegistry(
        registry_id="mrw.project-retrieval.discriminators.v1", registry_version="1"
    )
    discriminator_refs = _register_retrieval_discriminators(discriminator_registry)

    review = _work_leaf_atom(RETRIEVAL_CANDIDATE_REVIEW_KIND, work_ref, budget_ref)
    url_pipeline = then_node(
        map_output_node(identity_node(CANDIDATE_WORK_TYPE), transform_refs["work_to_url"], URL_SINGLE_URL_REQUEST_TYPE),
        url_leaf.program.root,
    )
    approved = zip_ordered_node(
        identity_node(CANDIDATE_WORK_TYPE),
        url_pipeline,
        merge_refs["work_url"],
        CANDIDATE_WORK_TYPE,
    )
    reviewed = then_node(
        review,
        decide_node(
            discriminator_refs["project_retrieval.review.branch"],
            (
                DecisionBranch("approved", "disposition == 'approved'", approved),
                DecisionBranch(
                    "stopped",
                    "disposition != 'approved'",
                    map_output_node(
                        identity_node(CANDIDATE_WORK_TYPE),
                        transform_refs["work_identity"],
                        CANDIDATE_WORK_TYPE,
                    ),
                ),
            ),
        ),
    )
    body = _work_leaf_atom(RETRIEVAL_MATERIAL_READ_BODY_KIND, work_ref, budget_ref)
    ingested = then_node(
        reviewed,
        decide_node(
            discriminator_refs["project_retrieval.ingest.branch"],
            (
                DecisionBranch("body", "stage == 'ingested' and disposition == 'approved'", body),
                DecisionBranch(
                    "stopped",
                    "stage != 'ingested' or disposition != 'approved'",
                    map_output_node(
                        identity_node(CANDIDATE_WORK_TYPE),
                        transform_refs["work_identity"],
                        CANDIDATE_WORK_TYPE,
                    ),
                ),
            ),
        ),
    )
    formal = then_node(
        _work_leaf_atom(RETRIEVAL_MATERIAL_FORMALIZE_KIND, work_ref, budget_ref),
        _work_leaf_atom(RETRIEVAL_MATERIAL_REVALIDATE_KIND, work_ref, budget_ref),
    )
    root = then_node(
        ingested,
        decide_node(
            discriminator_refs["project_retrieval.body.branch"],
            (
                DecisionBranch("formalize", "stage == 'body_read' and disposition == 'approved'", formal),
                DecisionBranch(
                    "stopped",
                    "stage != 'body_read' or disposition != 'approved'",
                    map_output_node(
                        identity_node(CANDIDATE_WORK_TYPE),
                        transform_refs["work_identity"],
                        CANDIDATE_WORK_TYPE,
                    ),
                ),
            ),
        ),
    )
    root = map_output_node(root, transform_refs["work_identity"], CANDIDATE_WORK_TYPE)
    catalog, registry = _retrieval_operation_environment()
    program = ProgramSpec(
        program_id=program_id,
        contract_version="mrw.functorial-successor.program-spec.v1",
        project_key=work.project_key,
        project_registry_revision=project_registry_revision,
        project_scope_digest=project_scope_digest,
        semantic_identity="project_retrieval.candidate-work.v1",
        input_type=CANDIDATE_WORK_TYPE,
        output_type=CANDIDATE_WORK_TYPE,
        root=root,
        algebra_refs=(AlgebraRef("mrw.successor.language.algebra", "1"),),
        transform_refs=tuple(transform_refs.values()),
        observation_profile="project_retrieval.candidate-work.observation.v1",
        metadata=freeze_json_object(
            {
                "schema": "mrw.project-retrieval.candidate-work.program.v1",
                "root_run_id": work.root_run_id,
                "root_budget_id": work.retrieval_budget_id,
                "candidate_id": work.candidate_id,
                "element_index": element_index,
                "element_digest": element_digest,
            }
        ),
        program_digest="",
    ).with_digest()
    plan = compile_program(
        program,
        catalog,
        operation_contracts=registry,
        transform_registry=transform_registry,
        merge_registry=merge_registry,
        discriminator_registry=discriminator_registry,
    )
    effects = tuple(step for step in plan.ordered_steps if step.step_kind == "EFFECT")
    values_by_ref = {budget_ref: budget_bytes, work_ref: work_bytes}
    for ref, exact in url_leaf.values:
        previous = values_by_ref.setdefault(ref, exact)
        if previous != exact:
            raise_retrieval_contract_error(ValueError, 'retrieval work value identity collision')
    return RetrievalWorkChildProgram(
        element_index=element_index,
        element_digest=element_digest,
        program=program,
        values=tuple(values_by_ref.items()),
        invocation_ref=work_ref,
        budget_ref=budget_ref,
        canonical_bindings={step.step_id: (0, incarnation) for step in effects},
        approvals_by_step={},
        logical_request_id=f"{work.retrieval_budget_id}:candidate:{work.candidate_id}",
        idempotency_id="retrieval-work-idem:" + _digest((child_run_id, work.candidate_id)),
        child_run_id=child_run_id,
        incarnation=incarnation,
    )


def validate_retrieval_work_bound_inputs(
    work: CandidateWork | RetrievalControl,
    bound_inputs: tuple[tuple[ValueRef, bytes], ...],
) -> None:
    budget_entries = tuple(item for item in bound_inputs if item[0].object_type == RETRIEVAL_BUDGET_STATE_TYPE)
    if len(budget_entries) != 1:
        raise_retrieval_contract_error(ValueError, 'retrieval work requires one immutable root budget')
    definition = build_retrieval_candidate_runtime_definition()
    budget_ref, budget_bytes = budget_entries[0]
    payload_type = CANDIDATE_WORK_TYPE if isinstance(work, CandidateWork) else RETRIEVAL_CONTROL_TYPE
    payload_entries = tuple(item for item in bound_inputs if item[0].object_type == payload_type)
    if len(bound_inputs) != 2 or len(payload_entries) != 1:
        raise_retrieval_contract_error(ValueError, 'retrieval work requires exactly budget and typed payload inputs')
    payload_ref, payload_bytes = payload_entries[0]
    payload_codec = _candidate_work_codec() if isinstance(work, CandidateWork) else _control_codec()
    if (
        budget_ref.codec_id != definition.budget_codec.codec_id
        or payload_ref.codec_id != payload_codec.codec_id
    ):
        raise_retrieval_contract_error(ValueError, 'retrieval work bound input codec drift')
    budget_raw = json.loads(budget_bytes)
    payload_raw = json.loads(payload_bytes)
    if (
        not isinstance(budget_raw, dict)
        or not isinstance(payload_raw, dict)
        or canonical_json(cast(CanonicalJsonObject, budget_raw)).encode("utf-8") != budget_bytes
        or canonical_json(cast(CanonicalJsonObject, payload_raw)).encode("utf-8") != payload_bytes
    ):
        raise_retrieval_contract_error(ValueError, 'retrieval work bound input is not canonical JSON')
    budget = definition.budget_codec.decode_payload(cast(CanonicalJsonObject, budget_raw))
    bound_payload = payload_codec.decode_payload(cast(CanonicalJsonObject, payload_raw))
    if (
        bound_payload != work
        or work.project_key != budget.project_key
        or work.root_run_id != budget.root_run_id
        or work.retrieval_budget_id != budget.budget_id
        or work.plan_id != budget.plan_id
        or work.mode_version != budget.mode_version
        or budget_ref.project_key != work.project_key
        or payload_ref.project_key != work.project_key
        or (
            isinstance(work, CandidateWork)
            and work.material_budget_remaining > budget.max_materials
        )
    ):
        raise_retrieval_contract_error(ValueError, 'retrieval work crosses its immutable root budget')
    for ref, exact in bound_inputs:
        if ref.byte_size != len(exact) or ref.content_digest != sha256_hex(exact):
            raise_retrieval_contract_error(ValueError, 'retrieval work bound input bytes differ from ValueRef')


def validate_retrieval_url_bound_inputs(
    request: UrlSingleUrlRequest,
    bound_inputs: tuple[tuple[ValueRef, bytes], ...],
) -> None:
    """Bind a retrieval URL leaf to its exact request and immutable root budget."""

    if len(bound_inputs) != 2:
        raise_retrieval_contract_error(ValueError, 'retrieval URL operation requires exactly budget and request inputs')
    budget_entries = tuple(
        item for item in bound_inputs if item[0].object_type == RETRIEVAL_BUDGET_STATE_TYPE
    )
    request_entries = tuple(
        item for item in bound_inputs if item[0].object_type == URL_SINGLE_URL_REQUEST_TYPE
    )
    if len(budget_entries) != 1 or len(request_entries) != 1:
        raise_retrieval_contract_error(ValueError, 'retrieval URL bound input types drift')
    budget_ref, budget_bytes = budget_entries[0]
    request_ref, request_bytes = request_entries[0]
    budget_definition = build_retrieval_candidate_runtime_definition()
    request_codec = build_url_single_url_request_codec(build_url_single_url_contract().ref)
    if (
        budget_ref.codec_id != budget_definition.budget_codec.codec_id
        or request_ref.codec_id != request_codec.codec_id
    ):
        raise_retrieval_contract_error(ValueError, 'retrieval URL bound input codec drift')
    budget_raw = json.loads(budget_bytes)
    request_raw = json.loads(request_bytes)
    if (
        not isinstance(budget_raw, dict)
        or not isinstance(request_raw, dict)
        or canonical_json(cast(CanonicalJsonObject, budget_raw)).encode("utf-8") != budget_bytes
        or canonical_json(cast(CanonicalJsonObject, request_raw)).encode("utf-8") != request_bytes
    ):
        raise_retrieval_contract_error(ValueError, 'retrieval URL bound input is not canonical JSON')
    budget = budget_definition.budget_codec.decode_payload(
        cast(CanonicalJsonObject, budget_raw)
    )
    bound_request = request_codec.decode_payload(cast(CanonicalJsonObject, request_raw))
    if bound_request != request:
        raise_retrieval_contract_error(ValueError, 'retrieval URL request differs from its bound input')
    context = _mapping(request.context) or {}
    target = _mapping(request.target) or {}
    if (
        request.project_key != budget.project_key
        or budget_ref.project_key != budget.project_key
        or request_ref.project_key != budget.project_key
        or str(context.get("root_run_id") or "") != budget.root_run_id
        or str(context.get("retrieval_budget_id") or "") != budget.budget_id
        or not str(target.get("candidate_id") or "").strip()
        or not str(target.get("query_id") or "").strip()
    ):
        raise_retrieval_contract_error(ValueError, 'retrieval URL request crosses its CandidateWork root binding')
    for ref, exact in bound_inputs:
        if ref.byte_size != len(exact) or ref.content_digest != sha256_hex(exact):
            raise_retrieval_contract_error(ValueError, 'retrieval URL bound input bytes differ from ValueRef')


def build_retrieval_work_active_child_bytes(
    observations: tuple[ActiveChildTerminalObservation, ...],
) -> Annotated[
    bytes,
    "kit:non-authoritative derived_as=settlement fact_source=active_child_terminal_observations witness=test:test_candidate_work_settlement_binds_exact_input_and_result",
]:
    from app.successor_runtime.language.checksum import canonical_bytes as sequence_bytes
    from app.successor_runtime.language.plan import traversal_element_digests

    codec = _candidate_work_codec()
    encoded: list[CanonicalJsonObject] = []
    for index, observation in enumerate(observations):
        if observation.element_index != index:
            raise_retrieval_contract_error(ValueError, 'retrieval work terminal observations are not ordered')
        if observation.state != "COMPLETED":
            raise_retrieval_contract_error(
                ValueError,
                "retrieval work settlement requires completed child observations",
            )
        before_raw = cast(CanonicalJsonObject, json.loads(observation.input_bytes))
        if canonical_json(before_raw).encode("utf-8") != observation.input_bytes:
            raise_retrieval_contract_error(ValueError, 'retrieval work child input is not canonical JSON')
        if (
            observation.input_ref.object_type != CANDIDATE_WORK_TYPE
            or observation.input_ref.codec_id != codec.codec_id
            or observation.input_ref.byte_size != len(observation.input_bytes)
            or observation.input_ref.content_digest != sha256_hex(observation.input_bytes)
            or observation.element_digest != traversal_element_digests((before_raw,))[0]
        ):
            raise_retrieval_contract_error(ValueError, 'retrieval work child input binding drift')
        before = codec.decode_payload(before_raw)
        if observation.result_ref is None or observation.result_bytes is None:
            raise_retrieval_contract_error(ValueError, 'completed retrieval work child lacks its result')
        after_raw = cast(CanonicalJsonObject, json.loads(observation.result_bytes))
        if canonical_json(after_raw).encode("utf-8") != observation.result_bytes:
            raise_retrieval_contract_error(ValueError, 'retrieval work child result is not canonical JSON')
        if (
            observation.result_ref.object_type != CANDIDATE_WORK_TYPE
            or observation.result_ref.codec_id != codec.codec_id
            or observation.result_ref.byte_size != len(observation.result_bytes)
            or observation.result_ref.content_digest != sha256_hex(observation.result_bytes)
            or observation.result_ref.project_key != observation.input_ref.project_key
        ):
            raise_retrieval_contract_error(ValueError, 'retrieval work child result binding drift')
        after = codec.decode_payload(after_raw)
        validate_candidate_work_transition(before, after)
        encoded.append(codec.encode_payload(after))
    return sequence_bytes(encoded)


class RetrievalWorkActiveChildMaterializer:
    """The sole domain materializer for the CandidateWork traversal."""

    def __init__(
        self,
        activation_catalog: OperationActivationCatalog,
        *,
        active_child_materializer_factory: Callable[
            [OperationActivationCatalog], ActiveChildMaterializer
        ]
        | None = None,
        child_activation_catalog_factory: Callable[
            [Connection, RuntimeScope, ProgramSpec], OperationActivationCatalog
        ]
        | None = None,
    ) -> None:
        self._activation_catalog = activation_catalog
        self._active_child_materializer_factory = active_child_materializer_factory
        self._child_activation_catalog_factory = child_activation_catalog_factory

    def __call__(
        self,
        *,
        connection: Connection,
        scope: RuntimeScope,
        parent_run_id: str,
        descriptor: TraversalMaterialization,
        trigger: ActivationTrigger,
    ) -> ActiveChildMaterializationReceipt:
        run = one_mapping(
            connection.execute(
                select(PUBLIC_TABLES["runtime_runs"]).where(
                    PUBLIC_TABLES["runtime_runs"].c.project_key == scope.project_scope.project_key,
                    PUBLIC_TABLES["runtime_runs"].c.run_id == parent_run_id,
                )
            )
        )
        if run is None:
            raise_retrieval_contract_error(ValueError, 'retrieval work parent run is absent')
        tables = project_tables(MetaData(), scope.project_scope.resolved_schema)
        program = ProgramRepository(connection, tables).get(
            scope, str(run["program_id"]), expected_digest=str(run["program_digest"])
        )
        metadata = dict(program.metadata)
        if (
            metadata.get("schema") != "mrw.project-retrieval.runtime.program.v1"
            or metadata.get("candidate_work_ast_digest") != descriptor.element_program_digest
        ):
            raise_retrieval_contract_error(ValueError, 'retrieval work traversal descriptor differs from its Program')
        candidate_atoms = tuple(
            atom
            for atom in program_atoms(program.root)
            if atom.operation.contract_ref.kind == RETRIEVAL_CANDIDATE_DISCOVER_V3_KIND
        )
        budget_refs = {
            ref
            for atom in candidate_atoms
            for ref in atom.operation.input_refs
            if ref.object_type == RETRIEVAL_BUDGET_STATE_TYPE
        }
        if not candidate_atoms or len(budget_refs) != 1:
            raise_retrieval_contract_error(ValueError, 'retrieval work Program lacks one shared root budget')
        budget_ref = next(iter(budget_refs))
        reader = PostgresRuntimeActivationBindingAdapter()
        budget_bytes = reader.read_value_bytes(connection, scope, tables, budget_ref)
        budget = build_retrieval_candidate_runtime_definition().budget_codec.decode_payload(
            cast(CanonicalJsonObject, json.loads(budget_bytes))
        )
        input_bytes = reader.read_value_bytes(connection, scope, tables, descriptor.input_ref)
        if sha256_hex(input_bytes) != descriptor.input_sequence_digest:
            raise_retrieval_contract_error(ValueError, 'retrieval work traversal input digest drift')
        raw_items = json.loads(input_bytes)
        if not isinstance(raw_items, list):
            raise_retrieval_contract_error(TypeError, 'retrieval work traversal input must be a sequence')
        codec = _candidate_work_codec()
        raw_item_list = cast(list[object], raw_items)
        works = tuple(
            codec.decode_payload(cast(CanonicalJsonObject, item))
            for item in raw_item_list
            if isinstance(item, dict)
        )
        if len(works) != descriptor.element_count or len(works) != len(raw_item_list):
            raise_retrieval_contract_error(ValueError, 'retrieval work traversal element count drift')
        round_material_budgets = {work.material_budget_remaining for work in works}
        if len(round_material_budgets) > 1 or any(
            remaining > budget.max_materials for remaining in round_material_budgets
        ):
            raise_retrieval_contract_error(
                ValueError,
                "retrieval work traversal material budget differs within its immutable root budget",
            )
        children: list[RetrievalWorkChildProgram] = []
        for index, (work, element_digest) in enumerate(zip(works, descriptor.element_digests, strict=True)):
            child_identity = _digest(
                (parent_run_id, descriptor.step_id, work.query_id, work.candidate_id, index, element_digest)
            )
            child_run_id = f"retrieval-work:{child_identity}"
            child = build_retrieval_work_child_program(
                work=work,
                budget_ref=budget_ref,
                budget_bytes=budget_bytes,
                element_index=index,
                element_digest=element_digest,
                program_id=f"program:retrieval-work:{child_identity}",
                child_run_id=child_run_id,
                project_registry_revision=scope.project_scope.project_registry_revision,
                project_scope_digest=scope.project_scope.scope_digest,
            )
            validate_retrieval_work_bound_inputs(work, ((budget_ref, budget_bytes), (child.invocation_ref, dict(child.values)[child.invocation_ref])))
            children.append(child)
        catalog, registry = _retrieval_operation_environment()
        return materialize_active_children(
            connection,
            scope,
            parent_run_id=parent_run_id,
            descriptor=descriptor,
            children=cast(tuple[ActiveChildSubmission, ...], tuple(children)),
            root_value_identity=budget.budget_id,
            operation_catalog=catalog,
            operation_contracts=registry,
            activation_catalog=self._activation_catalog,
            trigger=trigger,
            empty_result_bytes=canonical_json([]).encode("utf-8") if not children else None,
            active_child_materializer_factory=self._active_child_materializer_factory,
            child_activation_catalog_factory=self._child_activation_catalog_factory,
        )


def plan_retrieval_followup(
    journal_reader: RetrievalJournalReader,
    control: RetrievalControl,
) -> Annotated[
    RetrievalControl,
    "kit:non-authoritative derived_as=decision fact_source=runtime_journal+exact_retrieval_budget witness=test:test_followup_planner_uses_settled_runtime_budget",
]:
    """Derive one of at most two follow-up slots from settled Runtime facts."""

    observation = journal_reader(control)
    attempts = _mapping_list(observation.get("attempts"))
    works = _mapping_list(observation.get("works"))
    raw_budget = _mapping(observation.get("budget"))
    if raw_budget is None:
        raise_retrieval_contract_error(ValueError, 'retrieval journal lacks an exact budget observation')
    queries_attempted = _required_budget_counter(raw_budget, "queries_attempted")
    materials_accepted = _required_budget_counter(raw_budget, "materials_accepted")
    max_queries = _required_budget_counter(raw_budget, "max_queries", positive=True)
    max_materials = _required_budget_counter(raw_budget, "max_materials", positive=True)
    if queries_attempted > max_queries or materials_accepted > max_materials:
        raise_retrieval_contract_error(ValueError, 'retrieval journal budget consumption exceeds its ceiling')
    budget: dict[str, CanonicalJsonValue] = {
        "queries_attempted": queries_attempted,
        "materials_accepted": materials_accepted,
        "remaining_queries": max(0, max_queries - queries_attempted),
        "remaining_materials": max(0, max_materials - materials_accepted),
        "max_queries": max_queries,
        "max_materials": max_materials,
        "gap_count": sum(len(cast(list[object], item.get("gaps") or [])) for item in works),
    }
    if (
        control.round < 1
        or control.round > 2
        or control.state == "skipped"
        or budget["remaining_queries"] == 0
        or budget["remaining_materials"] == 0
        or any(item.get("disposition") == "ready" for item in works)
    ):
        return replace(control, state="skipped", planned_query=None, budget=budget)
    gap_terms: list[str] = []
    for item in works:
        for gap in _mapping_list(item.get("gaps")):
            for candidate in (gap.get("detail"), gap.get("code")):
                text = str(candidate or "").strip()
                if text and text not in gap_terms:
                    gap_terms.append(text)
    if not gap_terms:
        return replace(control, state="skipped", planned_query=None, budget=budget)
    executed = {str(item.get("actual_query") or "").strip() for item in attempts}
    planned_rows = build_source_discovery_search_queries(
        topic=control.route_id,
        query_terms=gap_terms[:6],
        source_kinds=["official", "regulatory", "company", "academic", "news", "database"],
        limit=12,
    )
    selected = next((item for item in planned_rows if str(item.get("query") or "").strip() not in executed), None)
    if selected is None:
        return replace(control, state="skipped", planned_query=None, budget=budget)
    expression = str(selected.get("query") or "").strip()
    planned_query: dict[str, CanonicalJsonValue] = {
        "query_id": "followup:" + _digest((control.retrieval_budget_id, control.round, expression))[:32],
        "expression": expression,
        "query_ordinal": queries_attempted + 1,
        "followup_round": control.round,
        "language": "bi",
        "max_results": min(20, cast(int, budget["remaining_materials"])),
        "source_kind": str(selected.get("source_kind") or "followup"),
        "purpose": str(selected.get("purpose") or "close formalization gaps"),
    }
    return replace(control, state="planned", planned_query=planned_query, budget=budget)


def commit_retrieval_topology(
    topology_service: InformationTopologyService,
    journal_reader: RetrievalJournalReader,
    control: RetrievalControl,
) -> RetrievalControl:
    """Call the original topology writer once from settled Runtime readback."""

    observation = journal_reader(control)
    attempt_rows = _mapping_list(observation.get("attempts"))
    works = _mapping_list(observation.get("works"))
    attempts = [
        RetrievalAttempt(
            attempt_id=str(item.get("attempt_id") or ""),
            query_id=str(item.get("query_id") or ""),
            round_id=str(item.get("round_id") or control.root_run_id),
            clue_key=str(item.get("clue_key") or control.route_id),
            executed_at=str(item.get("executed_at") or ""),
            tool=str(item.get("tool") or "source.web.search"),
            actual_query=str(item.get("actual_query") or ""),
            result=str(item.get("result") or "miss"),
            source_ids=tuple(str(value) for value in cast(list[object], item.get("source_ids") or [])),
            material_ids=tuple(str(value) for value in cast(list[object], item.get("material_ids") or [])),
            next_step=str(item.get("next_step") or ""),
            result_note=str(item.get("result_note") or ""),
            raw_return_location=str(item.get("raw_return_location") or ""),
        )
        for item in attempt_rows
    ]
    formal_packages = [
        {
            "candidate_id": item.get("candidate_id"),
            "proposal": (_mapping(item.get("formalization")) or {}).get("proposal"),
            "body_read": item.get("body"),
            "body": item.get("body_text"),
        }
        for item in works
        if item.get("disposition") == "ready"
    ]
    plan = control.plan_snapshot
    target = _mapping(plan.get("topology_ref")) or {
        "module_id": "retrieval",
        "namespace": "runs",
        "state_id": f"retrieval-run:{control.root_run_id}",
    }
    receipt = _append_attempts(
        topology_service=topology_service,
        project_key=control.project_key,
        topology_ref={str(key): str(value) for key, value in target.items()},
        topology_seed=_mapping(plan.get("topology_seed")),
        profile_id=str(plan.get("profile_id") or ""),
        profile_version=str(plan.get("profile_version") or ""),
        session_id=control.root_run_id,
        attempts=tuple(attempts),
        formal_packages=tuple(formal_packages),
    ).to_mapping()
    state: Literal["topology_committed", "topology_failed"] = (
        "topology_committed"
        if receipt.get("status") in {"completed", "not_needed"}
        else "topology_failed"
    )
    return replace(
        control,
        state=state,
        planned_query=None,
        topology=cast(CanonicalJsonObject, receipt),
    )


def build_retrieval_leaf_invocations(
    *,
    topology_service: InformationTopologyService,
    plan_loader: RetrievalPlanLoader,
    journal_reader: RetrievalJournalReader,
) -> Annotated[
    tuple[
        Mapping[str, Callable[[CandidateWork], CandidateWork]],
        Mapping[str, Callable[[RetrievalControl], RetrievalControl]],
    ],
    "kit:prepared-command effect_boundary=successor_retrieval_leaf_handlers witness=test:test_retrieval_runtime_builder_metadata_preserves_semantic_sources",
]:
    """Return the stable kind-to-typed-invoke table for generic handlers."""

    return ({
        RETRIEVAL_MATERIAL_READ_BODY_KIND: partial(read_candidate_work_body, topology_service),
        RETRIEVAL_MATERIAL_FORMALIZE_KIND: partial(formalize_candidate_work, plan_loader),
        RETRIEVAL_MATERIAL_REVALIDATE_KIND: partial(revalidate_candidate_work, topology_service),
    }, {
        RETRIEVAL_FOLLOWUP_PLAN_KIND: partial(plan_retrieval_followup, journal_reader),
        RETRIEVAL_TOPOLOGY_COMMIT_KIND: partial(
            commit_retrieval_topology, topology_service, journal_reader,
        ),
    })


@dataclass(frozen=True, slots=True)
class RetrievalRuntimeProgram:
    run_id: str
    budget: RetrievalBudgetState
    program: ProgramSpec
    values: tuple[tuple[ValueRef, bytes], ...]
    budget_ref: ValueRef
    catalog: OperationContractCatalogSnapshot
    registry: OperationContractRegistry
    transform_registry: TransformRegistry
    merge_registry: TransformRegistry
    discriminator_registry: TransformRegistry
    canonical_bindings: Mapping[str, tuple[int, str]]
    approvals_by_step: Mapping[str, tuple[str, ...]]
    logical_request_id: str
    idempotency_id: str
    incarnation: str


def _control_literal_node(input_type: ObjectType, control: RetrievalControl) -> ProgramNode:
    return pure_node(
        input_type,
        build_retrieval_leaf_contract(RETRIEVAL_FOLLOWUP_PLAN_KIND).input_type,
        freeze_json_value(_encode_control(control)),
        _control_codec().codec_id,
    )


def _control_atom(kind: str, control_ref: ValueRef, budget_ref: ValueRef) -> ProgramNode:
    contract = build_retrieval_leaf_contract(kind)
    return atom_node(
        OperationSpec(
            operation_id=kind,
            contract_ref=contract.ref,
            input_refs=(budget_ref, control_ref),
            payload_ref=control_ref,
            allowed_overrides=freeze_json_object({}),
        ),
        input_type=contract.input_type,
        output_type=contract.output_type,
    )


def _work_traversal_to_control(
    *,
    specimen_root: ProgramNode,
    next_control: RetrievalControl,
    work_control_merge: MergeRef,
) -> ProgramNode:
    traversal = traverse_ordered_node(
        specimen_root,
        "MATERIALIZED_SHAPE",
        sequence_codec_version="2",
    )
    return zip_ordered_node(
        traversal,
        _control_literal_node(CANDIDATE_WORK_SEQUENCE_TYPE, next_control),
        work_control_merge,
        build_retrieval_leaf_contract(RETRIEVAL_FOLLOWUP_PLAN_KIND).input_type,
    )


def build_initial_retrieval_program(
    *,
    project_key: str,
    root_run_id: str,
    plan: RetrievalJsonObject,
    project_registry_revision: int,
    project_scope_digest: str,
    idempotency_key: str,
) -> Annotated[
    RetrievalRuntimeProgram,
    "kit:prepared-command effect_boundary=successor_program_interpreter witness=test:test_actual_root_compiles_initial_candidates_in_declared_order",
]:
    """Build the finite formal root with one reusable CandidateWork Traverse."""

    raw = cast(Mapping[str, Any], plan)
    plan_id = str(raw.get("plan_id") or "").strip()
    mode_version = str(raw.get("mode_version") or "").strip()
    route_id = str(raw.get("route_id") or "").strip()
    selected = tuple(str(item) for item in _list(raw.get("query_ids")))
    queries = {
        str(item.get("id") or item.get("query_id") or ""): item
        for item in _mapping_list(raw.get("queries"))
        if item.get("id") or item.get("query_id")
    }
    limits = _mapping(raw.get("limits")) or {}
    if not all((project_key, root_run_id, plan_id, mode_version, route_id, idempotency_key)):
        raise_retrieval_contract_error(ValueError, 'retrieval root requires exact project, run, plan, mode and route identities')
    if not selected or any(query_id not in queries for query_id in selected):
        raise_retrieval_contract_error(ValueError, 'retrieval root requires selected queries from the immutable plan')
    max_queries = _bounded_limit(limits.get("max_queries"), 10, 10)
    max_materials = _bounded_limit(limits.get("max_materials"), 20, 20)
    max_followups = _bounded_limit(limits.get("max_followups"), 2, 2)
    if max_queries < 1 or max_materials < 1 or len(selected) > max_queries:
        raise_retrieval_contract_error(ValueError, 'retrieval root plan exceeds its domain budget')
    budget = RetrievalBudgetState(
        budget_id=retrieval_budget_id(
            project_key=project_key,
            root_run_id=root_run_id,
            plan_id=plan_id,
            mode_version=mode_version,
        ),
        project_key=project_key,
        root_run_id=root_run_id,
        plan_id=plan_id,
        mode_version=mode_version,
        max_queries=max_queries,
        max_materials=max_materials,
        max_followups=max_followups,
    )
    invocations: list[RetrievalCandidateInvocation] = []
    for ordinal, query_id in enumerate(selected, start=1):
        query = queries[query_id]
        expression = str(query.get("expression") or "").strip()
        owner_route = str(query.get("source_route_id") or query.get("route_id") or route_id)
        if not expression or owner_route != route_id:
            raise_retrieval_contract_error(ValueError, 'retrieval root query does not belong to its route')
        invocations.append(
            RetrievalCandidateInvocation(
                query_id=query_id,
                route_id=route_id,
                query_kind="initial",
                query_ordinal=ordinal,
                followup_round=0,
                budget_id=budget.budget_id,
                request=CandidateSearchRequest(
                    topic=expression,
                    language=str(query.get("language") or "bi"),
                    max_results=min(20, max_materials),
                    project_ref=project_key,
                    source_ref=route_id,
                ),
            )
        )
    prefix = build_retrieval_candidate_prefix(
        invocations=tuple(invocations),
        budget=budget,
        program_id=f"program:{root_run_id}:candidate-root",
        project_key=project_key,
        runtime=build_retrieval_candidate_runtime_definition(),
    )
    transform_registry = TransformRegistry(
        registry_id="mrw.project-retrieval.transforms.v1", registry_version="1"
    )
    transform_refs = _register_retrieval_transforms(transform_registry)
    merge_registry = build_retrieval_merge_registry()
    merge_refs = _retrieval_merge_refs(merge_registry)
    discriminator_registry = TransformRegistry(
        registry_id="mrw.project-retrieval.discriminators.v1", registry_version="1"
    )
    discriminator_refs = _register_retrieval_discriminators(discriminator_registry)
    control_type = build_retrieval_leaf_contract(RETRIEVAL_FOLLOWUP_PLAN_KIND).input_type
    base_control = RetrievalControl(
        project_key=project_key,
        root_run_id=root_run_id,
        retrieval_budget_id=budget.budget_id,
        plan_id=plan_id,
        mode_version=mode_version,
        route_id=route_id,
        round=1,
        plan_snapshot=cast(CanonicalJsonObject, dict(raw)),
        budget={
            "max_queries": max_queries,
            "max_materials": max_materials,
            "max_followups": max_followups,
            "remaining_queries": max_queries,
            "remaining_materials": max_materials,
        },
    )
    initial_candidate_root = prefix.root
    if prefix.root.output_type == RETRIEVAL_CANDIDATE_ATTEMPT_OUTCOME_TYPE:
        initial_candidate_root = map_output_node(
            initial_candidate_root,
            transform_refs["candidate_to_sequence"],
            RETRIEVAL_CANDIDATE_ATTEMPT_SEQUENCE_TYPE,
        )
    initial_work = zip_ordered_node(
        initial_candidate_root,
        _control_literal_node(prefix.root.input_type, base_control),
        merge_refs["candidates_work"],
        CANDIDATE_WORK_SEQUENCE_TYPE,
    )
    specimen_work = CandidateWork(
        project_key=project_key,
        root_run_id=root_run_id,
        retrieval_budget_id=budget.budget_id,
        plan_id=plan_id,
        mode_version=mode_version,
        route_id=route_id,
        query_id=selected[0],
        query_kind="initial",
        query_ordinal=1,
        followup_round=0,
        candidate_ordinal=1,
        candidate_id="candidate:specimen",
        material_budget_remaining=max_materials,
        candidate={"url": "https://specimen.invalid/", "trust": {"status": "pending_review"}},
    )
    specimen = build_retrieval_work_child_program(
        work=specimen_work,
        budget_ref=prefix.budget_ref,
        budget_bytes=dict(prefix.values)[prefix.budget_ref],
        element_index=0,
        element_digest="0" * 64,
        program_id=f"program:{root_run_id}:candidate-work-specimen",
        child_run_id=f"{root_run_id}:candidate-work-specimen",
        project_registry_revision=project_registry_revision,
        project_scope_digest=project_scope_digest,
    )

    followup_slots = tuple(range(1, min(2, max_followups, max_queries - len(invocations)) + 1))
    control_rounds = followup_slots or (0,)
    controls: dict[int, RetrievalControl] = {
        round_id: replace(base_control, round=round_id, state="request", planned_query=None)
        for round_id in control_rounds
    }
    control_values: dict[int, tuple[ValueRef, bytes]] = {}
    for round_id, control in controls.items():
        control_values[round_id] = retrieval_payload_value(
            value=control,
            contract_ref=build_retrieval_leaf_contract(RETRIEVAL_FOLLOWUP_PLAN_KIND).ref,
            value_id=f"program:{root_run_id}:control:{round_id}",
            project_key=project_key,
        )
    topology_ref, _ = control_values[control_rounds[-1]]

    current: ProgramNode = then_node(
        initial_work,
        _work_traversal_to_control(
            specimen_root=specimen.program.root,
            next_control=controls[control_rounds[0]],
            work_control_merge=merge_refs["work_control"],
        ),
    )
    candidate_definition = build_retrieval_candidate_runtime_definition()
    extra_values: list[tuple[ValueRef, bytes]] = list(control_values.values())
    for slot_index, round_id in enumerate(followup_slots):
        control_ref = control_values[round_id][0]
        current = then_node(current, _control_atom(RETRIEVAL_FOLLOWUP_PLAN_KIND, control_ref, prefix.budget_ref))
        ordinal = len(invocations) + round_id
        template = RetrievalCandidateInvocation(
            query_id=f"dynamic-followup:{round_id}",
            route_id=route_id,
            query_kind="followup",
            query_ordinal=ordinal,
            followup_round=round_id,
            budget_id=budget.budget_id,
            request=CandidateSearchRequest(
                topic="__runtime_planned_followup__",
                language="bi",
                max_results=min(20, max_materials),
                project_ref=project_key,
                source_ref=route_id,
            ),
        )
        candidate_leaf = build_retrieval_candidate_atom(
            invocation=template,
            budget=budget,
            program_id=f"program:{root_run_id}:followup:{round_id}",
            project_key=project_key,
            runtime=candidate_definition,
            budget_binding=(prefix.budget_ref, dict(prefix.values)[prefix.budget_ref]),
        )
        extra_values.extend(candidate_leaf.values)
        candidate_path = then_node(
            map_output_node(identity_node(control_type), transform_refs["control_to_invocation"], candidate_definition.program_atom.input_type),
            candidate_leaf.root,
        )
        followup_work = zip_ordered_node(
            identity_node(control_type),
            candidate_path,
            merge_refs["followup_work"],
            CANDIDATE_WORK_SEQUENCE_TYPE,
        )
        next_round = followup_slots[slot_index + 1] if slot_index + 1 < len(followup_slots) else control_rounds[-1]
        next_control = controls[next_round]
        planned_branch = then_node(
            followup_work,
            _work_traversal_to_control(
                specimen_root=specimen.program.root,
                next_control=next_control,
                work_control_merge=merge_refs["work_control"],
            ),
        )
        current = then_node(
            current,
            decide_node(
                discriminator_refs["project_retrieval.control.branch"],
                (
                    DecisionBranch("planned", "state == 'planned'", planned_branch),
                    DecisionBranch(
                        "skipped",
                        "state != 'planned'",
                        map_output_node(
                            identity_node(control_type),
                            transform_refs["control_identity"],
                            control_type,
                        ),
                    ),
                ),
            ),
        )
    root = then_node(current, _control_atom(RETRIEVAL_TOPOLOGY_COMMIT_KIND, topology_ref, prefix.budget_ref))
    catalog, registry = _retrieval_operation_environment(candidate_definition.operation_contract)
    program = ProgramSpec(
        program_id=f"program:{root_run_id}:retrieval-runtime",
        contract_version="mrw.functorial-successor.program-spec.v1",
        project_key=project_key,
        project_registry_revision=project_registry_revision,
        project_scope_digest=project_scope_digest,
        semantic_identity="project_retrieval.runtime.v1",
        input_type=root.input_type,
        output_type=root.output_type,
        root=root,
        algebra_refs=(AlgebraRef("mrw.successor.language.algebra", "1"),),
        transform_refs=tuple(transform_refs.values()),
        observation_profile="project_retrieval.runtime.observation.v1",
        metadata=freeze_json_object(
            {
                "schema": "mrw.project-retrieval.runtime.program.v1",
                "root_run_id": root_run_id,
                "root_budget_id": budget.budget_id,
                "candidate_work_ast_digest": specimen.program.root.ast_digest(),
                "max_followups": max_followups,
                "plan_id": plan_id,
                "mode_version": mode_version,
                "route_id": route_id,
            }
        ),
        program_digest="",
    ).with_digest()
    compiled = compile_program(
        program,
        catalog,
        operation_contracts=registry,
        transform_registry=transform_registry,
        merge_registry=merge_registry,
        discriminator_registry=discriminator_registry,
    )
    values_by_ref = dict(prefix.values)
    for ref, exact in (*specimen.values, *extra_values):
        previous = values_by_ref.setdefault(ref, exact)
        if previous != exact:
            raise_retrieval_contract_error(ValueError, 'retrieval root value identity collision')
    incarnation = f"retrieval-root:{budget.budget_id}"
    effects = tuple(step for step in compiled.ordered_steps if step.step_kind == "EFFECT")
    return RetrievalRuntimeProgram(
        run_id=root_run_id,
        budget=budget,
        program=program,
        values=tuple(values_by_ref.items()),
        budget_ref=prefix.budget_ref,
        catalog=catalog,
        registry=registry,
        transform_registry=transform_registry,
        merge_registry=merge_registry,
        discriminator_registry=discriminator_registry,
        canonical_bindings={step.step_id: (0, incarnation) for step in effects},
        approvals_by_step={},
        logical_request_id=f"{budget.budget_id}:formal-retrieval",
        idempotency_id=f"retrieval-root-idem:{_digest((project_key, idempotency_key))}",
        incarnation=incarnation,
    )

@dataclass(frozen=True, slots=True)
class RetrievalAttempt:
    """One executed search attempt owned by this run; identities are explicit."""

    attempt_id: str
    query_id: str
    round_id: str
    clue_key: str
    executed_at: str
    tool: str
    actual_query: str
    result: str
    source_ids: tuple[str, ...] = ()
    material_ids: tuple[str, ...] = ()
    next_step: str = ""
    result_note: str = ""
    raw_return_location: str = ""

    def to_mapping(self) -> RetrievalJsonObject:
        return {
            "attempt_id": self.attempt_id,
            "query_id": self.query_id,
            "round_id": self.round_id,
            "clue_key": self.clue_key,
            "executed_at": self.executed_at,
            "tool": self.tool,
            "actual_query": self.actual_query,
            "result": self.result,
            "source_ids": list(self.source_ids),
            "material_ids": list(self.material_ids),
            "next_step": self.next_step,
            "result_note": self.result_note,
            "raw_return_location": self.raw_return_location,
        }


@dataclass(frozen=True, slots=True)
class TopologyCommitObservation:
    """Typed receipt for one run topology commit plus verified readback."""

    status: Literal["completed", "not_needed", "blocked", "failed", "readback_failed"]
    attempt_refs: tuple[Mapping[str, object], ...] = ()
    rejected_formal: tuple[Mapping[str, object], ...] = ()
    formal_graph_refs: tuple[Mapping[str, object], ...] = ()
    error: Mapping[str, object] | None = None
    state_digest: str | None = None
    topology_ref: Mapping[str, str] | None = None
    profile_id: str = ""
    profile_version: str = ""
    state_revision: int | None = None

    def to_mapping(self) -> dict[str, object]:
        # Preserve the original per-branch wire shape: empty/absent fields are
        # omitted exactly where the former dict branches omitted them.
        wire: dict[str, object] = {
            "status": self.status,
            "attempt_refs": [dict(ref) for ref in self.attempt_refs],
        }
        if self.error is not None:
            wire["error"] = dict(self.error)
        if self.status in {"readback_failed", "completed"}:
            wire["rejected_formal"] = [dict(item) for item in self.rejected_formal]
            wire["formal_graph_refs"] = [dict(item) for item in self.formal_graph_refs]
            wire["state_revision"] = self.state_revision
        if self.status == "completed":
            wire["state_digest"] = self.state_digest
            wire["topology_ref"] = dict(self.topology_ref) if self.topology_ref is not None else None
            wire["profile_id"] = self.profile_id
            wire["profile_version"] = self.profile_version
        return wire


def _mapping(value: object) -> Mapping[str, Any] | None:
    return cast(Mapping[str, Any], value) if isinstance(value, Mapping) else None


def _mapping_list(value: object) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [cast(Mapping[str, Any], row) for row in cast(list[object], value) if isinstance(row, Mapping)]


def _list(value: object) -> list[Any]:
    return cast(list[Any], value) if isinstance(value, list) else []


def _failure(value: Any) -> dict[str, Any]:
    if isinstance(value, Failure):
        return {"code": value.code, "message": value.message, "context": dict(value.context or {})}
    return {"code": type(value).__name__, "message": str(value)}


def _exact_int(value: object, *, default: int) -> int:
    return value if type(value) is int else default


def _required_budget_counter(
    budget: Mapping[str, object],
    field: str,
    *,
    positive: bool = False,
) -> int:
    value = budget.get(field)
    if type(value) is not int or value < (1 if positive else 0):
        raise_retrieval_contract_error(
            ValueError,
            f'retrieval journal budget field {field} is missing or invalid',
        )
    return value


def _bounded_limit(raw: Any, maximum: int, default: int) -> int:
    try:
        number = int(raw)
    except (TypeError, ValueError):
        number = default
    return max(0, min(maximum, number))


def _compile_topology_seed(
    project_key: str,
    target: Mapping[str, str],
    raw: Mapping[str, Any],
    session_id: str,
    attempts: tuple[RetrievalAttempt, ...],
) -> dict[str, Any] | dict[str, str]:
    """Derive a run state from the fixed project vocabulary and selected route/query rows."""
    vocabulary = resolve_domain_vocabulary(project_key, raw)
    if isinstance(vocabulary, Failure):
        return {"error": vocabulary.code, "message": vocabulary.message}
    try:
        profile = make_retrieval_profile(vocabulary)
        elements = [domain_vocabulary_element(vocabulary)]
        by_query = {attempt.query_id: attempt.result for attempt in attempts}
        for kind, rows_value, identity in (
            ("source_route", raw.get("source_routes"), "route_id"),
            ("keyword_plan", raw.get("keyword_plans"), "plan_id"),
            ("source_registry", raw.get("source_registry", []), "source_id"),
        ):
            if not isinstance(rows_value, list):
                return {"error": "TOPOLOGY_SEED_INVALID", "message": f"{kind} rows are absent"}
            for row_value in cast(list[object], rows_value):
                row = _mapping(row_value)
                if row is None or not str(row.get(identity) or ""):
                    return {"error": "TOPOLOGY_SEED_INVALID", "message": f"{kind} identity is absent"}
                attrs = {key: value for key, value in row.items() if key in profile.types[kind].attributes}
                if kind == "keyword_plan" and str(row[identity]) in by_query:
                    attrs["execution_status"] = "executed"
                    attrs["result"] = by_query[str(row[identity])]
                elif kind == "source_route" and attempts:
                    attrs["status"] = "attempted"
                ref = BoundRef(
                    ElementRef(project_key, target["module_id"], target["namespace"], kind, str(row[identity])),
                    session_id,
                    _digest(attrs),
                )
                elements.append(Element(ref, attrs))
        declared_queries = {str(row.get("plan_id") or "") for row in _mapping_list(raw.get("keyword_plans"))}
        route_ids = [str(row.get("route_id") or "") for row in _mapping_list(raw.get("source_routes"))]
        for attempt in attempts:
            query_id = str(attempt.query_id)
            if query_id in declared_queries:
                continue
            attrs = {
                "plan_id": query_id,
                "kind": "followup",
                "expression": attempt.actual_query,
                "execution_status": "executed",
                "result": attempt.result,
                "source_route_id": route_ids[0] if route_ids else "",
            }
            ref = BoundRef(
                ElementRef(project_key, target["module_id"], target["namespace"], "keyword_plan", query_id),
                session_id,
                _digest(attrs),
            )
            elements.append(Element(ref, attrs))
            declared_queries.add(query_id)
        wire = topology_state_codec.to_wire(TopologyState(profile.profile_id, profile.version, tuple(elements)))
        return {"profile_id": profile.profile_id, "profile_version": profile.version, "elements": wire["elements"]}
    except (TypeError, ValueError, KeyError) as exc:
        return {"error": "TOPOLOGY_SEED_INVALID", "message": str(exc)}


def _read_document_body(
    topology_service: InformationTopologyService, project_key: str, document_id: object
) -> tuple[dict[str, Any], str | None]:
    """Read the persisted ingest output; a queued task or document ID alone is not a body."""
    try:
        from app.models.entities import Document
        from app.services.projects import bind_project

        normalized_document_id = int(str(document_id))
        with bind_project(project_key):
            with topology_service.dependencies.session_factory() as session:
                document = session.get(Document, normalized_document_id)
                if document is None:
                    return {"status": "missing", "error": {"code": "DOCUMENT_NOT_FOUND"}}, None
                body = str(document.content or "").strip()
                if not body:
                    return {"status": "missing", "error": {"code": "DOCUMENT_BODY_EMPTY"}}, None
                return {
                    "status": "read",
                    "document_id": normalized_document_id,
                    "title": str(document.title or ""),
                    "uri": str(document.uri or ""),
                    "body_digest": sha256(body.encode("utf-8")).hexdigest(),
                    "body_length": len(body),
                    "document_updated_at": document.updated_at.isoformat()
                    if getattr(document, "updated_at", None)
                    else None,
                }, body
    except Exception as exc:
        return {"status": "failed", "error": _failure(exc)}, None


def _formal_group(
    *, project_key: str, target: Mapping[str, str], session_id: str, package: Mapping[str, Any], profile: ProfileSpec
) -> tuple[list[Element], dict[str, Any]] | dict[str, Any]:
    """Interpret one formalizer proposal against the bound profile and read body."""
    proposal = _mapping(package.get("proposal"))
    receipt = _mapping(package.get("body_read"))
    body = package.get("body")
    if proposal is None or receipt is None or not isinstance(body, str):
        return {"code": "FORMAL_PROPOSAL_INVALID", "message": "proposal or document observation is missing"}
    nodes_value = proposal.get("nodes")
    nodes = _mapping_list(nodes_value)
    judgment = _mapping(proposal.get("judgment"))
    evidence = _mapping(proposal.get("evidence"))
    clue = _mapping(proposal.get("clue"))
    raw_nodes = cast(list[object], nodes_value) if isinstance(nodes_value, list) else []
    if not isinstance(nodes_value, list) or len(nodes) != len(raw_nodes) or len(nodes) < 2:
        return {"code": "FORMAL_PROPOSAL_INVALID", "message": "at least two nodes are required"}
    if judgment is None or evidence is None or clue is None:
        return {"code": "FORMAL_PROPOSAL_INVALID", "message": "judgment, evidence and clue are required"}
    observed = str(receipt.get("body_digest") or "")
    if not observed or sha256(body.encode("utf-8")).hexdigest() != observed:
        return {"code": "SOURCE_CHANGED", "message": "body observation differs from the supplied document"}
    excerpt = str(evidence.get("original_excerpt") or "")
    if not excerpt or excerpt not in body:
        return {"code": "EVIDENCE_QUOTE_NOT_LOCATED", "message": "original_excerpt is absent from the read body"}
    document_id = str(receipt.get("document_id") or "")
    candidate_id = str(package.get("candidate_id") or "")
    if not document_id.isdigit() or int(document_id) <= 0 or not candidate_id:
        return {"code": "FORMAL_PROPOSAL_INVALID", "message": "document/candidate identity is missing"}
    observation = str(receipt.get("document_updated_at") or observed)
    prefix = _digest((session_id, document_id, candidate_id))[:24]

    def bound(kind: str, local_id: str, attrs: Mapping[str, Any]) -> BoundRef:
        return BoundRef(
            ElementRef(project_key, target["module_id"], target["namespace"], kind, local_id),
            observation,
            _digest(attrs),
        )

    node_refs: dict[str, BoundRef] = {}
    node_labels: dict[str, str] = {}
    group: list[Element] = []
    for node in nodes:
        key = str(node.get("local_key") or "").strip()
        raw_type = str(node.get("type_id") or "").strip()
        source_type = raw_type.removeprefix("node:")
        name = str(node.get("name") or "").strip()
        kind = f"node:{source_type}"
        if not key or key in node_refs or not name or kind not in profile.types:
            return {"code": "FORMAL_NODE_INVALID", "message": "node key, type or name is invalid"}
        attrs = {"source_type": source_type, "name": name}
        ref = bound(kind, f"node-{prefix}-{_digest(key)[:12]}", attrs)
        node_refs[key], node_labels[key] = ref, name
        group.append(Element(ref, attrs))

    from_key, to_key = str(judgment.get("from_key") or ""), str(judgment.get("to_key") or "")
    scene_key = str(clue.get("scene_key") or "")
    if from_key not in node_refs or to_key not in node_refs or scene_key not in node_refs:
        return {"code": "FORMAL_ENDPOINT_MISSING", "message": "proposal endpoint does not name a proposed node"}
    if node_refs[scene_key].ref.type_id != "node:现场":
        return {"code": "FORMAL_SCENE_INVALID", "message": "clue scene_key must point to a 现场 node"}
    for field in ("pools", "relation_classes"):
        if not isinstance(judgment.get(field), list):
            return {"code": "FORMAL_JUDGMENT_INVALID", "message": f"{field} must be an array"}
    outline_section = str(judgment.get("outline_section") or "")
    edge_type = str(judgment.get("edge_type") or "")
    query = _mapping(package.get("query")) or {}
    route = _mapping(package.get("source_route")) or {}
    if query.get("outline_sections") and outline_section not in query["outline_sections"]:
        return {"code": "QUERY_SCOPE_MISMATCH", "message": "judgment outline section is outside the selected query"}
    if query.get("target_edge") and edge_type != query["target_edge"]:
        return {"code": "QUERY_SCOPE_MISMATCH", "message": "judgment edge type differs from the selected query"}
    if route.get("pool") and any(pool != route["pool"] for pool in judgment["pools"]):
        return {"code": "ROUTE_SCOPE_MISMATCH", "message": "judgment pool differs from the selected route"}

    material_attrs: dict[str, Any] = {
        "title": str(receipt.get("title") or receipt.get("uri") or "material"),
        "url": str(receipt.get("uri") or package.get("url") or ""),
        "grade": str(evidence.get("grade") or ""),
        "outline_section": outline_section,
        "reference_status": "body_read",
        "node_ids": [ref.ref.local_id for ref in node_refs.values()],
        "edge_ids": [f"judgment-{prefix}"],
        "relation_classes": list(judgment["relation_classes"]),
        "candidate_id": candidate_id,
        "candidate_key": candidate_id,
        "snapshot_path": [f"material:{document_id}"],
    }
    from app.services.document_queries.identity import document_identity, material_identity

    if profile.version.startswith("2+"):
        material_attrs["document_ref"] = document_identity(project_key, int(document_id))
    else:
        material_attrs["material_ref"] = material_identity(project_key, int(document_id))
    if profile.version.startswith(("2+", "3+")):
        material_attrs.pop("title")
        material_attrs.pop("url")
    material_ref = bound("material", f"material-{prefix}", material_attrs)
    group.append(Element(material_ref, material_attrs))
    judgment_id, evidence_id, clue_id = f"judgment-{prefix}", f"evidence-{prefix}", f"clue-{prefix}"
    judgment_attrs = {
        "edge_type": edge_type,
        "judgment": str(judgment.get("judgment") or ""),
        "scope": str(judgment.get("scope") or ""),
        "judgment_version": session_id,
        "outline_section": outline_section,
        "pools": list(judgment["pools"]),
        "relation_classes": list(judgment["relation_classes"]),
        "evidence_ids": [evidence_id],
        "from_id": node_refs[from_key].ref.local_id,
        "to_id": node_refs[to_key].ref.local_id,
    }
    judgment_ref = bound("judgment", judgment_id, judgment_attrs)
    group.append(
        Element(
            judgment_ref, judgment_attrs, (Endpoint("from", node_refs[from_key]), Endpoint("to", node_refs[to_key]))
        )
    )
    evidence_attrs = {
        key: evidence[key]
        for key in (
            "grade",
            "conflict",
            "effect",
            "original_location",
            "original_excerpt",
            "applicable_scope",
            "inference_note",
            "proves",
            "source_role",
            "independence_group",
        )
        if key in evidence
    }
    evidence_attrs["upstream_material_ids"] = [material_ref.ref.local_id]
    evidence_attrs["conflicting_evidence_ids"] = list(evidence.get("conflicting_evidence_ids") or [])
    evidence_failure = validate_evidence_v2(evidence_attrs)
    if evidence_failure is not None:
        return {"code": evidence_failure.code, "message": evidence_failure.message}
    evidence_ref = bound("evidence", evidence_id, evidence_attrs)
    group.append(
        Element(evidence_ref, evidence_attrs, (Endpoint("material", material_ref), Endpoint("judgment", judgment_ref)))
    )
    clue_attrs = {
        "clue_id": clue_id,
        "round_id": session_id,
        "name": str(clue.get("name") or "").strip(),
        "scene_id": node_refs[scene_key].ref.local_id,
        "scene_label": node_labels[scene_key],
        "pools": list(judgment["pools"]),
        "generation_date": _now()[:10],
    }
    if not clue_attrs["name"]:
        return {"code": "FORMAL_CLUE_INVALID", "message": "clue name is missing"}
    clue_ref = bound("clue", clue_id, clue_attrs)
    group.append(Element(clue_ref, clue_attrs, (Endpoint("item", judgment_ref, 0), Endpoint("item", evidence_ref, 1))))
    refs = {
        "document_id": document_id,
        "candidate_id": candidate_id,
        "material": material_ref.ref.local_id,
        "nodes": [ref.ref.local_id for ref in node_refs.values()],
        "judgment": judgment_id,
        "evidence": evidence_id,
        "clue": clue_id,
        "body_digest": observed,
        "document_updated_at": receipt.get("document_updated_at"),
    }
    return group, refs


def _append_attempts(
    *,
    topology_service: InformationTopologyService,
    project_key: str,
    topology_ref: Mapping[str, Any] | None,
    topology_seed: Mapping[str, Any] | None,
    profile_id: str,
    profile_version: str,
    session_id: str,
    attempts: tuple[RetrievalAttempt, ...],
    formal_packages: tuple[Mapping[str, Any], ...] | None = None,
) -> TopologyCommitObservation:
    """Create a run-owned state in one write; historical states are never patched."""
    if not attempts:
        return TopologyCommitObservation("not_needed")
    if not isinstance(topology_ref, Mapping):
        return TopologyCommitObservation("blocked", error={"code": "TOPOLOGY_TARGET_MISSING"})
    target = {key: str(topology_ref.get(key) or "") for key in ("module_id", "namespace", "state_id")}
    if not all(target.values()):
        return TopologyCommitObservation("blocked", error={"code": "TOPOLOGY_TARGET_INCOMPLETE"})
    if not target["state_id"].startswith("retrieval-run:"):
        return TopologyCommitObservation("blocked", error={"code": "RUN_TOPOLOGY_TARGET_REQUIRED"})
    if not isinstance(topology_seed, Mapping):
        return TopologyCommitObservation("blocked", error={"code": "TOPOLOGY_SEED_MISSING"})
    if not isinstance(topology_seed.get("elements"), list):
        topology_seed = _compile_topology_seed(project_key, target, topology_seed, session_id, attempts)
    if "error" in topology_seed:
        return TopologyCommitObservation(
            "failed",
            error={"code": topology_seed["error"], "message": topology_seed.get("message")},
        )
    profile_id = profile_id or str(topology_seed.get("profile_id") or "")
    profile_version = profile_version or str(topology_seed.get("profile_version") or "")
    if (topology_seed.get("profile_id"), topology_seed.get("profile_version")) != (profile_id, profile_version):
        return TopologyCommitObservation("failed", error={"code": "PROFILE_VERSION_CONFLICT"})
    elements_value = topology_seed["elements"]
    elements = list(cast(list[Any], elements_value))
    element_mappings = [_mapping(element) for element in elements]
    if any(
        element is None
        or ((_mapping((_mapping(element.get("ref")) or {}).get("ref")) or {}).get("project_key")) != project_key
        for element in element_mappings
    ):
        return TopologyCommitObservation("failed", error={"code": "TOPOLOGY_SEED_PROJECT_MISMATCH"})
    if (
        sum(
            1
            for element in element_mappings
            if element is not None
            and ((_mapping((_mapping(element.get("ref")) or {}).get("ref")) or {}).get("type_id"))
            == "domain_vocabulary"
        )
        != 1
    ):
        return TopologyCommitObservation("failed", error={"code": "DOMAIN_VOCABULARY_SEED_REQUIRED"})
    try:
        current = topology_service.read_topology(project_key, target, {})
    except Exception as exc:
        return TopologyCommitObservation("failed", error=_failure(exc))
    if not isinstance(current, Failure) or current.code != "NOT_FOUND":
        return TopologyCommitObservation(
            "failed",
            error={
                "code": "IDENTITY_CONFLICT" if not isinstance(current, Failure) else current.code,
                "message": "run topology identity already exists or cannot be read",
            },
        )
    refs: list[dict[str, Any]] = []
    for attempt in attempts:
        local_id = str(attempt.attempt_id)
        ref = {
            "ref": {
                "project_key": project_key,
                "module_id": target["module_id"],
                "namespace": target["namespace"],
                "type_id": "attempt",
                "local_id": local_id,
            },
            "observed_revision": session_id,
            "content_digest": _digest(attempt.to_mapping()),
        }
        element: dict[str, Any] = {"ref": ref, "attributes": attempt.to_mapping(), "endpoints": []}
        elements.append(element)
        refs.append(ref)
    wire = {
        "kind": "information_topology.state.v1",
        "profile_id": profile_id,
        "profile_version": profile_version,
        "elements": elements,
    }
    profile = profile_from_state_payload(project_key, profile_id, profile_version, wire)
    if isinstance(profile, Failure):
        return TopologyCommitObservation("failed", error=_failure(profile))
    base = decode_state(profile, wire)
    if isinstance(base, Failure):
        return TopologyCommitObservation("failed", error=_failure(base))
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    state_elements = list(base.elements)
    for package in formal_packages or []:
        candidate_id = str(package.get("candidate_id") or "")
        group = _formal_group(
            project_key=project_key, target=target, session_id=session_id, package=package, profile=profile
        )
        if isinstance(group, dict):
            rejected.append({"candidate_id": candidate_id, "error": group})
            continue
        proposed_elements, group_refs = group
        candidate_state = TopologyState(profile_id, profile_version, tuple(state_elements + proposed_elements))
        invalid = validate_state(profile, candidate_state)
        if invalid is not None:
            rejected.append({"candidate_id": candidate_id, "error": _failure(invalid)})
            continue
        state_elements.extend(proposed_elements)
        accepted.append(group_refs)
    elements = topology_state_codec.to_wire(TopologyState(profile_id, profile_version, tuple(state_elements)))[
        "elements"
    ]
    try:
        result = topology_service.apply_batch(
            project_key,
            state_patches=[
                {
                    "target": target,
                    "base_revision": None,
                    "initial_state": {
                        "profile_id": profile_id,
                        "profile_version": profile_version,
                        "elements": elements,
                    },
                    "patch": [],
                }
            ],
            link_writes=[],
            read_set=[],
            link_read_set=[],
        )
    except Exception as exc:
        return TopologyCommitObservation("failed", error=_failure(exc))
    if isinstance(result, Failure):
        return TopologyCommitObservation("failed", error=_failure(result))
    revision_rows = _mapping_list(result.get("state_revisions"))
    revision = revision_rows[0].get("revision") if revision_rows else None
    try:
        readback = topology_service.read_topology(project_key, {**target, "revision": revision}, {})
    except Exception as exc:
        return TopologyCommitObservation(
            "readback_failed",
            attempt_refs=tuple(refs),
            rejected_formal=tuple(rejected),
            error=_failure(exc),
            state_revision=revision,
        )
    if isinstance(readback, Failure):
        return TopologyCommitObservation(
            "readback_failed",
            attempt_refs=tuple(refs),
            rejected_formal=tuple(rejected),
            error=_failure(readback),
            state_revision=revision,
        )
    readback_topology = _mapping(readback.get("topology")) or {}
    read_ids = {
        str((_mapping((_mapping(element.get("ref")) or {}).get("ref")) or {}).get("local_id") or "")
        for element in _mapping_list(readback_topology.get("elements"))
    }
    verified = [
        group
        for group in accepted
        if all(
            key in read_ids
            for key in (group["material"], *group["nodes"], group["judgment"], group["evidence"], group["clue"])
        )
    ]
    if len(verified) != len(accepted) or readback.get("revision") != revision:
        return TopologyCommitObservation(
            "readback_failed",
            attempt_refs=tuple(refs),
            rejected_formal=tuple(rejected),
            error={"code": "TOPOLOGY_READBACK_MISMATCH"},
            state_revision=revision,
        )
    return TopologyCommitObservation(
        "completed",
        attempt_refs=tuple(refs),
        rejected_formal=tuple(rejected),
        formal_graph_refs=tuple(verified),
        state_digest=readback.get("digest") if isinstance(readback.get("digest"), str) else None,
        topology_ref=target,
        profile_id=profile_id,
        profile_version=profile_version,
        state_revision=revision,
    )


__all__ = [
    "RetrievalRuntimeProgram",
    "RetrievalWorkActiveChildMaterializer",
    "build_initial_retrieval_program",
    "build_retrieval_discriminator_registry",
    "build_retrieval_leaf_invocations",
    "build_retrieval_merge_registry",
    "build_retrieval_transform_registry",
    "build_retrieval_work_active_child_bytes",
    "commit_retrieval_topology",
    "formalize_candidate_work",
    "plan_retrieval_followup",
    "read_candidate_work_body",
    "review_candidate_work",
    "revalidate_candidate_work",
    "validate_retrieval_work_bound_inputs",
]
