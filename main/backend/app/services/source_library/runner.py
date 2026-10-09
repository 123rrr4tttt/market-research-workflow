from __future__ import annotations

import os
from collections.abc import Iterable, Mapping, Sequence, Set
from typing import NoReturn, Protocol, TypeAlias, TypeGuard, TypeVar

from functorial_kit import Failure


from mrw_functorial_kit.core.application_failure_semantics import source_library_contract_failures
from mrw_functorial_kit.core.provider_port_failures import crawler_runtime_failures

from ...project_customization import get_project_customization
from ...project_customization.interfaces import (
    CustomizationJsonObject,
    CustomizationJsonValue,
)
from ..crawlers.base import (
    CrawlerDispatchRequest,
    CrawlerDispatchResult,
    CrawlerProvider,
    is_crawler_dispatch_acknowledged,
    typed_crawler_readback,
)
from ..crawlers.durable_effect_bridge import CrawlerAttemptStore, DurableCrawlerEffectBridge
from ...successor_runtime.capabilities.source_contracts import (
    AuthoritativeProviderReadback,
    ProviderReadbackResult,
    ReadbackTerminal,
    ReadbackUnavailable,
    ReadbackWaiting,
)
from .handler_registry import get
from .provider_ports import (
    CrawlerOutputIngestRequest,
    CrawlerOutputIngestResult,
    ingest_crawler_output,
    resolve_crawler_provider,
)
from .single_source_guard import validate_single_source_guard
from .types import default_source_layer_boundary, derive_source_tiering

RunnerValue: TypeAlias = (
    None
    | bool
    | int
    | float
    | str
    | BaseException
    | Sequence["RunnerValue"]
    | Set["RunnerValue"]
    | Mapping[str, "RunnerValue"]
)
RunnerObject: TypeAlias = dict[str, RunnerValue]
_JsonKey = TypeVar("_JsonKey")
_CRAWLER_OPTION_FAILURE_LIFT_INVALID = "crawler option failure lift context is incomplete or inconsistent"
_RUNNER_FAILURE_LIFT_INVALID = "source-library runner failure lift context is incomplete or inconsistent"


class _ProviderClient(Protocol):
    base_url: str | None


class _PlainReadback(Protocol):
    def to_plain(self) -> Mapping[str, RunnerValue]: ...


def _mapping_contains_runner_values(value: Mapping[object, object]) -> bool:
    return all(isinstance(key, str) and _is_runner_value(item) for key, item in value.items())


def _iterable_contains_runner_values(value: Iterable[object]) -> bool:
    return all(_is_runner_value(item) for item in value)


def _is_object_mapping(value: object) -> TypeGuard[Mapping[object, object]]:
    return isinstance(value, dict)


def _is_runner_value(value: object) -> TypeGuard[RunnerValue]:
    if value is None or isinstance(value, (bool, int, float, str, BaseException)):
        return True
    if _is_object_mapping(value):
        return _mapping_contains_runner_values(value)
    if _is_object_iterable(value):
        return _iterable_contains_runner_values(value)
    return False


def is_runner_mapping(value: object) -> TypeGuard[Mapping[str, RunnerValue]]:
    return _is_object_mapping(value) and _is_runner_value(value)


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _is_object_iterable(value: object) -> TypeGuard[Iterable[object]]:
    return isinstance(value, (list, tuple, set, frozenset))


def _is_attempt_store(value: object) -> TypeGuard[CrawlerAttemptStore]:
    return all(
        hasattr(value, member)
        for member in ("reserve", "save_dispatch", "save_readback", "save_cancel", "find_by_job_id")
    )


def _is_provider_client(value: object) -> TypeGuard[_ProviderClient]:
    return hasattr(value, "base_url")


def _is_plain_readback(value: object) -> TypeGuard[_PlainReadback]:
    return hasattr(value, "to_plain")


def _mapping(value: object) -> RunnerObject:
    if not is_runner_mapping(value):
        return {}
    return dict(value)


def _runner_json_value(value: object) -> CustomizationJsonValue:
    if isinstance(value, BaseException):
        return str(value)
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if _is_object_mapping(value):
        return {str(key): _runner_json_value(item) for key, item in value.items()}
    if _is_object_iterable(value):
        return [_runner_json_value(item) for item in value]
    return str(value)


