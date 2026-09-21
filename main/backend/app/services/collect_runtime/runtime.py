from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from contextvars import copy_context
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from math import ceil
from collections.abc import Mapping
from typing import Any, NoReturn

from functorial_kit import Failure
from mrw_functorial_kit.core.provider_port_failures import collect_runtime_failures
from .contracts import CollectAdapter, CollectRequest, CollectResult, FLOW_SOURCE_COLLECT
from ..agent_batch.task_contract import parse_source_library_runtime_params


_AUTO_BATCH_CHANNELS = {"search.market", "search.policy"}
_DEFAULT_AUTO_BATCH_PARALLELISM = 1

_SKILL_REGISTRY: dict[str, CollectAdapter] = {}
_SOURCE_LIBRARY_COMPAT_PROJECTOR: Any | None = None
_SUCCESSOR_EFFECT_GATEWAY: Any | None = None


def _collect_contract_failure(code: str, message: str, *, site: str) -> Failure:
    return collect_runtime_failures.fail(
        code,
        message,
        {"operation": "collect.runtime", "site": site},
    )


def _raise_collect_contract(failure: Failure, exception_type: type[Exception] = ValueError) -> NoReturn:
    # kit:boundary owner=collect.runtime.contract_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=collect.runtime.failure witness=test:test_w03_collect_contract_failures
    raise exception_type(failure.message)


def register_collect_skill(skill_id: str, adapter: CollectAdapter) -> None:
    sid = str(skill_id or "").strip()
    if not sid:
        _raise_collect_contract(
            _collect_contract_failure("skill_id_required", "skill_id is required", site="register_collect_skill.skill_id")
        )
    if not callable(getattr(adapter, "run", None)):
        _raise_collect_contract(
            _collect_contract_failure(
                "collect_adapter_contract_invalid",
                "collect adapter must provide run(request)",
                site="register_collect_skill.adapter",
            ),
            TypeError,
        )
    _SKILL_REGISTRY[sid] = adapter


def list_collect_skills() -> list[str]:
    return sorted(_SKILL_REGISTRY.keys())


def register_collect_adapters(adapters: Mapping[str, CollectAdapter]) -> None:
    """Register a complete adapter set without importing concrete adapters."""

    for channel, adapter in adapters.items():
        register_collect_skill(str(channel), adapter)
        register_collect_skill(f"collect.{channel}", adapter)
        register_collect_skill(f"skill.collect.{channel}", adapter)


def reset_collect_adapters() -> None:
    """Reset process-local adapter registration; intended for composition tests."""

    _SKILL_REGISTRY.clear()


def register_source_library_compat_projector(projector: Any) -> None:
    """Inject the legacy source-library response projection at composition time."""

    global _SOURCE_LIBRARY_COMPAT_PROJECTOR
    if not callable(projector):
        _raise_collect_contract(
            _collect_contract_failure(
                "compat_projector_contract_invalid",
                "source-library compatibility projector must be callable",
                site="register_source_library_compat_projector.projector",
            ),
            TypeError,
        )
    _SOURCE_LIBRARY_COMPAT_PROJECTOR = projector


def register_successor_collect_effect_gateway(gateway: Any) -> None:
    """Inject the effectful successor gateway; it is separate from legacy adapters."""

    global _SUCCESSOR_EFFECT_GATEWAY
    if not callable(gateway):
        _raise_collect_contract(
            _collect_contract_failure(
                "successor_effect_gateway_invalid",
                "successor collect effect gateway must be callable",
                site="register_successor_collect_effect_gateway.gateway",
            ),
            TypeError,
        )
    _SUCCESSOR_EFFECT_GATEWAY = gateway


def reset_successor_collect_effect_gateway() -> None:
    global _SUCCESSOR_EFFECT_GATEWAY

    _SUCCESSOR_EFFECT_GATEWAY = None


def _resolve_collect_adapter(channel: str) -> CollectAdapter | None:
    candidates = [
        str(channel or "").strip(),
        f"collect.{str(channel or '').strip()}",
        f"skill.collect.{str(channel or '').strip()}",
    ]
    for key in candidates:
        if key and key in _SKILL_REGISTRY:
            return _SKILL_REGISTRY[key]
    return None

