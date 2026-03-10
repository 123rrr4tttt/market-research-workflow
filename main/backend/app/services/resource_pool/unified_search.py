"""Unified search over site entries bound to a source_library item."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import re
from typing import Any
from urllib.parse import parse_qsl, quote_plus, urlencode, urljoin, urlsplit, urlunsplit
import xml.etree.ElementTree as ET
import gzip

from ..ingest.adapters.http_utils import HttpFetchError, fetch_html, make_html_parser
from .auto_classify import infer_keyword_capabilities
from ..source_library.resolver import list_effective_items
from .extract import append_url
from .resolver import list_urls
from .search_capabilities import make_search_candidate
from .search_capabilities import normalize_match_text
from .search_capabilities import select_search_candidates
from .site_entries import get_site_entry_by_url
from .url_utils import domain_from_url, normalize_url


@dataclass
class UnifiedSearchResult:
    item_key: str
    query_terms: list[str]
    site_entries_used: list[dict[str, Any]]
    candidates: list[str]
    written: dict[str, int] | None
    ingest_result: dict[str, Any] | None
    errors: list[dict[str, str]]


def _collect_history_pool_urls(
    *,
    scope: str,
    project_key: str,
    source: str,
    limit: int = 3000,
) -> set[str]:
    if not source:
        return set()
    out: set[str] = set()
    page = 1
    page_size = 100
    while len(out) < max(1, int(limit)):
        items, total = list_urls(
            scope=scope,
            project_key=project_key,
            source=source,
            page=page,
            page_size=page_size,
        )
        if not items:
            break
        for item in items:
            url = str((item or {}).get("url") or "").strip()
            if url:
                out.add(url)
            if len(out) >= limit:
                break
        if page * page_size >= int(total or 0):
            break
        page += 1
    return out


def _as_terms(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        s = raw.strip()
        return [s] if s else []
    if isinstance(raw, list):
        out: list[str] = []
        for x in raw:
            s = str(x).strip()
            if s:
                out.append(s)
        # preserve order, dedup
        return list(dict.fromkeys(out))
    return [str(raw).strip()] if str(raw).strip() else []


_TRACKING_QUERY_KEYS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "utm_name",
    "utm_reader",
    "utm_referrer",
    "utm_social",
    "utm_social-type",
    "gclid",
    "fbclid",
    "igshid",
    "mc_cid",
    "mc_eid",
    "mkt_tok",
    "ref",
    "ref_src",
    "spm",
}

_ENCODED_Q_PLACEHOLDER = re.compile(r"%7B%7Bq%7D%7D", re.IGNORECASE)
_ENCODED_PAGE_PLACEHOLDER = re.compile(r"%7B%7Bpage%7D%7D", re.IGNORECASE)


def _normalize_candidate_url(url: str) -> str | None:
    """Normalize candidate URL for storage/display (strip fragment + tracking params)."""
    norm = normalize_url(url)
    if not norm:
        return None
    try:
        parts = urlsplit(norm)
        q = [
            (k, v)
            for (k, v) in parse_qsl(parts.query, keep_blank_values=True)
            if k.lower() not in _TRACKING_QUERY_KEYS
        ]
        query = urlencode(q, doseq=True) if q else ""
        cleaned = urlunsplit((parts.scheme, parts.netloc, parts.path or "/", query, ""))
        return normalize_url(cleaned) or norm
    except Exception:
        return norm


def _normalize_search_template_placeholders(template: str | None) -> str:
    tpl = str(template or "").strip()
    if not tpl:
        return ""
    tpl = _ENCODED_Q_PLACEHOLDER.sub("{{q}}", tpl)
    tpl = _ENCODED_PAGE_PLACEHOLDER.sub("{{page}}", tpl)
    return tpl


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _extract_urls_from_rss_xml(xml_text: str) -> list[str]:
    return [item["url"] for item in _extract_rss_candidates_from_xml(xml_text)]


def _extract_rss_candidates_from_xml(xml_text: str) -> list[dict[str, str]]:
    urls: list[str] = []
    candidates: list[dict[str, str]] = []
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return candidates

    # RSS: item/link, and guid permalink
    for item in root.findall(".//{*}item"):
        title = str((item.findtext("{*}title") or "")).strip()
        description = str((item.findtext("{*}description") or "")).strip()
        link = item.find("{*}link")
        if link is not None and link.text:
            norm = _normalize_candidate_url(link.text.strip())
            if norm and norm not in urls:
                urls.append(norm)
                candidates.append({"url": norm, "title": title, "text": description, "extra": {"title_hint": title}})
        guid = item.find("{*}guid")
        if guid is not None and guid.text:
            is_permalink = str(guid.attrib.get("isPermaLink") or "").lower() == "true"
            if is_permalink:
                norm = _normalize_candidate_url(guid.text.strip())
                if norm and norm not in urls:
                    urls.append(norm)
                    candidates.append({"url": norm, "title": title, "text": description, "extra": {"title_hint": title}})

    # Atom: entry/link[@href], prefer rel=alternate
    for entry in root.findall(".//{*}entry"):
        title = str((entry.findtext("{*}title") or "")).strip()
        summary = str((entry.findtext("{*}summary") or entry.findtext("{*}content") or "")).strip()
        for link in entry.findall("{*}link"):
            href = (link.attrib.get("href") or "").strip()
            if not href:
                continue
            rel = (link.attrib.get("rel") or "").strip().lower()
            typ = (link.attrib.get("type") or "").strip().lower()
            if rel and rel != "alternate":
                continue
            if typ and "html" not in typ and "xml" in typ:
                continue
            norm = _normalize_candidate_url(href)
            if norm and norm not in urls:
                urls.append(norm)
                candidates.append({"url": norm, "title": title, "text": summary, "extra": {"title_hint": title}})
    return candidates


def _parse_sitemap_xml(xml_text: str) -> tuple[str, list[str]]:
    """Return (kind, locs). kind: urlset|sitemapindex|unknown."""
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return "unknown", []

    kind = _local_name(root.tag).lower()
    locs: list[str] = []
    for loc in root.findall(".//{*}loc"):
        if loc.text:
            norm = _normalize_candidate_url(loc.text.strip())
            if norm and norm not in locs:
                locs.append(norm)
    return kind, locs


def _fetch_text_maybe_gzip(url: str, *, timeout: float) -> str:
    text, resp = fetch_html(url, timeout=timeout, retries=1)
    if url.lower().endswith(".gz"):
        try:
            raw = resp.content
            return gzip.decompress(raw).decode("utf-8", errors="ignore")
        except Exception:
            return text
    return text


def _collect_sitemap_urls(
    *,
    sitemap_url: str,
    timeout: float,
    max_depth: int = 2,
    max_sitemaps: int = 50,
) -> list[str]:
    """Fetch sitemap urlset, or recursively expand sitemapindex, with limits."""
    seen: set[str] = set()
    urls: list[str] = []
    to_fetch: list[tuple[str, int]] = [(sitemap_url, 0)]
    fetched = 0

    while to_fetch and fetched < max_sitemaps:
        u, depth = to_fetch.pop(0)
        if u in seen:
            continue
        seen.add(u)
        fetched += 1

        xml_text = _fetch_text_maybe_gzip(u, timeout=timeout)
        kind, locs = _parse_sitemap_xml(xml_text)
        if kind.endswith("sitemapindex") and depth < max_depth:
            for loc in locs:
                if loc not in seen:
                    to_fetch.append((loc, depth + 1))
            continue

        for loc in locs:
            if loc not in urls:
                urls.append(loc)

    return urls


def _build_sitemap_candidates(urls: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for url in urls:
        norm = _normalize_candidate_url(url)
        if not norm:
            continue
        path = urlsplit(norm).path or ""
        slug = path.rstrip("/").rsplit("/", 1)[-1].rsplit(".", 1)[0]
        title_hint = slug.replace("-", " ").replace("_", " ")
        out.append({"url": norm, "title": "", "text": "", "extra": {"title_hint": title_hint}})
    return out


def _extract_urls_from_html(html: str, *, base_url: str) -> list[str]:
    urls: list[str] = []
    try:
        parser = make_html_parser(html)
        for node in parser.css("a"):
            href = (node.attributes.get("href") or "").strip()
            if not href:
                continue
            abs_url = urljoin(base_url, href)
            norm = _normalize_candidate_url(abs_url)
            if norm and norm not in urls:
                urls.append(norm)
    except Exception:
        return urls
    return urls


def _normalize_match_text(value: str | None) -> str:
    return normalize_match_text(value)


def _term_matches_texts(term: str, texts: list[str]) -> bool:
    normalized_term = _normalize_match_text(term)
    if not normalized_term:
        return False
    return any(normalized_term in _normalize_match_text(text) for text in texts if str(text or "").strip())


def _extract_link_candidates_from_html(html: str, *, base_url: str) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    try:
        parser = make_html_parser(html)
        for node in parser.css("a"):
            href = (node.attributes.get("href") or "").strip()
            if not href:
                continue
            abs_url = urljoin(base_url, href)
            norm = _normalize_candidate_url(abs_url)
            if not norm or norm in seen_urls:
                continue
            seen_urls.add(norm)
            candidates.append(
                {
                    "url": norm,
                    "text": str(node.text(separator=" ", strip=True) or "").strip(),
                    "title": str(node.attributes.get("title") or "").strip(),
                }
            )
    except Exception:
        return candidates
    return candidates


def _filter_urls_by_terms(urls: list[str], terms: list[str]) -> list[str]:
    if not terms:
        return urls
    t = [x.lower() for x in terms if x]
    out: list[str] = []
    for u in urls:
        lu = u.lower()
        if any(term in lu for term in t):
            out.append(u)
    return out


def _filter_urls_by_terms_with_fallback(
    urls: list[str],
    terms: list[str],
    *,
    fallback_limit: int = 30,
    allow_fallback: bool = True,
) -> tuple[list[str], bool]:
    """
    First try strict URL-term match; if nothing matches, fall back to top URLs.
    This avoids false-zero results on sites where result URLs don't carry query terms.
    """
    filtered = _filter_urls_by_terms(urls, terms)
    if filtered:
        return filtered, False
    if not terms:
        return urls, False
    if not allow_fallback:
        return [], True
    return urls[: max(1, int(fallback_limit))], True


def _filter_link_candidates_by_terms_with_fallback(
    candidates: list[dict[str, str]],
    terms: list[str],
    *,
    strategy: str = "search_template",
    entry_domain: str | None = None,
    search_url: str | None = None,
    fallback_limit: int = 30,
    allow_fallback: bool = True,
) -> tuple[list[dict[str, str]], bool]:
    scored = [
        item
        for item in (
            make_search_candidate(
                url=str(candidate.get("url") or "").strip(),
                strategy=strategy,
                title=str(candidate.get("title") or "").strip(),
                text=str(candidate.get("text") or "").strip(),
                extra=dict(candidate.get("extra") or {}),
            )
            for candidate in candidates
        )
        if item is not None
    ]
    decisions, used_fallback = select_search_candidates(
        scored,
        terms,
        strategy=strategy,
        entry_domain=entry_domain,
        search_url=search_url,
        fallback_limit=fallback_limit,
        allow_fallback=allow_fallback,
    )
    by_url = {str(candidate.get("url") or "").strip(): candidate for candidate in candidates}
    return [by_url[item.url] for item in decisions if item.url in by_url], used_fallback


def _is_low_value_candidate_url(url: str) -> bool:
    u = str(url or "").strip().lower()
    if not u:
        return True
    low_markers = (
        "/login",
        "/signin",
        "/sign-in",
        "/signup",
        "/sign-up",
        "/register",
        "/privacy",
        "/tos",
        "/terms",
        "/about",
        "/account",
        "/settings",
        "/subscribe",
    )
    return any(marker in u for marker in low_markers)


def _resolve_item_site_entries(item: dict[str, Any]) -> list[str]:
    params = item.get("params") or {}
    if not isinstance(params, dict):
        return []
    raw = params.get("site_entries") or params.get("site_entry_urls") or []
    urls: list[str] = []
    if isinstance(raw, list):
        for x in raw:
            if isinstance(x, str):
                u = normalize_url(x)
            elif isinstance(x, dict):
                u = normalize_url(str(x.get("site_url") or x.get("url") or "").strip())
            else:
                u = normalize_url(str(x).strip())
            if u and u not in urls:
                urls.append(u)
    elif isinstance(raw, str):
        u = normalize_url(raw)
        if u:
            urls.append(u)
    return urls


def _entry_supports_query_terms(entry: dict[str, Any], entry_type: str) -> bool:
    capabilities = entry.get("capabilities") if isinstance(entry, dict) else None
    if not isinstance(capabilities, dict) or not capabilities:
        capabilities = infer_keyword_capabilities(entry_type)
    return bool(capabilities.get("supports_query_terms"))


def _entry_keyword_mode(entry: dict[str, Any], entry_type: str) -> str:
    capabilities = entry.get("capabilities") if isinstance(entry, dict) else None
    if not isinstance(capabilities, dict) or not capabilities:
        capabilities = infer_keyword_capabilities(entry_type)
    return str(capabilities.get("keyword_mode") or "none").strip().lower()


def _build_search_candidates(
    raw_candidates: list[dict[str, Any]],
    *,
    strategy: str,
    source_url: str,
    entry_domain: str,
) -> list[Any]:
    built = []
    for candidate in raw_candidates:
        metadata = dict(candidate.get("extra") or {}) if isinstance(candidate.get("extra"), dict) else {}
        item = make_search_candidate(
            url=str(candidate.get("url") or "").strip(),
            strategy=strategy,
            title=str(candidate.get("title") or "").strip(),
            text=str(candidate.get("text") or "").strip(),
            source_url=source_url,
            entry_domain=entry_domain,
            metadata=metadata,
        )
        if item is not None:
            built.append(item)
    return built


def unified_search_by_item(
    *,
    project_key: str,
    item_key: str,
    query_terms: list[str] | str,
    max_candidates: int = 200,
    write_to_pool: bool = False,
    pool_scope: str = "project",
    pool_source: str = "unified_search",
    probe_timeout: float = 10.0,
    sitemap_max_depth: int = 2,
    sitemap_max_sitemaps: int = 50,
    auto_ingest: bool = False,
    ingest_limit: int = 10,
    enable_extraction: bool = True,
    allow_term_fallback: bool = True,
) -> UnifiedSearchResult:
    terms = _as_terms(query_terms)
    item_key = (item_key or "").strip()
    if not item_key:
        raise ValueError("item_key is required")
    if not project_key:
        raise ValueError("project_key is required")
    max_candidates = min(max(1, int(max_candidates)), 2000)
    if pool_scope not in {"project", "shared"}:
        pool_scope = "project"

    items = list_effective_items(scope="effective", project_key=project_key)
    item_map = {x.get("item_key"): x for x in items if isinstance(x, dict)}
    item = item_map.get(item_key)
    if not item:
        raise ValueError(f"source item not found: {item_key}")

    return unified_search_by_item_payload(
        project_key=project_key,
        item=item,
        query_terms=terms,
        max_candidates=max_candidates,
        write_to_pool=write_to_pool,
        pool_scope=pool_scope,
        pool_source=pool_source,
        probe_timeout=probe_timeout,
        sitemap_max_depth=sitemap_max_depth,
        sitemap_max_sitemaps=sitemap_max_sitemaps,
        auto_ingest=auto_ingest,
        ingest_limit=ingest_limit,
        enable_extraction=enable_extraction,
        allow_term_fallback=allow_term_fallback,
    )


def unified_search_by_item_payload(
    *,
    project_key: str,
    item: dict[str, Any],
    query_terms: list[str] | str,
    max_candidates: int = 200,
    write_to_pool: bool = False,
    pool_scope: str = "project",
    pool_source: str = "unified_search",
    probe_timeout: float = 10.0,
    sitemap_max_depth: int = 2,
    sitemap_max_sitemaps: int = 50,
    auto_ingest: bool = False,
    ingest_limit: int = 10,
    enable_extraction: bool = True,
    allow_term_fallback: bool = True,
) -> UnifiedSearchResult:
    terms = _as_terms(query_terms)
    item_key = str(item.get("item_key") or "").strip()
    if not item_key:
        raise ValueError("item.item_key is required")
    if not project_key:
        raise ValueError("project_key is required")
    max_candidates = min(max(1, int(max_candidates)), 2000)
    if pool_scope not in {"project", "shared"}:
        pool_scope = "project"

    params = item.get("params") or {}
    if not isinstance(params, dict):
        params = {}
    extra = item.get("extra") or {}
    if not isinstance(extra, dict):
        extra = {}
    expected_entry_type = str(params.get("expected_entry_type") or extra.get("expected_entry_type") or "").strip().lower()

    site_entry_urls = _resolve_item_site_entries(item)
    if not site_entry_urls:
        raise ValueError("item.params.site_entries is required and cannot be empty for unified search")

    used_entries: list[dict[str, Any]] = []
    candidates: list[str] = []
    candidate_refs: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, str]] = []
    history_pool_urls: set[str] = set()

    def _push(u: str, *, ref: dict[str, Any]) -> None:
        if u and u not in candidates:
            candidates.append(u)
            candidate_refs[u] = ref

    joined_q = quote_plus(" ".join(terms)) if terms else ""

    def _process_site_entry(su: str) -> dict[str, Any]:
        local_errors: list[dict[str, str]] = []
        local_candidates: list[tuple[str, dict[str, Any], float]] = []
        try:
            entry = get_site_entry_by_url(scope="effective", project_key=project_key, site_url=su) or {
                "site_url": su,
                "domain": domain_from_url(su),
                "entry_type": "domain_root",
                "template": None,
                "scope": None,
            }
            etype = str(entry.get("entry_type") or "domain_root").strip().lower()
            if expected_entry_type and etype != expected_entry_type:
                local_errors.append(
                    {
                        "site_url": su,
                        "error": f"entry_type mismatch: expected={expected_entry_type}, actual={etype}",
                    }
                )
                return {"entry": entry, "candidates": local_candidates, "errors": local_errors}

            base_url = str(entry.get("site_url") or su)
            template = entry.get("template")
            entry_domain = (entry.get("domain") or domain_from_url(base_url) or "").strip().lower()
            if not _entry_supports_query_terms(entry, etype):
                return {"entry": None, "candidates": local_candidates, "errors": local_errors}
            # Only keep sources that can accept keyword parameters directly.
            # e.g. search_template(q={{q}}). Filter-style sources (rss/sitemap) are excluded
            # from keyword candidate pool to avoid semantic confusion.
            if _entry_keyword_mode(entry, etype) != "search":
                return {"entry": None, "candidates": local_candidates, "errors": local_errors}

            def _push_local(u: str, *, ref: dict[str, Any], score: float = 0.0) -> None:
                if u:
                    local_candidates.append((u, ref, score))

            if etype == "rss":
                xml_text, _ = fetch_html(base_url, timeout=probe_timeout, retries=1)
                decisions, used_fallback = select_search_candidates(
                    _build_search_candidates(
                        _extract_rss_candidates_from_xml(xml_text),
                        strategy="rss",
                        source_url=base_url,
                        entry_domain=entry_domain,
                    ),
                    terms,
                    strategy="rss",
                    entry_domain=entry_domain,
                    search_url=base_url,
                    allow_fallback=allow_term_fallback,
                )
                if used_fallback:
                    local_errors.append(
                        {
                            "site_url": base_url,
                            "error": (
                                "url_term_filter_empty_fallback_used"
                                if allow_term_fallback
                                else "url_term_filter_empty_no_fallback"
                            ),
                        }
                    )
                for decision in decisions:
                    u = str(decision.url or "").strip()
                    if not u:
                        continue
                    _push_local(
                        u,
                        ref={
                            "site_entry_url": base_url,
                            "entry_type": etype,
                            "entry_domain": entry_domain,
                            "tool": "rss",
                            "matched_by": decision.matched_by,
                            "candidate_quality": decision.candidate_quality,
                            "usable_for_search": decision.usable_for_search,
                        },
                        score=decision.score,
                    )
            elif etype == "sitemap":
                urls = _collect_sitemap_urls(
                    sitemap_url=base_url,
                    timeout=probe_timeout,
                    max_depth=max(0, int(sitemap_max_depth)),
                    max_sitemaps=max(1, int(sitemap_max_sitemaps)),
                )
                decisions, used_fallback = select_search_candidates(
                    _build_search_candidates(
                        [{"url": u, "title": "", "text": ""} for u in urls],
                        strategy="sitemap",
                        source_url=base_url,
                        entry_domain=entry_domain,
                    ),
                    terms,
                    strategy="sitemap",
                    entry_domain=entry_domain,
                    search_url=base_url,
                    allow_fallback=allow_term_fallback,
                )
                if used_fallback:
                    local_errors.append(
                        {
                            "site_url": base_url,
                            "error": (
                                "url_term_filter_empty_fallback_used"
                                if allow_term_fallback
                                else "url_term_filter_empty_no_fallback"
                            ),
                        }
                    )
                for decision in decisions:
                    u = str(decision.url or "").strip()
                    if not u:
                        continue
                    if entry_domain and (domain_from_url(u) or "").lower() != entry_domain:
                        continue
                    _push_local(
                        u,
                        ref={
                            "site_entry_url": base_url,
                            "entry_type": etype,
                            "entry_domain": entry_domain,
                            "tool": "sitemap",
                            "matched_by": decision.matched_by,
                            "candidate_quality": decision.candidate_quality,
                            "usable_for_search": decision.usable_for_search,
                        },
                        score=decision.score,
                    )
            elif etype == "search_template":
                tpl = _normalize_search_template_placeholders(str(template or base_url).strip())
                if "{{q}}" not in tpl:
                    raise ValueError("search_template requires template containing {{q}}")
                url = tpl.replace("{{q}}", joined_q).replace("{{page}}", "1")
                html, _ = fetch_html(url, timeout=probe_timeout, retries=1)
                decisions, used_fallback = select_search_candidates(
                    _build_search_candidates(
                        _extract_link_candidates_from_html(html, base_url=url),
                        strategy="search_template",
                        source_url=url,
                        entry_domain=entry_domain,
                    ),
                    terms,
                    strategy="search_template",
                    entry_domain=entry_domain,
                    search_url=url,
                    allow_fallback=allow_term_fallback,
                )
                if used_fallback:
                    local_errors.append(
                        {
                            "site_url": base_url,
                            "error": (
                                "url_term_filter_empty_fallback_used"
                                if allow_term_fallback
                                else "url_term_filter_empty_no_fallback"
                            ),
                        }
                    )
                for decision in decisions:
                    u = str(decision.url or "").strip()
                    if not u:
                        continue
                    if entry_domain and (domain_from_url(u) or "").lower() != entry_domain:
                        continue
                    _push_local(
                        u,
                        ref={
                            "site_entry_url": base_url,
                            "entry_type": etype,
                            "entry_domain": entry_domain,
                            "tool": "search_template",
                            "matched_by": decision.matched_by,
                            "candidate_quality": decision.candidate_quality,
                            "usable_for_search": decision.usable_for_search,
                        },
                        score=decision.score,
                    )
            else:
                local_errors.append({"site_url": base_url, "error": f"unsupported query entry_type: {etype}"})
            return {"entry": entry, "candidates": local_candidates, "errors": local_errors}
        except HttpFetchError as exc:
            local_errors.append({"site_url": su, "error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            local_errors.append({"site_url": su, "error": str(exc)})
        return {"entry": None, "candidates": local_candidates, "errors": local_errors}

    max_workers = max(1, min(8, len(site_entry_urls)))
    scored_candidates: list[tuple[float, str, dict[str, Any]]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = [ex.submit(_process_site_entry, su) for su in site_entry_urls]
        for fut in as_completed(futures):
            res = fut.result()
            entry = res.get("entry")
            if isinstance(entry, dict):
                used_entries.append(entry)
            for e in res.get("errors") or []:
                if isinstance(e, dict):
                    errors.append(e)
            for u, ref, score in (res.get("candidates") or []):
                scored_candidates.append((float(score or 0.0), u, ref))

    scored_candidates.sort(key=lambda item: (-item[0], item[1]))
    for _, u, ref in scored_candidates:
        _push(u, ref=ref)

    candidates = candidates[:max_candidates]
    # For fallback-retrieved links, drop low-value navigation/legal/account pages.
    candidates = [u for u in candidates if not _is_low_value_candidate_url(u)]

    written: dict[str, int] | None = None
    if auto_ingest:
        try:
            history_pool_urls = _collect_history_pool_urls(
                scope=pool_scope,
                project_key=project_key,
                source=pool_source,
            )
        except Exception:
            history_pool_urls = set()

    if write_to_pool and candidates:
        new_count = 0
        skipped = 0
        for u in candidates:
            ref = candidate_refs.get(u) or {}
            ok = append_url(
                url=u,
                source=pool_source,
                source_ref={"item_key": item_key, "query_terms": terms, **ref},
                scope=pool_scope,
                project_key=project_key,
            )
            if ok:
                new_count += 1
            else:
                skipped += 1
        written = {"urls_new": new_count, "urls_skipped": skipped}

    ingest_result: dict[str, Any] | None = None
    if auto_ingest and (written or candidates):
        try:
            from ..ingest.url_pool import collect_urls_from_list
            from ..projects import bind_project

            ingest_candidates = [u for u in candidates if u not in history_pool_urls]
            ingest_candidates = ingest_candidates[: max(1, min(int(ingest_limit), len(ingest_candidates)))]
            with bind_project(project_key):
                # Auto-ingest should consume current-run candidates directly, instead of
                # pulling historical URLs from shared unified_search pool.
                ir = collect_urls_from_list(
                    ingest_candidates,
                    project_key=project_key,
                    query_terms=terms,
                    enable_extraction=bool(enable_extraction),
                    extra_params={"single_url_target_mode": "detail_only"},
                )
            debug = ir.get("debug")
            if not isinstance(debug, dict):
                debug = {}
                ir["debug"] = debug
            debug["history_pool_filter_applied"] = True
            debug["history_pool_size"] = len(history_pool_urls)
            debug["ingest_candidates_count"] = len(ingest_candidates)
            ingest_result = ir
        except Exception as exc:  # noqa: BLE001
            errors.append({"phase": "auto_ingest", "error": str(exc)})

    return UnifiedSearchResult(
        item_key=item_key,
        query_terms=terms,
        site_entries_used=used_entries,
        candidates=candidates,
        written=written,
        ingest_result=ingest_result,
        errors=errors,
    )
