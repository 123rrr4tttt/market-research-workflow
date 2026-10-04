"""Rapid round handoff over the existing project retrieval executor and proposal writer.

The original Rapid method and its internal Agent loop are separate from this
adapter. Method judgments arrive as explicit inputs; only observed executor
attempts and body read receipts supply source provenance. Continuation starts a
new bounded executor run and retains the saved proposal as its reason.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from hashlib import sha256
import json
from typing import Annotated, Any

from functorial_kit import Failure, define_failure_family

from app.services.project_retrieval.execution import execute_retrieval_run
from app.services.project_retrieval.proposals import (
    ProposalAttempt,
    ProposalDigest,
    ProposalFacet,
    ProposalFrontier,
    ProposalGap,
    ProposalOccurrence,
    ProposalQuery,
    ProposalSnapshot,
    RapidProposal,
    RapidProposalTopologyAdapter,
)


rapid_macro_failures = define_failure_family(
    "project_retrieval.rapid_macro",
    ("ROUND_OBSERVATION_INVALID", "CONTINUATION_INVALID", "CONTINUATION_BUDGET_EXHAUSTED"),
)


def _identity(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:20]


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def build_round_proposal(
    *,
    plan: Mapping[str, Any],
    result: Mapping[str, Any],
    proposal_id: str,
    proposal_version: str,
    facet_ref: str,
    facet_source_ref: str,
    digest_summary: str,
    classification_proposals: Sequence[str],
    analysis_positions: Sequence[str],
    coverage_boundary: str,
    failure_boundary: str,
    gap_description: str,
    proposed_query: str = "",
    next_query_reason: str = "",
    outline_section: str = "",
    target_edge: str = "",
) -> Annotated[
    RapidProposal | Failure,
    "kit:non-authoritative derived_as=round_proposal fact_source=plan+observed_result+method_judgments "
    "witness=test:test_round_digest_and_frontier_have_closed_observed_provenance",
]:
    """Associate one method judgment with actual query, attempt and body receipts.

    A candidate hit without a read body stays an ``unknown`` proposal attempt;
    it cannot be presented as a material snapshot. A miss or access failure can
    still produce a digest with an explicit gap and no invented body.
    """
    required = (
        proposal_id, proposal_version, facet_ref, facet_source_ref, digest_summary,
        coverage_boundary, failure_boundary, gap_description,
    )
    if any(not _text(value) for value in required):
        return rapid_macro_failures.fail("ROUND_OBSERVATION_INVALID", "round identity and method judgments are required")
    if any(not _text(value) for value in (*classification_proposals, *analysis_positions)):
        return rapid_macro_failures.fail("ROUND_OBSERVATION_INVALID", "classification and position values must be nonempty")
    session_id = _text(result.get("session_id"))
    if not session_id or _text(result.get("plan_id")) != _text(plan.get("plan_id")):
        return rapid_macro_failures.fail("ROUND_OBSERVATION_INVALID", "executor session or plan identity is missing")
    attempts_raw = result.get("attempts")
    if not isinstance(attempts_raw, list) or not attempts_raw:
        return rapid_macro_failures.fail("ROUND_OBSERVATION_INVALID", "an actual search attempt is required")
    plan_queries = {
        str(row.get("query_id") or row.get("id") or ""): row
        for row in plan.get("queries") or [] if isinstance(row, Mapping)
    }
    route_id = _text(plan.get("route_id"))
    queries: list[ProposalQuery] = []
    attempts: list[ProposalAttempt] = []
    snapshots: list[ProposalSnapshot] = []
    occurrences: list[ProposalOccurrence] = []
    material_refs: list[str] = []
    body_digests: list[str] = []
    query_ids: set[str] = set()
    snapshot_ids: set[str] = set()
    candidate_rows = {
        str(row.get("candidate_id") or ""): row
        for row in result.get("candidates") or [] if isinstance(row, Mapping)
    }
    materials_by_query: dict[str, list[Mapping[str, Any]]] = {}
    for material in result.get("materials") or []:
        if not isinstance(material, Mapping):
            continue
        candidate = candidate_rows.get(str(material.get("candidate_id") or ""))
        if candidate is not None:
            materials_by_query.setdefault(str(candidate.get("query_id") or ""), []).append(material)
    for raw in attempts_raw:
        if not isinstance(raw, Mapping):
            return rapid_macro_failures.fail("ROUND_OBSERVATION_INVALID", "attempt row is invalid")
        query_id = _text(raw.get("query_id"))
        attempt_id = _text(raw.get("attempt_id"))
        expression = _text(raw.get("actual_query"))
        outcome = _text(raw.get("result"))
        if (
            not query_id or not attempt_id or not expression
            or outcome not in {"hit", "miss", "access_failed"}
            or _text(raw.get("round_id")) != session_id
            or raw.get("tool") != "source.web.search"
            or not _text(raw.get("raw_return_location"))
        ):
            return rapid_macro_failures.fail("ROUND_OBSERVATION_INVALID", "attempt identity, expression or outcome is invalid")
        declared = plan_queries.get(query_id)
        if declared is not None and _text(declared.get("expression")) != expression:
            return rapid_macro_failures.fail("ROUND_OBSERVATION_INVALID", "attempt differs from selected plan query")
        if query_id in query_ids:
            return rapid_macro_failures.fail("ROUND_OBSERVATION_INVALID", "one executor query must have one observed attempt")
        query_ids.add(query_id)
        queries.append(ProposalQuery(query_id, facet_ref, expression))
        refs: list[str] = []
        for material in materials_by_query.get(query_id, []):
            read = material.get("body_read")
            if material.get("status") != "body_read" or not isinstance(read, Mapping) or read.get("status") != "read":
                continue
            document_id = read.get("document_id")
            body_digest = _text(read.get("body_digest"))
            candidate_id = _text(material.get("candidate_id"))
            source_ref = _text(read.get("uri")) or _text(material.get("url"))
            if (
                not document_id or len(body_digest) != 64
                or any(char not in "0123456789abcdef" for char in body_digest.lower())
                or not candidate_id or not source_ref
            ):
                return rapid_macro_failures.fail("ROUND_OBSERVATION_INVALID", "read body lacks source identity or digest")
            snapshot_ref = f"document:{document_id}@{body_digest}"
            refs.append(snapshot_ref)
            if snapshot_ref not in snapshot_ids:
                snapshot_ids.add(snapshot_ref)
                snapshots.append(ProposalSnapshot(snapshot_ref, body_digest, source_ref))
                material_refs.append(snapshot_ref)
                body_digests.append(body_digest)
            occurrences.append(ProposalOccurrence(
                f"occurrence:{_identity((attempt_id, candidate_id, snapshot_ref))}",
                facet_ref, query_id, attempt_id, snapshot_ref, candidate_id,
            ))
        attempts.append(ProposalAttempt(
            attempt_id, query_id,
            outcome if outcome != "hit" or refs else "unknown",
            tuple(refs),
        ))
    if len({item.attempt_id for item in attempts}) != len(attempts):
        return rapid_macro_failures.fail("ROUND_OBSERVATION_INVALID", "attempt identity repeats")
    prefix = _identity((proposal_id, proposal_version, tuple(item.attempt_id for item in attempts)))
    gap_id, digest_id = f"gap:{prefix}", f"digest:{prefix}"
    gap = ProposalGap(
        gap_id, facet_ref, gap_description,
        tuple(item.attempt_id for item in attempts),
        tuple(item.occurrence_id for item in occurrences),
    )
    digest = ProposalDigest(
        digest_id, tuple(item.occurrence_id for item in occurrences), digest_summary,
        tuple(classification_proposals), tuple(analysis_positions), coverage_boundary, failure_boundary,
        tuple(item.query_id for item in queries), tuple(item.attempt_id for item in attempts),
        tuple(material_refs), tuple(body_digests), (gap_id,),
    )
    frontier: tuple[ProposalFrontier, ...] = ()
    if any((_text(proposed_query), _text(next_query_reason), _text(outline_section), _text(target_edge))):
        if not all((_text(proposed_query), _text(next_query_reason), _text(outline_section), _text(target_edge))):
            return rapid_macro_failures.fail("ROUND_OBSERVATION_INVALID", "next query needs reason, outline section and target edge")
        frontier = (ProposalFrontier(
            f"frontier:{prefix}", facet_ref, proposed_query, next_query_reason,
            (digest_id,), (gap_id,), tuple(item.occurrence_id for item in occurrences),
            digest_id, gap_id, outline_section, target_edge,
        ),)
    proposal = RapidProposal(
        proposal_id, proposal_version, (ProposalFacet(facet_ref, facet_source_ref),),
        tuple(queries), tuple(snapshots), tuple(attempts), tuple(occurrences),
        (digest,), (gap,), frontier,
    )
    invalid = proposal.validate()
    return invalid if invalid is not None else proposal


def save_round_proposal(
    *, adapter: RapidProposalTopologyAdapter, project_key: str, proposal: RapidProposal, vocabulary: Any,
) -> Any:
    """Use the existing writer; only persisted plus verified readback closes delivery."""
    return adapter.save(project_key, proposal, vocabulary)


def continuation_plan_from_saved_frontier(
    *, adapter: RapidProposalTopologyAdapter, project_key: str, proposal_id: str,
    proposal_version: str, frontier_id: str, base_plan: Mapping[str, Any],
    remaining_followup_budget: int,
) -> dict[str, Any] | Failure:
    """Turn one saved frontier into a single query for the original executor.

    ``remaining_followup_budget`` is the caller's explicit continuation budget.
    The base plan's ``max_queries`` only limits searches inside one executor run.
    """
    if type(remaining_followup_budget) is not int or remaining_followup_budget <= 0:
        return rapid_macro_failures.fail("CONTINUATION_BUDGET_EXHAUSTED", "no authorized continuation remains")
    saved = adapter.read(project_key, proposal_id, proposal_version)
    if isinstance(saved, Failure):
        return saved
    frontier = next((item for item in saved.frontier if item.frontier_id == frontier_id), None)
    if frontier is None:
        return rapid_macro_failures.fail("CONTINUATION_INVALID", "saved frontier has no complete continuation basis")
    # Proposal v1/v2 persisted the continuation basis in source id arrays and
    # the JSON reason field.  Project that representation forward so migration
    # does not strand a valid frontier.
    parent_digest_id = frontier.parent_digest_id or (frontier.source_digest_ids[0] if frontier.source_digest_ids else "")
    gap_id = frontier.gap_id or (frontier.source_gap_ids[0] if frontier.source_gap_ids else "")
    outline_section = frontier.outline_section
    target_edge = frontier.target_edge
    if (not outline_section or not target_edge) and frontier.reason:
        try:
            reason_payload = json.loads(frontier.reason)
        except (TypeError, ValueError):
            reason_payload = {}
        if isinstance(reason_payload, Mapping):
            outline_section = outline_section or _text(reason_payload.get("outline_section"))
            target_edge = target_edge or _text(reason_payload.get("target_edge"))
    if not all((parent_digest_id, gap_id, outline_section, target_edge, frontier.proposed_query, frontier.reason)):
        return rapid_macro_failures.fail("CONTINUATION_INVALID", "saved frontier has no complete continuation basis")
    route_id = _text(base_plan.get("route_id"))
    routes = (base_plan.get("binding_snapshot") or {}).get("routes") or []
    route = next((row for row in routes if isinstance(row, Mapping) and row.get("route_id") == route_id), None)
    if not route_id or route is None:
        return rapid_macro_failures.fail("CONTINUATION_INVALID", "base plan has no matching route snapshot")
    if (
        outline_section not in (route.get("outline_sections") or [])
        or target_edge not in (route.get("target_edges") or [])
    ):
        return rapid_macro_failures.fail("CONTINUATION_INVALID", "frontier is outside the bound route")
    previous = [row for row in base_plan.get("queries") or [] if isinstance(row, Mapping)]
    # The frozen base plan may already contain the next query as an unexecuted
    # route seed (the normal preview path does exactly that).  It is only a
    # duplicate continuation when the expression was actually persisted in the
    # saved proposal.  Rejecting against the base plan itself made valid
    # frontiers fail with CONTINUATION_INVALID before the executor ran.
    prior_expressions = {query.expression for query in saved.queries}
    if frontier.proposed_query in prior_expressions:
        return rapid_macro_failures.fail("CONTINUATION_INVALID", "frontier repeats a bound query")
    basis = dict(previous[0]) if previous else {}
    query_id = f"rapid-followup:{_identity((saved.content_digest, frontier.frontier_id))}"
    basis.update({
        "query_id": query_id,
        "route_id": route_id,
        "source_route_id": route_id,
        "expression": frontier.proposed_query,
        "outline_sections": [outline_section],
        "target_edge": target_edge,
    })
    limits = dict(base_plan.get("limits") or {})
    if type(limits.get("max_materials")) is not int or limits["max_materials"] < 1:
        return rapid_macro_failures.fail("CONTINUATION_INVALID", "base plan material budget is invalid")
    limits.update({"max_queries": 1, "max_followups": 0})
    continuation = {
        "parent_proposal_id": saved.proposal_id,
        "parent_proposal_version": saved.proposal_version,
        "parent_content_digest": saved.content_digest,
        "parent_digest_id": parent_digest_id,
        "gap_id": gap_id,
        "frontier_id": frontier.frontier_id,
        "reason": frontier.reason,
        "remaining_followup_budget": remaining_followup_budget - 1,
    }
    plan = dict(base_plan)
    topology_ref = base_plan.get("topology_ref")
    if isinstance(topology_ref, Mapping):
        plan["topology_ref"] = {
            **topology_ref,
            "state_id": f"retrieval-run:{query_id}",
        }
    plan.update({
        "plan_id": f"rapid-continuation:{_identity((base_plan.get('plan_id'), continuation, query_id))}",
        "query_ids": [query_id],
        "queries": [basis],
        "limits": limits,
        "rapid_continuation": continuation,
    })
    return plan


def execute_saved_frontier(
    *, adapter: RapidProposalTopologyAdapter, project_key: str, proposal_id: str,
    proposal_version: str, frontier_id: str, base_plan: Mapping[str, Any],
    remaining_followup_budget: int, topology_service: Any,
    session_factory: Callable[[], Any],
    emit: Callable[[str, Mapping[str, Any]], None] | None = None,
) -> dict[str, Any] | Failure:
    """Dispatch the saved next query through the existing executor, preserving its receipts."""
    plan = continuation_plan_from_saved_frontier(
        adapter=adapter, project_key=project_key, proposal_id=proposal_id,
        proposal_version=proposal_version, frontier_id=frontier_id, base_plan=base_plan,
        remaining_followup_budget=remaining_followup_budget,
    )
    if isinstance(plan, Failure):
        return plan
    result = execute_retrieval_run(
        project_key=project_key, plan=plan, topology_service=topology_service,
        session_factory=session_factory, emit=emit,
    )
    return {"plan": plan, "result": result, "continuation": plan["rapid_continuation"]}


__all__ = [
    "build_round_proposal", "save_round_proposal", "continuation_plan_from_saved_frontier",
    "execute_saved_frontier", "rapid_macro_failures",
]