# Environment-driven workflow boundary switch.
# - INGEST_WORKFLOW_ADAPTER: off|legacy -> legacy path (default)
# - INGEST_WORKFLOW_ADAPTER: on|workflow|canary -> use WorkflowRoutingAdapter boundary
# Read env directly (no settings dependency) and keep return types unchanged.
def _resolve_workflow_mode() -> str:
    # Local import for unit-safety and to avoid global side effects.
    import os  # unit-safe import

    raw = str(os.environ.get("INGEST_WORKFLOW_ADAPTER", "off") or "off").strip().lower()
    if raw in {"on", "workflow", "canary"}:
        return "workflow"
    # Treat anything else as legacy for safe rollback.
    return "legacy"


class WorkflowRoutingAdapter:
    """Adapter boundary for workflow-based routing.

    Thin indirection that preserves existing adapter return semantics while
    allowing future orchestration (Temporal/Dagster/etc.) behind an env switch.
    """

    def run(self, request: CollectRequest) -> CollectResult:
        adapter = _resolve_collect_adapter(request.channel)
        if adapter is None:
            _raise_collect_contract(
                _collect_contract_failure(
                    "collect_channel_unsupported",
                    f"unsupported collect channel: {request.channel}",
                    site="workflow_routing_adapter.channel",
                )
            )
        # Delegate to existing channel adapter. Keep result types and display_meta.
        return adapter.run(request)


def run_collect(request: CollectRequest) -> CollectResult:
    """Runtime entry.

    Routes to legacy adapter path or the workflow boundary based on
    INGEST_WORKFLOW_ADAPTER. Defaults to legacy for safe rollback.
    Auto-batch behavior and display_meta building are preserved.
    """
    successor_mode = _resolve_successor_collect_mode()
    if successor_mode in {"on", "canary"}:
        successor_result = _run_successor_collect(request)
        if successor_result is not None:
            return successor_result
        # Explicit successor mode never silently falls back to the legacy
        # registry for an ineligible/non-C3 request.
        from .successor_bridge import outcome_unknown_result

        return outcome_unknown_result(request)
    elif _successor_switch_configured():
        # An explicit off/legacy value is the rollback authority and must not
        # be shadowed by the older workflow switch.
        batched = _maybe_run_auto_batched(request)
        if batched is not None:
            return batched
        return _run_collect_no_batch(request)

    mode = _resolve_workflow_mode()

    if mode == "legacy":
        # Legacy path (default): existing auto-batch + direct adapter dispatch.
        batched = _maybe_run_auto_batched(request)
        if batched is not None:
            return batched
        return _run_collect_no_batch(request)

    # Workflow boundary path: reuse the same batching rules, but delegate each
    # execution to WorkflowRoutingAdapter. Return types remain CollectResult.
    wr = WorkflowRoutingAdapter()
    batch_result = _run_auto_batch(request, wr.run)
    if batch_result is not None:
        return batch_result

    # No auto-batch; single-run through workflow boundary.
    return wr.run(request)


def _resolve_successor_collect_mode() -> str:
    """Resolve the explicit successor switch; unknown values fail closed."""

    import os

    raw = os.environ.get("SUCCESSOR_RUNTIME_COLLECT")
    if raw is None:
        return "legacy"
    try:
        from app.successor_runtime.capabilities.collect_c3 import collect_runtime_mode

        return collect_runtime_mode(raw)
    except Exception:
        return "legacy"


def _successor_switch_configured() -> bool:
    import os

    return "SUCCESSOR_RUNTIME_COLLECT" in os.environ


@dataclass(frozen=True, slots=True)
class _CollectProjectScope:
    project_key: str
    registry_revision: int
    scope_digest: str


def _successor_request_id(request: CollectRequest) -> str:
    from app.successor_runtime.capabilities.checksum import content_digest

    return "collect:" + content_digest(
        {
            "flow": request.flow,
            "channel": request.channel,
            "project_key": request.project_key,
            "query_terms": list(request.query_terms or []),
            "urls": list(request.urls or []),
            "limit": request.limit,
            "provider": request.provider,
            "language": request.language,
            "scope": request.scope,
            "item_key": request.item_key,
            "options": dict(request.options or {}),
            "source_context": dict(request.source_context or {}),
        }
    )


