"""Source-template search contract normalization and URL rendering helpers."""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qsl, quote, quote_plus, urlencode, urlparse, urlunparse

_ENTRY_QUERY_KEYS = {"q", "query", "keyword", "keywords", "search", "s", "term"}
_SUPPORTED_FIELDS = {
    "param_key",
    "encoding",
    "lang",
    "region",
    "page",
    "page_size",
    "sort",
    "min_results_required",
    "max_candidates",
}


def _as_int(value: Any, default: int, *, min_value: int, max_value: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = int(default)
    return max(min_value, min(max_value, parsed))


def _normalize_encoding(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"percent", "quote", "url"}:
        return "percent"
    if raw in {"raw", "none"}:
        return "raw"
    return "plus"


def normalize_source_search_contract(
    template_url: str,
    contract: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Normalize per-template search contract into a stable dict.

    Returns None when the URL is not search-like and no explicit contract fields are provided.
    """
    raw_contract = dict(contract or {})
    explicit_fields = {k: v for k, v in raw_contract.items() if k in _SUPPORTED_FIELDS}

    parsed = urlparse(str(template_url or ""))
    path = str(parsed.path or "").lower()
    pairs = parse_qsl(parsed.query or "", keep_blank_values=True)

    has_placeholder = "{{q}}" in str(template_url or "")
    existing_key = ""
    for key, value in pairs:
        lk = str(key or "").strip().lower()
        if lk in _ENTRY_QUERY_KEYS:
            existing_key = str(key or "").strip() or lk
            if str(value or "").strip() in {"{{q}}", "%7B%7Bq%7D%7D"}:
                has_placeholder = True
            break
    is_search_like = bool("/search" in path or existing_key or has_placeholder)

    if not is_search_like and not explicit_fields:
        return None

    param_key = str(explicit_fields.get("param_key") or existing_key or "q").strip() or "q"

    page_default = 1
    for key, value in pairs:
        lk = str(key or "").strip().lower()
        if lk in {"page", "p", "paged"}:
            page_default = _as_int(value, 1, min_value=1, max_value=9999)
            break

    page_size_default = _as_int(explicit_fields.get("page_size"), 20, min_value=1, max_value=200)
    min_results_default = 6
    max_candidates_default = 6

    return {
        "param_key": param_key,
        "encoding": _normalize_encoding(explicit_fields.get("encoding")),
        "lang": str(explicit_fields.get("lang") or "").strip() or None,
        "region": str(explicit_fields.get("region") or "").strip() or None,
        "page": _as_int(explicit_fields.get("page"), page_default, min_value=1, max_value=9999),
        "page_size": _as_int(explicit_fields.get("page_size"), page_size_default, min_value=1, max_value=200),
        "sort": str(explicit_fields.get("sort") or "").strip() or None,
        "min_results_required": _as_int(
            explicit_fields.get("min_results_required"),
            min_results_default,
            min_value=1,
            max_value=20,
        ),
        "max_candidates": _as_int(explicit_fields.get("max_candidates"), max_candidates_default, min_value=1, max_value=2000),
    }


def build_query_url_from_contract(
    template_url: str,
    query_terms: list[str] | None,
    contract: dict[str, Any] | None = None,
) -> str:
    """Build query URL from a search template URL and normalized search contract."""
    url = str(template_url or "").strip()
    if not url:
        return ""

    normalized = normalize_source_search_contract(url, contract)
    if normalized is None:
        return url

    terms = [str(x or "").strip() for x in (query_terms or []) if str(x or "").strip()]
    joined = " ".join(terms)
    encoding = str(normalized.get("encoding") or "plus")
    if encoding == "percent":
        encoded_inline = quote(joined, safe="") if joined else ""
    elif encoding == "raw":
        encoded_inline = joined
    else:
        encoded_inline = quote_plus(joined) if joined else ""

    param_key = str(normalized.get("param_key") or "q").strip() or "q"

    replaced = False
    if "{{q}}" in url:
        url = url.replace("{{q}}", encoded_inline)
        replaced = True

    parsed = urlparse(url)
    pairs = parse_qsl(parsed.query or "", keep_blank_values=True)
    out_pairs: list[tuple[str, str]] = []
    query_key_matched = False
    page_key_matched = False
    for key, value in pairs:
        key_str = str(key or "")
        lk = key_str.strip().lower()
        vv = str(value or "")
        if lk == param_key.lower() or (lk in _ENTRY_QUERY_KEYS and not query_key_matched):
            out_pairs.append((key_str or param_key, joined))
            query_key_matched = True
            continue
        if lk in {"page", "p", "paged"}:
            out_pairs.append((key_str or "page", str(int(normalized.get("page") or 1))))
            page_key_matched = True
            continue
        if vv == "{{page}}":
            out_pairs.append((key_str, str(int(normalized.get("page") or 1))))
            page_key_matched = True
            continue
        out_pairs.append((key_str, vv))

    if not replaced and not query_key_matched:
        out_pairs.append((param_key, joined))
    page_value = int(normalized.get("page") or 1)
    if not page_key_matched and (page_value > 1 or "{{page}}" in str(template_url or "")):
        out_pairs.append(("page", str(page_value)))

    for key in ("lang", "region", "page_size", "sort"):
        value = normalized.get(key)
        if value in (None, ""):
            continue
        out_pairs.append((key, str(value)))

    if encoding == "percent":
        new_query = urlencode(out_pairs, doseq=True, quote_via=quote)
    else:
        new_query = urlencode(out_pairs, doseq=True)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))
