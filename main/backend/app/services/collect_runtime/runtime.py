from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, NoReturn

from functorial_kit import Failure

from mrw_functorial_kit.core.provider_port_failures import collect_runtime_failures

from ..agent_batch.task_contract import parse_source_library_runtime_params

from .contracts import (
    FLOW_SOURCE_COLLECT,
    CollectAdapter,
    CollectEffectGateway,
    CollectRequest,
    CollectResult,
    SourceLibraryCompatResponse,
    SourceLibraryCompatProjector,
)
from .delivery import DeliveryObservation, observe_delivery, resource_compatibility
from .successor_bridge import outcome_unknown_result

_SKILL_REGISTRY: dict[str, CollectAdapter] = {}
_SOURCE_LIBRARY_COMPAT_PROJECTOR: SourceLibraryCompatProjector | None = None
_SUCCESSOR_EFFECT_GATEWAY: CollectEffectGateway | None = None


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


def register_source_library_compat_projector(projector: SourceLibraryCompatProjector) -> None:
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


def register_successor_collect_effect_gateway(gateway: CollectEffectGateway) -> None:
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



def run_collect(request: CollectRequest) -> CollectResult:
    """Dispatch every collect through the one typed adapter-effect gateway."""

    batched = _run_successor_collect(request)
    if batched is not None:
        return _attach_delivery_observation(batched)
    return _run_collect_no_batch(request)


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


def _successor_resource_policy(request: CollectRequest, acquisition: Any) -> Any:
    # C3 has a provider key but no write scopes or capacity ledger. A caller's
    # independence hint cannot establish that two effects are compatible.
    provider_key = f"{request.channel}:{request.provider or 'default'}"
    siblings = SimpleNamespace(provider_concurrency_key=provider_key)
    compatibility = resource_compatibility(siblings, siblings)
    requested = acquisition.resolve_auto_batch_parallelism(request) if compatibility == "compatible" else 1
    options = request.options if isinstance(request.options, dict) else {}
    raw_deadline = options.get("deadline_seconds")
    try:
        deadline = None if raw_deadline is None else max(1, int(raw_deadline))
    except (TypeError, ValueError):
        deadline = None
    return acquisition.CollectResourcePolicy(
        schema_ref=acquisition.COLLECT_RESOURCE_POLICY_SCHEMA_REF,
        max_parallelism=max(1, requested),
        deadline_seconds=deadline,
        cancellation=("COORDINATED" if acquisition.resolve_auto_batch_fail_fast(request) else "NONE"),
        backpressure=True,
        provider_concurrency_key=provider_key,
        policy_digest="",
    )


def _collect_delivery_observation(
    result: CollectResult, *, expected_delivery: str = "unknown"
) -> DeliveryObservation:
    meta = result.meta if isinstance(result.meta, dict) else {}
    raw = meta.get("raw") if isinstance(meta.get("raw"), dict) else {}
    raw_result = raw.get("result") if isinstance(raw.get("result"), dict) else {}
    terminal_output = meta.get("terminal_output") if isinstance(meta.get("terminal_output"), dict) else {}
    terminal_meta = terminal_output.get("meta") if isinstance(terminal_output.get("meta"), dict) else {}
    handoff = terminal_meta.get("provider_handoff") if isinstance(terminal_meta.get("provider_handoff"), dict) else {}
    readback = (
        meta.get("terminal_readback") or raw.get("terminal_readback")
        or raw_result.get("terminal_readback") or terminal_meta.get("terminal_readback")
    )
    provider_job_id = result.provider_job_id or raw.get("provider_job_id") or raw_result.get("provider_job_id") or terminal_meta.get("provider_job_id") or handoff.get("provider_job_id")
    return observe_delivery(SimpleNamespace(
        status=result.status,
        provider_job_id=provider_job_id,
        provider_type=result.provider_type or raw.get("provider_type") or raw_result.get("provider_type") or handoff.get("provider_type"),
        provider_status=result.provider_status or raw.get("provider_status") or raw_result.get("provider_status") or handoff.get("provider_status") or terminal_output.get("status"),
        meta={"terminal_readback": readback},
    ), expected_delivery=expected_delivery)


def _attach_delivery_observation(result: CollectResult) -> CollectResult:
    observation = _collect_delivery_observation(result)
    result.meta = dict(result.meta or {})
    result.meta["delivery_observation"] = asdict(observation)
    raw = result.meta.get("raw")
    if isinstance(raw, dict):
        result.meta["raw"] = {**raw, "delivery_observation": asdict(observation)}
    return result


