from __future__ import annotations

from typing import Any

from .base import CrawlerDispatchRequest
from .registry import get_provider


def _normalize(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    if hasattr(payload, "__dict__"):
        return {k: v for k, v in vars(payload).items() if not k.startswith("_")}
    return {"raw": payload}


def submit_crawler_job(
    *,
    provider: str,
    project: str,
    spider: str,
    arguments: dict[str, Any] | None = None,
    settings: dict[str, Any] | None = None,
    version: str | None = None,
    priority: int | None = None,
) -> dict[str, Any]:
    p = get_provider(provider)
    if p is None:
        raise ValueError(f"crawler provider is not registered: {provider}")
    result = p.dispatch(
        CrawlerDispatchRequest(
            provider=provider,
            project=project,
            spider=spider,
            arguments=dict(arguments or {}),
            settings=dict(settings or {}),
            version=version,
            priority=priority,
        )
    )
    return {
        "provider_status": result.provider_status,
        "provider_job_id": result.provider_job_id,
        "provider_type": result.provider_type,
        "attempt_count": result.attempt_count,
        "raw": result.raw,
    }


def poll_crawler_job(
    *,
    external_provider: str,
    external_job_id: str,
    project: str | None = None,
    spider: str | None = None,
    options: dict[str, Any] | None = None,
    **_: Any,
) -> dict[str, Any]:
    p = get_provider(external_provider)
    if p is None:
        raise ValueError(f"crawler provider is not registered: {external_provider}")
    poll_fn = getattr(p, "poll", None)
    if not callable(poll_fn):
        raise ValueError(f"crawler provider does not support poll(): {external_provider}")
    payload = _normalize(
        poll_fn(
            external_job_id=external_job_id,
            project=project,
            spider=spider,
            options=dict(options or {}),
        )
    )
    payload.setdefault("external_provider", external_provider)
    payload.setdefault("external_job_id", external_job_id)
    return payload


__all__ = ["submit_crawler_job", "poll_crawler_job"]
