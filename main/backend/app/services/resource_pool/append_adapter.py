"""Default adapter for appending URLs to resource pool during capture flows."""

from __future__ import annotations

from .extract import append_url
from .capture_config import get_capture_config


class DefaultResourcePoolAppendAdapter:
    """Appends URLs to resource pool when capture is enabled for project + job_type."""

    def append_url(
        self,
        url: str,
        source: str,
        source_ref: dict,
        *,
        project_key: str,
        job_type: str,
    ) -> None:
        """Append URL if capture is enabled for this project + job_type. No-op otherwise."""
        cfg = get_capture_config(project_key)
        if not cfg.get("enabled"):
            return
        job_types = cfg.get("job_types") or []
        if job_type not in job_types:
            return
        scope = cfg.get("scope") or "project"
        append_url(url, source, source_ref, scope=scope, project_key=project_key)
