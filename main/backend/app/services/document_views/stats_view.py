from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from .common_view import get_extracted_data
from .policy_view import get_policy_data


def _clean_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def get_prompt_time_density_fields(doc: Any) -> dict[str, Any]:
    extracted = get_extracted_data(doc)
    policy = get_policy_data(doc)
    return {
        "effective_time": extracted.get("effective_time"),
        "source_time": extracted.get("source_time"),
        "policy_effective_date": policy.get("effective_date"),
        "time_parse_version": extracted.get("time_parse_version") or policy.get("time_parse_version"),
    }


def get_prompt_time_density_group(doc: Any) -> str:
    extracted = get_extracted_data(doc)
    policy = get_policy_data(doc)
    return (
        _clean_text(extracted.get("prompt_group_id"))
        or _clean_text(extracted.get("topic_cluster"))
        or _clean_text(extracted.get("topic"))
        or _clean_text(policy.get("policy_type"))
        or "unknown"
    )


def get_prompt_time_density_source_domain(doc: Any) -> str:
    extracted = get_extracted_data(doc)
    source_domain = _clean_text(extracted.get("source_domain"))
    if source_domain:
        return source_domain.lower()

    uri = str(getattr(doc, "uri", "") or "").strip()
    if not uri:
        return "unknown"
    host = urlparse(uri).netloc.strip().lower()
    return host or "unknown"