def _successor_independence_is_explicit(request: CollectRequest) -> bool:
    options = request.options if isinstance(request.options, dict) else {}
    source_context = request.source_context if isinstance(request.source_context, dict) else {}
    raw = options.get(
        "batch_independence_policy",
        options.get(
            "independence_policy",
            source_context.get(
                "batch_independence_policy", source_context.get("independence_policy")
            ),
        ),
    )
    if isinstance(raw, bool):
        return raw
    return str(raw or "").strip().lower() in {
        "explicit",
        "independent",
        "disjoint_resources",
        "proven",
    }


def _successor_resource_policy(request: CollectRequest, c3: Any) -> Any:
    requested = _resolve_auto_batch_parallelism(request)
    if not _successor_independence_is_explicit(request):
        requested = 1
    options = request.options if isinstance(request.options, dict) else {}
    raw_deadline = options.get("deadline_seconds")
    try:
        deadline = None if raw_deadline is None else max(1, int(raw_deadline))
    except (TypeError, ValueError):
        deadline = None
    return c3.CollectResourcePolicy(
        schema_ref=c3.COLLECT_RESOURCE_POLICY_SCHEMA_REF,
        max_parallelism=max(1, requested),
        deadline_seconds=deadline,
        cancellation=("COORDINATED" if _resolve_auto_batch_fail_fast(request) else "NONE"),
        backpressure=True,
        provider_concurrency_key=f"{request.channel}:{request.provider or 'default'}",
        policy_digest="",
    )


def _collect_result_to_c3_outcome(result: CollectResult, element: Any, c3: Any) -> Any:
    from app.successor_runtime.capabilities.checksum import content_digest

    raw = dict((result.meta or {}).get("raw") or {})
    links = tuple(str(link).strip() for link in (raw.get("links") or []) if str(link).strip())
    terminal_readback = (result.meta or {}).get("terminal_readback") or raw.get("terminal_readback")
    terminal_readback_ok = (
        isinstance(terminal_readback, dict)
        and str(terminal_readback.get("kind") or "").strip().lower() == "terminal"
        and str(terminal_readback.get("status") or "").strip().lower()
        in {"completed", "complete", "succeeded"}
    )
    receipt = None
    if result.provider_job_id:
        provider_status = None if result.provider_status is None else str(result.provider_status)
        authoritative = terminal_readback_ok
        receipt = c3.CollectAttemptReceipt(
            schema_version=c3.COLLECT_ATTEMPT_RECEIPT_SCHEMA_REF,
            receipt_kind=("AUTHORITATIVE_READBACK" if authoritative else "DISPATCH_ACKNOWLEDGEMENT"),
            provider_type=str(result.provider_type or "unknown"),
            provider_job_id=str(result.provider_job_id),
            provider_status=provider_status,
            attempt_count=int(result.attempt_count or 0),
            observed_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            raw_digest=content_digest(raw),
            authoritative_readback=authoritative,
            receipt_digest="",
        )
    counts = c3.CollectCounts(
        inserted=int(result.inserted or 0),
        updated=int(result.updated or 0),
        skipped=int(result.skipped or 0),
    )
    legacy_ref = "legacy:" + content_digest({"element": element.element_id, "result": raw})
    if (
        str(result.status or "").strip().lower()
        in {"completed", "complete", "succeeded"}
        and terminal_readback_ok
    ):
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
    first_error = (result.errors or [{}])[0]
    if not terminal_readback_ok and not first_error.get("message"):
        first_error = {
            "code": "runner_unavailable",
            "message": "provider terminal readback is required for successor completion",
        }
    return c3.CollectElementFailed(
        schema_version=c3.COLLECT_ELEMENT_OUTCOME_SCHEMA_REF,
        element_id=element.element_id,
        input_index=element.input_index,
        error=c3.CollectElementError(
            code=(str(first_error.get("code") or "auto_batch_execution_failed") if str(first_error.get("code") or "") in c3.COLLECT_ELEMENT_ERROR_CODES else "auto_batch_execution_failed"),
            message=str(first_error.get("message") or result.status or "collect element failed"),
            query_terms=tuple(element.query_terms),
            exception_type=first_error.get("exception_type"),
            error_digest="",
        ),
        counts=counts,
        links=links,
        receipt=receipt,
        legacy_observation_ref=legacy_ref,
        outcome_digest="",
    )


