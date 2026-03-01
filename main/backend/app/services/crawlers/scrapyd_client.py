from __future__ import annotations

from typing import Any

import httpx


class ScrapydClient:
    def __init__(self, *, base_url: str, timeout: float = 10.0) -> None:
        base = str(base_url or "").strip()
        if not base:
            raise ValueError("scrapyd base_url is required")
        self.base_url = base.rstrip("/")
        self.timeout = float(timeout)

    def _post(self, path: str, data: Any) -> dict[str, Any]:
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(f"{self.base_url}{path}", data=data)
            resp.raise_for_status()
            body = resp.json()
            return body if isinstance(body, dict) else {"status": "error", "body": body}

    def schedule_spider(
        self,
        *,
        project: str,
        spider: str,
        arguments: dict[str, Any] | None = None,
        settings: dict[str, Any] | None = None,
        version: str | None = None,
        priority: int | None = None,
        job_id: str | None = None,
    ) -> dict[str, Any]:
        payload: list[tuple[str, str]] = [("project", project), ("spider", spider)]
        if version:
            payload.append(("_version", version))
        if priority is not None:
            payload.append(("priority", str(int(priority))))
        if job_id:
            payload.append(("jobid", job_id))

        # Scrapyd accepts spider args as plain fields and settings prefixed by "setting=".
        for key, value in (arguments or {}).items():
            if value is None:
                continue
            payload.append((str(key), str(value)))
        for key, value in (settings or {}).items():
            if value is None:
                continue
            payload.append(("setting", f"{key}={value}"))

        return self._post("/schedule.json", payload)

    def list_jobs(self, *, project: str) -> dict[str, Any]:
        return self._post("/listjobs.json", {"project": project})

    def cancel_job(self, *, project: str, job_id: str) -> dict[str, Any]:
        return self._post("/cancel.json", {"project": project, "job": job_id})


__all__ = ["ScrapydClient"]