def _json_object(value: Mapping[_JsonKey, object]) -> CustomizationJsonObject:
    return {str(key): _runner_json_value(item) for key, item in value.items()}


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _raise_crawler_option_failure(
    failure: Failure,
    *,
    cause: TypeError | ValueError,
) -> NoReturn:
    context = failure.context or {}
    public_exception = context.get("public_exception")
    if (
        not crawler_runtime_failures.matches(failure)
        or context.get("failure_family") != crawler_runtime_failures.name
        or context.get("boundary_class") != "PURE_CONTRACT_FAILURE"
        or public_exception not in {"TypeError", "ValueError"}
        or context.get("public_message") != failure.message
    ):
        # kit:boundary owner=source_library.runner.crawler_option_failure_lift class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w03_crawler_failure_lifts
        raise TypeError(_CRAWLER_OPTION_FAILURE_LIFT_INVALID)
    if public_exception == "TypeError":
        # kit:boundary owner=source_library.runner.crawler_option_failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=crawler.runtime.failure witness=test:test_w03_crawler_failure_lifts
        raise TypeError(failure.message) from cause
    # kit:boundary owner=source_library.runner.crawler_option_failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=crawler.runtime.failure witness=test:test_w03_crawler_failure_lifts
    raise ValueError(failure.message) from cause


def _invalid_numeric_option(*, name: str, value: object, cause: TypeError | ValueError) -> NoReturn:
    message = f"crawler option '{name}' must be numeric"
    _raise_crawler_option_failure(
        _crawler_effect_failure(
            "scrapyd_response_invalid",
            message,
            site="app.services.source_library.runner.crawler_options",
            option=name,
            observed_type=type(value).__name__,
            public_exception=type(cause).__name__,
            cause=cause,
        ),
        cause=cause,
    )


def _optional_int(value: object, *, name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float, str)):
        try:
            return int(value)
        except ValueError as exc:
            _invalid_numeric_option(name=name, value=value, cause=exc)
    _invalid_numeric_option(
        name=name,
        value=value,
        cause=TypeError(f"int() argument has unsupported type {type(value).__name__}"),
    )


def _numeric_float(value: object, *, default: float, name: str) -> float:
    candidate = value or default
    if isinstance(candidate, (int, float, str)):
        try:
            return float(candidate)
        except ValueError as exc:
            _invalid_numeric_option(name=name, value=value, cause=exc)
    _invalid_numeric_option(
        name=name,
        value=value,
        cause=TypeError(f"float() argument has unsupported type {type(value).__name__}"),
    )


def _numeric_int(value: object, *, default: int, name: str) -> int:
    candidate = value or default
    if isinstance(candidate, (int, float, str)):
        try:
            return int(candidate)
        except ValueError as exc:
            _invalid_numeric_option(name=name, value=value, cause=exc)
    _invalid_numeric_option(
        name=name,
        value=value,
        cause=TypeError(f"int() argument has unsupported type {type(value).__name__}"),
    )


def _bounded_float(
    value: object,
    *,
    default: float,
    minimum: float,
    maximum: float,
    name: str,
) -> float:
    parsed = _numeric_float(value, default=default, name=name)
    return min(maximum, max(minimum, parsed))


def _bounded_int(
    value: object,
    *,
    default: int,
    minimum: int,
    maximum: int,
    name: str,
) -> int:
    parsed = _numeric_int(value, default=default, name=name)
    return min(maximum, max(minimum, parsed))


def _observe_readback(value: object) -> ProviderReadbackResult | RunnerObject | None:
    if (
        isinstance(value, ReadbackTerminal)
        and type(value) is ReadbackTerminal
        and type(value.readback) is AuthoritativeProviderReadback
    ):
        return value
    if isinstance(value, (ReadbackWaiting, ReadbackUnavailable)) and type(value) in (ReadbackWaiting, ReadbackUnavailable):
        return value
    if value is None:
        return None
    # Legacy provider observations are narrowed where they originally controlled polling.
    if _is_plain_readback(value):
        return dict(value.to_plain())
    if is_runner_mapping(value):
        return dict(value)
    return None