def _run_successor_collect(request: CollectRequest) -> CollectResult | None:
    """Execute eligible search batches through the real typed C3 interpreters."""

    if request.channel not in _AUTO_BATCH_CHANNELS or not request.project_key or not _should_auto_batch(request):
        return None
    if _SUCCESSOR_EFFECT_GATEWAY is None:
        from .successor_bridge import outcome_unknown_result

        return outcome_unknown_result(request)
    from app.successor_runtime.capabilities import collect_c3 as c3
    from app.successor_runtime.capabilities import collect_c3_interpreters as ci
    from app.successor_runtime.capabilities import collect_c3_program as cp
    from app.successor_runtime.runtime.assignments import InterpreterBinding

    bundle = c3.build_collect_c3_bundle()
    catalog = c3.build_collect_c3_catalog(bundle)
    registry = c3.build_collect_c3_registry(bundle)
    request_ref = c3.build_collect_request_ref(
        request_id=_successor_request_id(request),
        project_key=str(request.project_key),
        channel=request.channel,
    )
    snapshot = c3.CollectLegacyRequestSnapshot(
        schema_version=c3.COLLECT_REQUEST_SNAPSHOT_SCHEMA_REF,
        flow=request.flow,
        channel=request.channel,
        project_key=request.project_key,
        query_terms=tuple(request.query_terms or ()),
        urls=tuple(request.urls or ()),
        limit=request.limit,
        options=c3.freeze_json_object(dict(request.options or {})),
        source_context=c3.freeze_json_object(dict(request.source_context or {})),
        snapshot_digest="",
    )
    policy = _successor_resource_policy(request, c3)
    plan = c3.build_collect_batch_plan(
        request_ref=request_ref,
        snapshot=snapshot,
        plan_id=f"successor:{request_ref.request_id}",
        resource_policy=policy,
        authority_scope_ref=f"project:{request.project_key}",
    )
    scope = _CollectProjectScope(
        project_key=str(request.project_key),
        registry_revision=1,
        scope_digest=c3.content_digest({"project_key": request.project_key, "revision": 1}),
    )

    class _BoundRunner:
        def run(self, element: Any) -> Any:
            payload = c3.CollectBatchElementPayload(
                schema_version=c3.COLLECT_C3_1_PAYLOAD_SCHEMA,
                operation_kind=c3.COLLECT_C3_1_KIND,
                parent_request_ref=request_ref,
                request_snapshot=snapshot,
                element=element,
                resource_policy=policy,
                authority_scope_ref=f"project:{request.project_key}",
                payload_digest="",
            )
            program_id = f"{plan.plan_id}:c3.1:{element.input_index}"
            program = cp.build_collect_c3_1_program(
                payload=payload,
                catalog=catalog,
                program_id=program_id,
                project_key=scope.project_key,
                project_registry_revision=scope.registry_revision,
                project_scope_digest=scope.scope_digest,
            )
            bound_plan = cp.compile_collect_c3_program(program, catalog, operation_contracts=registry)
            outcome = ci.CollectTraversalSuccessorInterpreter().interpret(
                program=program,
                plan=bound_plan,
                contract_ref=program.root.operation.contract_ref,
                payload_ref=program.root.operation.payload_ref,
                payload=payload,
                project_scope=scope,
                catalog=catalog,
                deployment_catalog_digest=c3.deployment_catalog_digest(),
                binding=InterpreterBinding.from_content(
                    operation_contract_digest=program.root.operation.contract_ref.contract_digest,
                    interpreter_profile_digest=ci.successor_interpreter_profile_digest_c3_1(),
                    deployment_catalog_digest=c3.deployment_catalog_digest(),
                    runtime_protocol_version="mrw.runtime.protocol.v1",
                    project_scope_digest=scope.scope_digest,
                    resource_policy_epoch=1,
                    authority_requirement_digest=ci.authority_requirement_digest(),
                ),
                runner=type(
                    "AdapterRunner",
                    (),
                    {
                        "run": lambda _self, e: _collect_result_to_c3_outcome(
                            _SUCCESSOR_EFFECT_GATEWAY(
                                replace(
                                    request,
                                    query_terms=list(e.query_terms),
                                    limit=e.per_batch_limit,
                                    source_context={
                                        **dict(request.source_context or {}),
                                        "auto_batched_child": True,
                                    },
                                )
                            ),
                            e,
                            c3,
                        )
                    },
                )(),
            )
            if isinstance(outcome, ci.InterpreterSuccess):
                return outcome.value
            return c3.CollectElementFailed(
                schema_version=c3.COLLECT_ELEMENT_OUTCOME_SCHEMA_REF,
                element_id=element.element_id,
                input_index=element.input_index,
                error=c3.CollectElementError(
                    code="auto_batch_execution_failed",
                    message=outcome.message,
                    query_terms=tuple(element.query_terms),
                    error_digest="",
                ),
                counts=c3.CollectCounts(),
                links=(),
                receipt=None,
                legacy_observation_ref="legacy:" + c3.content_digest({"element": element.element_id, "error": outcome.code}),
                outcome_digest="",
            )

    traversal = ci.run_ordered_traversal(plan, _BoundRunner())
    if isinstance(traversal, c3.OrderedTraversalAborted):
        ordered_outcomes = tuple(sorted(traversal.partial_outcomes, key=lambda item: item.input_index))
        cancelled = True
        cancellation = traversal.cancellation_receipt
    else:
        observation = getattr(traversal, "observation", None)
        if observation is None:
            return CollectResult(channel=request.channel, status="failed", errors=[{"code": "auto_batch_execution_failed", "message": "successor traversal produced no observation"}])
        ordered_outcomes = observation.ordered_outcomes
        cancelled = False
        cancellation = None
    sequence = c3.OrderedCollectElementOutcomeSequence(
        schema_version="mrw.successor.collect.c3.outcome-sequence.v1",
        parent_request_ref=request_ref,
        outcomes=ordered_outcomes,
        sequence_digest="",
    )
    fold_payload = c3.build_collect_fold_payload(parent_request_ref=request_ref, ordered_outcomes=sequence)
    fold_program = cp.build_collect_c3_2_program(
        payload=fold_payload,
        catalog=catalog,
        program_id=f"{plan.plan_id}:c3.2",
        project_key=scope.project_key,
        project_registry_revision=scope.registry_revision,
        project_scope_digest=scope.scope_digest,
    )
    fold_plan = cp.compile_collect_c3_program(fold_program, catalog, operation_contracts=registry)
    fold_result = ci.CollectFoldSuccessorInterpreter().interpret(
        program=fold_program,
        plan=fold_plan,
        contract_ref=fold_program.root.operation.contract_ref,
        payload_ref=fold_program.root.operation.payload_ref,
        payload=fold_payload,
        project_scope=scope,
        catalog=catalog,
        deployment_catalog_digest=c3.deployment_catalog_digest(),
        binding=InterpreterBinding.from_content(
            operation_contract_digest=fold_program.root.operation.contract_ref.contract_digest,
            interpreter_profile_digest=ci.successor_interpreter_profile_digest_c3_2(),
            deployment_catalog_digest=c3.deployment_catalog_digest(),
            runtime_protocol_version="mrw.runtime.protocol.v1",
            project_scope_digest=scope.scope_digest,
            resource_policy_epoch=1,
            authority_requirement_digest=ci.authority_requirement_digest(),
        ),
    )
    if not isinstance(fold_result, ci.InterpreterSuccess):
        return CollectResult(channel=request.channel, status="failed", errors=[{"code": "auto_batch_execution_failed", "message": fold_result.message}])
    aggregate = fold_result.value
    from .successor_bridge import project_successor_aggregate

    result = project_successor_aggregate(
        request,
        aggregate,
        sequence,
        plan,
        c3,
        cancellation=(cancellation if cancelled else None),
    )
    from .display_meta import build_display_meta

    result.display_meta = build_display_meta(request, result, summary=(request.source_context or {}).get("summary"))
    return result