def _collect_result_to_c3_outcome(result: CollectResult, element: Any, acquisition: Any) -> Any:
    from app.successor_runtime.capabilities.checksum import content_digest

    raw = dict((result.meta or {}).get("raw") or {})
    links = tuple(str(link).strip() for link in (raw.get("links") or []) if str(link).strip())
    delivery = _collect_delivery_observation(result)
    target_delivery_ok = delivery.state == "delivered"
    receipt = None
    if delivery.provider_job_id:
        provider_status = None if result.provider_status is None else str(result.provider_status)
        authoritative = target_delivery_ok
        receipt = acquisition.CollectAttemptReceipt(
            schema_version=acquisition.COLLECT_ATTEMPT_RECEIPT_SCHEMA_REF,
            receipt_kind=("AUTHORITATIVE_READBACK" if authoritative else "DISPATCH_ACKNOWLEDGEMENT"),
            provider_type=str(result.provider_type or "unknown"),
            provider_job_id=delivery.provider_job_id,
            provider_status=provider_status,
            attempt_count=int(result.attempt_count or 0),
            observed_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            raw_digest=content_digest(raw),
            authoritative_readback=authoritative,
            receipt_digest="",
        )
    counts = acquisition.CollectCounts(
        inserted=int(result.inserted or 0),
        updated=int(result.updated or 0),
        skipped=int(result.skipped or 0),
    )
    legacy_ref = "legacy:" + content_digest({"element": element.element_id, "result": raw})
    if target_delivery_ok:
        return acquisition.CollectElementSucceeded(
            schema_version=acquisition.COLLECT_ELEMENT_OUTCOME_SCHEMA_REF,
            element_id=element.element_id,
            input_index=element.input_index,
            counts=counts,
            links=links,
            receipt=receipt,
            legacy_observation_ref=legacy_ref,
            outcome_digest="",
        )
    first_error = (result.errors or [{}])[0]
    if not target_delivery_ok and not first_error.get("message"):
        first_error = {
            "code": "runner_unavailable",
            "message": "target delivery readback is required for successor completion",
        }
    return acquisition.CollectElementFailed(
        schema_version=acquisition.COLLECT_ELEMENT_OUTCOME_SCHEMA_REF,
        element_id=element.element_id,
        input_index=element.input_index,
        error=acquisition.CollectElementError(
            code=(str(first_error.get("code") or "auto_batch_execution_failed") if str(first_error.get("code") or "") in acquisition.COLLECT_ELEMENT_ERROR_CODES else "auto_batch_execution_failed"),
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

    from app.successor_runtime.capabilities import acquisition_batch as acquisition
    if (
        request.channel not in acquisition.COLLECT_AUTO_BATCH_CHANNELS
        or not request.project_key
        or not acquisition.should_auto_batch(request)
    ):
        return None
    if _SUCCESSOR_EFFECT_GATEWAY is None:
        return outcome_unknown_result(request)
    from app.successor_runtime.capabilities import acquisition_batch_interpreters as ci
    from app.successor_runtime.capabilities import acquisition_batch_program as cp
    from app.successor_runtime.capabilities.acquisition_native_contribution import (
        default_acquisition_native_definition,
    )
    from app.successor_runtime.runtime.assignments import InterpreterBinding
    from functorial_kit.core.failure import Failure

    native_definition = default_acquisition_native_definition()
    if isinstance(native_definition, Failure):
        return None
    catalog = native_definition.catalog
    registry = native_definition.registry
    request_ref = acquisition.build_collect_request_ref(
        request_id=_successor_request_id(request),
        project_key=str(request.project_key),
        channel=request.channel,
    )
    snapshot = acquisition.CollectLegacyRequestSnapshot(
        schema_version=acquisition.COLLECT_REQUEST_SNAPSHOT_SCHEMA_REF,
        flow=request.flow,
        channel=request.channel,
        project_key=request.project_key,
        query_terms=tuple(request.query_terms or ()),
        urls=tuple(request.urls or ()),
        limit=request.limit,
        options=acquisition.freeze_json_object(dict(request.options or {})),
        source_context=acquisition.freeze_json_object(dict(request.source_context or {})),
        snapshot_digest="",
    )
    policy = _successor_resource_policy(request, acquisition)
    plan = acquisition.build_collect_batch_plan(
        request_ref=request_ref,
        snapshot=snapshot,
        plan_id=f"successor:{request_ref.request_id}",
        resource_policy=policy,
        authority_scope_ref=f"project:{request.project_key}",
    )
    scope = _CollectProjectScope(
        project_key=str(request.project_key),
        registry_revision=1,
        scope_digest=acquisition.content_digest({"project_key": request.project_key, "revision": 1}),
    )
    delivery_by_index: dict[int, dict[str, Any]] = {}

    def _run_bound_effect(element: Any) -> Any:
        effect_request = replace(
            request,
            query_terms=list(element.query_terms),
            limit=element.per_batch_limit,
            source_context={
                **dict(request.source_context or {}),
                "auto_batched_child": True,
            },
        )
        effect_result = _SUCCESSOR_EFFECT_GATEWAY(effect_request)
        effect_raw = (effect_result.meta or {}).get("raw")
        effect_raw = effect_raw if isinstance(effect_raw, dict) else {}
        delivery_by_index[element.input_index] = {
            "element_id": element.element_id,
            "input_index": element.input_index,
            "query_terms": list(element.query_terms),
            "observation": asdict(_collect_delivery_observation(effect_result)),
            "counts": {
                "inserted": int(effect_result.inserted or 0),
                "updated": int(effect_result.updated or 0),
                "skipped": int(effect_result.skipped or 0),
            },
            "links": [str(link) for link in (effect_raw.get("links") or []) if str(link).strip()],
        }
        return _collect_result_to_c3_outcome(effect_result, element, acquisition)

    class _BoundRunner:
        def run(self, element: Any) -> Any:
            payload = acquisition.CollectBatchElementPayload(
                schema_version=acquisition.ACQUISITION_BATCH_ELEMENT_PAYLOAD_SCHEMA,
                operation_kind=acquisition.COLLECT_EXECUTE_BATCH_ELEMENT_KIND,
                parent_request_ref=request_ref,
                request_snapshot=snapshot,
                element=element,
                resource_policy=policy,
                authority_scope_ref=f"project:{request.project_key}",
                payload_digest="",
            )
            program_id = (
                f"{plan.plan_id}:execute-element:{element.input_index}"
            )
            program = cp.build_collect_batch_element_program(
                payload=payload,
                catalog=catalog,
                program_id=program_id,
                project_key=scope.project_key,
                project_registry_revision=scope.registry_revision,
                project_scope_digest=scope.scope_digest,
            )
            bound_plan = cp.compile_collect_program(program, catalog, operation_contracts=registry)
            outcome = ci.CollectTraversalSuccessorInterpreter().interpret(
                program=program,
                plan=bound_plan,
                contract_ref=program.root.operation.contract_ref,
                payload_ref=program.root.operation.payload_ref,
                payload=payload,
                project_scope=scope,
                catalog=catalog,
                deployment_catalog_digest=acquisition.deployment_catalog_digest(),
                binding=InterpreterBinding.from_content(
                    operation_contract_digest=program.root.operation.contract_ref.contract_digest,
                    interpreter_profile_digest=ci.successor_execute_element_interpreter_profile_digest(),
                    deployment_catalog_digest=acquisition.deployment_catalog_digest(),
                    runtime_protocol_version="mrw.runtime.protocol.v1",
                    project_scope_digest=scope.scope_digest,
                    resource_policy_epoch=1,
                    authority_requirement_digest=ci.authority_requirement_digest(
                        acquisition.COLLECT_EXECUTE_BATCH_ELEMENT_KIND
                    ),
                ),
                runner=type(
                    "AdapterRunner",
                    (),
                    {
                        "run": lambda _self, e: _run_bound_effect(e)
                    },
                )(),
            )
            if isinstance(outcome, ci.InterpreterSuccess):
                return outcome.value
            return acquisition.CollectElementFailed(
                schema_version=acquisition.COLLECT_ELEMENT_OUTCOME_SCHEMA_REF,
                element_id=element.element_id,
                input_index=element.input_index,
                error=acquisition.CollectElementError(
                    code="auto_batch_execution_failed",
                    message=outcome.message,
                    query_terms=tuple(element.query_terms),
                    error_digest="",
                ),
                counts=acquisition.CollectCounts(),
                links=(),
                receipt=None,
                legacy_observation_ref="legacy:" + acquisition.content_digest({"element": element.element_id, "error": outcome.code}),
                outcome_digest="",
            )

    traversal = ci.run_ordered_traversal(plan, _BoundRunner())
    if isinstance(traversal, acquisition.OrderedTraversalAborted):
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
    outcome_indexes = {item.input_index for item in ordered_outcomes}
    delivery_rows = []
    for element in plan.elements:
        row = delivery_by_index.get(element.input_index)
        if row is None:
            row = {
                "element_id": element.element_id,
                "input_index": element.input_index,
                "query_terms": list(element.query_terms),
                "observation": asdict(observe_delivery(None)),
            }
        delivery_rows.append({
            **row,
            "execution_state": (
                "attempted" if element.input_index in delivery_by_index
                else "attempted_unknown" if element.input_index in outcome_indexes
                else "not_attempted"
            ),
        })
    delivery_states = [
        row["observation"]["state"]
        for row in delivery_rows if row["execution_state"] == "attempted"
    ]
    pending_delivery = any(state in {"waiting", "unknown"} for state in delivery_states)
    delivery_cancelled = any(state == "cancelled" for state in delivery_states)
    if pending_delivery or delivery_cancelled:
        # C3 currently has only succeeded/failed element variants. Preserve
        # uncertain or cancelled owner observations before its fold would
        # mislabel them as failures, and do not unlock the next collect step.
        counts = {
            key: sum(int((row.get("counts") or {}).get(key) or 0) for row in delivery_rows)
            for key in ("inserted", "updated", "skipped")
        }
        links = list(dict.fromkeys(
            link for row in delivery_rows for link in (row.get("links") or [])
        ))
        state = "unknown" if pending_delivery else "cancelled"
        requested_parallelism = acquisition.resolve_auto_batch_parallelism(request)
        fail_fast = acquisition.resolve_auto_batch_fail_fast(request)
        reason = (
            "target_delivery_readback_required"
            if any(
                row["observation"]["state"] == "unknown"
                and row["observation"]["provider_state"] == "delivered"
                for row in delivery_rows if row["execution_state"] == "attempted"
            )
            else "provider_readback_pending" if pending_delivery else "provider_cancelled"
        )
        return CollectResult(
            flow=request.flow,
            channel=request.channel,
            status=state,
            inserted=counts["inserted"],
            updated=counts["updated"],
            skipped=counts["skipped"],
            meta={
                "batch_parallelism": policy.max_parallelism,
                "batch_parallelism_requested": requested_parallelism,
                "batch_fail_fast": fail_fast,
                "raw": {
                    **counts,
                    "links": links,
                    "outcome": "OutcomeUnknown" if pending_delivery else "Cancelled",
                    "reason": reason,
                    "batch_parallelism": policy.max_parallelism,
                    "batch_parallelism_requested": requested_parallelism,
                    "batch_fail_fast": fail_fast,
                    "delivery_observations": delivery_rows,
                    "typed_batch_results": [item.to_plain() for item in ordered_outcomes],
                    **({"cancellation_receipt": cancellation.to_plain()} if cancellation is not None else {}),
                },
            },
        )
    sequence = acquisition.OrderedCollectElementOutcomeSequence(
        schema_version=acquisition.ORDERED_OUTCOME_SEQUENCE_SCHEMA_REF,
        parent_request_ref=request_ref,
        outcomes=ordered_outcomes,
        sequence_digest="",
    )
    fold_payload = acquisition.build_collect_fold_payload(parent_request_ref=request_ref, ordered_outcomes=sequence)
    fold_program = cp.build_collect_fold_ordered_results_program(
        payload=fold_payload,
        catalog=catalog,
        program_id=f"{plan.plan_id}:fold-ordered-results",
        project_key=scope.project_key,
        project_registry_revision=scope.registry_revision,
        project_scope_digest=scope.scope_digest,
    )
    fold_plan = cp.compile_collect_program(fold_program, catalog, operation_contracts=registry)
    fold_result = ci.CollectFoldSuccessorInterpreter().interpret(
        program=fold_program,
        plan=fold_plan,
        contract_ref=fold_program.root.operation.contract_ref,
        payload_ref=fold_program.root.operation.payload_ref,
        payload=fold_payload,
        project_scope=scope,
        catalog=catalog,
        deployment_catalog_digest=acquisition.deployment_catalog_digest(),
        binding=InterpreterBinding.from_content(
            operation_contract_digest=fold_program.root.operation.contract_ref.contract_digest,
            interpreter_profile_digest=ci.successor_fold_ordered_results_interpreter_profile_digest(),
            deployment_catalog_digest=acquisition.deployment_catalog_digest(),
            runtime_protocol_version="mrw.runtime.protocol.v1",
            project_scope_digest=scope.scope_digest,
            resource_policy_epoch=1,
            authority_requirement_digest=ci.authority_requirement_digest(
                acquisition.COLLECT_FOLD_ORDERED_RESULTS_KIND
            ),
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
        acquisition,
        cancellation=(cancellation if cancelled else None),
    )
    result.meta["delivery_observations"] = delivery_rows
    result.meta["raw"]["delivery_observations"] = delivery_rows
    from .display_meta import build_display_meta

    result.display_meta = build_display_meta(request, result, summary=(request.source_context or {}).get("summary"))
    return result


def _run_collect_no_batch(request: CollectRequest) -> CollectResult:
    if _SUCCESSOR_EFFECT_GATEWAY is None:
        return _attach_delivery_observation(outcome_unknown_result(request))
    return _attach_delivery_observation(_SUCCESSOR_EFFECT_GATEWAY(request))


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


def collect_request_from_source_library_api(
    *,
    item_key: str,
    project_key: str | None,
    override_params: CollectJsonObject | None = None,
) -> CollectRequest:
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
    override_params: CollectJsonObject | None = None,
) -> SourceLibraryCompatResponse:
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
    response.setdefault("display_meta", result.display_meta)
    return response
