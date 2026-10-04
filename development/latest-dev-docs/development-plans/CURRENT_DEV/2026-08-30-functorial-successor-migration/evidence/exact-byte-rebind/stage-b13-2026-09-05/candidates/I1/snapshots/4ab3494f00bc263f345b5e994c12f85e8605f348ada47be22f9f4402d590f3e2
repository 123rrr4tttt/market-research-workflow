from __future__ import annotations

from typing import Any

from functorial_kit import Failure
from mrw_functorial_kit.core.provider_port_failures import crawler_runtime_failures

from ...crawlers.base import (
    CrawlerDispatchResult,
    is_crawler_dispatch_acknowledged,
    typed_crawler_readback,
)
from ...crawlers.durable_effect_bridge import DurableCrawlerEffectBridge
from ..contracts import CollectRequest, CollectResult
from ..display_meta import build_display_meta


_CRAWLER_FAILURE_WITNESS = "test:test_w03_crawler_failure_lifts"


def _crawler_failure(code: str, message: str, *, provider_type: str, **details: Any) -> Failure:
    context: dict[str, Any] = {
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


def _crawler_failure_error(failure: Failure) -> dict[str, Any]:
    if not crawler_runtime_failures.matches(failure):
        failure = _crawler_failure(
            "scrapyd_transport",
            f"crawler provider returned an out-of-family failure: {failure.message}",
            provider_type="scrapy",
            observed_family=failure.family,
            observed_code=failure.code,
        )
    return {
        "code": failure.code,
        "family": failure.family,
        "message": failure.message,
        "context": dict(failure.context or {}),
    }


def _normalize_dict(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}


def _as_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


class CrawlerScrapyAdapter:
    def run(self, request: CollectRequest) -> CollectResult:
        from ...crawlers import CrawlerDispatchRequest, get_provider

        options = _normalize_dict(request.options)
        provider = get_provider("scrapy")
        if provider is None:
            raise ValueError("crawler provider 'scrapy' is not available; set SCRAPYD_BASE_URL")

        project = str(options.get("scrapy_project") or options.get("project") or request.project_key or "").strip()
        spider = str(options.get("spider") or options.get("spider_name") or "").strip()
        if not project:
            raise ValueError("crawler.scrapy requires options.scrapy_project or project_key")
        if not spider:
            raise ValueError("crawler.scrapy requires options.spider")

        arguments = {
            str(k): v
            for k, v in _normalize_dict(options.get("arguments")).items()
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
                str(k): v
                for k, v in _normalize_dict(options.get("settings")).items()
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
        durable_store = options.get("durable_store")
        durable_bridge = (
            DurableCrawlerEffectBridge(provider=provider, store=durable_store)
            if durable_store is not None
            else None
        )
        try:
            dispatch = (
                durable_bridge.dispatch(dispatch_request)
                if durable_bridge is not None
                else provider.dispatch(dispatch_request)
            )
        except Exception as exc:  # noqa: BLE001 - crawler provider effect boundary
            dispatch = _crawler_failure(
                "scrapyd_transport",
                f"crawler provider dispatch failed: {exc}",
                provider_type="scrapy",
                cause=exc,
            )

        if isinstance(dispatch, Failure):
            dispatch_result: CrawlerDispatchResult | None = None
            status = "failed"
            errors = [_crawler_failure_error(dispatch)]
        elif isinstance(dispatch, CrawlerDispatchResult):
            dispatch_result = dispatch
            status = "accepted" if is_crawler_dispatch_acknowledged(dispatch.provider_status) else "failed"
            errors = [] if status == "accepted" else [
                _crawler_failure_error(
                    _crawler_failure(
                        "scrapyd_response_invalid",
                        f"crawler provider status was not acknowledged: {dispatch.provider_status}",
                        provider_type="scrapy",
                        provider_status=dispatch.provider_status,
                    )
                )
            ]
        else:
            dispatch_result = None
            failure = _crawler_failure(
                "scrapyd_response_invalid",
                "crawler provider dispatch returned a non-canonical result",
                provider_type="scrapy",
                result_type=type(dispatch).__name__,
            )
            status = "failed"
            errors = [_crawler_failure_error(failure)]

        terminal_readback = dispatch_result.terminal_readback if dispatch_result is not None else None
        poll_fn = getattr(provider, "poll", None)
        if terminal_readback is None and dispatch_result is not None and dispatch_result.provider_job_id and callable(poll_fn):
            try:
                poll_payload = poll_fn(
                    external_job_id=dispatch_result.provider_job_id,
                    project=project,
                    spider=spider,
                    options={"idempotency_key": dispatch_request.idempotency_key, "attempt_id": dispatch_request.attempt_id},
                )
                terminal_readback = typed_crawler_readback(
                    attempt_id=dispatch_request.attempt_id or dispatch_request.request_digest or "unknown",
                    provider_job_id=dispatch_result.provider_job_id,
                    payload=poll_payload,
                )
            except Exception:
                terminal_readback = None
        readback_plain = terminal_readback.to_plain() if hasattr(terminal_readback, "to_plain") else terminal_readback
        if isinstance(readback_plain, dict) and readback_plain.get("kind") == "terminal":
            terminal_status = str((readback_plain.get("readback") or {}).get("terminal_status") or "").lower()
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
            raw: dict[str, Any] = {}
            provider_type = "scrapy"
            provider_status = "failed"
            provider_job_id = None
            attempt_count = None
        else:
            raw = dispatch_result.raw
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
                    "terminal_readback": readback_plain,
                    "readback": readback_plain,
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
                            if isinstance(readback_plain, dict) and readback_plain.get("kind") == "terminal"
                            else "waiting"
                            if isinstance(readback_plain, dict) and readback_plain.get("kind") == "waiting"
                            else "unavailable"
                            if isinstance(readback_plain, dict) and readback_plain.get("kind") == "unavailable"
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