def _should_auto_batch(request: CollectRequest) -> bool:
    if request.channel not in _AUTO_BATCH_CHANNELS:
        return False
    qn = len([x for x in (request.query_terms or []) if str(x).strip()])
    lim = int(request.limit or 0)
    return qn >= 6 or lim >= 60


def _split_query_terms(terms: list[str]) -> list[list[str]]:
    clean = [str(x).strip() for x in (terms or []) if str(x).strip()]
    if not clean:
        return [[]]
    chunk_size = 4 if len(clean) >= 8 else 5
    return [clean[i : i + chunk_size] for i in range(0, len(clean), chunk_size)]


def _merge_collect_results(parent_request: CollectRequest, batch_results: list[tuple[list[str], CollectResult]]) -> CollectResult:
    out = CollectResult(channel=parent_request.channel, status="completed")
    links_seen: set[str] = set()
    merged_links: list[str] = []
    raw_batches: list[dict[str, Any]] = []
    provider_types: set[str] = set()
    provider_statuses: list[str] = []
    provider_job_ids: list[str] = []
    provider_jobs_seen: set[str] = set()
    attempts_total = 0
    has_attempt_count = False
    batches_failed = 0
    for terms, cr in batch_results:
        out.inserted += int(cr.inserted or 0)
        out.updated += int(cr.updated or 0)
        out.skipped += int(cr.skipped or 0)
        out.errors.extend(cr.errors or [])
        if str(cr.status or "").lower() == "failed":
            batches_failed += 1
        raw = dict((cr.meta or {}).get("raw") or {})
        batch_meta: dict[str, Any] = {"query_terms": terms, "result": raw}
        if cr.provider_job_id:
            batch_meta["provider_job_id"] = cr.provider_job_id
        if cr.provider_type:
            batch_meta["provider_type"] = cr.provider_type
            provider_types.add(cr.provider_type)
        if cr.provider_status:
            batch_meta["provider_status"] = cr.provider_status
            provider_statuses.append(cr.provider_status)
        if cr.attempt_count is not None:
            batch_meta["attempt_count"] = int(cr.attempt_count)
            attempts_total += int(cr.attempt_count)
            has_attempt_count = True
        if cr.provider_job_id and cr.provider_job_id not in provider_jobs_seen:
            provider_jobs_seen.add(cr.provider_job_id)
            provider_job_ids.append(cr.provider_job_id)
        raw_batches.append(batch_meta)
        for link in (raw.get("links") or []):
            s = str(link or "").strip()
            if s and s not in links_seen:
                links_seen.add(s)
                merged_links.append(s)
    raw_merged = {
        "inserted": out.inserted,
        "updated": out.updated,
        "skipped": out.skipped,
        "errors": out.errors,
        "auto_batched": True,
        "batches_total": len(batch_results),
        "batches_completed": len(batch_results),
        "batches_failed": batches_failed,
        "batches_succeeded": max(0, len(batch_results) - batches_failed),
        "batch_results": raw_batches,
    }
    if merged_links:
        raw_merged["links"] = merged_links
    if provider_job_ids:
        raw_merged["provider_job_ids"] = provider_job_ids
    if provider_types:
        raw_merged["provider_types"] = sorted(provider_types)
    if provider_statuses:
        raw_merged["provider_statuses"] = provider_statuses
    if has_attempt_count:
        raw_merged["attempt_count_total"] = attempts_total
    out.meta = {
        "raw": raw_merged,
        "auto_batched": True,
        "batches_total": len(batch_results),
        "batches_failed": batches_failed,
        "batches_succeeded": max(0, len(batch_results) - batches_failed),
        "query_term_batches": [terms for terms, _ in batch_results],
    }
    # Adapter-specific summary stays same; display_meta builder will fill standard stats.
    from .display_meta import build_display_meta
    summary = (parent_request.source_context or {}).get("summary")
    if len(provider_job_ids) == 1:
        out.provider_job_id = provider_job_ids[0]
    if len(provider_types) == 1:
        out.provider_type = next(iter(provider_types))
    if provider_statuses:
        unique_statuses = set(provider_statuses)
        out.provider_status = provider_statuses[0] if len(unique_statuses) == 1 else "mixed"
    if has_attempt_count:
        out.attempt_count = attempts_total
    out.display_meta = build_display_meta(parent_request, out, summary=summary)
    return out


