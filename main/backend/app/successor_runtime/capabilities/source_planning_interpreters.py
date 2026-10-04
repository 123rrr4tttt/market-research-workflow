"""Successor-native pure planners and interpreter for the four source planning modes.

The four planners consume the exact C2.1 ``shared.SourceExecutionRequest`` and the
immutable channel catalog snapshot, and produce one ordered ``shared.SourceModePlan``
of C2.3 provider-effect requests.  No effect is executed here; fallback rules
are declared with ``authority_bound=True`` so provider/credential grants can
never be widened by a plan.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any, Generic, Literal, TypeAlias, TypeVar

from functorial_kit import Failure

from app.successor_runtime.capabilities import source_contracts as contracts
from app.successor_runtime.capabilities.checksum import content_digest

__all__ = [
    "SOURCE_PLANNING_SUCCESSOR_INTERPRETER_ID",
    "PlanningBindingMismatch",
    "SourcePlanningSuccessorInterpreter",
    "kind_for_mode",
    "mode_for_kind",
    "plan_protocol_search",
    "plan_provider_harvest",
    "plan_site_search",
    "plan_source_mode",
    "plan_url_execution",
    "require_exact_planning_binding",
    "try_plan_source_mode",
    "try_require_exact_planning_binding",
    "successor_planning_interpreter_profile_digest",
]


SOURCE_PLANNING_SUCCESSOR_INTERPRETER_ID = "mrw.source.plan-source-mode.native.v2"

mode_for_kind = contracts.mode_for_kind
kind_for_mode = contracts.kind_for_mode


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class InterpreterSuccess(Generic[T]):
    value: T


@dataclass(frozen=True, slots=True)
class InterpreterFailure:
    code: str
    message: str
    retryable: bool = False


InterpreterOutcome: TypeAlias = InterpreterSuccess[T] | InterpreterFailure


class PlanningBindingMismatch(ValueError):
    """Exact source planning binding drifted or was never established."""


def _raise_planning_binding_mismatch(message: str) -> None:
    """Lift the retained binding-mismatch exception at one ABI boundary."""

    # kit:boundary owner=source.plan_source_mode.v2 class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=source.runtime-binding.failure witness=test:test_w06_c2_total_core_failure_lifts
    raise PlanningBindingMismatch(message)


def successor_planning_interpreter_profile_digest() -> str:
    return content_digest(
        {
            "interpreter_id": SOURCE_PLANNING_SUCCESSOR_INTERPRETER_ID,
            "version": "1.0.0",
            "boundary": "pure source-mode planner",
        }
    )


def require_exact_planning_binding(
    payload: contracts.SourceModePlanningPayload,
    *,
    program: Any = None,
    plan: Any = None,
    contract_ref: Any = None,
    payload_ref: Any = None,
    project_scope: Any = None,
    catalog: Any = None,
    deployment_catalog_digest: str | None = None,
    binding: Any = None,
    expected_interpreter_profile_digest: str | None = None,
) -> None:
    """Validate the exact source planning planning binding before any plan is produced."""

    if payload.operation_kind not in contracts.MODE_BY_KIND:
        _raise_planning_binding_mismatch("source planning payload operation kind is not one of four")
    mode = contracts.mode_for_kind(payload.operation_kind)
    request = payload.execution_request
    if request.source_mode.mode != mode:
        _raise_planning_binding_mismatch(
            f"source planning planner mode {mode} does not match request mode {request.source_mode.mode}"
        )
    expected_request_digest = content_digest(request.to_plain())
    if payload.execution_request_digest != expected_request_digest:
        _raise_planning_binding_mismatch("source planning execution_request_digest does not match the exact request")
    if (
        payload.project_scope.project_key != request.project_scope.project_key
        or payload.project_scope.registry_revision != request.project_scope.registry_revision
        or payload.project_scope.resolved_schema != request.project_scope.resolved_schema
        or payload.project_scope.incarnation != request.project_scope.incarnation
        or payload.project_scope.scope_digest != request.project_scope.scope_digest
    ):
        _raise_planning_binding_mismatch("source planning payload project scope does not match the exact request")
    if (
        payload.catalog.revision != request.catalog_revision
        or payload.catalog.incarnation != request.catalog_incarnation
        or payload.catalog.digest != request.catalog_digest
    ):
        _raise_planning_binding_mismatch(
            "source planning payload catalog does not match the exact request catalog binding"
        )
    if (
        payload.item_revision != request.item_revision
        or payload.item_incarnation != request.item_incarnation
        or payload.item_content_digest != request.item_content_digest
    ):
        _raise_planning_binding_mismatch("source planning payload item does not match the exact request item binding")
    if payload.resource_ceiling_digest != contracts.resource_ceiling_digest():
        _raise_planning_binding_mismatch("source planning resource ceiling digest drift")
    if project_scope is not None and (
        project_scope.project_key != payload.project_scope.project_key
        or project_scope.registry_revision != payload.project_scope.registry_revision
        or project_scope.resolved_schema != payload.project_scope.resolved_schema
        or project_scope.incarnation != payload.project_scope.incarnation
        or project_scope.scope_digest != payload.project_scope.scope_digest
    ):
        _raise_planning_binding_mismatch("source planning project scope binding drift")
    if (
        catalog is not None
        and getattr(catalog, "digest", None) is not None
        and catalog.digest != payload.catalog.digest
    ):
        _raise_planning_binding_mismatch("source planning catalog snapshot binding drift")
    if (
        binding is not None
        and expected_interpreter_profile_digest is not None
        and getattr(binding, "interpreter_profile_digest", None) != expected_interpreter_profile_digest
    ):
        _raise_planning_binding_mismatch("source planning interpreter binding profile digest does not match")
    if program is not None and plan is not None:
        if getattr(plan, "program_digest", None) != getattr(program, "program_digest", None):
            _raise_planning_binding_mismatch("plan.program_digest does not match program.program_digest")
        if getattr(plan, "program_id", None) != getattr(program, "program_id", None):
            _raise_planning_binding_mismatch("plan.program_id does not match program.program_id")
        if payload_ref is not None and getattr(plan, "plan_digest", None) is None:
            _raise_planning_binding_mismatch("source planning plan digest is not available")


def try_require_exact_planning_binding(
    payload: contracts.SourceModePlanningPayload,
    **kwargs: Any,
) -> None | Failure:
    try:
        require_exact_planning_binding(payload, **kwargs)
        return None
    except PlanningBindingMismatch as exc:
        return contracts.source_interpreter_failure(
            str(exc),
            operation="source.plan_source_mode.require_exact_planning_binding",
            site="require_exact_planning_binding",
        )
    except (TypeError, ValueError, KeyError, AttributeError) as exc:
        return contracts.source_contract_failure(
            "binding_contract_invalid",
            str(exc),
            operation="source.plan_source_mode.require_exact_planning_binding",
            site="require_exact_planning_binding",
            owner=contracts.SOURCE_PLANNING_OWNERS[payload.operation_kind],
        )


def _reject(code: str, message: str) -> contracts.RejectedPlanning:
    return contracts.RejectedPlanning(code=code, message=message)


def _channel_entry(
    payload: contracts.SourceModePlanningPayload,
    *,
    channel_key: str | None = None,
) -> tuple[contracts.ChannelCatalogEntry | None, str]:
    request = payload.execution_request
    key = channel_key or request.item_channel_key
    entry = payload.catalog.entry_by_key(key)
    return entry, key


def _validate_channel(
    payload: contracts.SourceModePlanningPayload,
    *,
    channel_key: str | None = None,
) -> contracts.RejectedPlanning | None:
    entry, key = _channel_entry(payload, channel_key=channel_key)
    if entry is None:
        return _reject(
            "CHANNEL_NOT_FOUND",
            f"channel not found for item {payload.execution_request.item_key}: {key}",
        )
    if not entry.enabled:
        return _reject(
            "CHANNEL_DISABLED",
            f"channel disabled for item {payload.execution_request.item_key}: {key}",
        )
    if key.lower().startswith("generic_web.") and payload.operation_kind not in {
        contracts.SOURCE_PLANNING_SITE_SEARCH_KIND
    }:
        return _reject(
            "FORBIDDEN_INTERNAL_ADAPTER",
            "generic_web.* channels are internal; direct non-site-search execution is forbidden",
        )
    return None


def _credential_refs(
    payload: contracts.SourceModePlanningPayload,
    *,
    channel_key: str,
    provider: str,
) -> tuple[contracts.CredentialRef, ...]:
    entry = payload.catalog.entry_by_key(channel_key)
    raw = ()
    if entry is not None:
        raw = tuple(dict(entry.extra).get("credential_refs") or ())
    refs: list[contracts.CredentialRef] = []
    for name in raw:
        if isinstance(name, str) and name.strip():
            refs.append(
                contracts.CredentialRef(
                    ref=name.strip(),
                    provider=provider,
                    grant_scope=payload.execution_request.project_scope.project_key,
                )
            )
    return tuple(refs)


def _provider_for(
    payload: contracts.SourceModePlanningPayload,
    *,
    channel_key: str,
    mode_default: str = "native",
) -> str:
    entry = payload.catalog.entry_by_key(channel_key)
    if entry is None:
        return mode_default
    provider = str(entry.provider or "").strip().lower()
    if provider:
        return provider
    provider_type = str(entry.provider_type or "").strip().lower()
    return provider_type or mode_default


def _effect_request(
    payload: contracts.SourceModePlanningPayload,
    *,
    mode: str,
    occurrence_id: str,
    channel_key: str,
    effect_payload: dict[str, Any],
    terminal_output_only: bool,
) -> contracts.ProviderEffectRequest:
    request = payload.execution_request
    provider = _provider_for(payload, channel_key=channel_key)
    provider_config_ref = f"catalog:{payload.catalog.digest}:{request.catalog_incarnation}:{channel_key}"
    frozen_payload = _freeze_payload(effect_payload)
    effect_payload_digest = content_digest(
        {
            "schema": f"mrw.source.provider-acquisition.effect-payload.{mode}.v2",
            "channel_key": channel_key,
            "payload": dict(frozen_payload),
        }
    )
    return contracts.ProviderEffectRequest(
        schema_version=contracts.SOURCE_PROVIDER_ACQUISITION_PAYLOAD_SCHEMA,
        operation_kind=contracts.SOURCE_PROVIDER_ACQUISITION_KIND,
        request_id=f"source-acquisition:{mode}:{occurrence_id}",
        idempotency_key=(f"idem:source-acquisition:{mode}:{payload.execution_request_digest}:{occurrence_id}"),
        project_scope=request.project_scope,
        item_key=request.item_key,
        item_revision=request.item_revision,
        item_incarnation=request.item_incarnation,
        item_content_digest=request.item_content_digest,
        channel_key=channel_key,
        provider=provider,
        provider_config_ref=provider_config_ref,
        effect_payload_codec_ref=(f"mrw.source.provider-acquisition.effect-payload.{mode}.v2"),
        effect_payload_digest=effect_payload_digest,
        effect_payload=frozen_payload,
        credential_refs=_credential_refs(payload, channel_key=channel_key, provider=provider),
        policy=contracts.SOURCE_PROVIDER_ACQUISITION_DEFAULT_RESOURCE_POLICY,
        catalog_revision=request.catalog_revision,
        catalog_incarnation=request.catalog_incarnation,
        catalog_digest=request.catalog_digest,
        terminal_output_only=terminal_output_only,
    )


def _freeze_payload(value: dict[str, Any]):
    from app.successor_runtime.language.algebra import freeze_json_object

    return freeze_json_object(value)


def _plan(
    payload: contracts.SourceModePlanningPayload,
    *,
    mode: str,
    plan_id: str,
    tasks: tuple[contracts.SourceModeTask, ...],
    fallback_rules: tuple[contracts.FallbackRule, ...] = (),
    failure_mode: str = "CONTINUE_ON_ORDERED_FAILURE",
) -> contracts.SourceModePlan:
    return contracts.SourceModePlan(
        plan_id=plan_id,
        mode=mode,
        execution_request_digest=payload.execution_request_digest,
        catalog_revision=payload.execution_request.catalog_revision,
        catalog_incarnation=payload.execution_request.catalog_incarnation,
        catalog_digest=payload.execution_request.catalog_digest,
        ordered_tasks=tasks,
        ordered_fold_policy=contracts.OrderedFoldPolicy(failure_mode=failure_mode),  # type: ignore[arg-type]
        fallback_rules=fallback_rules,
        terminal_profile=contracts.TerminalConstructionProfile(
            collect_only=all(task.terminal_output_only for task in tasks),
        ),
    )


def plan_protocol_search(
    payload: contracts.SourceModePlanningPayload,
) -> Annotated[
    contracts.SourceModePlanningResult,
    Literal[
        "kit:non-authoritative derived_as=view fact_source=request+catalog+interpreter_profile witness=test:test_w06_successor_authority_metadata"
    ],
]:
    blocked = _validate_channel(payload)
    if blocked is not None:
        return blocked
    request = payload.execution_request
    terms = tuple(
        str(term).strip() for term in (request.params.query_terms or request.protocol.query_terms) if str(term).strip()
    )
    if not terms:
        return _reject("INVALID_REQUEST", "protocol_search requires at least one query term")
    if len(terms) > contracts.SOURCE_PLANNING_MAX_QUERY_TERMS:
        return _reject(
            "RESOURCE_CEILING_EXCEEDED",
            f"protocol_search query terms exceed {contracts.SOURCE_PLANNING_MAX_QUERY_TERMS}",
        )
    tasks: list[contracts.SourceModeTask] = []
    for index, term in enumerate(terms[: contracts.SOURCE_PLANNING_MAX_TASKS]):
        occurrence_id = f"query-{index}"
        effect = _effect_request(
            payload,
            mode="protocol_search",
            occurrence_id=occurrence_id,
            channel_key=request.item_channel_key,
            effect_payload={
                "query_term": term,
                "protocol_search": True,
                "expected_entry_type": request.protocol.expected_entry_type,
                "ingest_limit": request.protocol.ingest_limit,
            },
            terminal_output_only=False,
        )
        tasks.append(
            contracts.SourceModeTask(
                task_id=f"source-plan:protocol_search:{occurrence_id}",
                occurrence_id=occurrence_id,
                mode="protocol_search",
                order_index=index,
                effect_request=effect,
                fallback_rule=contracts.FallbackRule(
                    when="term_failure",
                    reason="one query term failed inside the ordered fold",
                    target="ordered_failure_row",
                ),
                terminal_output_only=False,
            )
        )
    return contracts.PlannedPlanning(
        plan=_plan(
            payload,
            mode="protocol_search",
            plan_id=f"plan:source:protocol_search:{payload.execution_request_digest[:16]}",
            tasks=tuple(tasks),
            fallback_rules=(
                contracts.FallbackRule(
                    when="term_failure",
                    reason="ordered fold continues with per-term failure rows",
                    target="ordered_failure_row",
                ),
            ),
        )
    )


def plan_provider_harvest(
    payload: contracts.SourceModePlanningPayload,
) -> Annotated[
    contracts.SourceModePlanningResult,
    Literal[
        "kit:non-authoritative derived_as=view fact_source=request+catalog+interpreter_profile witness=test:test_w06_successor_authority_metadata"
    ],
]:
    blocked = _validate_channel(payload)
    if blocked is not None:
        return blocked
    request = payload.execution_request
    occurrence_id = "harvest-0"
    effect = _effect_request(
        payload,
        mode="provider_harvest",
        occurrence_id=occurrence_id,
        channel_key=request.item_channel_key,
        effect_payload={
            "prefer_crawler_first": True,
            "provider_harvest_mode": "terminal_output_only",
            "channel_key": request.item_channel_key,
            "query_terms": list(request.params.query_terms or ()),
        },
        terminal_output_only=True,
    )
    task = contracts.SourceModeTask(
        task_id=f"source-plan:provider_harvest:{occurrence_id}",
        occurrence_id=occurrence_id,
        mode="provider_harvest",
        order_index=0,
        effect_request=effect,
        fallback_rule=contracts.FallbackRule(
            when="provider_unavailable",
            reason="crawler provider unavailable; native fallback stays authority-bound",
            target="native_fallback",
        ),
        terminal_output_only=True,
    )
    return contracts.PlannedPlanning(
        plan=_plan(
            payload,
            mode="provider_harvest",
            plan_id=(f"plan:source:provider_harvest:{payload.execution_request_digest[:16]}"),
            tasks=(task,),
            fallback_rules=(
                contracts.FallbackRule(
                    when="provider_unavailable",
                    reason="native fallback must not widen provider/credential grants",
                    target="native_fallback",
                ),
            ),
        )
    )


def plan_site_search(
    payload: contracts.SourceModePlanningPayload,
) -> Annotated[
    contracts.SourceModePlanningResult,
    Literal[
        "kit:non-authoritative derived_as=view fact_source=request+catalog+interpreter_profile witness=test:test_w06_successor_authority_metadata"
    ],
]:
    request = payload.execution_request
    handler_entry = payload.catalog.entry_by_key("handler.cluster")
    if handler_entry is None:
        return _reject(
            "CHANNEL_NOT_FOUND",
            "site_search requires the handler.cluster channel in the catalog",
        )
    if not handler_entry.enabled:
        return _reject(
            "CHANNEL_DISABLED",
            "site_search requires the handler.cluster channel to be enabled",
        )
    entries = tuple(
        str(entry).strip()
        for entry in (request.params.site_entries or request.params.site_entry_urls or request.protocol.site_entries)
        if str(entry).strip()
    )
    if not entries:
        return _reject("INVALID_REQUEST", "site_search requires at least one site entry")
    if len(entries) > contracts.SOURCE_PLANNING_MAX_URLS:
        return _reject(
            "RESOURCE_CEILING_EXCEEDED",
            f"site_search site entries exceed {contracts.SOURCE_PLANNING_MAX_URLS}",
        )
    tasks: list[contracts.SourceModeTask] = []
    for index, entry in enumerate(entries[: contracts.SOURCE_PLANNING_MAX_TASKS]):
        occurrence_id = f"site-{index}"
        effect = _effect_request(
            payload,
            mode="site_search",
            occurrence_id=occurrence_id,
            channel_key="handler.cluster",
            effect_payload={
                "site_entry": entry,
                "site_search": True,
                "forced_handler_cluster": True,
                "query_terms": list(request.params.query_terms or ()),
            },
            terminal_output_only=False,
        )
        tasks.append(
            contracts.SourceModeTask(
                task_id=f"source-plan:site_search:{occurrence_id}",
                occurrence_id=occurrence_id,
                mode="site_search",
                order_index=index,
                effect_request=effect,
                fallback_rule=contracts.FallbackRule(
                    when="site_entry_failure",
                    reason="one site entry failed; ordered fold keeps the failure row",
                    target="ordered_failure_row",
                ),
                terminal_output_only=False,
            )
        )
    return contracts.PlannedPlanning(
        plan=_plan(
            payload,
            mode="site_search",
            plan_id=f"plan:source:site_search:{payload.execution_request_digest[:16]}",
            tasks=tuple(tasks),
            fallback_rules=(
                contracts.FallbackRule(
                    when="site_entry_failure",
                    reason="site search keeps ordered per-entry failures",
                    target="ordered_failure_row",
                ),
            ),
        )
    )


def plan_url_execution(
    payload: contracts.SourceModePlanningPayload,
) -> Annotated[
    contracts.SourceModePlanningResult,
    Literal[
        "kit:non-authoritative derived_as=view fact_source=request+catalog+interpreter_profile witness=test:test_w06_successor_authority_metadata"
    ],
]:
    blocked = _validate_channel(payload)
    if blocked is not None:
        return blocked
    request = payload.execution_request
    urls = tuple(
        str(url).strip()
        for url in (request.params.urls or request.protocol.candidate_urls or request.params.site_entry_urls)
        if str(url).strip()
    )
    if not urls:
        return _reject("INVALID_REQUEST", "url_execution requires at least one URL")
    if len(urls) > contracts.SOURCE_PLANNING_MAX_URLS:
        return _reject(
            "RESOURCE_CEILING_EXCEEDED",
            f"url_execution URLs exceed {contracts.SOURCE_PLANNING_MAX_URLS}",
        )
    tasks: list[contracts.SourceModeTask] = []
    for index, url in enumerate(urls[: contracts.SOURCE_PLANNING_MAX_TASKS]):
        occurrence_id = f"url-{index}"
        effect = _effect_request(
            payload,
            mode="url_execution",
            occurrence_id=occurrence_id,
            channel_key=request.item_channel_key or "url_pool",
            effect_payload={
                "url": url,
                "url_execution": True,
                "terminal_output_only": True,
                "routing_parallelism": request.protocol.routing_parallelism,
            },
            terminal_output_only=True,
        )
        tasks.append(
            contracts.SourceModeTask(
                task_id=f"source-plan:url_execution:{occurrence_id}",
                occurrence_id=occurrence_id,
                mode="url_execution",
                order_index=index,
                effect_request=effect,
                fallback_rule=contracts.FallbackRule(
                    when="url_failure",
                    reason="single URL failure becomes an ordered by_url error row",
                    target="ordered_failure_row",
                ),
                terminal_output_only=True,
            )
        )
    return contracts.PlannedPlanning(
        plan=_plan(
            payload,
            mode="url_execution",
            plan_id=f"plan:source:url_execution:{payload.execution_request_digest[:16]}",
            tasks=tuple(tasks),
            fallback_rules=(
                contracts.FallbackRule(
                    when="url_failure",
                    reason="URL input order is preserved; failures stay per-URL",
                    target="ordered_failure_row",
                ),
            ),
        )
    )


PLANNERS = {
    "protocol_search": plan_protocol_search,
    "provider_harvest": plan_provider_harvest,
    "site_search": plan_site_search,
    "url_execution": plan_url_execution,
}


def plan_source_mode(
    payload: contracts.SourceModePlanningPayload,
) -> Annotated[
    contracts.SourceModePlanningResult,
    Literal[
        "kit:non-authoritative derived_as=view fact_source=request+catalog+interpreter_profile witness=test:test_w06_successor_authority_metadata"
    ],
]:
    mode_result = contracts.try_mode_for_kind(payload.operation_kind)
    if isinstance(mode_result, Failure):
        return _reject("INVALID_REQUEST", mode_result.message)
    mode = mode_result
    planner = PLANNERS[mode]
    return planner(payload)


def try_plan_source_mode(
    payload: contracts.SourceModePlanningPayload,
) -> contracts.SourceModePlanningResult | Failure:
    """Total planner dispatch; malformed payloads stay in the C2 family."""

    try:
        result = plan_source_mode(payload)
    except (TypeError, ValueError, KeyError, AttributeError, OverflowError) as exc:
        return contracts.source_contract_failure(
            "schema_contract_invalid",
            str(exc),
            operation="source.plan_source_mode.plan",
            site="plan_source_mode",
            owner=contracts.SOURCE_PLANNING_OWNERS[payload.operation_kind],
        )
    return result


class SourcePlanningSuccessorInterpreter:
    """Bound successor interpreter for the four source planning planner atoms."""

    interpreter_id = SOURCE_PLANNING_SUCCESSOR_INTERPRETER_ID

    def interpret(
        self,
        payload: contracts.SourceModePlanningPayload,
        *,
        program: Any = None,
        plan: Any = None,
        contract_ref: Any = None,
        payload_ref: Any = None,
        project_scope: Any = None,
        catalog: Any = None,
        deployment_catalog_digest: str | None = None,
        binding: Any = None,
        expected_interpreter_profile_digest: str | None = None,
    ) -> InterpreterOutcome[contracts.SourceModePlan]:
        try:
            require_exact_planning_binding(
                payload,
                program=program,
                plan=plan,
                contract_ref=contract_ref,
                payload_ref=payload_ref,
                project_scope=project_scope,
                catalog=catalog,
                deployment_catalog_digest=deployment_catalog_digest,
                binding=binding,
                expected_interpreter_profile_digest=(
                    expected_interpreter_profile_digest or successor_planning_interpreter_profile_digest()
                ),
            )
        except PlanningBindingMismatch as exc:
            return InterpreterFailure(
                code="ASSIGNMENT_BINDING_MISMATCH",
                message=str(exc),
                retryable=False,
            )
        result = try_plan_source_mode(payload)
        if isinstance(result, Failure):
            return InterpreterFailure(
                code=result.code,
                message=result.message,
                retryable=False,
            )
        if isinstance(result, contracts.RejectedPlanning):
            return InterpreterFailure(
                code=result.code,
                message=result.message,
                retryable=False,
            )
        return InterpreterSuccess(result.plan)
