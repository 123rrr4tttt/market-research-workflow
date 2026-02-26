"""Script-first discovery of site entries from resource_pool_urls."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

from sqlalchemy import select

from ...models.base import SessionLocal
from ...models.entities import ResourcePoolUrl, SharedResourcePoolUrl
from ..projects import bind_project, bind_schema
from ..ingest.adapters.http_utils import HttpFetchError, fetch_html, make_html_parser
from .auto_classify import classify_site_entry
from .site_entries import upsert_site_entry
from .url_utils import domain_from_url, normalize_url


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


def _best_effort_base_urls(domain: str) -> list[str]:
    d = (domain or "").strip().lower()
    d = d.lstrip("www.")
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
    use_llm: bool = False,
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

    allow_set = {str(x).strip().lower().lstrip("www.") for x in (allow_domains or []) if str(x).strip()}
    deny_set = {str(x).strip().lower().lstrip("www.") for x in (deny_domains or []) if str(x).strip()}

    def _domain_allowed(d: str) -> bool:
        if deny_set and d in deny_set:
            return False
        if allow_set and d not in allow_set:
            return False
        return True

    domains: list[str] = []
    seen_domains: set[str] = set()

    def _add_domain(d: str | None) -> None:
        dd = (d or "").strip().lower().lstrip("www.")
        if not dd:
            return
        if domain and dd != domain.strip().lower().lstrip("www."):
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
                    q = q.where(ResourcePoolUrl.domain == domain.strip().lower().lstrip("www."))
                q = q.order_by(ResourcePoolUrl.created_at.desc()).limit(limit_domains * 20)
                rows = session.execute(q).all()
                for (d,) in rows:
                    _add_domain(d)

    def _collect_shared_domains() -> None:
        with bind_schema("public"):
            with SessionLocal() as session:
                q = select(SharedResourcePoolUrl.domain).where(SharedResourcePoolUrl.domain.is_not(None))
                if domain:
                    q = q.where(SharedResourcePoolUrl.domain == domain.strip().lower().lstrip("www."))
                q = q.order_by(SharedResourcePoolUrl.created_at.desc()).limit(limit_domains * 20)
                rows = session.execute(q).all()
                for (d,) in rows:
                    _add_domain(d)

    if url_scope == "project":
        _collect_project_domains()
    elif url_scope == "shared":
        _collect_shared_domains()
    else:
        _collect_project_domains()
        if len(domains) < limit_domains:
            _collect_shared_domains()

    domains = domains[:limit_domains]

    candidates: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    stats = {"domain_root": 0, "sitemap": 0, "rss": 0, "link_alternate": 0}

    def _push_candidate(
        *,
        site_url: str,
        entry_type: str,
        d: str,
        template: str | None = None,
        source_ref: dict[str, Any] | None = None,
    ) -> None:
        norm = normalize_url(site_url)
        if not norm:
            return
        item = {
            "site_url": norm,
            "domain": d,
            "entry_type": entry_type,
            "template": template,
            "name": None,
            "capabilities": {},
            "source": "discovery",
            "source_ref": source_ref or {},
            "tags": [],
            "enabled": True,
            "extra": {},
            "_target_scope": target_scope,
        }
        if all(x.get("site_url") != norm for x in candidates):
            candidates.append(item)

    for d in domains:
        try:
            base_urls = _best_effort_base_urls(d)
            if not base_urls:
                continue

            # Always emit domain_root candidate (best-effort, no probe).
            _push_candidate(
                site_url=base_urls[0],
                entry_type="domain_root",
                d=d,
                source_ref={"probe": "domain_root"},
            )
            stats["domain_root"] += 1

            # Probe sitemap/rss on both https/http; stop after first success per type.
            sitemap_ok = False
            rss_ok = False

            sitemap_probe_paths = [p for p in (sitemap_paths or list(_DEFAULT_SITEMAP_PATHS)) if str(p).strip().startswith("/")]
            rss_probe_paths = [p for p in (rss_paths or list(_DEFAULT_RSS_PATHS)) if str(p).strip().startswith("/")]

            for base in base_urls:
                if not sitemap_ok:
                    for p in sitemap_probe_paths:
                        u = urljoin(base, p)
                        ok, ctype = _probe_url_candidate(u, timeout=probe_timeout)
                        if ok:
                            _push_candidate(site_url=u, entry_type="sitemap", d=d, source_ref={"probe": "sitemap", "content_type": ctype or ""})
                            stats["sitemap"] += 1
                            sitemap_ok = True
                            break
                if not rss_ok:
                    for p in rss_probe_paths:
                        u = urljoin(base, p)
                        ok, ctype = _probe_url_candidate(u, timeout=probe_timeout)
                        if ok:
                            _push_candidate(site_url=u, entry_type="rss", d=d, source_ref={"probe": "rss", "content_type": ctype or ""})
                            stats["rss"] += 1
                            rss_ok = True
                            break

                if include_link_alternate and base.startswith("https://"):
                    try:
                        html, _ = fetch_html(base, timeout=probe_timeout, retries=1)
                        for feed_url in _extract_link_alternate_feeds(html, base_url=base):
                            fd = domain_from_url(feed_url) or d
                            _push_candidate(
                                site_url=feed_url,
                                entry_type="rss",
                                d=fd,
                                source_ref={"probe": "link_alternate", "base": base},
                            )
                            stats["link_alternate"] += 1
                    except Exception:
                        pass
        except Exception as exc:  # noqa: BLE001
            errors.append({"domain": d, "error": str(exc)})

    # Optional: run auto_classify on domain_root candidates that have no sitemap/rss for that domain
    if run_auto_classify:
        domains_with_sitemap_or_rss = {
            c.get("domain") for c in candidates
            if c.get("entry_type") in ("sitemap", "rss") and c.get("domain")
        }
        for c in candidates:
            if c.get("entry_type") != "domain_root":
                continue
            d = c.get("domain")
            if d and d in domains_with_sitemap_or_rss:
                continue
            try:
                rec = classify_site_entry(
                    site_url=c.get("site_url", ""),
                    entry_type="domain_root",
                    template=c.get("template"),
                    use_llm=use_llm,
                )
                extra = c.get("extra") or {}
                extra["recommended_channel_key"] = rec.channel_key
                extra["recommend_source"] = rec.source
                c["extra"] = extra
            except Exception:
                pass

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

