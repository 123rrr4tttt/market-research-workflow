from __future__ import annotations

from copy import deepcopy
from typing import Any

from .adapters.http_utils import HttpFetchError, fetch_html
from .content_cleaner import clean_frontdoor_document_candidate
from .content_extraction import apply_main_content_extraction, extract_main_text_from_html


def execute_frontdoor_cleanup(
    *,
    document_candidate: dict[str, Any],
    terminal_context: dict[str, Any],
    cleanup_actions: list[str] | None,
) -> dict[str, Any]:
    candidate = dict(document_candidate or {})
    context = dict(terminal_context or {})
    actions = list(cleanup_actions or [])
    result = {
        "executed": False,
        "recovered": False,
        "actions": actions,
        "errors": [],
        "document_candidate": candidate,
        "terminal_context": context,
        "content_extraction": deepcopy(context.get("content_extraction") or {}),
        "cleaning": deepcopy(context.get("frontdoor_cleaning") or {}),
    }
    if not actions:
        return result

    if "refetch_suggested" in actions:
        uri = str(candidate.get("uri") or "").strip()
        if not uri:
            result["errors"].append("missing_uri_for_refetch")
            return result
        try:
            html, response = fetch_html(uri, timeout=12.0, retries=1)
        except HttpFetchError as exc:
            result["errors"].append(str(exc))
            return result
        except Exception as exc:  # noqa: BLE001
            result["errors"].append(repr(exc))
            return result
        extracted = extract_main_text_from_html(html)
        if extracted:
            candidate["content"] = extracted
            context["http_status"] = int(getattr(response, "status_code", 0) or 0)
            result["executed"] = True

    if "strip_boilerplate" in actions or result["executed"]:
        candidate, extraction_profile = apply_main_content_extraction(candidate)
        candidate, cleaning = clean_frontdoor_document_candidate(candidate)
        context["content_extraction"] = dict(extraction_profile)
        context["frontdoor_cleaning"] = dict(cleaning)
        result["executed"] = True
        result["recovered"] = True
        result["document_candidate"] = candidate
        result["terminal_context"] = context
        result["content_extraction"] = deepcopy(extraction_profile)
        result["cleaning"] = deepcopy(cleaning)
        return result

    return result
