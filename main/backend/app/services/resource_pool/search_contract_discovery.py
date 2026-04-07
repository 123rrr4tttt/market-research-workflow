"""Search contract discovery and persistence for site entries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .search_template_service import execute_search_template, normalize_search_template_placeholders
from .site_entries import get_site_entry_by_url, upsert_site_entry
from .url_utils import domain_from_url, normalize_url

_DEFAULT_TEMPLATE_PATHS = (
    "/search?q={{q}}",
    "/search?query={{q}}",
    "/?s={{q}}",
)

_DEFAULT_QUERY_SUFFIXES = (
    "",
    "news",
    "blog",
    "release",
    "announcement",
    "pricing",
)


@dataclass(frozen=True)
class SearchContractProbeRow:
    template: str
    query_text: str
    candidate_count: int
    selected_count: int
    search_service: str
    score: float


@dataclass(frozen=True)
class SearchContractDiscoveryResult:
    site_url: str
    domain: str
    entry_type: str
    templates_tried: list[str]
    suffixes_tried: list[str]
    best_template: str | None
    best_suffix: str | None
    best_score: float
    probe_rows: list[SearchContractProbeRow]
    persisted_entry: dict[str, Any] | None


def _candidate_templates(site_url: str, template: str | None) -> list[str]:
    out: list[str] = []
    normalized_template = normalize_search_template_placeholders(template)
    if normalized_template and "{{q}}" in normalized_template:
        out.append(normalized_template)
    normalized_site = normalize_url(site_url) or str(site_url or "").strip()
    if normalized_site:
        if "{{q}}" in normalized_site and normalized_site not in out:
            out.append(normalized_site)
        if "?" not in normalized_site:
            for path in _DEFAULT_TEMPLATE_PATHS:
                candidate = f"{normalized_site.rstrip('/')}{path}"
                if candidate not in out:
                    out.append(candidate)
    return out


def _query_variants(query_terms: list[str], suffixes: list[str]) -> list[tuple[str, str]]:
    base = " ".join([term for term in query_terms if str(term or "").strip()]).strip()
    if not base:
        raise ValueError("query_terms is required")
    variants: list[tuple[str, str]] = []
    for suffix in suffixes:
        normalized_suffix = str(suffix or "").strip()
        query_text = f"{base} {normalized_suffix}".strip()
        variants.append((query_text, normalized_suffix))
    return variants


def discover_search_contract(
    *,
    scope: str,
    project_key: str | None,
    site_url: str,
    query_terms: list[str] | str,
    suffixes: list[str] | None = None,
    max_pages: int = 1,
    probe_timeout: float = 6.0,
    persist: bool = True,
) -> SearchContractDiscoveryResult:
    terms = query_terms if isinstance(query_terms, list) else [str(query_terms or "").strip()]
    entry = get_site_entry_by_url(scope="effective", project_key=project_key, site_url=site_url) or {
        "site_url": site_url,
        "entry_type": "search_template",
        "template": None,
        "extra": {},
        "capabilities": {},
    }
    normalized_site_url = normalize_url(str(entry.get("site_url") or site_url).strip()) or str(site_url or "").strip()
    domain = str(entry.get("domain") or domain_from_url(normalized_site_url) or "").strip().lower()
    templates = _candidate_templates(normalized_site_url, str(entry.get("template") or "").strip() or None)
    suffix_rows = _query_variants(terms, list(suffixes or _DEFAULT_QUERY_SUFFIXES))
    rows: list[SearchContractProbeRow] = []
    best_template: str | None = None
    best_suffix: str | None = None
    best_score = -1.0

    for template in templates:
        for query_text, suffix in suffix_rows:
            execution = execute_search_template(
                template=template,
                query_terms=[query_text],
                params={"max_pages": max(1, int(max_pages)), "enable_search_service_fallback": True},
                probe_timeout=float(probe_timeout or 6.0),
                allow_term_fallback=False,
                entry_domain=domain or None,
            )
            selected_count = len(execution.selected_candidates or [])
            candidate_count = len(execution.raw_candidates or [])
            score = float(selected_count * 10 + candidate_count)
            rows.append(
                SearchContractProbeRow(
                    template=template,
                    query_text=query_text,
                    candidate_count=candidate_count,
                    selected_count=selected_count,
                    search_service=str(execution.diagnostics.get("search_service") or "basic"),
                    score=score,
                )
            )
            if score > best_score:
                best_score = score
                best_template = template
                best_suffix = suffix or None

    persisted_entry = None
    if persist and best_template:
        existing_extra = dict(entry.get("extra") or {})
        existing_extra["search_contract_profile"] = {
            "service": "search_contract_discovery",
            "best_template": best_template,
            "best_suffix": best_suffix,
            "best_score": best_score,
            "templates_tried": templates,
            "suffixes_tried": [suffix for _, suffix in suffix_rows],
            "probe_rows": [
                {
                    "template": row.template,
                    "query_text": row.query_text,
                    "candidate_count": row.candidate_count,
                    "selected_count": row.selected_count,
                    "search_service": row.search_service,
                    "score": row.score,
                }
                for row in rows
            ],
        }
        persisted_entry = upsert_site_entry(
            scope=scope,
            project_key=project_key,
            site_url=normalized_site_url,
            entry_type=str(entry.get("entry_type") or "search_template").strip() or "search_template",
            template=best_template,
            domain=domain or None,
            capabilities=dict(entry.get("capabilities") or {}),
            source=str(entry.get("source") or "search_contract_discovery"),
            source_ref={
                **dict(entry.get("source_ref") or {}),
                "service": "search_contract_discovery",
                "best_suffix": best_suffix,
            },
            tags=list(entry.get("tags") or []),
            enabled=bool(entry.get("enabled", True)),
            extra=existing_extra,
        )

    return SearchContractDiscoveryResult(
        site_url=normalized_site_url,
        domain=domain,
        entry_type=str(entry.get("entry_type") or "search_template"),
        templates_tried=templates,
        suffixes_tried=[suffix for _, suffix in suffix_rows],
        best_template=best_template,
        best_suffix=best_suffix,
        best_score=max(best_score, 0.0),
        probe_rows=rows,
        persisted_entry=persisted_entry,
    )
