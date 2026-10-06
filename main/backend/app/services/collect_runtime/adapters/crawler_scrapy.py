from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
from typing import TypeGuard

from app.successor_runtime.capabilities.source_contracts import ProviderReadbackResult
from functorial_kit import Failure
from mrw_functorial_kit.core.provider_port_failures import (
    CrawlerRuntimeFailureCode,
    crawler_runtime_failures,
)

from ...crawlers.base import (
    CrawlerProvider,
    CrawlerDispatchResult,
    CrawlerJsonObject,
    CrawlerJsonValue,
    CrawlerPollOutcome,
    is_crawler_dispatch_acknowledged,
    typed_crawler_readback,
)
from ...crawlers.durable_effect_bridge import (
    CrawlerAttemptStore,
    DurableCrawlerEffectBridge,
)
from ..contracts import (
    CollectFailure,
    CollectJsonObject,
    CollectRequest,
    CollectResult,
    CollectStatus,
    CollectJsonValue,
)
from ..display_meta import build_display_meta


_CRAWLER_FAILURE_WITNESS = "test:test_w03_crawler_failure_lifts"


def _is_dispatch_result(value: object) -> TypeGuard[CrawlerDispatchResult]:
    return isinstance(value, CrawlerDispatchResult)


def _crawler_failure_code(value: str) -> CrawlerRuntimeFailureCode | None:
    match value:
        case "provider_not_registered":
            return "provider_not_registered"
        case "provider_poll_unsupported":
            return "provider_poll_unsupported"
        case "poll_project_required":
            return "poll_project_required"
        case "scrapyd_base_url_required":
            return "scrapyd_base_url_required"
        case "scrapyd_compose_file_missing":
            return "scrapyd_compose_file_missing"
        case "scrapyd_compose_unavailable":
            return "scrapyd_compose_unavailable"
        case "scrapyd_module_unavailable":
            return "scrapyd_module_unavailable"
        case "scrapyd_unavailable":
            return "scrapyd_unavailable"
        case "scrapyd_lazy_start_failed":
            return "scrapyd_lazy_start_failed"
        case "scrapyd_readiness_timeout":
            return "scrapyd_readiness_timeout"
        case "scrapyd_transport":
            return "scrapyd_transport"
        case "scrapyd_http_status":
            return "scrapyd_http_status"
        case "scrapyd_response_invalid":
            return "scrapyd_response_invalid"
        case "bootstrap_project_name_invalid":
            return "bootstrap_project_name_invalid"
        case "bootstrap_build_failed":
            return "bootstrap_build_failed"
        case "bootstrap_artifact_missing":
            return "bootstrap_artifact_missing"
        case "bootstrap_project_required":
            return "bootstrap_project_required"
        case "bootstrap_deploy_failed":
            return "bootstrap_deploy_failed"
        case _:
            return None


def _durable_bridge(
    provider: CrawlerProvider,
    store: CrawlerAttemptStore,
) -> DurableCrawlerEffectBridge:
    return DurableCrawlerEffectBridge(provider=provider, store=store)


def _crawler_failure(
    code: CrawlerRuntimeFailureCode,
    message: str,
    *,
    provider_type: str,
    **details: object,
) -> Failure:
    context: dict[str, object] = {
        "boundary_class": "PURE_CONTRACT_FAILURE",
        "failure_family": crawler_runtime_failures.name,
        "operation": "collect_runtime.crawler_scrapy",
        "owner": "collect_runtime.adapters.crawler_scrapy",
        "public_exception": "RuntimeError",
        "public_message": message,
        "site": "app.services.collect_runtime.adapters.crawler_scrapy.CrawlerScrapyAdapter.run",
        "witness": _CRAWLER_FAILURE_WITNESS,
        "provider_type": provider_type,
    }
    context.update(details)
    return crawler_runtime_failures.fail(code, message, context)


def _crawler_failure_error(failure: Failure) -> CollectFailure:
    code = (
        _crawler_failure_code(failure.code)
        if failure.family == "crawler.runtime.failure"
        else None
    )
    if code is None:
        failure = _crawler_failure(
            "scrapyd_transport",
            f"crawler provider returned an out-of-family failure: {failure.message}",
            provider_type="scrapy",
            observed_family=failure.family,
            observed_code=failure.code,
        )
        code = "scrapyd_transport"
    error: CollectFailure = {
        "code": code,
        "family": "crawler.runtime.failure",
        "message": failure.message,
        "context": _json_object(failure.context or {}),
    }
    return error


def _as_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool | int):
        return int(value)
    if isinstance(value, float | str):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    return None


def _is_json_mapping(value: object) -> TypeGuard[Mapping[object, object]]:
    return isinstance(value, Mapping)