def _provider_base_url(provider: CrawlerProvider) -> str | None:
    client: object = getattr(provider, "client", None)
    if not _is_provider_client(client):
        return None
    return str(client.base_url or "").strip() or None


def _dispatch_provider_effect(
    *,
    provider: CrawlerProvider,
    durable_bridge: DurableCrawlerEffectBridge | None,
    request: CrawlerDispatchRequest,
) -> object:
    """Observe the runtime provider result before trusting its protocol shape."""

    try:
        if durable_bridge is not None:
            return durable_bridge.dispatch(request)
        return provider.dispatch(request)
    except Exception as exc:  # noqa: BLE001 - provider effect boundary
        return _crawler_effect_failure(
            "scrapyd_transport",
            f"crawler provider dispatch failed: {exc}",
            site="app.services.source_library.runner.crawler_dispatch",
            provider_type=request.provider,
            cause=exc,
        )


_handlers_registered = False
_CRAWLER_PROVIDER_TYPES = {"scrapy", "crawlee", "meltano"}
_FAILURE_WITNESS = "test:test_w01_source_export_failures"
_CRAWLER_FAILURE_WITNESS = "test:test_w03_crawler_failure_lifts"


def _crawler_effect_failure(code: str, message: str, *, site: str, **details: object) -> Failure:
    context: RunnerObject = {
        "boundary_class": "PURE_CONTRACT_FAILURE",
        "failure_family": crawler_runtime_failures.name,
        "operation": "source_library.crawler_provider",
        "owner": site,
        "public_exception": "RuntimeError",
        "public_message": message,
        "site": site,
        "witness": _CRAWLER_FAILURE_WITNESS,
    }
    for key, value in details.items():
        context[key] = value if _is_runner_value(value) else str(value)
    return crawler_runtime_failures.fail(code, message, context)


def _crawler_failure_result(
    failure: Failure,
    *,
    provider_type: str,
    channel_fields: RunnerObject,
    channel: Mapping[str, object],
    project_key: str | None,
    request: CrawlerDispatchRequest | None = None,
    durable: bool = False,
) -> RunnerObject:
    if not crawler_runtime_failures.matches(failure):
        failure = _crawler_effect_failure(
            "scrapyd_transport",
            f"crawler provider returned an out-of-family failure: {failure.message}",
            site="app.services.source_library.runner.crawler_dispatch",
            provider_type=provider_type,
            observed_family=failure.family,
            observed_code=failure.code,
        )
    result: RunnerObject = {
        "status": "failed",
        "inserted": 0,
        "updated": 0,
        "skipped": 0,
        "errors": [
            {
                "code": failure.code,
                "family": failure.family,
                "message": failure.message,
                "context": _mapping(failure.context or {}),
            }
        ],
        "provider_job_id": None,
        "provider_type": provider_type,
        "provider_status": "failed",
        "attempt_count": None,
        **channel_fields,
        "runtime_channel": _build_runtime_channel_meta(channel=channel, project_key=project_key),
        "output_ingest": None,
    }
    if request is not None:
        result.update(
            attempt_id=request.attempt_id,
            idempotency_key=request.idempotency_key,
            reconciliation=_crawler_reconciliation(durable=durable, state="unknown"),
        )
    return result


def _crawler_reconciliation(*, durable: bool, state: str) -> RunnerObject:
    return {
        "required": durable,
        "state": state,
        "derived_as": "durable_attempt_store" if durable else "none",
        "durability": "injected_repository" if durable else "not_configured",
    }


def _runner_failure(code: str, message: str, *, site: str, **details: object) -> Failure:
    context: RunnerObject = {
        "boundary_class": "PURE_CONTRACT_FAILURE",
        "failure_family": source_library_contract_failures.name,
        "operation": "source_library.runner",
        "owner": "source_library.runner",
        "public_exception": "ValueError",
        "public_message": message,
        "site": site,
        "witness": _FAILURE_WITNESS,
    }
    for key, value in details.items():
        context[key] = value if _is_runner_value(value) else str(value)
    return source_library_contract_failures.fail(code, message, context)


