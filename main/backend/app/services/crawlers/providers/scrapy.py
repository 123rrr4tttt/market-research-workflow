from __future__ import annotations

import os

from ..base import (
    CrawlerDispatchRequest,
    CrawlerDispatchResult,
    CrawlerJsonObject,
    CrawlerJsonValue,
)
from ..registry import crawler_failure, raise_crawler_contract_failure
from ..scrapyd_bootstrap import (
    ensure_bootstrap_project_deployed,
    is_bootstrap_recoverable_schedule_error,
)
from ..scrapyd_client import ScrapydClient
from ..scrapyd_runtime import ensure_scrapyd_ready, resolve_scrapyd_base_url


def _json_value(value: CrawlerJsonValue) -> CrawlerJsonValue:
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    return value


def _json_object(value: CrawlerJsonValue) -> CrawlerJsonObject:
    normalized = _json_value(value)
    return normalized if isinstance(normalized, dict) else {}


def _job_rows(value: CrawlerJsonValue) -> list[CrawlerJsonObject]:
    if not isinstance(value, list):
        return []
    return [_json_object(item) for item in value if isinstance(item, dict)]


class ScrapyCrawlerProvider:
    provider_type = "scrapy"

    def __init__(self, *, base_url: str | None = None, timeout: float | None = None) -> None:
        configured_base_url = resolve_scrapyd_base_url(base_url or os.getenv("SCRAPYD_BASE_URL"))
        self.client = ScrapydClient(
            base_url=configured_base_url,
            timeout=float(timeout if timeout is not None else os.getenv("SCRAPYD_TIMEOUT", 10.0)),
        )

    def dispatch(self, request: CrawlerDispatchRequest) -> CrawlerDispatchResult:
        ensure_scrapyd_ready(base_url=self.client.base_url)
        first_response = _json_object(
            self.client.schedule_spider(
                project=request.project,
                spider=request.spider,
                arguments=dict(request.arguments or {}),
                settings=dict(request.settings or {}),
                version=request.version,
                priority=request.priority,
                job_id=request.job_id,
            )
        )
        response = first_response
        attempt_count = 1
        raw: CrawlerJsonObject = {"schedule": first_response}
        if is_bootstrap_recoverable_schedule_error(
            first_response,
            project=request.project,
            spider=request.spider,
        ):
            raw["schedule_first"] = first_response
            raw.pop("schedule", None)
            try:
                bootstrap = ensure_bootstrap_project_deployed(
                    self.client,
                    project=request.project,
                    spider=request.spider,
                )
                raw["bootstrap"] = _json_object(bootstrap)
                response = _json_object(
                    self.client.schedule_spider(
                        project=request.project,
                        spider=request.spider,
                        arguments=dict(request.arguments or {}),
                        settings=dict(request.settings or {}),
                        version=request.version,
                        priority=request.priority,
                        job_id=request.job_id,
                    )
                )
                raw["schedule_retry"] = response
                attempt_count = 2
            except Exception as exc:  # noqa: BLE001
                raw["bootstrap_error"] = str(exc)
                response = first_response

        status = str(response.get("status") or "unknown").strip().lower()
        return CrawlerDispatchResult(
            provider_type=self.provider_type,
            provider_status=status,
            provider_job_id=str(response.get("jobid") or "").strip() or None,
            attempt_count=attempt_count,
            raw=raw,
        )

    def poll(
        self,
        *,
        external_job_id: str,
        project: str | None = None,
        spider: str | None = None,
        options: CrawlerJsonObject | None = None,
    ) -> CrawlerJsonObject:
        target_project = str(project or "").strip()
        if not target_project:
            failure = crawler_failure(
                "poll_project_required",
                "poll requires project for scrapy provider",
                operation="scrapy.poll",
                site="app.services.crawlers.providers.scrapy.ScrapyCrawlerProvider.poll",
            )
            raise_crawler_contract_failure(failure)
        ensure_scrapyd_ready(base_url=self.client.base_url)
        response = _json_object(self.client.list_jobs(project=target_project))
        job_id = str(external_job_id or "").strip()
        running = _job_rows(response.get("running"))
        pending = _job_rows(response.get("pending"))
        finished = _job_rows(response.get("finished"))
        all_jobs = running + pending + finished
        matched = next((row for row in all_jobs if str(row.get("id") or "").strip() == job_id), None)
        status = "unavailable"
        if matched is not None:
            if matched in running:
                status = "running"
            elif matched in pending:
                status = "queued"
            else:
                status = finished_job_status(matched)
        return {
            "external_provider": self.provider_type,
            "external_job_id": job_id,
            "provider_status": status,
            "attempt_count": 1,
            "project": target_project,
            "spider": spider,
            "raw": {"listjobs": response, "matched": matched, "options": dict(options or {})},
        }


def finished_job_status(job: CrawlerJsonObject) -> str:
    """Map Scrapyd's finished row to the closed crawler terminal vocabulary."""

    observed = " ".join(
        str(job.get(key) or "").strip().lower()
        for key in ("status", "state", "close_reason", "finish_reason", "reason", "error")
    )
    if any(token in observed for token in ("cancel", "canceled", "killed", "stopped", "shutdown")):
        return "cancelled"
    if any(token in observed for token in ("fail", "error", "exception", "crash")):
        return "failed"
    return "completed"


__all__ = ["ScrapyCrawlerProvider", "finished_job_status"]