def _is_json_sequence(value: object) -> TypeGuard[Sequence[object]]:
    return isinstance(value, list | tuple)


def _json_value(value: object) -> CollectJsonValue:
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, BaseException):
        return str(value)
    if _is_json_mapping(value):
        return _json_object(value)
    if _is_json_sequence(value):
        return [_json_value(item) for item in value]
    return str(value)


def _json_object(value: object) -> CollectJsonObject:
    if not _is_json_mapping(value):
        return {}
    normalized: CollectJsonObject = {}
    for raw_key, raw_value in value.items():
        key: object = raw_key
        item: object = raw_value
        normalized[str(key)] = _json_value(item)
    return normalized


def _json_dict(value: CollectJsonValue) -> CollectJsonObject:
    return value if isinstance(value, dict) else {}


def _crawler_json_value(value: CollectJsonValue) -> CrawlerJsonValue:
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, list):
        return [_crawler_json_value(item) for item in value]
    return {str(key): _crawler_json_value(item) for key, item in value.items()}


def _crawler_poll_outcome(value: object) -> CrawlerPollOutcome:
    if isinstance(value, Failure):
        return value
    if _is_json_mapping(value):
        return {
            str(key): _crawler_json_value(_json_value(item))
            for key, item in value.items()
        }
    return _crawler_failure(
        "scrapyd_response_invalid",
        "crawler provider poll returned a non-object result",
        provider_type="scrapy",
        result_type=type(value).__name__,
    )