def _run_collect_no_batch(request: CollectRequest) -> CollectResult:
    adapter = _resolve_collect_adapter(request.channel)
    if adapter is None:
        _raise_collect_contract(
            _collect_contract_failure(
                "collect_channel_unsupported",
                f"unsupported collect channel: {request.channel}",
                site="run_collect.channel",
            )
        )
    return adapter.run(request)


def _maybe_run_auto_batched(request: CollectRequest) -> CollectResult | None:
    return _run_auto_batch(request, _run_collect_no_batch)


def _run_auto_batch(
    request: CollectRequest,
    runner: Any,
) -> CollectResult | None:
    if not _should_auto_batch(request):
        return None
    term_batches = _split_query_terms(request.query_terms)
    if len(term_batches) <= 1:
        return None
    per_batch_limit = max(10, int(ceil(max(1, int(request.limit or 20)) / len(term_batches))))
    fail_fast = _resolve_auto_batch_fail_fast(request)
    max_workers = min(len(term_batches), _resolve_auto_batch_parallelism(request))
    batch_results = _execute_auto_batch(request, term_batches, per_batch_limit, runner, max_workers=max_workers, fail_fast=fail_fast)
    merged = _merge_collect_results(request, batch_results)
    merged.meta = {
        **(merged.meta or {}),
        "batch_parallelism": max_workers,
        "batch_parallelism_requested": _resolve_auto_batch_parallelism(request),
        "batch_fail_fast": fail_fast,
    }
    raw_meta = dict((merged.meta or {}).get("raw") or {})
    raw_meta.update(
        {
            "batch_parallelism": max_workers,
            "batch_parallelism_requested": _resolve_auto_batch_parallelism(request),
            "batch_fail_fast": fail_fast,
        }
    )
    merged.meta["raw"] = raw_meta
    return merged


