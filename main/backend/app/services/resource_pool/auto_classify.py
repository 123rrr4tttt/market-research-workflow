"""Rule-first site entry classification. LLM fallback when rules cannot determine."""

from __future__ import annotations

import logging
import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse

from ...settings.config import settings
from ..extraction.json_utils import extract_json_payload
from ..llm.config_loader import format_prompt_template, get_llm_config
from ..llm.provider import get_chat_model
from .llm_validator import validate_llm_recommendation
from .url_utils import domain_from_url

_log = logging.getLogger(__name__)

_DEFAULT_LLM_PROMPT = """Given this site URL: {site_url}

Classify it as one of: rss, sitemap, domain_root, search_template, official_api.

If it looks like a search page (has q=, query=, search in path), return search_template and provide a template URL with {{q}} and optionally {{page}} placeholders. The template domain must match the site domain.

Return JSON only:
{{"entry_type": "...", "channel_key": "generic_web.rss|generic_web.sitemap|generic_web.search_template|official_access.api|url_pool", "template": "optional for search_template"}}
"""

_DEFAULT_BATCH_LLM_PROMPT = """Classify these site entry URLs for ingestion.

For each item, return:
- index (same integer as input)
- entry_type: rss|sitemap|domain_root|search_template|official_api
- channel_key: generic_web.rss|generic_web.sitemap|generic_web.search_template|official_access.api|url_pool
- template: required when entry_type=search_template and must contain {{q}}
- symbol_suggestion: optional short identifier for later symbolization

Use rule-like reasoning first. If URL clearly contains search path/query (e.g. /search, ?q=), prefer search_template.
Return JSON only in this shape:
{"items":[{...}]}

Inputs:
{inputs_json}
"""

_ENTRY_TYPE_TO_CHANNEL: dict[str, str] = {
    "rss": "generic_web.rss",
    "sitemap": "generic_web.sitemap",
    "domain_root": "url_pool",
    "search_template": "generic_web.search_template",
    "official_api": "official_access.api",
}

_ALLOWED_ENTRY_TYPES = frozenset(_ENTRY_TYPE_TO_CHANNEL)
_ALLOWED_CHANNEL_KEYS = frozenset(_ENTRY_TYPE_TO_CHANNEL.values()) | {"url_pool"}


@dataclass
class Recommendation:
    """Classify result: channel_key, entry_type, template (if search_template), validated flag."""

    channel_key: str
    entry_type: str
    template: str | None
    validated: bool
    source: str  # "rule" | "llm" | "fallback"
    capabilities: dict[str, Any] | None = None


def infer_keyword_capabilities(entry_type: str | None, channel_key: str | None = None) -> dict[str, Any]:
    """
    Keyword capability classification for site entries (URL fact layer metadata).
    This does not store task keywords, only labels what the entry can support.
    """
    et = str(entry_type or "").strip().lower()
    ch = str(channel_key or "").strip().lower()
    supports = False
    keyword_mode = "none"
    if et == "search_template" or ch.endswith("search_template"):
        supports = True
        keyword_mode = "search"
    elif et in {"rss", "sitemap"} or ch.endswith(".rss") or ch.endswith(".sitemap"):
        supports = True
        keyword_mode = "filter"
    elif et in {"domain_root", "official_api"}:
        supports = False
        keyword_mode = "none"
    return {
        "supports_query_terms": supports,
        "keyword_mode": keyword_mode,
    }


def _path_from_url(url: str) -> str:
    """Extract path from URL (lowercase)."""
    if not url or not isinstance(url, str):
        return ""
    try:
        parsed = urlparse(url)
        return (parsed.path or "").lower()
    except Exception:
        return ""


def _path_suggests_rss(path: str) -> bool:
    """Check if path suggests RSS/Atom feed."""
    if not path:
        return False
    path = path.lower()
    return any(x in path for x in (".xml", "/feed", "/rss", "/atom"))


def _path_suggests_sitemap(path: str) -> bool:
    """Check if path suggests sitemap."""
    if not path:
        return False
    return "sitemap" in path.lower()


def _build_search_template_from_url(site_url: str) -> str | None:
    """
    Convert an obvious search URL to a reusable template:
    - replace q/query/keyword/keywords/search param value with {{q}}
    - preserve other query params
    - optionally normalize page-like params to {{page}}
    """
    try:
        parsed = urlparse(site_url)
    except Exception:
        return None
    if not (parsed.scheme and parsed.netloc):
        return None
    pairs = parse_qsl(parsed.query or "", keep_blank_values=True)
    if not pairs:
        return None
    replaced_any = False
    out_pairs: list[tuple[str, str]] = []
    for k, v in pairs:
        lk = (k or "").lower()
        if lk in {"q", "query", "keyword", "keywords", "search"}:
            out_pairs.append((k, "{{q}}"))
            replaced_any = True
            continue
        if lk in {"page", "p", "paged"} and str(v).strip():
            out_pairs.append((k, "{{page}}"))
            continue
        out_pairs.append((k, v))
    if not replaced_any:
        return None
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, urlencode(out_pairs), ""))