class CrawlerScrapyAdapter:
    def __init__(self, *, attempt_store: CrawlerAttemptStore | None = None) -> None:
        self._attempt_store = attempt_store

    def run(self, request: CollectRequest) -> CollectResult:
        from ...crawlers import CrawlerDispatchRequest, get_provider

        options = request.options
        provider = get_provider("scrapy")
        if provider is None:
            raise ValueError("crawler provider 'scrapy' is not available; set SCRAPYD_BASE_URL")

        project = str(options.get("scrapy_project") or options.get("project") or request.project_key or "").strip()
        spider = str(options.get("spider") or options.get("spider_name") or "").strip()
        if not project:
            raise ValueError("crawler.scrapy requires options.scrapy_project or project_key")
        if not spider:
            raise ValueError("crawler.scrapy requires options.spider")

        arguments: CrawlerJsonObject = {
            str(k): _crawler_json_value(v)
            for k, v in _json_dict(options.get("arguments", {})).items()
            if str(k).strip()
        }
        if request.query_terms and "query_terms" not in arguments:
            arguments["query_terms"] = "\n".join(request.query_terms)
        if request.urls and "urls" not in arguments:
            arguments["urls"] = "\n".join(request.urls)
        if request.project_key and "project_key" not in arguments:
            arguments["project_key"] = request.project_key

        dispatch_request = CrawlerDispatchRequest(
            provider="scrapy",
            project=project,
            spider=spider,
            arguments=arguments,
            settings={
                str(k): _crawler_json_value(v)
                for k, v in _json_dict(options.get("settings", {})).items()
                if str(k).strip()
            },
            version=(str(options.get("version")).strip() or None) if options.get("version") is not None else None,
            priority=_as_int(options.get("priority")),
            job_id=(str(options.get("job_id")).strip() or None) if options.get("job_id") is not None else None,
            idempotency_key=(str(options.get("idempotency_key")).strip() or None)
            if options.get("idempotency_key") is not None
            else None,
            attempt_id=(str(options.get("attempt_id")).strip() or None)
            if options.get("attempt_id") is not None
            else None,
        )
        durable_bridge = (
            _durable_bridge(provider, self._attempt_store)
            if self._attempt_store is not None
            else None
        )
        try:
            dispatch_value: object = (
                durable_bridge.dispatch(dispatch_request)
                if durable_bridge is not None
                else provider.dispatch(dispatch_request)
            )
        except Exception as exc:  # noqa: BLE001 - crawler provider effect boundary
            dispatch_value = _crawler_failure(
                "scrapyd_transport",
                f"crawler provider dispatch failed: {exc}",
                provider_type="scrapy",
                cause=str(exc),
            )

        if isinstance(dispatch_value, Failure):
            dispatch_result: CrawlerDispatchResult | None = None
            status: CollectStatus = "failed"
            errors = [_crawler_failure_error(dispatch_value)]
        elif _is_dispatch_result(dispatch_value):
            dispatch_result = dispatch_value
            status = "accepted" if is_crawler_dispatch_acknowledged(dispatch_value.provider_status) else "failed"
            errors = [] if status == "accepted" else [
                _crawler_failure_error(
                    _crawler_failure(
                        "scrapyd_response_invalid",
                        f"crawler provider status was not acknowledged: {dispatch_value.provider_status}",
                        provider_type="scrapy",
                        provider_status=dispatch_value.provider_status,
                    )
                )
            ]
        else:
            dispatch_result = None
            failure = _crawler_failure(
                "scrapyd_response_invalid",
                "crawler provider dispatch returned a non-canonical result",
                provider_type="scrapy",
                result_type=type(dispatch_value).__name__,
            )
            status = "failed"
            errors = [_crawler_failure_error(failure)]

        terminal_readback: ProviderReadbackResult | None = (
            dispatch_result.terminal_readback if dispatch_result is not None else None
        )
        poll_fn = getattr(provider, "poll", None)
        if (
            terminal_readback is None
            and dispatch_result is not None
            and dispatch_result.provider_job_id
            and callable(poll_fn)
        ):
            try:
                poll_payload = _crawler_poll_outcome(
                    poll_fn(
                        external_job_id=dispatch_result.provider_job_id,
                        project=project,
                        spider=spider,
                        options={
                            "idempotency_key": dispatch_request.idempotency_key,
                            "attempt_id": dispatch_request.attempt_id,
                        },
                    )
                )
                terminal_readback = typed_crawler_readback(
                    attempt_id=dispatch_request.attempt_id or dispatch_request.request_digest or "unknown",
                    provider_job_id=dispatch_result.provider_job_id,
                    payload=poll_payload,
                )
            except Exception:
                terminal_readback = None
        readback_plain: object = terminal_readback.to_plain() if terminal_readback is not None else terminal_readback
        readback_json = _json_value(readback_plain)
        if isinstance(readback_plain, dict):
            plain = _json_object(readback_plain)
        else:
            plain = {}
        if plain.get("kind") == "terminal":
            nested = plain.get("readback")
            terminal_status = str((_json_dict(nested)).get("terminal_status") or "").lower()
            status = "completed" if terminal_status == "completed" else "failed"
            if terminal_status == "completed":
                errors = []
            elif not errors:
                errors = [
                    _crawler_failure_error(
                        _crawler_failure(
                            "scrapyd_transport",
                            f"crawler provider terminal status: {terminal_status or 'unknown'}",
                            provider_type="scrapy",
                            terminal_status=terminal_status,
                        )
                    )
                ]

        if dispatch_result is None:
            raw: CollectJsonObject = {}
            provider_type = "scrapy"
            provider_status = "failed"
            provider_job_id = None
            attempt_count = None
        else:
            raw = _json_object(dispatch_result.raw)
            provider_type = dispatch_result.provider_type
            provider_status = dispatch_result.provider_status
            provider_job_id = dispatch_result.provider_job_id
            attempt_count = dispatch_result.attempt_count
        cr = CollectResult(
            channel=request.channel or "crawler.scrapy",
            status=status,
            inserted=0,
            updated=0,
            skipped=0,
            errors=errors,
            meta={
                "raw": raw,
                "crawler": {
                    "provider_type": provider_type,
                    "provider_status": provider_status,
                    "provider_job_id": provider_job_id,
                    "attempt_count": attempt_count,
                    "project": project,
                    "spider": spider,
                    "dispatch_acknowledged": bool(
                        dispatch_result is not None and is_crawler_dispatch_acknowledged(dispatch_result.provider_status)
                    ),
                    "idempotency_key": dispatch_request.idempotency_key,
                    "attempt_id": dispatch_request.attempt_id,
                    "terminal_readback": readback_json,
                    "readback": readback_json,
                    "acknowledgement": {
                        "provider_status": provider_status,
                        "acknowledged": bool(
                            dispatch_result is not None
                            and is_crawler_dispatch_acknowledged(dispatch_result.provider_status)
                        ),
                    },
                    "reconciliation": {
                        "required": bool(durable_bridge is not None),
                        "derived_as": "durable_attempt_store" if durable_bridge is not None else "none",
                        "durability": "injected_repository" if durable_bridge is not None else "not_configured",
                        "state": (
                            "terminal_readback"
                            if plain.get("kind") == "terminal"
                            else "waiting"
                            if plain.get("kind") == "waiting"
                            else "unavailable"
                            if plain.get("kind") == "unavailable"
                            else "unknown"
                            if dispatch_result is not None
                            and not is_crawler_dispatch_acknowledged(dispatch_result.provider_status)
                            else "not_attempted"
                        ),
                    },
                },
            },
            provider_job_id=provider_job_id,
            provider_type=provider_type,
            provider_status=provider_status,
            attempt_count=attempt_count,
        )
        cr.display_meta = build_display_meta(request, cr, summary="Crawler scrapy 调度")
        return cr