def _execute_auto_batch(
    request: CollectRequest,
    term_batches: list[list[str]],
    per_batch_limit: int,
    runner: Any,
    *,
    max_workers: int,
    fail_fast: bool,
) -> list[tuple[list[str], CollectResult]]:
    indexed_results: list[tuple[int, list[str], CollectResult]] = []
    if max_workers <= 1:
        for idx, terms in enumerate(term_batches):
            indexed_results.append((idx, terms, _run_single_auto_batch(request, terms, per_batch_limit, runner, fail_fast=fail_fast)))
        return [(terms, result) for idx, terms, result in sorted(indexed_results, key=lambda item: item[0])]

    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="collect-auto-batch") as executor:
        future_map = {
            executor.submit(copy_context().run, _run_single_auto_batch, request, terms, per_batch_limit, runner, fail_fast): (idx, terms)
            for idx, terms in enumerate(term_batches)
        }
        for future in as_completed(future_map):
            idx, terms = future_map[future]
            indexed_results.append((idx, terms, future.result()))
    return [(terms, result) for idx, terms, result in sorted(indexed_results, key=lambda item: item[0])]


def _run_single_auto_batch(
    request: CollectRequest,
    terms: list[str],
    per_batch_limit: int,
    runner: Any,
    fail_fast: bool = False,
) -> CollectResult:
    sub = replace(
        request,
        query_terms=terms,
        limit=per_batch_limit,
        source_context={**(request.source_context or {}), "auto_batched_child": True},
    )
    try:
        return runner(sub)
    except Exception as exc:
        if fail_fast:
            # kit:boundary owner=collect.runtime.auto_batch class=SHELL_BOUNDARY_EXCEPTION failure_family=collect.runtime.failure witness=test:test_w03_effect_boundaries
            raise
        return CollectResult(
            channel=request.channel,
            status="failed",
            errors=[
                {
                    "code": "auto_batch_execution_failed",
                    "message": str(exc) or exc.__class__.__name__,
                    "query_terms": list(terms),
                }
            ],
            meta={
                "raw": {
                    "auto_batched": True,
                    "query_terms": list(terms),
                    "exception_type": exc.__class__.__name__,
                    "failed": True,
                }
            },
        )


def _resolve_auto_batch_parallelism(request: CollectRequest) -> int:
    options = request.options if isinstance(request.options, dict) else {}
    source_context = request.source_context if isinstance(request.source_context, dict) else {}
    raw = options.get("batch_parallelism", source_context.get("batch_parallelism", _DEFAULT_AUTO_BATCH_PARALLELISM))
    try:
        return max(1, int(raw))
    except Exception:
        return _DEFAULT_AUTO_BATCH_PARALLELISM


def _resolve_auto_batch_fail_fast(request: CollectRequest) -> bool:
    options = request.options if isinstance(request.options, dict) else {}
    source_context = request.source_context if isinstance(request.source_context, dict) else {}
    raw = options.get("batch_fail_fast", source_context.get("batch_fail_fast", False))
    if isinstance(raw, bool):
        return raw
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


