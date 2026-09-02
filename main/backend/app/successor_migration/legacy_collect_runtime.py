"""Sibling legacy adapters for the C3 collect batch-traverse and result-fold atoms.

This is the only file allowed to call the legacy pure helpers
``collect_runtime.runtime._should_auto_batch``,
``_split_query_terms``, ``_resolve_auto_batch_parallelism``,
``_resolve_auto_batch_fail_fast`` and ``_merge_collect_results``.  It never
dispatches a real provider adapter: element execution is injected through a
bounded fixture runner, so the adapter only replays deterministic legacy
planning/fold semantics and projects the legacy observation into the frozen
successor union.

The adapters validate the exact Program/Plan/contract/payload/project/binding
closure before touching the legacy helpers, and expose the independent exact
binding builders for the legacy and successor interpreters.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import ceil
from typing import Any, Protocol, runtime_checkable

from app.successor_runtime.capabilities import collect_c3 as c3
from app.successor_runtime.capabilities.checksum import content_digest
from app.successor_runtime.capabilities.collect_c3_interpreters import (
    COLLECT_C3_1_LEGACY_INTERPRETER_ID,
    COLLECT_C3_2_LEGACY_INTERPRETER_ID,
    CollectBindingMismatch,
    InterpreterFailure,
    InterpreterSuccess,
    authority_requirement_digest,
    deterministic_composed_element_runner,
    legacy_interpreter_profile_digest_c3_1,
    legacy_interpreter_profile_digest_c3_2,
    require_exact_collect_binding,
    require_exact_composed_binding,
    run_ordered_traversal,
    successor_interpreter_profile_digest_c3_1,
    successor_interpreter_profile_digest_c3_2,
)
from app.successor_runtime.runtime.assignments import InterpreterBinding

__all__ = [
    "COLLECT_C3_COMPOSED_LEGACY_INTERPRETER_ID",
    "LegacyCollectBatchTraverseAdapter",
    "LegacyCollectResultFoldAdapter",
    "LegacyComposedCollectInterpreter",
    "LegacyComposedShadowObservation",
    "LegacyElementRunner",
    "bindings_are_distinct",
    "build_legacy_collect_c3_1_binding",
    "build_legacy_collect_c3_2_binding",
    "build_successor_collect_c3_1_binding",
    "build_successor_collect_c3_2_binding",
]


@runtime_checkable
class LegacyElementRunner(Protocol):
    def run(self, request: Any) -> Any:
        """Run one legacy CollectRequest and return a legacy CollectResult."""


def _legacy_request_from_snapshot(
    snapshot: c3.CollectLegacyRequestSnapshot,
) -> Any:
    from app.services.collect_runtime.contracts import CollectRequest

    return CollectRequest(
        contract_version="collect.request.v1",
        flow=snapshot.flow,
        channel=snapshot.channel,
        project_key=snapshot.project_key,
        query_terms=list(snapshot.query_terms),
        urls=list(snapshot.urls),
        limit=snapshot.limit,
        options=dict(snapshot.options),
        source_context=dict(snapshot.source_context),
    )


def _legacy_plan_values(
    request: Any,
    *,
    resource_policy: c3.CollectResourcePolicy,
) -> dict[str, Any]:
    from app.services.collect_runtime.runtime import (
        _resolve_auto_batch_fail_fast,
        _resolve_auto_batch_parallelism,
        _should_auto_batch,
        _split_query_terms,
    )

    applicable = bool(_should_auto_batch(request))
    term_batches = _split_query_terms(list(request.query_terms or []))
    if not applicable:
        return {
            "applicable": False,
            "disposition": "BYPASSED",
            "term_batches": [],
            "per_batch_limit": 1,
            "requested_parallelism": 1,
            "effective_parallelism": 1,
            "fail_fast": False,
            "batches_total": 0,
        }
    per_limit = max(
        10,
        ceil(max(1, request.limit or 20) / max(1, len(term_batches))),
    )
    requested = _resolve_auto_batch_parallelism(request)
    fail_fast = bool(_resolve_auto_batch_fail_fast(request))
    ceiling = max(1, len(term_batches))
    effective = min(requested, ceiling, int(resource_policy.max_parallelism))
    return {
        "applicable": True,
        "disposition": ("SINGLETON_IDENTITY" if len(term_batches) <= 1 else "TRAVERSE"),
        "term_batches": term_batches,
        "per_batch_limit": per_limit,
        "requested_parallelism": requested,
        "effective_parallelism": effective,
        "fail_fast": fail_fast,
        "batches_total": len(term_batches),
    }


def _typed_plan_from_legacy_values(
    *,
    request_ref: c3.CollectRequestRef,
    snapshot: c3.CollectLegacyRequestSnapshot,
    plan_id: str,
    resource_policy: c3.CollectResourcePolicy,
    authority_scope_ref: str,
    values: dict[str, Any],
) -> c3.CollectBatchPlan:
    failure_policy = (
        "FAIL_FAST_WITH_PARTIAL_OBSERVATION" if values["fail_fast"] else "ACCUMULATE"
    )
    elements: tuple[c3.CollectBatchElement, ...] = ()
    if values["disposition"] != "BYPASSED":
        elements = tuple(
            c3.CollectBatchElement(
                schema_version=c3.COLLECT_BATCH_ELEMENT_SCHEMA_REF,
                element_id=f"{plan_id}:element:{index}",
                input_index=index,
                query_terms=tuple(batch),
                per_batch_limit=values["per_batch_limit"],
                traversal_policy="MATERIALIZED_SHAPE",
                failure_policy=failure_policy,
                element_digest="",
            )
            for index, batch in enumerate(values["term_batches"])
        )
    return c3.CollectBatchPlan(
        schema_version=c3.COLLECT_BATCH_PLAN_SCHEMA_REF,
        plan_id=plan_id,
        request_ref=request_ref,
        disposition=values["disposition"],
        traversal_policy="MATERIALIZED_SHAPE",
        failure_policy=failure_policy,
        elements=elements,
        per_batch_limit=values["per_batch_limit"],
        requested_parallelism=values["requested_parallelism"],
        effective_parallelism=values["effective_parallelism"],
        batches_total=values["batches_total"],
        plan_digest="",
    )


def _outcome_from_legacy_result(
    *,
    element: c3.CollectBatchElement,
    terms: list[str],
    result: Any,
    raw_digest: str,
) -> c3.CollectElementOutcome:
    failed = str(getattr(result, "status", "") or "").strip().lower() == "failed"
    links = tuple(
        str(link or "").strip()
        for link in (
            ((getattr(result, "meta", None) or {}).get("raw") or {}).get("links") or []
        )
        if str(link or "").strip()
    )
    receipt: c3.CollectAttemptReceipt | None = None
    provider_job_id = getattr(result, "provider_job_id", None)
    if provider_job_id:
        provider_type = str(getattr(result, "provider_type", "") or "").strip()
        provider_status = getattr(result, "provider_status", None)
        authoritative = str(provider_status or "").strip().lower() in {
            "completed",
            "complete",
            "succeeded",
        }
        receipt = c3.CollectAttemptReceipt(
            schema_version=c3.COLLECT_ATTEMPT_RECEIPT_SCHEMA_REF,
            receipt_kind=(
                "AUTHORITATIVE_READBACK"
                if authoritative
                else "DISPATCH_ACKNOWLEDGEMENT"
            ),
            provider_type=provider_type or "unknown",
            provider_job_id=str(provider_job_id),
            provider_status=(None if provider_status is None else str(provider_status)),
            attempt_count=int(getattr(result, "attempt_count", None) or 0),
            observed_at="1970-01-01T00:00:00Z",
            raw_digest=raw_digest,
            authoritative_readback=authoritative,
            receipt_digest="",
        )
    counts = c3.CollectCounts(
        inserted=int(getattr(result, "inserted", None) or 0),
        updated=int(getattr(result, "updated", None) or 0),
        skipped=int(getattr(result, "skipped", None) or 0),
    )
    legacy_ref = "legacy:" + content_digest(
        {
            "schema": "mrw.successor.collect.c3.legacy-result.v1",
            "element_id": element.element_id,
            "query_terms": terms,
            "status": getattr(result, "status", ""),
            "inserted": counts.inserted,
            "updated": counts.updated,
            "skipped": counts.skipped,
            "raw_digest": raw_digest,
        }
    )
    if failed:
        first_error = ((getattr(result, "errors", None) or []) or [{}])[0]
        error = c3.CollectElementError(
            code=(
                str(first_error.get("code") or "auto_batch_execution_failed")
                if first_error.get("code") in c3.COLLECT_ELEMENT_ERROR_CODES
                else "auto_batch_execution_failed"
            ),
            message=str(first_error.get("message") or "legacy element failed"),
            query_terms=tuple(terms),
            exception_type=first_error.get("exception_type"),
            error_digest="",
        )
        return c3.CollectElementFailed(
            schema_version=c3.COLLECT_ELEMENT_OUTCOME_SCHEMA_REF,
            element_id=element.element_id,
            input_index=element.input_index,
            error=error,
            counts=counts,
            links=links,
            receipt=receipt,
            legacy_observation_ref=legacy_ref,
            outcome_digest="",
        )
    return c3.CollectElementSucceeded(
        schema_version=c3.COLLECT_ELEMENT_OUTCOME_SCHEMA_REF,
        element_id=element.element_id,
        input_index=element.input_index,
        counts=counts,
        links=links,
        receipt=receipt,
        legacy_observation_ref=legacy_ref,
        outcome_digest="",
    )


@dataclass(frozen=True, slots=True)
class LegacyCollectTrace:
    """Deterministic replay trace over the legacy pure planning helpers."""

    trace_id: str
    applicable: bool
    disposition: str
    term_batches: list[list[str]]
    per_batch_limit: int
    requested_parallelism: int
    effective_parallelism: int
    fail_fast: bool
    trace_digest: str = ""

    def __post_init__(self) -> None:
        if not self.trace_id:
            raise ValueError("LegacyCollectTrace.trace_id is required")
        if self.trace_digest == "":
            object.__setattr__(
                self,
                "trace_digest",
                content_digest(
                    {
                        "schema": "mrw.successor.collect.c3.legacy-trace.v1",
                        "trace_id": self.trace_id,
                        "applicable": self.applicable,
                        "disposition": self.disposition,
                        "term_batches": self.term_batches,
                        "per_batch_limit": self.per_batch_limit,
                        "requested_parallelism": self.requested_parallelism,
                        "effective_parallelism": self.effective_parallelism,
                        "fail_fast": self.fail_fast,
                    }
                ),
            )


class LegacyCollectBatchTraverseAdapter:
    """Legacy sibling interpreter for the C3.1 batch traverse atom."""

    interpreter_id = COLLECT_C3_1_LEGACY_INTERPRETER_ID

    def __init__(self) -> None:
        self.resolves = 0
        self.traces: list[LegacyCollectTrace] = []

    def _legacy_trace_values(
        self,
        payload: c3.CollectBatchElementPayload,
        resource_policy: c3.CollectResourcePolicy,
    ) -> dict[str, Any]:
        request = _legacy_request_from_snapshot(payload.request_snapshot)
        return _legacy_plan_values(
            request,
            resource_policy=resource_policy,
        )

    def _trace(
        self,
        payload: c3.CollectBatchElementPayload,
        *,
        trace_id: str = "legacy.collect.c3_1.trace",
    ) -> LegacyCollectTrace:
        values = self._legacy_trace_values(payload, payload.resource_policy)
        trace = LegacyCollectTrace(
            trace_id=trace_id,
            applicable=values["applicable"],
            disposition=values["disposition"],
            term_batches=values["term_batches"],
            per_batch_limit=values["per_batch_limit"],
            requested_parallelism=values["requested_parallelism"],
            effective_parallelism=values["effective_parallelism"],
            fail_fast=values["fail_fast"],
            trace_digest="",
        )
        self.traces.append(trace)
        return trace

    def resolve(
        self,
        payload: c3.CollectBatchElementPayload,
        *,
        program: Any,
        plan: Any,
        contract_ref: Any,
        payload_ref: Any,
        project_scope: Any,
        catalog: Any,
        deployment_catalog_digest: str,
        binding: Any,
        runner: LegacyElementRunner,
        expected_interpreter_profile_digest: str | None = None,
    ):
        try:
            require_exact_collect_binding(
                program=program,
                plan=plan,
                contract_ref=contract_ref,
                payload_ref=payload_ref,
                payload=payload,
                project_scope=project_scope,
                catalog=catalog,
                deployment_catalog_digest=deployment_catalog_digest,
                binding=binding,
                expected_interpreter_profile_digest=(
                    expected_interpreter_profile_digest
                    or legacy_interpreter_profile_digest_c3_1()
                ),
            )
        except CollectBindingMismatch as exc:
            return InterpreterFailure(
                code="ASSIGNMENT_BINDING_MISMATCH",
                message=str(exc),
                retryable=False,
            )

        values = self._legacy_trace_values(payload, payload.resource_policy)
        plan_id = f"legacy-c3-1:{payload.parent_request_ref.request_id}"
        typed_plan = _typed_plan_from_legacy_values(
            request_ref=payload.parent_request_ref,
            snapshot=payload.request_snapshot,
            plan_id=plan_id,
            resource_policy=payload.resource_policy,
            authority_scope_ref=payload.authority_scope_ref,
            values=values,
        )
        successor_plan = c3.build_collect_batch_plan(
            request_ref=payload.parent_request_ref,
            snapshot=payload.request_snapshot,
            plan_id=plan_id,
            resource_policy=payload.resource_policy,
            authority_scope_ref=payload.authority_scope_ref,
        )
        if typed_plan.plan_digest != successor_plan.plan_digest:
            return InterpreterFailure(
                code="LEGACY_PLAN_PARITY_MISMATCH",
                message=(
                    "legacy plan derivation diverges from the successor pure plan"
                ),
                retryable=False,
            )

        outcomes: list[c3.CollectElementOutcome] = []
        for element in typed_plan.elements:
            sub = replace(
                _legacy_request_from_snapshot(payload.request_snapshot),
                query_terms=list(element.query_terms),
                limit=element.per_batch_limit,
                source_context={
                    **dict(payload.request_snapshot.source_context),
                    "auto_batched_child": True,
                },
            )
            try:
                result = runner.run(sub)
            except Exception as exc:  # noqa: BLE001 - legacy runner boundary
                if typed_plan.failure_policy == "FAIL_FAST_WITH_PARTIAL_OBSERVATION":
                    error = c3.CollectElementError(
                        code="auto_batch_execution_failed",
                        message=str(exc) or exc.__class__.__name__,
                        query_terms=element.query_terms,
                        exception_type=exc.__class__.__name__,
                        error_digest="",
                    )
                    partial = tuple(
                        outcomes
                        + [
                            c3.CollectElementFailed(
                                schema_version=c3.COLLECT_ELEMENT_OUTCOME_SCHEMA_REF,
                                element_id=element.element_id,
                                input_index=element.input_index,
                                error=error,
                                counts=c3.CollectCounts(),
                                links=(),
                                receipt=None,
                                legacy_observation_ref=("legacy:" + error.error_digest),
                                outcome_digest="",
                            )
                        ]
                    )
                    return InterpreterSuccess(
                        c3.OrderedTraversalAborted(
                            schema_version=(
                                "mrw.successor.collect.c3.traversal-result.v1"
                            ),
                            partial_outcomes=partial,
                            cause=error,
                            cancellation_observed=True,
                            request_ref=payload.parent_request_ref,
                        )
                    )
                result = type(
                    "LegacyFailedResult",
                    (),
                    {
                        "status": "failed",
                        "inserted": 0,
                        "updated": 0,
                        "skipped": 0,
                        "errors": [
                            {
                                "code": "auto_batch_execution_failed",
                                "message": str(exc) or exc.__class__.__name__,
                                "exception_type": exc.__class__.__name__,
                            }
                        ],
                        "meta": {"raw": {}},
                        "provider_job_id": None,
                        "provider_type": None,
                        "provider_status": None,
                        "attempt_count": None,
                    },
                )()
            raw_digest = content_digest(
                {
                    "schema": "mrw.successor.collect.c3.legacy-result-raw.v1",
                    "query_terms": list(element.query_terms),
                    "result": dict(
                        (getattr(result, "meta", None) or {}).get("raw") or {}
                    ),
                }
            )
            outcomes.append(
                _outcome_from_legacy_result(
                    element=element,
                    terms=list(element.query_terms),
                    result=result,
                    raw_digest=raw_digest,
                )
            )

        self.resolves += 1
        ordered = tuple(sorted(outcomes, key=lambda item: item.input_index))
        observation = c3.CollectTraversalObservation(
            schema_version=c3.COLLECT_TRAVERSAL_OBSERVATION_SCHEMA_REF,
            observation_profile=c3.COLLECT_TRAVERSAL_OBSERVATION_PROFILE,
            request_ref=payload.parent_request_ref,
            traversal_policy="MATERIALIZED_SHAPE",
            failure_policy=typed_plan.failure_policy,
            ordered_outcomes=ordered,
            requested_parallelism=typed_plan.requested_parallelism,
            effective_parallelism=typed_plan.effective_parallelism,
            cancellation_observed=False,
            observation_digest="",
        )
        if len(ordered) <= 1:
            return InterpreterSuccess(
                c3.CollectTraversalSingleton(
                    schema_version="mrw.successor.collect.c3.traversal-result.v1",
                    observation=observation,
                )
            )
        return InterpreterSuccess(
            c3.OrderedTraversalCompleted(
                schema_version="mrw.successor.collect.c3.traversal-result.v1",
                observation=observation,
            )
        )


class LegacyCollectResultFoldAdapter:
    """Legacy sibling interpreter for the C3.2 ordered result fold."""

    interpreter_id = COLLECT_C3_2_LEGACY_INTERPRETER_ID

    def __init__(self) -> None:
        self.folds = 0

    def fold(
        self,
        payload: c3.CollectFoldPayload,
        *,
        program: Any,
        plan: Any,
        contract_ref: Any,
        payload_ref: Any,
        project_scope: Any,
        catalog: Any,
        deployment_catalog_digest: str,
        binding: Any,
        expected_interpreter_profile_digest: str | None = None,
    ) -> Any:
        try:
            require_exact_collect_binding(
                program=program,
                plan=plan,
                contract_ref=contract_ref,
                payload_ref=payload_ref,
                payload=payload,
                project_scope=project_scope,
                catalog=catalog,
                deployment_catalog_digest=deployment_catalog_digest,
                binding=binding,
                expected_interpreter_profile_digest=(
                    expected_interpreter_profile_digest
                    or legacy_interpreter_profile_digest_c3_2()
                ),
            )
        except CollectBindingMismatch as exc:
            return InterpreterFailure(
                code="ASSIGNMENT_BINDING_MISMATCH",
                message=str(exc),
                retryable=False,
            )

        from app.services.collect_runtime.runtime import _merge_collect_results

        legacy_request = _legacy_request_from_snapshot(
            c3.CollectLegacyRequestSnapshot(
                schema_version=c3.COLLECT_REQUEST_SNAPSHOT_SCHEMA_REF,
                flow="collect",
                channel=payload.parent_request_ref.channel,
                project_key=payload.parent_request_ref.project_key,
                query_terms=(),
                urls=(),
                limit=None,
                options=c3.freeze_json_object({}),
                source_context=c3.freeze_json_object({}),
                snapshot_digest="",
            )
        )
        batch_results: list[tuple[list[str], Any]] = []
        for outcome in payload.ordered_outcomes.outcomes:
            terms = list(outcome_terms(outcome))
            result = _legacy_result_for_outcome(outcome)
            batch_results.append((terms, result))
        merged = _merge_collect_results(legacy_request, batch_results)
        self.folds += 1

        successor_aggregate = c3.fold_ordered_results(
            payload.ordered_outcomes,
            aggregation_policy_ref=payload.aggregation_policy_ref,
            observation_profile_ref=payload.observation_profile_ref,
        )
        if isinstance(successor_aggregate, c3.CollectFoldContractFailure):
            return InterpreterSuccess(successor_aggregate)

        legacy_counts = (
            int(merged.inserted or 0),
            int(merged.updated or 0),
            int(merged.skipped or 0),
        )
        typed_counts = (
            successor_aggregate.aggregate_counts.inserted,
            successor_aggregate.aggregate_counts.updated,
            successor_aggregate.aggregate_counts.skipped,
        )
        raw = dict((merged.meta or {}).get("raw") or {})
        legacy_links = tuple(str(link) for link in (raw.get("links") or []))
        if legacy_counts != typed_counts or legacy_links != successor_aggregate.links:
            return InterpreterSuccess(
                c3.CollectFoldContractFailure(
                    schema_version=c3.COLLECT_AGGREGATE_OUTCOME_SCHEMA_REF,
                    reason="legacy fold parity mismatch",
                    unconsumed_outcomes=payload.ordered_outcomes,
                    aggregate_digest="",
                )
            )
        return InterpreterSuccess(successor_aggregate)


def outcome_terms(outcome: c3.CollectElementOutcome) -> tuple[str, ...]:
    """Return the element terms carried by a typed outcome."""

    return getattr(outcome, "query_terms", ()) or ()


def _legacy_result_for_outcome(outcome: c3.CollectElementOutcome) -> Any:
    from app.services.collect_runtime.contracts import CollectResult

    failed = isinstance(outcome, c3.CollectElementFailed)
    errors: list[dict[str, Any]] = []
    if failed and outcome.error is not None:
        errors = [
            {
                "code": outcome.error.code,
                "message": outcome.error.message,
                "query_terms": list(outcome.error.query_terms),
                "exception_type": outcome.error.exception_type,
            }
        ]
    meta_raw: dict[str, Any] = {}
    if outcome.links:
        meta_raw["links"] = list(outcome.links)
    receipt = outcome.receipt
    return CollectResult(
        flow="collect",
        channel="",
        status="failed" if failed else "completed",
        inserted=outcome.counts.inserted,
        updated=outcome.counts.updated,
        skipped=outcome.counts.skipped,
        errors=errors,
        meta={"raw": meta_raw},
        provider_job_id=None if receipt is None else receipt.provider_job_id,
        provider_type=None if receipt is None else receipt.provider_type,
        provider_status=None if receipt is None else receipt.provider_status,
        attempt_count=None if receipt is None else receipt.attempt_count,
    )


def build_legacy_collect_c3_1_binding(
    *,
    contract_digest: str,
    deployment_catalog_digest: str,
    project_scope_digest: str,
    resource_policy_epoch: int = 1,
    runtime_protocol_version: str = "mrw.runtime.protocol.v1",
) -> InterpreterBinding:
    return InterpreterBinding.from_content(
        operation_contract_digest=contract_digest,
        interpreter_profile_digest=legacy_interpreter_profile_digest_c3_1(),
        deployment_catalog_digest=deployment_catalog_digest,
        runtime_protocol_version=runtime_protocol_version,
        project_scope_digest=project_scope_digest,
        resource_policy_epoch=resource_policy_epoch,
        authority_requirement_digest=authority_requirement_digest(),
    )


def build_successor_collect_c3_1_binding(
    *,
    contract_digest: str,
    deployment_catalog_digest: str,
    project_scope_digest: str,
    resource_policy_epoch: int = 1,
    runtime_protocol_version: str = "mrw.runtime.protocol.v1",
) -> InterpreterBinding:
    return InterpreterBinding.from_content(
        operation_contract_digest=contract_digest,
        interpreter_profile_digest=successor_interpreter_profile_digest_c3_1(),
        deployment_catalog_digest=deployment_catalog_digest,
        runtime_protocol_version=runtime_protocol_version,
        project_scope_digest=project_scope_digest,
        resource_policy_epoch=resource_policy_epoch,
        authority_requirement_digest=authority_requirement_digest(),
    )


def build_legacy_collect_c3_2_binding(
    *,
    contract_digest: str,
    deployment_catalog_digest: str,
    project_scope_digest: str,
    resource_policy_epoch: int = 1,
    runtime_protocol_version: str = "mrw.runtime.protocol.v1",
) -> InterpreterBinding:
    return InterpreterBinding.from_content(
        operation_contract_digest=contract_digest,
        interpreter_profile_digest=legacy_interpreter_profile_digest_c3_2(),
        deployment_catalog_digest=deployment_catalog_digest,
        runtime_protocol_version=runtime_protocol_version,
        project_scope_digest=project_scope_digest,
        resource_policy_epoch=resource_policy_epoch,
        authority_requirement_digest=authority_requirement_digest(),
    )


def build_successor_collect_c3_2_binding(
    *,
    contract_digest: str,
    deployment_catalog_digest: str,
    project_scope_digest: str,
    resource_policy_epoch: int = 1,
    runtime_protocol_version: str = "mrw.runtime.protocol.v1",
) -> InterpreterBinding:
    return InterpreterBinding.from_content(
        operation_contract_digest=contract_digest,
        interpreter_profile_digest=successor_interpreter_profile_digest_c3_2(),
        deployment_catalog_digest=deployment_catalog_digest,
        runtime_protocol_version=runtime_protocol_version,
        project_scope_digest=project_scope_digest,
        resource_policy_epoch=resource_policy_epoch,
        authority_requirement_digest=authority_requirement_digest(),
    )


def bindings_are_distinct(
    legacy: InterpreterBinding, successor: InterpreterBinding
) -> bool:
    return (
        legacy.interpreter_profile_digest != successor.interpreter_profile_digest
        and legacy.binding_digest != successor.binding_digest
    )


COLLECT_C3_COMPOSED_LEGACY_INTERPRETER_ID = "legacy.collect_runtime.composed_shadow.v1"


@dataclass(frozen=True, slots=True)
class LegacyComposedShadowObservation:
    """Deterministic legacy shadow over the same composed Program/Plan."""

    program_digest: str
    plan_digest: str
    legacy_binding_digest: str
    aggregate_digest: str
    element_count: int
    provider_calls: int = 0
    shadow_digest: str = ""

    def __post_init__(self) -> None:
        if self.shadow_digest == "":
            object.__setattr__(
                self,
                "shadow_digest",
                content_digest(
                    {
                        "schema": (
                            "mrw.successor.collect.c3.legacy-composed-shadow.v1"
                        ),
                        "program_digest": self.program_digest,
                        "plan_digest": self.plan_digest,
                        "legacy_binding_digest": self.legacy_binding_digest,
                        "aggregate_digest": self.aggregate_digest,
                        "element_count": self.element_count,
                        "provider_calls": self.provider_calls,
                    }
                ),
            )


class LegacyComposedCollectInterpreter:
    """Legacy composed shadow for the same TraverseOrdered->MapOutput->Fold epoch.

    Validates the exact composed Program/Plan/binding, consumes captured
    element fixtures/receipts through the deterministic no-provider runner,
    folds through the legacy ``_merge_collect_results`` path, and projects the
    aggregate observation for parity with the successor interpreter.
    """

    interpreter_id = COLLECT_C3_COMPOSED_LEGACY_INTERPRETER_ID

    def interpret(
        self,
        *,
        program: Any,
        plan: Any,
        catalog: Any,
        binding: Any,
        element_payloads: tuple[Any, ...],
        receipts: tuple[Any, ...] = (),
        assignment: Any | None = None,
    ) -> Any:
        from app.successor_runtime.capabilities.checksum import require_hex64

        try:
            require_hex64(binding.binding_digest, "legacy composed binding digest")
        except ValueError as exc:
            return InterpreterFailure(
                code="ASSIGNMENT_BINDING_MISMATCH",
                message=str(exc),
                retryable=False,
            )
        if binding.interpreter_profile_digest != (
            legacy_interpreter_profile_digest_c3_2()
        ):
            return InterpreterFailure(
                code="ASSIGNMENT_BINDING_MISMATCH",
                message="legacy composed binding is not the C3.2 fold profile",
                retryable=False,
            )
        try:
            require_exact_composed_binding(
                program=program,
                plan=plan,
                catalog=catalog,
                assignment=assignment,
            )
        except CollectBindingMismatch as exc:
            return InterpreterFailure(
                code="ASSIGNMENT_BINDING_MISMATCH",
                message=str(exc),
                retryable=False,
            )
        if not element_payloads:
            return InterpreterFailure(
                code="INVALID_INPUT",
                message="legacy composed shadow requires element payloads",
                retryable=False,
            )
        first_payload = element_payloads[0]
        family_plan = c3.build_collect_batch_plan(
            request_ref=first_payload.parent_request_ref,
            snapshot=first_payload.request_snapshot,
            plan_id=f"shadow:{program.program_id}",
            resource_policy=first_payload.resource_policy,
            authority_scope_ref=first_payload.authority_scope_ref,
        )
        traversal = run_ordered_traversal(
            family_plan,
            deterministic_composed_element_runner(receipts),
        )
        observation = getattr(traversal, "observation", None)
        if observation is None:
            return InterpreterFailure(
                code="ORDERED_TRAVERSAL_ABORTED",
                message="legacy composed shadow traversal aborted",
                retryable=False,
            )
        sequence = c3.OrderedCollectElementOutcomeSequence(
            schema_version="mrw.successor.collect.c3.outcome-sequence.v1",
            parent_request_ref=first_payload.parent_request_ref,
            outcomes=observation.ordered_outcomes,
            sequence_digest="",
        )
        typed = c3.fold_ordered_results(
            sequence,
            aggregation_policy_ref=c3.COLLECT_AGGREGATION_POLICY_ACCUMULATE_REF,
            observation_profile_ref=c3.COLLECT_FOLD_OBSERVATION_PROFILE,
        )
        if isinstance(typed, c3.CollectFoldContractFailure):
            return InterpreterFailure(
                code="FOLD_CONTRACT_FAILURE",
                message=typed.reason,
                retryable=False,
            )

        from app.services.collect_runtime.runtime import _merge_collect_results

        legacy_request = _legacy_request_from_snapshot(first_payload.request_snapshot)
        batch_results = [
            (list(outcome_terms(outcome)), _legacy_result_for_outcome(outcome))
            for outcome in observation.ordered_outcomes
        ]
        merged = _merge_collect_results(legacy_request, batch_results)
        legacy_counts = (
            int(merged.inserted or 0),
            int(merged.updated or 0),
            int(merged.skipped or 0),
        )
        raw = dict((merged.meta or {}).get("raw") or {})
        legacy_links = tuple(str(link) for link in (raw.get("links") or []))
        if (
            legacy_counts
            != (
                typed.aggregate_counts.inserted,
                typed.aggregate_counts.updated,
                typed.aggregate_counts.skipped,
            )
            or legacy_links != typed.links
        ):
            return InterpreterFailure(
                code="LEGACY_COMPOSED_FOLD_PARITY_MISMATCH",
                message="legacy merge diverges from the typed composed fold",
                retryable=False,
            )
        return InterpreterSuccess(
            LegacyComposedShadowObservation(
                program_digest=program.program_digest,
                plan_digest=plan.plan_digest,
                legacy_binding_digest=binding.binding_digest,
                aggregate_digest=typed.aggregate_digest,
                element_count=len(sequence.outcomes),
                provider_calls=0,
                shadow_digest="",
            )
        )