def _rule_search_template(site_url: str) -> Recommendation | None:
    if not site_url or not site_url.strip().lower().startswith(("http://", "https://")):
        return None
    try:
        parsed = urlparse(site_url)
    except Exception:
        return None
    path = (parsed.path or "").lower()
    query_pairs = parse_qsl(parsed.query or "", keep_blank_values=True)
    query_keys = {str(k or "").lower() for k, _ in query_pairs}
    has_search_path = any(x in path for x in ("/search", "/find", "/query"))
    has_query_key = any(k in {"q", "query", "keyword", "keywords", "search"} for k in query_keys)
    if not (has_search_path or has_query_key):
        return None
    template = _build_search_template_from_url(site_url)
    if not template and has_search_path:
        # Path looks like search page even if example URL omitted q param.
        sep = "&" if parsed.query else "?"
        template = f"{site_url}{sep}q={{q}}"
    if not template:
        return None
    return Recommendation(
        channel_key="generic_web.search_template",
        entry_type="search_template",
        template=template,
        validated=True,
        source="rule",
        capabilities=infer_keyword_capabilities("search_template", "generic_web.search_template"),
    )


def _rule_classify(
    site_url: str,
    entry_type: str | None,
    template: str | None,
) -> Recommendation | None:
    """
    Pure rule-based classification. Returns None when rules cannot determine.
    """
    if not site_url or not site_url.strip().lower().startswith(("http://", "https://")):
        return None

    path = _path_from_url(site_url)
    known_entry = (entry_type or "").strip().lower()

    # Known entry_type -> direct channel mapping
    if known_entry in _ALLOWED_ENTRY_TYPES:
        ch = _ENTRY_TYPE_TO_CHANNEL[known_entry]
        if known_entry == "search_template" and not template:
            return None  # search_template needs template, cannot rule-classify
        return Recommendation(
            channel_key=ch,
            entry_type=known_entry,
            template=template,
            validated=True,
            source="rule",
            capabilities=infer_keyword_capabilities(known_entry, ch),
        )

    # URL path/query heuristics when entry_type unknown
    rec = _rule_search_template(site_url)
    if rec is not None:
        return rec

    if _path_suggests_sitemap(path):
        return Recommendation(
            channel_key="generic_web.sitemap",
            entry_type="sitemap",
            template=None,
            validated=True,
            source="rule",
            capabilities=infer_keyword_capabilities("sitemap", "generic_web.sitemap"),
        )
    if _path_suggests_rss(path):
        return Recommendation(
            channel_key="generic_web.rss",
            entry_type="rss",
            template=None,
            validated=True,
            source="rule",
            capabilities=infer_keyword_capabilities("rss", "generic_web.rss"),
        )

    return None


def _llm_available() -> bool:
    """Check if LLM is configured and has API key."""
    p = (settings.llm_provider or "").lower()
    if p == "openai":
        return bool(settings.openai_api_key)
    if p == "azure":
        return bool(settings.azure_api_key)
    if p == "ollama":
        return True
    return False


def _llm_classify(site_url: str, entry_type: str | None, template: str | None) -> Recommendation | None:
    """
    Call LLM to classify site entry. Returns None on failure or invalid output.
    """
    if not _llm_available():
        _log.debug("_llm_classify: LLM not available, skip")
        return None

    config = get_llm_config("site_entry_classification")
    if config and config.get("user_prompt_template"):
        prompt = format_prompt_template(
            config["user_prompt_template"],
            site_url=site_url,
            entry_type=entry_type or "",
            template=template or "",
        )
    else:
        prompt = _DEFAULT_LLM_PROMPT.format(site_url=site_url)

    try:
        model = get_chat_model(
            model=config.get("model") if config else None,
            temperature=config.get("temperature", 0.2) if config else 0.2,
            max_tokens=config.get("max_tokens", 500) if config else 500,
        )
        response = model.invoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        raw = extract_json_payload(content)
        if not raw:
            _log.warning("_llm_classify: no valid JSON in response")
            return None
        return _recommendation_from_llm_row(raw, site_url=site_url)
    except Exception as exc:
        _log.warning("_llm_classify: %s", exc, exc_info=False)
        return None


def _recommendation_from_llm_row(row: dict[str, Any], *, site_url: str) -> Recommendation | None:
    """Validate one LLM row and map it to the internal Recommendation schema."""
    validated = validate_llm_recommendation(row, site_url)
    if not validated:
        _log.warning("_llm_classify: validation failed for raw=%s", row)
        return None
    return Recommendation(
        channel_key=validated["channel_key"],
        entry_type=validated["entry_type"],
        template=validated.get("template"),
        validated=True,
        source="llm",
        capabilities=infer_keyword_capabilities(validated.get("entry_type"), validated.get("channel_key")),
    )