def normalize_query_terms(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    s = str(value).strip()
    return [s] if s else []


def normalize_urls(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for x in value:
        s = str(x or "").strip()
        if s.startswith(("http://", "https://")):
            out.append(s)
    return out


def normalize_limit(value: Any, default: int | None = None) -> int | None:
    if value is None:
        return default
    try:
        return max(1, int(value))
    except Exception:
        return default


def normalize_language(value: Any) -> str | None:
    s = str(value or "").strip().lower()
    return s or None


def normalize_provider(value: Any) -> str | None:
    s = str(value or "").strip().lower()
    return s or None


def collect_request_from_market_api(*, query_terms: list[str], max_items: int, project_key: str | None, provider: str | None = None, language: str | None = None, start_offset: int | None = None, days_back: int | None = None, enable_extraction: bool = True) -> CollectRequest:
    return CollectRequest(
        channel="search.market",
        project_key=project_key,
        query_terms=normalize_query_terms(query_terms),
        limit=normalize_limit(max_items, 20),
        provider=normalize_provider(provider),
        language=normalize_language(language) or "en",
        options={"start_offset": start_offset, "days_back": days_back, "enable_extraction": enable_extraction},
        source_context={"summary": "市场信息采集"},
    )


def collect_request_from_policy_api(*, query_terms: list[str], max_items: int, project_key: str | None, provider: str | None = None, language: str | None = None, start_offset: int | None = None, days_back: int | None = None, enable_extraction: bool = True) -> CollectRequest:
    return CollectRequest(
        channel="search.policy",
        project_key=project_key,
        query_terms=normalize_query_terms(query_terms),
        limit=normalize_limit(max_items, 20),
        provider=normalize_provider(provider),
        language=normalize_language(language) or "en",
        options={"start_offset": start_offset, "days_back": days_back, "enable_extraction": enable_extraction},
        source_context={"summary": "法规来源"},
    )


def collect_request_from_source_library_api(*, item_key: str, project_key: str | None, override_params: dict | None = None) -> CollectRequest:
    parsed = parse_source_library_runtime_params(override_params)
    return CollectRequest(
        flow=FLOW_SOURCE_COLLECT,
        channel="source_library",
        project_key=project_key,
        item_key=str(item_key or "").strip() or None,
        query_terms=list(parsed.get("query_terms") or []),
        urls=list(parsed.get("urls") or []),
        limit=parsed.get("limit"),
        provider=parsed.get("provider"),
        language=parsed.get("language"),
        scope=parsed.get("scope"),
        platforms=parsed.get("platforms"),
        options={"override_params": dict(parsed.get("override_params") or {})},
        source_context={"summary": f"执行来源项 {item_key}"},
    )


def collect_request_from_url_pool(
    *,
    project_key: str | None,
    urls: list[str] | None = None,
    scope: str | None = None,
    limit: int | None = None,
    source_filter: str | None = None,
    domain: str | None = None,
    query_terms: list[str] | None = None,
    options: dict[str, Any] | None = None,
) -> CollectRequest:
    extra_options = dict(options or {})
    if source_filter is not None:
        extra_options["source_filter"] = source_filter
    if domain is not None:
        extra_options["domain"] = domain
    return CollectRequest(
        channel="url_pool",
        project_key=project_key,
        urls=normalize_urls(urls or []),
        query_terms=normalize_query_terms(query_terms or []),
        scope=(str(scope).strip() if scope else None),
        limit=normalize_limit(limit, 50),
        options=extra_options,
        source_context={"summary": "URL 池抓取并写入文档"},
    )


def run_source_library_item_compat(
    *,
    item_key: str,
    project_key: str | None = None,
    override_params: dict | None = None,
) -> dict:
    request = collect_request_from_source_library_api(
        item_key=item_key,
        project_key=project_key,
        override_params=override_params,
    )
    result = run_collect(request)
    if _SOURCE_LIBRARY_COMPAT_PROJECTOR is None:
        # kit:boundary owner=collect.runtime.compat_projector class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w03_collect_programmer_defect_boundary
        raise RuntimeError("source-library compatibility projector is not configured")
    response = _SOURCE_LIBRARY_COMPAT_PROJECTOR(result)
    if isinstance(response, dict):
        response.setdefault("display_meta", result.display_meta)
    return response
