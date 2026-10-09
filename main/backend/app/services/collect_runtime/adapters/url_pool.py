from __future__ import annotations

from dataclasses import replace

from app.successor_runtime.language.sync import interpret_ordered_sync
from app.successor_runtime.capabilities.acquisition_url import (
    UrlSingleUrlOutcome,
)

from ..contracts import (
    CollectFailure,
    CollectJsonObject,
    CollectStatus,
    CollectRequest,
    CollectResult,
)
from ..display_meta import build_display_meta


def _json_object(value: object) -> CollectJsonObject:
    from ..contracts import source_library_compat_response

    return source_library_compat_response(value)


def _integer_value(value: object) -> int:
    if isinstance(value, (int, float, str)):
        return int(value)
    raise TypeError("URL pool collection count must be an integer")


def _status(value: object) -> CollectStatus:
    raw = str(value or "").strip().lower()
    if raw == "failed":
        return "failed"
    if raw == "cancelled":
        return "cancelled"
    if raw in {"success", "degraded_success", "completed"}:
        return "completed"
    return "unknown"


def _target(source_context: CollectJsonObject) -> CollectJsonObject | None:
    value = source_context.get("url_pool_target")
    return value if isinstance(value, dict) else None


def _context(source_context: CollectJsonObject) -> CollectJsonObject:
    value = source_context.get("url_pool_context")
    return value if isinstance(value, dict) else {}


def _text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def project_url_single_url_outcome(
    outcome: UrlSingleUrlOutcome,
    request: CollectRequest,
) -> CollectResult:
    """Project a typed single-URL outcome back to the legacy result surface."""

    errors: list[CollectFailure] = []
    if outcome.error:
        errors.append({"code": "url_pool_execution_failed", "message": outcome.error})
    result = CollectResult(
        flow=request.flow,
        channel=request.channel or "url_pool",
        status=outcome.status,
        inserted=outcome.inserted,
        updated=outcome.updated,
        skipped=outcome.skipped,
        errors=errors,
        provider_job_id=str(outcome.material_id) if outcome.material_id is not None else None,
    )
    result.display_meta = build_display_meta(request, result, summary="URL 池抓取并写入文档")
    return result


def _failures(result: CollectJsonObject) -> list[CollectFailure]:
    failures: list[CollectFailure] = []
    raw_errors = result.get("errors")
    if isinstance(raw_errors, list):
        for item in raw_errors:
            message = str(item or "").strip()
            if not message:
                continue
            failure: CollectFailure = {
                "code": "url_pool_execution_failed",
                "message": message,
            }
            failures.append(failure)
    if not failures and _status(result.get("status")) == "failed":
        failure = {
            "code": "url_pool_execution_failed",
            "message": str(result.get("error") or "URL execution failed"),
        }
        failures.append(failure)
    return failures