def _raise_runner_failure(failure: Failure) -> NoReturn:
    context = failure.context or {}
    required = {
        "boundary_class",
        "failure_family",
        "operation",
        "owner",
        "public_exception",
        "public_message",
        "site",
        "witness",
    }
    if (
        not source_library_contract_failures.matches(failure)
        or required - set(context)
        or context.get("failure_family") != source_library_contract_failures.name
        or context.get("boundary_class") != "PURE_CONTRACT_FAILURE"
        or context.get("public_exception") != "ValueError"
        or context.get("public_message") != failure.message
    ):
        # kit:boundary owner=source_library.runner.failure_lift class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w01_source_export_failures
        raise TypeError(_RUNNER_FAILURE_LIFT_INVALID)
    # kit:boundary owner=source_library.runner.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=source_library.contract_failure witness=test:test_w01_source_export_failures
    raise ValueError(str(context["public_message"]))


def _ensure_handlers_registered() -> None:
    global _handlers_registered
    if _handlers_registered:
        return
    from . import adapters

    _handlers_registered = bool(adapters.__all__)


def resolve_credential(cred_name: str, project_key: str | None) -> str | None:
    normalized = (project_key or "").strip().upper()
    normalized = "".join(ch if ch.isalnum() else "_" for ch in normalized)
    if normalized:
        project_scoped = f"PROJECT_{normalized}_{cred_name}"
        value = os.getenv(project_scoped)
        if value:
            return value
    return os.getenv(cred_name)


def validate_params(params: Mapping[object, object], param_schema: Mapping[str, object]) -> None:
    required = param_schema.get("required", [])
    if not _is_object_list(required):
        return
    missing = [key for key in required if isinstance(key, str) and key not in params]
    if missing:
        _raise_runner_failure(
            _runner_failure(
                "required_params_missing",
                f"missing required params: {missing}",
                site="validate_params.required",
                missing=missing,
            )
        )


def _iter_string_values(value: object) -> list[str]:
    if isinstance(value, str):
        raw_values = [value]
    elif _is_object_iterable(value):
        raw_values = [str(v) for v in value if v is not None]
    else:
        return []
    return [v.strip() for v in raw_values if str(v).strip()]


def _normalize_identity(value: str | None) -> str:
    return str(value or "").strip().lower()


def _extract_gray_rollout_allowlist(execution_policy: Mapping[str, RunnerValue]) -> tuple[bool, set[str], set[str]]:
    def _collect_values(
        container: Mapping[str, RunnerValue],
        *,
        names: tuple[str, ...],
    ) -> tuple[bool, set[str]]:
        configured = False
        values: set[str] = set()
        for name in names:
            if name in container:
                configured = True
                for raw in _iter_string_values(container.get(name)):
                    values.add(_normalize_identity(raw))
        return configured, values

    rollout_nodes: list[Mapping[str, RunnerValue]] = [execution_policy]
    for key in ("gray_release", "gray_rollout", "rollout", "crawler_gray_release", "crawler_rollout"):
        value = execution_policy.get(key)
        if is_runner_mapping(value):
            rollout_nodes.append(value)

    project_keys: set[str] = set()
    item_keys: set[str] = set()
    configured = False

    project_fields = ("projects", "project_keys", "project_key_allowlist", "allow_projects")
    item_fields = ("items", "item_keys", "item_key_allowlist", "allow_items")

    for node in rollout_nodes:
        node_configured, node_projects = _collect_values(node, names=project_fields)
        configured = configured or node_configured
        project_keys.update(node_projects)

        node_configured, node_items = _collect_values(node, names=item_fields)
        configured = configured or node_configured
        item_keys.update(node_items)

        allowlist = node.get("allowlist")
        if is_runner_mapping(allowlist):
            configured = True
            _, nested_projects = _collect_values(allowlist, names=project_fields)
            _, nested_items = _collect_values(allowlist, names=item_fields)
            project_keys.update(nested_projects)
            item_keys.update(nested_items)

    return configured, project_keys, item_keys


def _is_crawler_rollout_allowed(
    *,
    execution_policy: Mapping[str, RunnerValue],
    project_key: str | None,
    item_key: str | None,
) -> bool:
    configured, project_allowlist, item_allowlist = _extract_gray_rollout_allowlist(execution_policy)
    if not configured:
        # Backward-compatible default: no rollout policy means keep crawler path.
        return True

    if "*" in project_allowlist or "*" in item_allowlist:
        return True

    normalized_project = _normalize_identity(project_key)
    normalized_item = _normalize_identity(item_key)
    return (normalized_project in project_allowlist) or (normalized_item in item_allowlist)


