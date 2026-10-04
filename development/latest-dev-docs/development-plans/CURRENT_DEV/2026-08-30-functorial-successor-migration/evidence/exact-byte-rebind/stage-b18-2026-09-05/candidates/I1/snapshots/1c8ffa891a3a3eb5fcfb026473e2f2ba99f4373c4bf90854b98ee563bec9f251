from __future__ import annotations

import os
from typing import Any, Dict, NoReturn

from functorial_kit import Failure
from mrw_functorial_kit.core.application_failure_semantics import source_library_contract_failures
from mrw_functorial_kit.core.provider_port_failures import crawler_runtime_failures

from ...project_customization import get_project_customization
from ..crawlers.base import (
    CrawlerDispatchResult,
    is_crawler_dispatch_acknowledged,
    typed_crawler_readback,
)
from ..crawlers.durable_effect_bridge import DurableCrawlerEffectBridge
from .handler_registry import get
from .provider_ports import resolve_crawler_provider
from .single_source_guard import validate_single_source_guard
from .types import default_source_layer_boundary, derive_source_tiering

_REGISTERED = False
_CRAWLER_PROVIDER_TYPES = {"scrapy", "crawlee", "meltano"}
_FAILURE_WITNESS = "test:test_w01_source_export_failures"
_CRAWLER_FAILURE_WITNESS = "test:test_w03_crawler_failure_lifts"


def _crawler_effect_failure(code: str, message: str, *, site: str, **details: Any) -> Failure:
    context: dict[str, Any] = {
        "boundary_class": "PURE_CONTRACT_FAILURE",
        "failure_family": crawler_runtime_failures.name,
        "operation": "source_library.crawler_provider",
        "owner": site,
        "public_exception": "RuntimeError",
        "public_message": message,
        "site": site,
        "witness": _CRAWLER_FAILURE_WITNESS,
    }
    context.update(details)
    return crawler_runtime_failures.fail(code, message, context)


def _crawler_failure_result(failure: Failure, *, provider_type: str) -> Dict[str, Any]:
    if not crawler_runtime_failures.matches(failure):
        failure = _crawler_effect_failure(
            "scrapyd_transport",
            f"crawler provider returned an out-of-family failure: {failure.message}",
            site="app.services.source_library.runner.crawler_dispatch",
            provider_type=provider_type,
            observed_family=failure.family,
            observed_code=failure.code,
        )
    return {
        "status": "failed",
        "inserted": 0,
        "updated": 0,
        "skipped": 0,
        "errors": [
            {
                "code": failure.code,
                "family": failure.family,
                "message": failure.message,
                "context": dict(failure.context or {}),
            }
        ],
        "provider_job_id": None,
        "provider_type": provider_type,
        "provider_status": "failed",
        "attempt_count": None,
        "execution_policy": {},
        "provider_config": {},
        "runtime_channel": {},
        "output_ingest": None,
    }


def _runner_failure(code: str, message: str, *, site: str, **details: Any) -> Failure:
    context: dict[str, Any] = {
        "boundary_class": "PURE_CONTRACT_FAILURE",
        "failure_family": source_library_contract_failures.name,
        "operation": "source_library.runner",
        "owner": "source_library.runner",
        "public_exception": "ValueError",
        "public_message": message,
        "site": site,
        "witness": _FAILURE_WITNESS,
    }
    context.update(details)
    return source_library_contract_failures.fail(code, message, context)


def _raise_runner_failure(failure: Failure) -> NoReturn:
    context = failure.context or {}
    required = {"boundary_class", "failure_family", "operation", "owner", "public_exception", "public_message", "site", "witness"}
    if (
        not source_library_contract_failures.matches(failure)
        or required - set(context)
        or context.get("failure_family") != source_library_contract_failures.name
        or context.get("boundary_class") != "PURE_CONTRACT_FAILURE"
        or context.get("public_exception") != "ValueError"
        or context.get("public_message") != failure.message
    ):
        # kit:boundary owner=source_library.runner.failure_lift class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w01_source_export_failures
        raise TypeError("source-library runner failure lift context is incomplete or inconsistent")
    # kit:boundary owner=source_library.runner.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=source_library.contract_failure witness=test:test_w01_source_export_failures
    raise ValueError(str(context["public_message"]))


def _ensure_handlers_registered() -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    from . import adapters  # noqa: F401 - trigger handler registration (lazy to avoid circular import)
    _REGISTERED = True


def resolve_credential(cred_name: str, project_key: str | None) -> str | None:
    normalized = (project_key or "").strip().upper()
    normalized = "".join(ch if ch.isalnum() else "_" for ch in normalized)
    if normalized:
        project_scoped = f"PROJECT_{normalized}_{cred_name}"
        value = os.getenv(project_scoped)
        if value:
            return value
    return os.getenv(cred_name)


def validate_params(params: Dict[str, Any], param_schema: Dict[str, Any]) -> None:
    required = param_schema.get("required", [])
    if not isinstance(required, list):
        return
    missing = [key for key in required if key not in params]
    if missing:
        _raise_runner_failure(
            _runner_failure(
                "required_params_missing",
                f"missing required params: {missing}",
                site="validate_params.required",
                missing=missing,
            )
        )