def _llm_classify_batch(url_items: list[dict[str, Any]]) -> dict[int, Recommendation]:
    """
    Batch classify site entries with one LLM call.
    Input items: [{"index": int, "site_url": str, "entry_type": str|None, "template": str|None}]
    Returns map[index] -> Recommendation (validated only). Invalid rows are skipped.
    """
    if not url_items or not _llm_available():
        return {}

    config = get_llm_config("site_entry_classification")
    inputs_payload = [
        {
            "index": int(item.get("index", i)),
            "site_url": str(item.get("site_url") or ""),
            "entry_type": str(item.get("entry_type") or ""),
            "template": str(item.get("template") or ""),
        }
        for i, item in enumerate(url_items)
    ]
    prompt = _DEFAULT_BATCH_LLM_PROMPT.format(
        inputs_json=json.dumps(inputs_payload, ensure_ascii=False, indent=2)
    )
    try:
        model = get_chat_model(
            model=config.get("model") if config else None,
            temperature=config.get("temperature", 0.1) if config else 0.1,
            max_tokens=config.get("max_tokens", 2000) if config else 2000,
        )
        response = model.invoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        raw = extract_json_payload(content)
        if not raw or not isinstance(raw, dict):
            return {}
        items = raw.get("items")
        if not isinstance(items, list):
            return {}
        by_index: dict[int, Recommendation] = {}
        src_map = {int(x.get("index", -1)): x for x in inputs_payload}
        for row in items:
            if not isinstance(row, dict):
                continue
            try:
                idx = int(row.get("index"))
            except Exception:
                continue
            src = src_map.get(idx)
            if not src:
                continue
            rec = _recommendation_from_llm_row(row, site_url=src["site_url"])
            if rec is None:
                continue
            by_index[idx] = rec
        return by_index
    except Exception as exc:
        _log.warning("_llm_classify_batch: %s", exc, exc_info=False)
        return {}


def classify_site_entries_batch(
    entries: list[dict[str, Any]],
    *,
    use_llm: bool = False,
    llm_batch_size: int = 20,
) -> list[dict[str, Any]]:
    """
    Batch classify site entries. Rule-first per row; unresolved rows can be sent to LLM in batches.
    Returns rows with recommendation fields merged for downstream symbolization/ingestion.
    """
    out: list[dict[str, Any]] = []
    unresolved: list[tuple[int, dict[str, Any]]] = []
    for i, row in enumerate(entries or []):
        item = dict(row or {})
        site_url = str(item.get("site_url") or "").strip()
        entry_type = item.get("entry_type")
        template = item.get("template")
        rec = _rule_classify(site_url, entry_type, template)
        if rec is None:
            unresolved.append((i, item))
            out.append(item)
            continue
        item.update(
            {
                "channel_key": rec.channel_key,
                "entry_type": rec.entry_type,
                "template": rec.template if rec.template is not None else item.get("template"),
                "validated": rec.validated,
                "source": rec.source,
                "capabilities": rec.capabilities or infer_keyword_capabilities(rec.entry_type, rec.channel_key),
            }
        )
        out.append(item)

    if not use_llm or not unresolved:
        # Fill unresolved with fallback
        for idx, item in unresolved:
            site_url = str(item.get("site_url") or "").strip()
            rec = classify_site_entry(site_url, item.get("entry_type"), item.get("template"), use_llm=False)
            out[idx].update(
                {
                    "channel_key": rec.channel_key,
                    "entry_type": rec.entry_type,
                    "template": rec.template if rec.template is not None else out[idx].get("template"),
                    "validated": rec.validated,
                    "source": rec.source,
                    "capabilities": rec.capabilities or infer_keyword_capabilities(rec.entry_type, rec.channel_key),
                }
            )
        return out

    llm_batch_size = max(1, min(100, int(llm_batch_size or 20)))
    for start in range(0, len(unresolved), llm_batch_size):
        chunk = unresolved[start : start + llm_batch_size]
        payload = [
            {
                "index": idx,
                "site_url": item.get("site_url"),
                "entry_type": item.get("entry_type"),
                "template": item.get("template"),
            }
            for idx, item in chunk
        ]
        llm_recs = _llm_classify_batch(payload)
        for idx, item in chunk:
            rec = llm_recs.get(idx)
            if rec is None:
                rec = classify_site_entry(str(item.get("site_url") or ""), item.get("entry_type"), item.get("template"), use_llm=False)
            out[idx].update(
                {
                    "channel_key": rec.channel_key,
                    "entry_type": rec.entry_type,
                    "template": rec.template if rec.template is not None else out[idx].get("template"),
                    "validated": rec.validated,
                    "source": rec.source,
                    "capabilities": rec.capabilities or infer_keyword_capabilities(rec.entry_type, rec.channel_key),
                }
            )
    return out


def classify_site_entry(
    site_url: str,
    entry_type: str | None = None,
    template: str | None = None,
    *,
    use_llm: bool = False,
) -> Recommendation:
    """
    Classify site entry: rule-first, LLM fallback when rules cannot determine.

    When use_llm=False or no LLM key available, falls back to url_pool/domain_root.
    """
    rec = _rule_classify(site_url, entry_type, template)
    if rec is not None:
        return rec

    if use_llm:
        rec = _llm_classify(site_url, entry_type, template)
        if rec is not None:
            return rec

    # Fallback
    return Recommendation(
        channel_key="url_pool",
        entry_type="domain_root",
        template=None,
        validated=False,
        source="fallback",
        capabilities=infer_keyword_capabilities("domain_root", "url_pool"),
    )