def _crawler_dispatch_request(
    *, params: Mapping[object, object], provider_config: RunnerObject, project_key: str | None, provider_type: str
) -> CrawlerDispatchRequest:
    spider = str(params.get("spider") or params.get("spider_name") or provider_config.get("spider") or "").strip()
    project = str(
        params.get("scrapy_project") or params.get("project") or provider_config.get("project") or project_key or ""
    ).strip()
    if not project:
        _raise_runner_failure(
            _runner_failure(
                "crawler_project_required",
                f"{provider_type} channel requires project/project_key",
                site="run_channel.crawler.project",
                provider_type=provider_type,
            )
        )
    if not spider:
        _raise_runner_failure(
            _runner_failure(
                "crawler_spider_required",
                f"{provider_type} channel requires spider/spider_name",
                site="run_channel.crawler.spider",
                provider_type=provider_type,
            )
        )
    return CrawlerDispatchRequest(
        provider=provider_type,
        project=project,
        spider=spider,
        arguments=_json_object(_mapping(params.get("arguments"))),
        settings=_json_object(_mapping(params.get("settings"))),
        version=_optional_string(params.get("version")),
        priority=_optional_int(params.get("priority"), name="priority"),
        job_id=_optional_string(params.get("job_id")),
        idempotency_key=_optional_string(params.get("idempotency_key")),
        attempt_id=_optional_string(params.get("attempt_id")),
    )


def _poll_crawler_readback(
    provider: CrawlerProvider, request: CrawlerDispatchRequest, dispatch: CrawlerDispatchResult
) -> ProviderReadbackResult | RunnerObject | None:
    if not dispatch.provider_job_id:
        return None
    try:
        return _observe_readback(
            typed_crawler_readback(
                attempt_id=request.attempt_id or request.request_digest or "unknown",
                provider_job_id=dispatch.provider_job_id,
                payload=provider.poll(
                    external_job_id=dispatch.provider_job_id,
                    project=request.project,
                    spider=request.spider,
                    options={"idempotency_key": request.idempotency_key, "attempt_id": request.attempt_id},
                ),
            )
        )
    except Exception:
        return None


def _crawler_output_ingest_request(
    *,
    channel: Mapping[str, object],
    config: RunnerObject,
    project_key: str,
    request: CrawlerDispatchRequest,
    provider_job_id: str,
    base_url: str | None,
) -> CrawlerOutputIngestRequest:
    return CrawlerOutputIngestRequest(
        provider_type=request.provider,
        project_key=project_key,
        provider_project=request.project,
        provider_job_id=provider_job_id,
        base_url=base_url,
        wait_timeout_seconds=_bounded_float(
            config.get("wait_timeout_seconds"),
            default=120.0,
            minimum=1.0,
            maximum=120.0,
            name="output_ingest.wait_timeout_seconds",
        ),
        poll_interval_seconds=_bounded_float(
            config.get("poll_interval_seconds"),
            default=0.5,
            minimum=0.1,
            maximum=5.0,
            name="output_ingest.poll_interval_seconds",
        ),
        source_name=str(config.get("source_name") or channel.get("channel_key") or f"crawler.{request.project}"),
        doc_type=str(config.get("doc_type") or "news"),
        enable_extraction=bool(config.get("enable_extraction", False)),
        max_items=_bounded_int(
            config.get("max_items"),
            default=100,
            minimum=1,
            maximum=1000,
            name="output_ingest.max_items",
        ),
    )


def _ingest_crawler_dispatch_output(
    *,
    provider: CrawlerProvider,
    channel: Mapping[str, object],
    config: RunnerObject,
    project_key: str | None,
    request: CrawlerDispatchRequest,
    dispatch: CrawlerDispatchResult,
) -> CrawlerOutputIngestResult | RunnerObject:
    if request.provider != "scrapy" or not project_key or not dispatch.provider_job_id:
        return CrawlerOutputIngestResult(
            status="failed", payload={"reason": "scrapy output ingest requires project_key and provider_job_id"}
        )
    base_url = _provider_base_url(provider)
    try:
        result = ingest_crawler_output(
            _crawler_output_ingest_request(
                channel=channel,
                config=config,
                project_key=project_key,
                request=request,
                provider_job_id=dispatch.provider_job_id,
                base_url=base_url,
            )
        )
        if type(result) is CrawlerOutputIngestResult and is_runner_mapping(result.payload):
            return result
        # Keep legacy or malformed port observations at their original exception boundary.
        return _mapping(result.to_plain())
    except Exception as exc:  # noqa: BLE001 - registered ingest effect boundary
        return CrawlerOutputIngestResult(status="failed", payload={"reason": str(exc)})


