from __future__ import annotations

from ..contracts import CollectRequest, CollectResult
from ..display_meta import build_display_meta


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

        dispatch = provider.dispatch(
            CrawlerDispatchRequest(
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
            )
        )

        provider_ok_statuses = {"ok", "queued", "scheduled", "running"}
        status = "completed" if dispatch.provider_status in provider_ok_statuses else "failed"
        errors = [] if status == "completed" else [{"message": f"crawler provider status: {dispatch.provider_status}"}]
        cr = CollectResult(
            channel=request.channel or "crawler.scrapy",
            status=status,
            inserted=0,
            updated=0,
            skipped=0,
            errors=errors,
            meta={
                "raw": dispatch.raw,
                "crawler": {
                    "provider_type": dispatch.provider_type,
                    "provider_status": dispatch.provider_status,
                    "provider_job_id": dispatch.provider_job_id,
                    "attempt_count": dispatch.attempt_count,
                    "project": project,
                    "spider": spider,
                },
            },
            provider_job_id=dispatch.provider_job_id,
            provider_type=dispatch.provider_type,
            provider_status=dispatch.provider_status,
            attempt_count=dispatch.attempt_count,
        )
        cr.display_meta = build_display_meta(request, cr, summary="Crawler scrapy 调度")
        return cr