def _iter_string_values(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_values = [value]
    elif isinstance(value, (list, tuple, set)):
        raw_values = [str(v) for v in value if v is not None]
    else:
        return []
    return [v.strip() for v in raw_values if str(v).strip()]


def _normalize_identity(value: str | None) -> str:
    return str(value or "").strip().lower()


def _extract_gray_rollout_allowlist(execution_policy: Dict[str, Any]) -> tuple[bool, set[str], set[str]]:
    def _collect_values(
        container: Dict[str, Any],
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

    rollout_nodes: list[Dict[str, Any]] = []
    if isinstance(execution_policy, dict):
        rollout_nodes.append(execution_policy)
        for key in ("gray_release", "gray_rollout", "rollout", "crawler_gray_release", "crawler_rollout"):
            value = execution_policy.get(key)
            if isinstance(value, dict):
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
        if isinstance(allowlist, dict):
            configured = True
            _, nested_projects = _collect_values(allowlist, names=project_fields)
            _, nested_items = _collect_values(allowlist, names=item_fields)
            project_keys.update(nested_projects)
            item_keys.update(nested_items)

    return configured, project_keys, item_keys


def _is_crawler_rollout_allowed(
    *,
    execution_policy: Dict[str, Any],
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


def _run_via_crawler_provider_registry(
    *,
    channel: Dict[str, Any],
    params: Dict[str, Any],
    project_key: str | None,
    provider_type: str,
) -> Dict[str, Any]:
    from ..crawlers.base import CrawlerDispatchRequest

    provider = resolve_crawler_provider(provider_type, channel=channel, params=params)

    provider_config = channel.get("provider_config")
    if not isinstance(provider_config, dict):
        provider_config = {}
    execution_policy = channel.get("execution_policy")
    if not isinstance(execution_policy, dict):
        execution_policy = {}

    spider = str(params.get("spider") or params.get("spider_name") or provider_config.get("spider") or "").strip()
    project = str(
        params.get("scrapy_project")
        or params.get("project")
        or provider_config.get("project")
        or project_key
        or ""
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

    request = CrawlerDispatchRequest(
        provider=provider_type,
        project=project,
        spider=spider,
        arguments=dict(params.get("arguments") or {}),
        settings=dict(params.get("settings") or {}),
        version=params.get("version"),
        priority=params.get("priority"),
        job_id=params.get("job_id"),
        idempotency_key=params.get("idempotency_key"),
        attempt_id=params.get("attempt_id"),
    )
    durable_store = params.get("durable_store") or channel.get("durable_store")
    durable_bridge = (
        DurableCrawlerEffectBridge(provider=provider, store=durable_store)
        if durable_store is not None
        else None
    )
    try:
        dispatch = (
            durable_bridge.dispatch(request)
            if durable_bridge is not None
            else provider.dispatch(request)
        )
    except Exception as exc:  # noqa: BLE001 - provider effect boundary
        failure = _crawler_effect_failure(
            "scrapyd_transport",
            f"crawler provider dispatch failed: {exc}",
            site="app.services.source_library.runner.crawler_dispatch",
            provider_type=provider_type,
            cause=exc,
        )
        result = _crawler_failure_result(failure, provider_type=provider_type)
        result["execution_policy"] = execution_policy
        result["provider_config"] = provider_config
        result["runtime_channel"] = _build_runtime_channel_meta(channel=channel, project_key=project_key)
        result["attempt_id"] = request.attempt_id
        result["idempotency_key"] = request.idempotency_key
        result["reconciliation"] = {
            "required": bool(durable_bridge is not None),
            "state": "unknown",
            "derived_as": "durable_attempt_store" if durable_bridge is not None else "none",
            "durability": "injected_repository" if durable_bridge is not None else "not_configured",
        }
        return result
    if isinstance(dispatch, Failure):
        result = _crawler_failure_result(dispatch, provider_type=provider_type)
        result["execution_policy"] = execution_policy
        result["provider_config"] = provider_config
        result["runtime_channel"] = _build_runtime_channel_meta(channel=channel, project_key=project_key)
        result["attempt_id"] = request.attempt_id
        result["idempotency_key"] = request.idempotency_key
        result["reconciliation"] = {
            "required": bool(durable_bridge is not None),
            "state": "unknown",
            "derived_as": "durable_attempt_store" if durable_bridge is not None else "none",
            "durability": "injected_repository" if durable_bridge is not None else "not_configured",
        }
        return result
    if not isinstance(dispatch, CrawlerDispatchResult):
        failure = _crawler_effect_failure(
            "scrapyd_response_invalid",
            "crawler provider dispatch returned a non-canonical result",
            site="app.services.source_library.runner.crawler_dispatch",
            provider_type=provider_type,
            result_type=type(dispatch).__name__,
        )
        result = _crawler_failure_result(failure, provider_type=provider_type)
        result["execution_policy"] = execution_policy
        result["provider_config"] = provider_config
        result["runtime_channel"] = _build_runtime_channel_meta(channel=channel, project_key=project_key)
        return result
    status = str(dispatch.provider_status or "").strip().lower()
    terminal_readback = dispatch.terminal_readback
    poll_fn = getattr(provider, "poll", None)
    if terminal_readback is None and dispatch.provider_job_id and callable(poll_fn):
        try:
            poll_payload = poll_fn(
                external_job_id=dispatch.provider_job_id,
                project=project,
                spider=spider,
                options={"idempotency_key": request.idempotency_key, "attempt_id": request.attempt_id},
            )
            terminal_readback = typed_crawler_readback(
                attempt_id=request.attempt_id or request.request_digest or "unknown",
                provider_job_id=dispatch.provider_job_id,
                payload=poll_payload,
            )
        except Exception:
            terminal_readback = None
    readback_plain = terminal_readback.to_plain() if hasattr(terminal_readback, "to_plain") else terminal_readback
    readback_kind = str(readback_plain.get("kind") or "") if isinstance(readback_plain, dict) else ""
    terminal_status = str(
        ((readback_plain.get("readback") or {}).get("terminal_status"))
        if isinstance(readback_plain, dict)
        else ""
    ).strip().lower()
    errors: list[str] = []
    if not is_crawler_dispatch_acknowledged(status) and readback_kind != "terminal":
        errors = [f"crawler provider status: {status or 'unknown'}"]
    # Source-library boundary stops at collection output; no structured ingest side effects here.
    inserted = 0
    updated = 0
    skipped = 0
    output_ingest: dict[str, Any] | None = None

    if readback_kind == "terminal":
        overall_status = "completed" if terminal_status == "completed" else "failed"
        if overall_status == "failed":
            errors = [f"crawler provider terminal status: {terminal_status or 'unknown'}"]
    elif is_crawler_dispatch_acknowledged(status):
        overall_status = "accepted"
    else:
        overall_status = "failed"
    reconciliation_state = (
        "terminal_readback"
        if readback_kind == "terminal"
        else "waiting"
        if readback_kind == "waiting"
        else "unavailable"
        if readback_kind == "unavailable"
        else "unknown"
        if not is_crawler_dispatch_acknowledged(status)
        else "not_attempted"
    )
    return {
        "status": overall_status,
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "provider_job_id": dispatch.provider_job_id,
        "provider_type": dispatch.provider_type,
        "provider_status": dispatch.provider_status,
        "attempt_count": dispatch.attempt_count,
        "execution_policy": execution_policy,
        "provider_config": provider_config,
        "runtime_channel": _build_runtime_channel_meta(channel=channel, project_key=project_key),
        "output_ingest": output_ingest,
        "dispatch_acknowledged": is_crawler_dispatch_acknowledged(status),
        "attempt_id": request.attempt_id,
        "idempotency_key": request.idempotency_key,
        "terminal_readback": readback_plain,
        "readback": readback_plain,
        "acknowledgement": {
            "provider_status": dispatch.provider_status,
            "acknowledged": is_crawler_dispatch_acknowledged(status),
        },
        "reconciliation": {
            "required": bool(durable_bridge is not None),
            "state": reconciliation_state,
            "derived_as": "durable_attempt_store" if durable_bridge is not None else "none",
            "durability": "injected_repository" if durable_bridge is not None else "not_configured",
        },
    }


def _build_runtime_channel_meta(*, channel: Dict[str, Any], project_key: str | None) -> Dict[str, Any]:
    channel_key = str(channel.get("channel_key") or "").strip()
    normalized_project = str(project_key or "").strip().lower()
    normalized_channel = channel_key.lower()
    provider_type = str(channel.get("provider_type") or "").strip().lower()
    extra = channel.get("extra")
    explicit_tier = extra.get("source_tier") if isinstance(extra, dict) else None
    explicit_priority = extra.get("onboarding_priority") if isinstance(extra, dict) else None
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
    channel: Dict[str, Any],
    params: Dict[str, Any],
    project_key: str | None = None,
    item_key: str | None = None,
) -> Dict[str, Any]:
    _ensure_handlers_registered()
    validate_single_source_guard(params)
    credential_refs = channel.get("credential_refs") or []
    if isinstance(credential_refs, list):
        missing_creds = [
            c for c in credential_refs if isinstance(c, str) and resolve_credential(c, project_key) is None
        ]
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

    validate_params(params=params, param_schema=channel.get("param_schema") or {})

    provider_type = str(channel.get("provider_type") or "native").strip().lower()
    if provider_type in _CRAWLER_PROVIDER_TYPES:
        execution_policy = channel.get("execution_policy")
        if not isinstance(execution_policy, dict):
            execution_policy = {}
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
        return handler(channel, params, project_key)

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
            params = {**params, "keywords": keywords}
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
    return handler(params, project_key)


__all__ = ["run_channel", "resolve_credential", "validate_params"]