class UrlPoolAdapter:
    def expand(self, request: CollectRequest) -> list[CollectRequest]:
        """Prepare single-URL child requests without executing any of them."""
        from ...ingest.url_pool import prepare_url_list_targets, prepare_url_pool_targets

        base_context = dict(request.source_context or {})
        if request.urls:
            targets, diagnostics = prepare_url_list_targets(
                urls=list(request.urls),
                query_terms=list(request.query_terms or []),
                extra_params=dict(request.options or {}),
            )
            prepared = [
                replace(
                    request,
                    urls=[target_url],
                    limit=1,
                    source_context={
                        **base_context,
                        "url_pool_prepare": diagnostics,
                        "url_pool_target": target,
                        "url_pool_context": {
                            "mode": "list",
                            "project_key": request.project_key,
                            "entry_type": target.get("entry_type"),
                            "site_seed": bool(target.get("is_site_seed")),
                            "domain": target.get("domain"),
                            "source_url": target.get("from_url"),
                        },
                    },
                )
                for target_url, target in targets
            ]
        else:
            targets, diagnostics = prepare_url_pool_targets(
                scope=str(request.scope or "effective"),
                project_key=request.project_key,
                domain=_text(request.options.get("domain")),
                source_filter=(
                    _text(request.options.get("source_filter"))
                    or _text(request.options.get("source"))
                ),
                limit=int(request.limit or 50),
                query_terms=list(request.query_terms or []),
                extra_params=dict(request.options or {}),
            )
            prepared = [
                replace(
                    request,
                    urls=[target_url],
                    limit=1,
                    scope=None,
                    source_context={
                        **base_context,
                        "url_pool_prepare": diagnostics,
                        "url_pool_target": target,
                        "url_pool_context": {
                            "mode": "pool",
                            "project_key": request.project_key,
                            "entry_type": target.get("entry_type"),
                            "site_seed": bool(target.get("is_site_seed")),
                            "scope": pool_item.get("scope"),
                            "source": pool_item.get("source"),
                            "domain": pool_item.get("domain") or target.get("domain"),
                            "source_ref": pool_item.get("source_ref"),
                        },
                    },
                )
                for target_url, target, pool_item in targets
            ]
        return prepared

    def run(self, request: CollectRequest) -> CollectResult:
        from ...ingest.url_pool import execute_single_url_kernel

        query_terms = list(request.query_terms or [])
        extra_params: dict[str, object] = dict(request.options or {})
        if request.urls:
            if len(request.urls) != 1:
                return self._run_inline_batch(request)
            raw = execute_single_url_kernel(
                url=request.urls[0],
                project_key=request.project_key,
                query_terms=query_terms,
                extra_params=extra_params,
                enable_extraction=bool(request.options.get("enable_extraction", True)),
                target=dict(_target(request.source_context) or {}),
                context=dict(_context(request.source_context)),
            )
            result = _json_object(raw)
        else:
            return self._run_inline_batch(request)
        cr = CollectResult(
            flow=request.flow,
            channel=request.channel or "url_pool",
            status=_status(result.get("status")),
            inserted=_integer_value(result.get("inserted") or 0),
            updated=_integer_value(result.get("updated") or 0),
            skipped=_integer_value(result.get("skipped") or 0),
            errors=_failures(result),
            meta={"raw": result},
        )
        cr.display_meta = build_display_meta(request, cr, summary="URL 池抓取并写入文档")
        return cr

    def _run_single_request(
        self,
        request: CollectRequest,
    ) -> tuple[CollectJsonObject, list[CollectFailure]]:
        from ...ingest.url_pool import execute_single_url_kernel

        raw = execute_single_url_kernel(
            url=request.urls[0],
            project_key=request.project_key,
            query_terms=list(request.query_terms or []),
            extra_params=dict(request.options or {}),
            enable_extraction=bool(request.options.get("enable_extraction", True)),
            target=dict(_target(request.source_context) or {}),
            context=dict(_context(request.source_context)),
        )
        result = _json_object(raw)
        return result, _failures(result)

    def _continue_after_classified_leaf(
        self,
        _result: tuple[CollectJsonObject, list[CollectFailure]],
    ) -> bool:
        # URL collection continues after classified leaf failures so partial
        # ordering and every failed result remain visible to the domain fold.
        return True

    def _run_inline_batch(self, request: CollectRequest) -> CollectResult:
        """Execute prepared children in order and fold their actual kernel results."""

        children = self.expand(request)
        leaf_results = interpret_ordered_sync(
            children,
            initial_value=None,
            invoke=lambda child, _previous: self._run_single_request(child),
            continue_after=self._continue_after_classified_leaf,
            output_value=lambda _result: None,
        )
        raw_results: list[CollectJsonObject] = []
        failures: list[CollectFailure] = []
        for result, child_failures in leaf_results:
            raw_results.append(result)
            failures.extend(child_failures)

        rejection_breakdown: CollectJsonObject = {}
        for result in raw_results:
            breakdown = result.get("rejection_breakdown")
            if isinstance(breakdown, dict):
                for key, count in breakdown.items():
                    current = _integer_value(rejection_breakdown.get(key, 0))
                    rejection_breakdown[key] = current + _integer_value(count)
        result: CollectJsonObject = {
            "inserted": sum(_integer_value(item.get("inserted") or 0) for item in raw_results),
            "inserted_valid": sum(_integer_value(item.get("inserted_valid") or 0) for item in raw_results),
            "updated": sum(_integer_value(item.get("updated") or 0) for item in raw_results),
            "skipped": sum(_integer_value(item.get("skipped") or 0) for item in raw_results),
            "rejected_count": sum(_integer_value(item.get("rejected_count") or 0) for item in raw_results),
            "rejection_breakdown": rejection_breakdown,
            "urls": len(children),
            "queued": 0,
            "debug": {
                "mode": "list" if request.urls else "pool",
                "dispatch_mode": "inline",
                "url_details": [
                    {
                        "url": child.urls[0] if child.urls else None,
                        "status": item.get("status"),
                        "material_id": item.get("material_id"),
                        "error": item.get("error"),
                    }
                    for child, item in zip(children, raw_results, strict=True)
                ],
                "errors": [failure.get("message") for failure in failures],
            },
        }
        cr = CollectResult(
            flow=request.flow,
            channel=request.channel or "url_pool",
            inserted=_integer_value(result.get("inserted") or 0),
            updated=_integer_value(result.get("updated") or 0),
            skipped=_integer_value(result.get("skipped") or 0),
            errors=failures,
            meta={"raw": result},
        )
        cr.display_meta = build_display_meta(request, cr, summary="URL 池抓取并写入文档")
        return cr