def _crawler_runner_result(
    *,
    dispatch: CrawlerDispatchResult,
    request: CrawlerDispatchRequest,
    channel_fields: RunnerObject,
    channel: Mapping[str, object],
    project_key: str | None,
    readback: ProviderReadbackResult | RunnerObject | None,
    output_ingest: CrawlerOutputIngestResult | RunnerObject | None,
    output_ingest_enabled: bool,
    durable: bool,
) -> RunnerObject:
    # Canonical effect values cross to the exported runner representation only here.
    readback_plain = dict(readback.to_plain()) if readback is not None and not isinstance(readback, dict) else readback
    ingest_plain = (
        _mapping(output_ingest.to_plain()) if isinstance(output_ingest, CrawlerOutputIngestResult) else output_ingest
    )
    status = str(dispatch.provider_status or "").strip().lower()
    acknowledged = is_crawler_dispatch_acknowledged(status)
    readback_kind = str(readback_plain.get("kind") or "") if readback_plain is not None else ""
    nested_readback = _mapping(readback_plain.get("readback")) if readback_plain is not None else {}
    terminal_status = str(nested_readback.get("terminal_status") or "").strip().lower()
    errors: list[str] = (
        [] if acknowledged or readback_kind == "terminal" else [f"crawler provider status: {status or 'unknown'}"]
    )
    import_result = _mapping(ingest_plain.get("import_result")) if ingest_plain is not None else {}
    counts = {
        name: _numeric_int(import_result.get(name), default=0, name=f"output_ingest.import_result.{name}")
        for name in ("inserted", "updated", "skipped")
    }
    output_ingest_status = str((ingest_plain or {}).get("status") or "").strip().lower()
    if output_ingest_enabled and output_ingest_status not in {"", "pending", "ingested", "finished_no_items"}:
        overall_status = "failed"
        errors = [
            f"crawler output ingest failed: {(ingest_plain or {}).get('reason') or output_ingest_status or 'unknown'}"
        ]
    elif output_ingest_status in {"ingested", "finished_no_items"}:
        overall_status = "completed"
    elif readback_kind == "terminal":
        overall_status = "completed" if terminal_status == "completed" else "failed"
        if overall_status == "failed":
            errors = [f"crawler provider terminal status: {terminal_status or 'unknown'}"]
    else:
        overall_status = "accepted" if acknowledged else "failed"
    reconciliation_state = {"terminal": "terminal_readback", "waiting": "waiting", "unavailable": "unavailable"}.get(
        readback_kind, "not_attempted" if acknowledged else "unknown"
    )
    return {
        "status": overall_status,
        **counts,
        "errors": errors,
        "provider_job_id": dispatch.provider_job_id,
        "provider_type": dispatch.provider_type,
        "provider_status": dispatch.provider_status,
        "attempt_count": dispatch.attempt_count,
        **channel_fields,
        "runtime_channel": _build_runtime_channel_meta(channel=channel, project_key=project_key),
        "output_ingest": ingest_plain,
        "dispatch_acknowledged": acknowledged,
        "attempt_id": request.attempt_id,
        "idempotency_key": request.idempotency_key,
        "terminal_readback": readback_plain,
        "readback": readback_plain,
        "acknowledgement": {"provider_status": dispatch.provider_status, "acknowledged": acknowledged},
        "reconciliation": _crawler_reconciliation(durable=durable, state=reconciliation_state),
    }


