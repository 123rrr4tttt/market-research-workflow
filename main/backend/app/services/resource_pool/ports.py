"""Resource pool ports."""

from __future__ import annotations

from typing import Protocol


class ResourcePoolAppendPort(Protocol):
    """Port for appending URLs to resource pool during capture flows."""

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
        ...
