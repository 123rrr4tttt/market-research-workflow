from __future__ import annotations

import os

from ..base import CrawlerDispatchRequest, CrawlerDispatchResult
from ..scrapyd_bootstrap import (
    ensure_bootstrap_project_deployed,
    is_bootstrap_recoverable_schedule_error,
)
from ..scrapyd_client import ScrapydClient
from ..scrapyd_runtime import ensure_scrapyd_ready


class ScrapyCrawlerProvider:
    provider_type = "scrapy"

    def __init__(self, *, base_url: str | None = None, timeout: float | None = None) -> None:
        configured_base_url = ensure_scrapyd_ready(base_url=base_url or os.getenv("SCRAPYD_BASE_URL"))
        self.client = ScrapydClient(
            base_url=configured_base_url,
            timeout=float(timeout if timeout is not None else os.getenv("SCRAPYD_TIMEOUT", 10.0)),
        )

    def dispatch(self, request: CrawlerDispatchRequest) -> CrawlerDispatchResult:
        first_response = self.client.schedule_spider(
            project=request.project,
            spider=request.spider,
            arguments=dict(request.arguments or {}),
            settings=dict(request.settings or {}),
            version=request.version,
            priority=request.priority,
            job_id=request.job_id,
        )
        response = first_response
        attempt_count = 1
        raw: dict[str, object] = {"schedule": first_response}
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
                raw["bootstrap"] = bootstrap
                response = self.client.schedule_spider(
                    project=request.project,
                    spider=request.spider,
                    arguments=dict(request.arguments or {}),
                    settings=dict(request.settings or {}),
                    version=request.version,
                    priority=request.priority,
                    job_id=request.job_id,
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
        options: dict | None = None,
    ) -> dict:
        target_project = str(project or "").strip()
        if not target_project:
            raise ValueError("poll requires project for scrapy provider")
        response = self.client.list_jobs(project=target_project)
        job_id = str(external_job_id or "").strip()
        running = response.get("running") if isinstance(response.get("running"), list) else []
        pending = response.get("pending") if isinstance(response.get("pending"), list) else []
        finished = response.get("finished") if isinstance(response.get("finished"), list) else []
        all_jobs = running + pending + finished
        matched = next((x for x in all_jobs if str((x or {}).get("id") or "").strip() == job_id), None)
        status = "unknown"
        if matched is not None:
            if matched in running:
                status = "running"
            elif matched in pending:
                status = "queued"
            else:
                status = "completed"
        return {
            "external_provider": self.provider_type,
            "external_job_id": job_id,
            "provider_status": status,
            "attempt_count": 1,
            "project": target_project,
            "spider": spider,
            "raw": {"listjobs": response, "matched": matched, "options": dict(options or {})},
        }


__all__ = ["ScrapyCrawlerProvider"]