def _run_via_crawler_provider_registry(
    *, channel: Mapping[str, object], params: Mapping[object, object], project_key: str | None, provider_type: str
) -> RunnerObject:
    provider = resolve_crawler_provider(provider_type, channel=channel, params=params)
    provider_config = _mapping(channel.get("provider_config"))
    channel_fields: RunnerObject = {
        "provider_config": provider_config,
        "execution_policy": _mapping(channel.get("execution_policy")),
    }
    request = _crawler_dispatch_request(
        params=params, provider_config=provider_config, project_key=project_key, provider_type=provider_type
    )
    raw_durable_store = params.get("durable_store") or channel.get("durable_store")
    if raw_durable_store is not None and not _is_attempt_store(raw_durable_store):
        return _crawler_failure_result(
            _crawler_effect_failure(
                "scrapyd_transport",
                "crawler attempt store does not implement the durable store contract",
                site="app.services.source_library.runner.crawler_dispatch",
                provider_type=provider_type,
                reason_code="attempt_store_unavailable",
                observed_type=type(raw_durable_store).__name__,
            ),
            provider_type=provider_type,
            channel_fields=channel_fields,
            channel=channel,
            project_key=project_key,
            request=request,
            durable=True,
        )
    durable_store = raw_durable_store if _is_attempt_store(raw_durable_store) else None
    durable_bridge = (
        DurableCrawlerEffectBridge(provider=provider, store=durable_store) if durable_store is not None else None
    )
    dispatch = _dispatch_provider_effect(provider=provider, durable_bridge=durable_bridge, request=request)
    if isinstance(dispatch, Failure):
        return _crawler_failure_result(
            dispatch,
            provider_type=provider_type,
            channel_fields=channel_fields,
            request=request,
            channel=channel,
            project_key=project_key,
            durable=durable_bridge is not None,
        )
    if not isinstance(dispatch, CrawlerDispatchResult):
        return _crawler_failure_result(
            _crawler_effect_failure(
                "scrapyd_response_invalid",
                "crawler provider dispatch returned a non-canonical result",
                site="app.services.source_library.runner.crawler_dispatch",
                provider_type=provider_type,
                result_type=type(dispatch).__name__,
            ),
            provider_type=provider_type,
            channel_fields=channel_fields,
            channel=channel,
            project_key=project_key,
        )
    readback = _observe_readback(dispatch.terminal_readback)
    if readback is None:
        readback = _poll_crawler_readback(provider, request, dispatch)
    config = _mapping(params.get("output_ingest"))
    ingest = (
        _ingest_crawler_dispatch_output(
            provider=provider,
            channel=channel,
            config=config,
            project_key=project_key,
            request=request,
            dispatch=dispatch,
        )
        if config.get("enabled")
        else None
    )
    ingest_status = ingest.status if isinstance(ingest, CrawlerOutputIngestResult) else (ingest or {}).get("status")
    if ingest_status in {"ingested", "finished_no_items"}:
        refreshed = _poll_crawler_readback(provider, request, dispatch)
        if refreshed is not None:
            readback = refreshed
    return _crawler_runner_result(
        dispatch=dispatch,
        request=request,
        channel_fields=channel_fields,
        channel=channel,
        project_key=project_key,
        readback=readback,
        output_ingest=ingest,
        output_ingest_enabled=bool(config.get("enabled")),
        durable=durable_bridge is not None,
    )


def _build_runtime_channel_meta(*, channel: Mapping[str, object], project_key: str | None) -> RunnerObject:
    channel_key = str(channel.get("channel_key") or "").strip()
    normalized_project = str(project_key or "").strip().lower()
    normalized_channel = channel_key.lower()
    provider_type = str(channel.get("provider_type") or "").strip().lower()
    extra = _mapping(channel.get("extra"))
    explicit_tier = extra.get("source_tier")
    explicit_priority = extra.get("onboarding_priority")
    tiering = derive_source_tiering(
        provider=channel.get("provider"),
        provider_type=provider_type,
        explicit_tier=explicit_tier,
        explicit_priority=explicit_priority,
    )
    layer_boundary = default_source_layer_boundary(
        has_provider_dispatch=provider_type in _CRAWLER_PROVIDER_TYPES,
    )
    is_project_runtime = bool(normalized_project and normalized_channel == f"crawler.{normalized_project}")
    is_project_runtime = is_project_runtime or bool(
        normalized_project and normalized_channel.startswith(f"crawler.{normalized_project}.")
    )
    return {
        "channel_key": channel_key,
        "runtime_scope": "project_config" if is_project_runtime else "shared_config",
        "architecture_layer": "runtime_only",
        "source_tiering": {
            "tier": tiering.tier.value,
            "onboarding_priority": tiering.onboarding_priority.value,
            "reason": tiering.reason,
        },
        "layer_boundary": {
            "source_catalog": layer_boundary.source_catalog.value,
            "normalized_execution": layer_boundary.normalized_execution.value,
            "provider_dispatch": (
                layer_boundary.provider_dispatch.value if layer_boundary.provider_dispatch is not None else None
            ),
            "discovery": layer_boundary.discovery.value,
            "downstream_handoff": layer_boundary.downstream_handoff.value,
        },
    }


