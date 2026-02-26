"""Generic web tool adapters: rss / sitemap / search_template."""

from __future__ import annotations

from typing import Any, Dict, Iterable
from urllib.parse import quote_plus, urljoin
import gzip
import xml.etree.ElementTree as ET

from ...ingest.adapters.http_utils import fetch_html, make_html_parser
from ...resource_pool.extract import append_url
from ...resource_pool.url_utils import normalize_url


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
        return list(dict.fromkeys(out))
    return []


def _filter_by_terms(urls: list[str], terms: list[str]) -> list[str]:
    if not terms:
        return urls
    low_terms = [x.lower() for x in terms]
    return [u for u in urls if any(t in u.lower() for t in low_terms)]


def _extract_rss_urls(xml_text: str) -> list[str]:
    urls: list[str] = []
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return urls

    for item in root.findall(".//{*}item"):
        link = item.find("{*}link")
        if link is not None and link.text:
            u = normalize_url(link.text.strip())
            if u and u not in urls:
                urls.append(u)
    for entry in root.findall(".//{*}entry"):
        for link in entry.findall("{*}link"):
            href = (link.attrib.get("href") or "").strip()
            if not href:
                continue
            u = normalize_url(href)
            if u and u not in urls:
                urls.append(u)
    return urls


def _extract_sitemap_locs(xml_text: str) -> tuple[str, list[str]]:
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return "unknown", []
    tag = root.tag.split("}", 1)[-1].lower()
    locs: list[str] = []
    for loc in root.findall(".//{*}loc"):
        if loc.text:
            u = normalize_url(loc.text.strip())
            if u and u not in locs:
                locs.append(u)
    return tag, locs


def _fetch_text_maybe_gzip(url: str, timeout: float) -> str:
    text, resp = fetch_html(url, timeout=timeout, retries=1)
    if url.lower().endswith(".gz"):
        try:
            return gzip.decompress(resp.content).decode("utf-8", errors="ignore")
        except Exception:
            return text
    return text


def _collect_sitemap_urls(url: str, timeout: float, max_depth: int = 2, max_sitemaps: int = 30) -> list[str]:
    seen: set[str] = set()
    queue: list[tuple[str, int]] = [(url, 0)]
    urls: list[str] = []
    fetched = 0
    while queue and fetched < max_sitemaps:
        current, depth = queue.pop(0)
        if current in seen:
            continue
        seen.add(current)
        fetched += 1
        xml_text = _fetch_text_maybe_gzip(current, timeout=timeout)
        kind, locs = _extract_sitemap_locs(xml_text)
        if kind.endswith("sitemapindex") and depth < max_depth:
            for loc in locs:
                if loc not in seen:
                    queue.append((loc, depth + 1))
            continue
        for loc in locs:
            if loc not in urls:
                urls.append(loc)
    return urls


def _extract_html_links(html: str, *, base_url: str) -> list[str]:
    urls: list[str] = []
    parser = make_html_parser(html)
    for node in parser.css("a"):
        href = (node.attributes.get("href") or "").strip()
        if not href:
            continue
        u = normalize_url(urljoin(base_url, href))
        if u and u not in urls:
            urls.append(u)
    return urls


def _maybe_write_to_pool(urls: Iterable[str], *, params: Dict[str, Any], project_key: str | None, source: str) -> dict[str, int] | None:
    if not params.get("write_to_pool"):
        return None
    scope = str(params.get("pool_scope") or "project")
    if scope not in {"project", "shared"}:
        scope = "project"
    new_count = 0
    skipped = 0
    for u in urls:
        ok = append_url(
            url=u,
            source=source,
            source_ref={"tool": source, "query_terms": _as_terms(params.get("query_terms"))},
            scope=scope,
            project_key=(project_key or ""),
        )
        if ok:
            new_count += 1
        else:
            skipped += 1
    return {"urls_new": new_count, "urls_skipped": skipped}


def handle_generic_web_rss(params: Dict[str, Any], project_key: str | None) -> Dict[str, Any]:
    feed_url = str(params.get("feed_url") or params.get("site_url") or "").strip()
    if not feed_url:
        raise ValueError("generic_web.rss requires params.feed_url or params.site_url")
    timeout = float(params.get("probe_timeout") or 10)
    terms = _as_terms(params.get("query_terms"))
    xml_text = _fetch_text_maybe_gzip(feed_url, timeout=timeout)
    candidates = _filter_by_terms(_extract_rss_urls(xml_text), terms)
    written = _maybe_write_to_pool(candidates, params=params, project_key=project_key, source="generic_web_rss")
    return {"inserted": len(candidates), "skipped": 0, "candidates": candidates, "written": written}


def handle_generic_web_sitemap(params: Dict[str, Any], project_key: str | None) -> Dict[str, Any]:
    sitemap_url = str(params.get("sitemap_url") or params.get("site_url") or "").strip()
    if not sitemap_url:
        raise ValueError("generic_web.sitemap requires params.sitemap_url or params.site_url")
    timeout = float(params.get("probe_timeout") or 10)
    terms = _as_terms(params.get("query_terms"))
    candidates = _filter_by_terms(
        _collect_sitemap_urls(
            sitemap_url,
            timeout=timeout,
            max_depth=int(params.get("max_depth") or 2),
            max_sitemaps=int(params.get("max_sitemaps") or 30),
        ),
        terms,
    )
    written = _maybe_write_to_pool(candidates, params=params, project_key=project_key, source="generic_web_sitemap")
    return {"inserted": len(candidates), "skipped": 0, "candidates": candidates, "written": written}


def handle_generic_web_search_template(params: Dict[str, Any], project_key: str | None) -> Dict[str, Any]:
    template = str(params.get("template") or params.get("site_url") or "").strip()
    if not template or "{{q}}" not in template:
        raise ValueError("generic_web.search_template requires params.template containing {{q}}")
    timeout = float(params.get("probe_timeout") or 10)
    terms = _as_terms(params.get("query_terms"))
    joined = quote_plus(" ".join(terms)) if terms else ""
    page = str(params.get("page") or 1)
    search_url = template.replace("{{q}}", joined).replace("{{page}}", page)
    html, _ = fetch_html(search_url, timeout=timeout, retries=1)
    candidates = _filter_by_terms(_extract_html_links(html, base_url=search_url), terms)
    written = _maybe_write_to_pool(candidates, params=params, project_key=project_key, source="generic_web_search_template")
    return {"inserted": len(candidates), "skipped": 0, "candidates": candidates, "written": written}

