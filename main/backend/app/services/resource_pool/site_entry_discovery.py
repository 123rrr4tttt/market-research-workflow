"""Script-first discovery of site entries from resource_pool_urls."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import xml.etree.ElementTree as ET
from typing import Any, TypeGuard, cast
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from sqlalchemy import select

from ...models.base import SessionLocal
from ...models.entities import ResourcePoolUrl, SharedResourcePoolUrl
from ..projects import bind_project, bind_schema
from .auto_classify import classify_site_entries_batch, infer_keyword_capabilities
from .http_port import HttpFetchError, fetch_html, make_html_parser
from .site_entries import upsert_site_entry
from .url_utils import normalize_domain, normalize_url

_log = logging.getLogger(__name__)


def _is_string_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict) and all(
        isinstance(key, str) for key in cast(dict[object, object], value)
    )


_DEFAULT_SITEMAP_PATHS: tuple[str, ...] = (
    "/sitemap.xml",
    "/sitemap_index.xml",
    "/sitemap-index.xml",
)

_DEFAULT_RSS_PATHS: tuple[str, ...] = (
    "/rss",
    "/rss.xml",
    "/feed",
    "/feed.xml",
    "/atom.xml",
)

_DEFAULT_SEARCH_PROBE_PATHS: tuple[str, ...] = (
    "/search",
    "/search/",
    "/find",
    "/query",
)


@dataclass
class DiscoveryResult:
    domains_scanned: int
    candidates: list[dict[str, Any]]
    probe_stats: dict[str, int]
    errors: list[dict[str, str]]


@dataclass
class WriteResult:
    upserted: int
    skipped: int
    errors: list[dict[str, str]]


def _discover_domain_candidates(
    *,
    d: str,
    target_scope: str,
    probe_timeout: float,
    include_link_alternate: bool,
    sitemap_paths: list[str] | None,
    rss_paths: list[str] | None,
) -> tuple[list[dict[str, Any]], dict[str, int], list[dict[str, str]]]:
    """Probe a single domain and return candidates, stats, errors."""
    candidates: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    stats = {"domain_root": 0, "sitemap": 0, "rss": 0, "link_alternate": 0, "search_path": 0, "search_form": 0}

    def _push_candidate(
        *,
        site_url: str,
        entry_type: str,
        template: str | None = None,
        source_ref: dict[str, Any] | None = None,
    ) -> None:
        norm = normalize_url(site_url)
        if not norm:
            return
        item: dict[str, Any] = {
            "site_url": norm,
            "domain": d,
            "entry_type": entry_type,
            "template": template,
            "name": None,
            "capabilities": infer_keyword_capabilities(entry_type),
            "source": "discovery",
            "source_ref": source_ref or {},
            "tags": [],
            "enabled": True,
            "extra": {},
            "_target_scope": target_scope,
        }
        if all(x.get("site_url") != norm for x in candidates):
            candidates.append(item)

    try:
        base_urls = _best_effort_base_urls(d)
        if not base_urls:
            return candidates, stats, errors
        _push_candidate(site_url=base_urls[0], entry_type="domain_root", source_ref={"probe": "domain_root"})
        stats["domain_root"] += 1
        sitemap_ok = False
        rss_ok = False
        search_ok = False
        sitemap_probe_paths = [p for p in (sitemap_paths or list(_DEFAULT_SITEMAP_PATHS)) if str(p).strip().startswith("/")]
        rss_probe_paths = [p for p in (rss_paths or list(_DEFAULT_RSS_PATHS)) if str(p).strip().startswith("/")]
        search_probe_paths = list(_DEFAULT_SEARCH_PROBE_PATHS)
        for base in base_urls:
            if not sitemap_ok:
                for p in sitemap_probe_paths:
                    u = urljoin(base, p)
                    ok, ctype = _probe_url_candidate(u, timeout=probe_timeout)
                    if ok:
                        _push_candidate(site_url=u, entry_type="sitemap", source_ref={"probe": "sitemap", "content_type": ctype or ""})
                        stats["sitemap"] += 1
                        sitemap_ok = True
                        break
            if not rss_ok:
                for p in rss_probe_paths:
                    u = urljoin(base, p)
                    ok, ctype = _probe_url_candidate(u, timeout=probe_timeout)
                    if ok:
                        _push_candidate(site_url=u, entry_type="rss", source_ref={"probe": "rss", "content_type": ctype or ""})
                        stats["rss"] += 1
                        rss_ok = True
                        break
            if not search_ok:
                for p in search_probe_paths:
                    u = urljoin(base, p)
                    ok, _ = _probe_url_candidate(u, timeout=probe_timeout)
                    if not ok:
                        continue
                    parsed = urlparse(u)
                    tpl = urlunparse((parsed.scheme, parsed.netloc, parsed.path or "/", parsed.params, "q={{q}}", ""))
                    _push_candidate(site_url=tpl, entry_type="search_template", template=tpl, source_ref={"probe": "search_path", "base": base, "path": p})
                    stats["search_path"] += 1
                    search_ok = True
                    break
            if include_link_alternate and base.startswith("https://"):
                try:
                    html, _ = fetch_html(base, timeout=probe_timeout, retries=1)
                    if not search_ok:
                        for tpl in _extract_search_templates_from_html(html, base_url=base):
                            _push_candidate(site_url=tpl, entry_type="search_template", template=tpl, source_ref={"probe": "search_form", "base": base})
                            stats["search_form"] += 1
                            search_ok = True
                            break
                    for feed_url in _extract_link_alternate_feeds(html, base_url=base):
                        _push_candidate(site_url=feed_url, entry_type="rss", source_ref={"probe": "link_alternate", "base": base})
                        stats["link_alternate"] += 1
                except Exception:
                    pass
    except Exception as exc:  # noqa: BLE001
        errors.append({"domain": d, "error": str(exc)})
    return candidates, stats, errors


def list_discovery_domains(
    *,
    project_key: str,
    url_scope: str = "effective",
    domain: str | None = None,
    limit_domains: int = 50,
    allow_domains: list[str] | None = None,
    deny_domains: list[str] | None = None,
) -> list[str]:
    """Collect candidate domains for site-entry discovery using the same filters as discovery."""
    if url_scope not in {"shared", "project", "effective"}:
        url_scope = "effective"
    limit_domains = min(max(1, int(limit_domains)), 500)

    allow_set = {normalize_domain(str(x)) for x in (allow_domains or []) if str(x).strip()}
    deny_set = {normalize_domain(str(x)) for x in (deny_domains or []) if str(x).strip()}

    def _domain_allowed(d: str) -> bool:
        if deny_set and d in deny_set:
            return False
        if allow_set and d not in allow_set:
            return False
        return True

    domains: list[str] = []
    seen_domains: set[str] = set()

    def _add_domain(d: str | None) -> None:
        dd = normalize_domain(d or "")
        if not dd:
            return
        if domain and dd != normalize_domain(domain):
            return
        if not _domain_allowed(dd):
            return
        if dd in seen_domains:
            return
        seen_domains.add(dd)
        domains.append(dd)

    def _collect_project_domains() -> None:
        with bind_project(project_key):
            with SessionLocal() as session:
                q = select(ResourcePoolUrl.domain).where(ResourcePoolUrl.domain.is_not(None))
                if domain:
                    q = q.where(ResourcePoolUrl.domain == normalize_domain(domain))
                q = q.order_by(ResourcePoolUrl.created_at.desc()).limit(limit_domains * 20)
                for (d,) in session.execute(q).all():
                    _add_domain(d)

    def _collect_shared_domains() -> None:
        with bind_schema("public"):
            with SessionLocal() as session:
                q = select(SharedResourcePoolUrl.domain).where(SharedResourcePoolUrl.domain.is_not(None))
                if domain:
                    q = q.where(SharedResourcePoolUrl.domain == normalize_domain(domain))
                q = q.order_by(SharedResourcePoolUrl.created_at.desc()).limit(limit_domains * 20)
                for (d,) in session.execute(q).all():
                    _add_domain(d)

    if url_scope == "project":
        _collect_project_domains()
    elif url_scope == "shared":
        _collect_shared_domains()
    else:
        _collect_project_domains()
        if len(domains) < limit_domains:
            _collect_shared_domains()
    return domains[:limit_domains]


def _best_effort_base_urls(domain: str) -> list[str]:
    d = normalize_domain(domain)
    if not d:
        return []
    return [f"https://{d}/", f"http://{d}/"]


def _extract_link_alternate_feeds(html: str, *, base_url: str) -> list[str]:
    urls: list[str] = []
    try:
        parser = make_html_parser(html)
        for node in parser.css("link"):
            rel = (node.attributes.get("rel") or "").lower()
            if "alternate" not in rel:
                continue
            typ = (node.attributes.get("type") or "").lower()
            if "rss" not in typ and "atom" not in typ and "xml" not in typ:
                continue
            href = (node.attributes.get("href") or "").strip()
            if not href:
                continue
            abs_url = urljoin(base_url, href)
            norm = normalize_url(abs_url)
            if norm and norm not in urls:
                urls.append(norm)
    except Exception:
        return urls
    return urls


def _probe_url_candidate(url: str, *, timeout: float) -> tuple[bool, str | None]:
    """
    Best-effort probe. Returns (ok, content_type).
    Uses fetch_html because it returns Response with headers/status.
    """
    try:
        _, resp = fetch_html(url, timeout=timeout, retries=1)
        ctype = (resp.headers.get("content-type") or "").lower()
        return True, ctype
    except HttpFetchError:
        return False, None
    except Exception:
        return False, None


def _build_search_template_from_form(base_url: str, form_action: str, query_param: str) -> str | None:
    try:
        action_url = urljoin(base_url, (form_action or "").strip() or base_url)
        parsed = urlparse(action_url)
        if not (parsed.scheme and parsed.netloc):
            return None
        pairs = parse_qsl(parsed.query or "", keep_blank_values=True)
        qkey = (query_param or "").strip()
        if not qkey:
            return None
        out_pairs: list[tuple[str, str]] = []
        replaced = False
        for k, v in pairs:
            lk = (k or "").lower()
            if k == qkey or lk in {"q", "query", "keyword", "keywords", "search"}:
                out_pairs.append((k, "{{q}}"))
                replaced = True
            elif lk in {"page", "p", "paged"} and str(v).strip():
                out_pairs.append((k, "{{page}}"))
            else:
                out_pairs.append((k, v))
        if not replaced:
            out_pairs.append((qkey, "{{q}}"))
        query = urlencode(out_pairs)
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path or "/", parsed.params, query, ""))
    except Exception:
        return None


def _extract_search_templates_from_html(html: str, *, base_url: str) -> list[str]:
    templates: list[str] = []
    try:
        parser = make_html_parser(html)
        for form in parser.css("form"):
            method = (form.attributes.get("method") or "get").strip().lower()
            if method not in {"", "get"}:
                continue
            action = (form.attributes.get("action") or "").strip()
            query_input_name: str | None = None
            for node in form.css("input"):
                input_type = (node.attributes.get("type") or "text").strip().lower()
                if input_type in {"hidden", "submit", "button", "reset", "checkbox", "radio", "password", "file"}:
                    continue
                name = (node.attributes.get("name") or "").strip()
                if not name:
                    continue
                lname = name.lower()
                if lname in {"q", "query", "keyword", "keywords", "search", "term", "s"}:
                    query_input_name = name
                    break
            if not query_input_name:
                continue
            tpl = _build_search_template_from_form(base_url, action, query_input_name)
            if tpl and tpl not in templates:
                templates.append(tpl)
    except Exception:
        return templates
    return templates


def extract_homepage_query_contract_clues(html: str, *, base_url: str) -> list[dict[str, str]]:
    """Extract deterministic GET-form, alternate-feed, and OpenSearch clues."""

    clues: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def _push(kind: str, value: str, evidence: str) -> None:
        key = (kind, value)
        if not value or key in seen:
            return
        seen.add(key)
        clues.append({"kind": kind, "value": value, "evidence": evidence})

    for template in _extract_search_templates_from_html(html, base_url=base_url):
        _push("search_template", template, "homepage_get_form")
    for feed_url in _extract_link_alternate_feeds(html, base_url=base_url):
        _push("rss", feed_url, "homepage_link_alternate")
    try:
        parser = make_html_parser(html)
        for node in parser.css("link"):
            rel = (node.attributes.get("rel") or "").lower()
            typ = (node.attributes.get("type") or "").lower()
            if "search" not in rel or "opensearchdescription" not in typ:
                continue
            href = (node.attributes.get("href") or "").strip()
            if not href:
                continue
            _push("opensearch", urljoin(base_url, href), "homepage_link_opensearch")
    except Exception:
        pass
    return clues


def extract_opensearch_templates(xml_text: str, *, base_url: str) -> list[str]:
    """Extract same-origin HTML query templates from an OpenSearch description."""

    templates: list[str] = []
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return templates
    for node in root.iter():
        if str(node.tag).split("}", 1)[-1] != "Url":
            continue
        typ = str(node.attrib.get("type") or "").strip().lower()
        raw_template = str(node.attrib.get("template") or "").strip()
        if typ != "text/html" or "{searchterms}" not in raw_template.lower():
            continue
        absolute = urljoin(base_url, raw_template)
        template = absolute.replace("{searchTerms}", "{{q}}").replace("{searchterms}", "{{q}}")
        if "{{q}}" in template and template not in templates:
            templates.append(template)
    return templates


def discover_site_entries_from_urls(
    *,
    project_key: str,
    url_scope: str = "effective",
    target_scope: str = "project",
    domain: str | None = None,
    limit_domains: int = 50,
    probe_timeout: float = 8.0,
    include_link_alternate: bool = True,
    sitemap_paths: list[str] | None = None,
    rss_paths: list[str] | None = None,
    allow_domains: list[str] | None = None,
    deny_domains: list[str] | None = None,
    run_auto_classify: bool = False,
    domain_probe_concurrency: int = 6,
) -> DiscoveryResult:
    """
    Scan resource_pool_urls, group by domain, probe common entry points.
    Returns candidates ready for upsert_site_entry.
    """
    if url_scope not in {"shared", "project", "effective"}:
        url_scope = "effective"
    if target_scope not in {"shared", "project"}:
        target_scope = "project"

    limit_domains = min(max(1, int(limit_domains)), 500)
    probe_timeout = float(probe_timeout or 8.0)

    domains = list_discovery_domains(
        project_key=project_key,
        url_scope=url_scope,
        domain=domain,
        limit_domains=limit_domains,
        allow_domains=allow_domains,
        deny_domains=deny_domains,
    )

    candidates: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    stats = {"domain_root": 0, "sitemap": 0, "rss": 0, "link_alternate": 0, "search_path": 0, "search_form": 0}
    seen_site_urls: set[str] = set()
    max_workers = max(1, min(16, int(domain_probe_concurrency or 6)))
    iter_results: list[tuple[list[dict[str, Any]], dict[str, int], list[dict[str, str]]]]
    if max_workers == 1 or len(domains) <= 1:
        iter_results = [
            _discover_domain_candidates(
                d=d,
                target_scope=target_scope,
                probe_timeout=probe_timeout,
                include_link_alternate=include_link_alternate,
                sitemap_paths=sitemap_paths,
                rss_paths=rss_paths,
            )
            for d in domains
        ]
    else:
        iter_results = []
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="site-entry-probe") as ex:
            futs = [
                ex.submit(
                    _discover_domain_candidates,
                    d=d,
                    target_scope=target_scope,
                    probe_timeout=probe_timeout,
                    include_link_alternate=include_link_alternate,
                    sitemap_paths=sitemap_paths,
                    rss_paths=rss_paths,
                )
                for d in domains
            ]
            for fut in as_completed(futs):
                iter_results.append(fut.result())
    for dcands, dstats, derrs in iter_results:
        for item in dcands:
            u = str(item.get("site_url") or "")
            if u and u not in seen_site_urls:
                seen_site_urls.add(u)
                candidates.append(item)
        for k, v in (dstats or {}).items():
            stats[k] = int(stats.get(k, 0)) + int(v or 0)
        errors.extend(derrs or [])

    # Optional: run auto_classify on domain_root candidates that have no sitemap/rss for that domain
    if run_auto_classify:
        domains_with_sitemap_or_rss = {
            c.get("domain") for c in candidates
            if c.get("entry_type") in ("sitemap", "rss") and c.get("domain")
        }
        batch_rows: list[dict[str, Any]] = []
        candidate_indexes: list[int] = []
        for i, c in enumerate(candidates):
            if c.get("entry_type") != "domain_root":
                continue
            d = c.get("domain")
            if d and d in domains_with_sitemap_or_rss:
                continue
            batch_rows.append(
                {
                    "site_url": c.get("site_url", ""),
                    "entry_type": "domain_root",
                    "template": c.get("template"),
                }
            )
            candidate_indexes.append(i)
        if batch_rows:
            try:
                recs = classify_site_entries_batch(batch_rows)
                for rec_row, idx in zip(recs, candidate_indexes):
                    c = candidates[idx]
                    raw_extra = c.get("extra")
                    extra = dict(raw_extra) if _is_string_object_dict(raw_extra) else {}
                    extra["recommended_channel_key"] = rec_row.get("channel_key")
                    extra["recommend_source"] = rec_row.get("source")
                    if rec_row.get("template"):
                        extra["recommended_template"] = rec_row.get("template")
                    c["extra"] = extra
                    current_capabilities = c.get("capabilities")
                    recommended_capabilities = rec_row.get("capabilities")
                    c["capabilities"] = {
                        **(dict(current_capabilities) if _is_string_object_dict(current_capabilities) else {}),
                        **(dict(recommended_capabilities) if _is_string_object_dict(recommended_capabilities) else {}),
                    }
                # Optionally materialize a search_template candidate when recommendation says so.
                existing_urls = {str(x.get("site_url") or "") for x in candidates}
                new_candidates: list[dict[str, Any]] = []
                for rec_row, idx in zip(recs, candidate_indexes):
                    if str(rec_row.get("entry_type") or "") != "search_template":
                        continue
                    tpl = str(rec_row.get("template") or "").strip()
                    if not tpl or tpl in existing_urls:
                        continue
                    src = candidates[idx]
                    source_extra = src.get("extra")
                    clone: dict[str, Any] = {
                        **src,
                        "site_url": tpl,
                        "entry_type": "search_template",
                        "template": tpl,
                        "capabilities": rec_row.get("capabilities") or infer_keyword_capabilities("search_template", "generic_web.search_template"),
                        "extra": {
                            **(dict(source_extra) if _is_string_object_dict(source_extra) else {}),
                            "generated_from_domain_root": src.get("site_url"),
                            "recommended_channel_key": "generic_web.search_template",
                            "recommend_source": rec_row.get("source") or "batch",
                        },
                    }
                    new_candidates.append(clone)
                    existing_urls.add(tpl)
                if new_candidates:
                    candidates.extend(new_candidates)
            except Exception as exc:
                _log.warning("site_entry_discovery auto_classify batch fallback to probes only: %s", exc, exc_info=False)

    return DiscoveryResult(domains_scanned=len(domains), candidates=candidates, probe_stats=stats, errors=errors)


def write_discovered_site_entries(
    *,
    project_key: str,
    candidates: list[dict[str, Any]],
    target_scope: str,
    dry_run: bool = True,
) -> WriteResult:
    if target_scope not in {"shared", "project"}:
        target_scope = "project"

    if dry_run:
        return WriteResult(upserted=0, skipped=len(candidates), errors=[])

    upserted = 0
    skipped = 0
    errors: list[dict[str, str]] = []
    for c in candidates:
        try:
            upsert_site_entry(
                scope=target_scope,
                project_key=project_key if target_scope == "project" else None,
                site_url=c["site_url"],
                entry_type=c.get("entry_type") or "domain_root",
                template=c.get("template"),
                name=c.get("name"),
                domain=c.get("domain"),
                capabilities=c.get("capabilities") or {},
                source=c.get("source") or "discovery",
                source_ref=c.get("source_ref") or {},
                tags=c.get("tags") or [],
                enabled=bool(c.get("enabled", True)),
                extra=c.get("extra") or {},
            )
            upserted += 1
        except Exception as exc:  # noqa: BLE001
            errors.append({"site_url": str(c.get("site_url")), "error": str(exc)})
            skipped += 1
    return WriteResult(upserted=upserted, skipped=skipped, errors=errors)