def run_channel(
    *,
    channel: Mapping[str, object],
    params: Mapping[object, object],
    project_key: str | None = None,
    item_key: str | None = None,
) -> RunnerObject:
    _ensure_handlers_registered()
    mutable_params = dict(params)
    mutable_channel = dict(channel)
    validate_single_source_guard(mutable_params)
    raw_credential_refs = channel.get("credential_refs")
    credential_refs: list[object] = raw_credential_refs if _is_object_list(raw_credential_refs) else []
    missing_creds = [c for c in credential_refs if isinstance(c, str) and resolve_credential(c, project_key) is None]
    if missing_creds:
        _raise_runner_failure(
            _runner_failure(
                "channel_credentials_missing",
                f"missing credentials for channel {channel.get('channel_key')}: {missing_creds}",
                site="run_channel.credentials",
                channel_key=channel.get("channel_key"),
                missing_credentials=missing_creds,
            )
        )

    validate_params(params=params, param_schema=_mapping(channel.get("param_schema")))

    provider_type = str(channel.get("provider_type") or "native").strip().lower()
    if provider_type in _CRAWLER_PROVIDER_TYPES:
        execution_policy = _mapping(channel.get("execution_policy"))
        if _is_crawler_rollout_allowed(
            execution_policy=execution_policy,
            project_key=project_key,
            item_key=item_key,
        ):
            return _run_via_crawler_provider_registry(
                channel=channel,
                params=params,
                project_key=project_key,
                provider_type=provider_type,
            )

    provider = str(channel.get("provider", "")).strip().lower()
    kind = str(channel.get("kind", "")).strip().lower()

    customization = get_project_customization(project_key)
    project_handlers = customization.get_channel_handlers()
    handler = project_handlers.get((provider, kind)) if project_handlers else None
    if handler is not None:
        return {
            str(key): _runner_json_value(value)
            for key, value in handler(_json_object(mutable_channel), _json_object(mutable_params), project_key).items()
        }

    handler = get(provider, kind)
    if handler is None:
        _raise_runner_failure(
            _runner_failure(
                "channel_provider_unsupported",
                f"unsupported channel provider/kind: {provider}/{kind}",
                site="run_channel.provider_kind",
                provider=provider,
                kind=kind,
            )
        )
    if provider == "policy" and not str(params.get("state") or "").strip():
        _raise_runner_failure(
            _runner_failure(
                "policy_state_required",
                "policy channel requires params.state",
                site="run_channel.policy.state",
            )
        )
    if provider == "market":
        keywords = params.get("keywords") or params.get("query_terms")
        if not isinstance(keywords, list) or not keywords:
            _raise_runner_failure(
                _runner_failure(
                    "market_keywords_required",
                    "market channel requires params.keywords or params.query_terms",
                    site="run_channel.market.keywords",
                )
            )
    if provider == "google_news":
        keywords = params.get("keywords")
        if isinstance(keywords, str):
            keywords = [keywords]
            mutable_params = {**mutable_params, "keywords": keywords}
        if not isinstance(keywords, list) or not keywords:
            _raise_runner_failure(
                _runner_failure(
                    "google_news_keywords_required",
                    "google_news requires params.keywords list",
                    site="run_channel.google_news.keywords",
                )
            )
    # Execute native/provider-specific handler and return as-is to keep full backward compatibility.
    # Any status unification for connectors should happen in higher-level adapters to avoid
    # changing existing handler return contracts expected by tests and downstream logic.
    return handler(mutable_params, project_key)


__all__ = ["run_channel", "resolve_credential", "validate_params", "is_runner_mapping"]
