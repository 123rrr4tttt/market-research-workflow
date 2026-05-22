from __future__ import annotations

from hashlib import sha256
import re
from typing import Any
from urllib.parse import urlparse

from ..ingest.meaningful_gate import url_policy_check
from ..ingest.url_unwrap import unwrap_url
from ..resource_pool.url_utils import canonicalize_url, domain_from_url
from .external_project import validate_external_http_url


SOURCE_CANDIDATE_PLAN_CONTRACT_VERSION = "source_library.source_candidate_plan.v1"
DEFAULT_MIN_TRUST_SCORE = 60.0
SOURCE_POLICY_ACTIONS = ("allow", "downgrade", "block")
PRE_INGEST_REQUIRED_CHECKS = [
    "redirect_chain_validation",
    "content_type_allowlist",
    "content_length_limit",
    "body_sha256",
    "dedupe_against_existing_sources",
    "rollback_log",
]

_LOW_TRUST_DOMAINS = {
    "google.com",
    "bing.com",
    "duckduckgo.com",
    "baidu.com",
    "yahoo.com",
    "x.com",
    "twitter.com",
    "facebook.com",
    "linkedin.com",
    "youtube.com",
    "reddit.com",
}
_PUBLIC_INTEREST_SUFFIXES = (".gov", ".edu", ".ac.uk", ".gov.uk", ".europa.eu")


def build_source_candidate_plan(
    *,
    project_key: str,
    query: str | None,
    urls: Any = None,
    domains: Any = None,
    source_library_items: list[dict[str, Any]] | None = None,
    max_candidates: int = 20,
    min_trust_score: float = DEFAULT_MIN_TRUST_SCORE,
) -> dict[str, Any]:
    """Build a no-fetch/no-write source candidate plan for AgentCore.

    This is intentionally a planning gate. It normalizes and scores URLs, but
    leaves redirect/content/checksum validation to the ingest path where
    network access and rollback logs exist.
    """

    project = str(project_key or "").strip()
    query_text = str(query or "").strip()
    limit = max(1, min(50, int(max_candidates or 20)))
    threshold = max(0.0, min(100.0, float(min_trust_score or DEFAULT_MIN_TRUST_SCORE)))
    domain_values = _normalize_domains(domains)

    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []
    seen_normalized: set[str] = set()

    for raw_url in _normalize_url_inputs(urls):
        evaluated = evaluate_source_candidate_url(
            raw_url,
            query=query_text,
            requested_domains=domain_values,
            min_trust_score=threshold,
        )
        normalized_url = str(evaluated.get("normalized_url") or "").strip()
        if normalized_url and normalized_url in seen_normalized:
            duplicate = dict(evaluated)
            duplicate["status"] = "duplicate"
            duplicate["blocked_reason"] = "duplicate_candidate_url"
            duplicate["source_policy_action"] = "downgrade"
            duplicate["source_policy_reason"] = "normalized_url_duplicate_retained_as_trace"
            duplicates.append(duplicate)
            continue
        if normalized_url:
            seen_normalized.add(normalized_url)
        if evaluated.get("status") == "accepted":
            accepted.append(evaluated)
        else:
            rejected.append(evaluated)

    accepted = accepted[:limit]
    candidate_items = rank_source_library_items_for_query(
        source_library_items or [],
        query=query_text,
        domains=domain_values,
        limit=limit,
    )

    search_queries = build_candidate_search_queries(query=query_text, domains=domain_values, limit=8)
    return {
        "contract_version": SOURCE_CANDIDATE_PLAN_CONTRACT_VERSION,
        "project_key": project,
        "query": query_text,
        "search_queries": search_queries,
        "candidate_urls": accepted,
        "rejected_urls": rejected,
        "duplicate_urls": duplicates,
        "candidate_source_items": candidate_items,
        "trust_policy": {
            "network_fetch_performed": False,
            "external_write_performed": False,
            "min_trust_score": threshold,
            "url_public_host_validation": "external_project.validate_external_http_url",
            "wrapper_normalization": "ingest.url_unwrap.unwrap_url:no_network_redirect",
            "url_quality_gate": "ingest.meaningful_gate.url_policy_check",
            "source_score": "0_to_100_trust_score",
            "duplicate_detection": "normalized_url_dedupe",
            "stale_source_handling": "record publication dates during ingest and down-rank stale evidence during synthesis",
            "source_conflict_notes": "record conflicting claims and preserve source locator before synthesis",
            "source_policy_actions": list(SOURCE_POLICY_ACTIONS),
            "source_policy_decision_field": "source_policy_action",
            "source_policy_reason_field": "source_policy_reason",
            "pre_ingest_required_checks": list(PRE_INGEST_REQUIRED_CHECKS),
        },
        "counts": {
            "candidate_urls": len(accepted),
            "rejected_urls": len(rejected),
            "duplicate_urls": len(duplicates),
            "candidate_source_items": len(candidate_items),
            "search_queries": len(search_queries),
        },
        "next_gate": "approval_governed_ingest_or_source_library_run",
    }


def evaluate_source_candidate_url(
    raw_url: Any,
    *,
    query: str | None = None,
    requested_domains: list[str] | None = None,
    min_trust_score: float = DEFAULT_MIN_TRUST_SCORE,
) -> dict[str, Any]:
    original = str(raw_url or "").strip()
    base = {
        "original_url": original,
        "normalized_url": None,
        "domain": None,
        "status": "rejected",
        "trust_score": 0.0,
        "trust_level": "blocked",
        "blocked_reason": None,
        "source_policy_action": "block",
        "source_policy_reason": "unvalidated_or_blocked_candidate",
        "normalization_steps": [],
        "url_checksum": None,
        "content_sha256": None,
        "pre_ingest_required_checks": list(PRE_INGEST_REQUIRED_CHECKS),
    }
    if not original:
        base["blocked_reason"] = "empty_url"
        return base

    unwrapped = unwrap_url(original, enable_network_redirect=False)
    candidate = str(unwrapped.url or original).strip()
    steps = list(unwrapped.steps or [])

    canonical, canonical_reason = canonicalize_url(candidate)
    if not canonical:
        base["normalization_steps"] = steps
        base["blocked_reason"] = canonical_reason
        return base
    if canonical_reason and canonical_reason != "exact_match":
        steps.append(canonical_reason)

    try:
        normalized_url = validate_external_http_url(canonical, field_name="source_candidate_url")
    except ValueError as exc:
        base.update(
            {
                "normalized_url": canonical,
                "domain": domain_from_url(canonical),
                "normalization_steps": steps,
                "blocked_reason": str(exc),
            }
        )
        return base

    parsed = urlparse(normalized_url)
    domain = str(domain_from_url(normalized_url) or "").strip().lower()
    gate = url_policy_check(normalized_url)
    score, reasons = _score_candidate_url(
        normalized_url,
        query=str(query or ""),
        requested_domains=requested_domains or [],
        url_policy_accepted=bool(getattr(gate, "accepted", False)),
        unwrapped=bool(unwrapped.changed),
    )
    status = "accepted" if bool(getattr(gate, "accepted", False)) and score >= float(min_trust_score) else "rejected"
    blocked_reason = None
    if not bool(getattr(gate, "accepted", False)):
        blocked_reason = str(getattr(gate, "reason", "") or "url_policy_rejected")
    elif status != "accepted":
        blocked_reason = "trust_score_below_minimum"

    policy_action, policy_reason = _source_policy_action(
        status=status,
        blocked_reason=blocked_reason,
        trust_score=score,
        url_policy_accepted=bool(getattr(gate, "accepted", False)),
    )
    return {
        **base,
        "normalized_url": normalized_url,
        "domain": domain,
        "scheme": str(parsed.scheme or "").lower(),
        "status": status,
        "trust_score": score,
        "trust_level": _trust_level(score),
        "blocked_reason": blocked_reason,
        "source_policy_action": policy_action,
        "source_policy_reason": policy_reason,
        "normalization_steps": steps,
        "url_policy": {
            "accepted": bool(getattr(gate, "accepted", False)),
            "blocked": bool(getattr(gate, "blocked", False)),
            "reason": str(getattr(gate, "reason", "") or ""),
            "quality_score": float(getattr(gate, "quality_score", 0.0) or 0.0),
            "diagnostics": dict(getattr(gate, "diagnostics", {}) or {}),
        },
        "trust_reasons": reasons,
        "url_checksum": sha256(normalized_url.encode("utf-8")).hexdigest(),
    }


def build_candidate_search_queries(*, query: str | None, domains: list[str] | None = None, limit: int = 8) -> list[str]:
    query_text = str(query or "").strip()
    domain_values = _normalize_domains(domains)
    queries: list[str] = []
    if query_text:
        queries.append(query_text)
        queries.extend(f"site:{domain} {query_text}" for domain in domain_values)
        if not any(token in query_text.lower() for token in ("source", "report", "data", "news")):
            queries.append(f"{query_text} report data news")
    else:
        queries.extend(f"site:{domain}" for domain in domain_values)
    return _dedupe_text(queries)[: max(1, int(limit or 8))]


def rank_source_library_items_for_query(
    items: list[dict[str, Any]],
    *,
    query: str | None,
    domains: list[str] | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    query_tokens = _tokens(query)
    domain_values = _normalize_domains(domains)
    ranked: list[dict[str, Any]] = []
    for raw in items:
        item = dict(raw or {})
        item_key = str(item.get("item_key") or "").strip()
        if not item_key:
            continue
        haystack = _item_haystack(item)
        score = 0.0
        matched_tokens: list[str] = []
        for token in query_tokens:
            if token and token in haystack:
                score += 8.0
                matched_tokens.append(token)
        for domain in domain_values:
            if domain and domain in haystack:
                score += 12.0
        channel_key = str(item.get("channel_key") or "").strip().lower()
        if item_key.startswith("handler.cluster") or channel_key == "handler.cluster":
            score += 25.0
            execution_fit = "preferred_handler_cluster_frontdoor"
        elif "generic_web" in item_key or channel_key == "generic_web":
            score += 8.0
            execution_fit = "site_search_adapter"
        else:
            score += 4.0
            execution_fit = "candidate_source_library_item"
        if bool(item.get("enabled", True)):
            score += 5.0
        ranked.append(
            {
                "item_key": item_key,
                "name": item.get("name") or item_key,
                "channel_key": item.get("channel_key"),
                "enabled": bool(item.get("enabled", True)),
                "item_type": item.get("item_type"),
                "managed_by": item.get("managed_by"),
                "score": round(score, 2),
                "matched_tokens": _dedupe_text(matched_tokens),
                "execution_fit": execution_fit,
            }
        )
    ranked.sort(key=lambda item: (-float(item.get("score") or 0.0), str(item.get("item_key") or "")))
    return ranked[: max(1, int(limit or 20))]


def _score_candidate_url(
    normalized_url: str,
    *,
    query: str,
    requested_domains: list[str],
    url_policy_accepted: bool,
    unwrapped: bool,
) -> tuple[float, list[str]]:
    parsed = urlparse(normalized_url)
    domain = str(domain_from_url(normalized_url) or "").strip().lower()
    score = 35.0
    reasons = ["http_url_public_host_validated"]
    if str(parsed.scheme or "").lower() == "https":
        score += 25.0
        reasons.append("https")
    if url_policy_accepted:
        score += 15.0
        reasons.append("url_policy_ok")
    if unwrapped:
        score += 5.0
        reasons.append("wrapper_unwrapped_without_network_redirect")
    if any(domain == item or domain.endswith(f".{item}") for item in requested_domains):
        score += 10.0
        reasons.append("requested_domain_match")
    if any(domain.endswith(suffix) for suffix in _PUBLIC_INTEREST_SUFFIXES):
        score += 10.0
        reasons.append("public_interest_domain")
    if domain in _LOW_TRUST_DOMAINS or any(domain.endswith(f".{item}") for item in _LOW_TRUST_DOMAINS):
        score -= 30.0
        reasons.append("low_trust_aggregator_or_social_domain")
    query_tokens = _tokens(query)
    path_text = f"{domain} {parsed.path or ''}".lower()
    if query_tokens and any(token in path_text for token in query_tokens):
        score += 5.0
        reasons.append("query_token_in_url")
    return round(max(0.0, min(100.0, score)), 2), reasons


def _trust_level(score: float) -> str:
    if score >= 85.0:
        return "high"
    if score >= 60.0:
        return "medium"
    if score > 0.0:
        return "low"
    return "blocked"


def _source_policy_action(
    *,
    status: str,
    blocked_reason: str | None,
    trust_score: float,
    url_policy_accepted: bool,
) -> tuple[str, str]:
    if not url_policy_accepted:
        return "block", str(blocked_reason or "url_policy_rejected")
    if status == "accepted" and trust_score >= 85.0:
        return "allow", "high_trust_candidate"
    if status == "accepted":
        return "downgrade", "medium_trust_candidate_requires_review_before_bulk_ingest"
    if str(blocked_reason or "") == "trust_score_below_minimum" and trust_score > 0.0:
        return "downgrade", "low_trust_candidate_retained_for_review_only"
    return "block", str(blocked_reason or "source_candidate_rejected")


def _normalize_url_inputs(value: Any) -> list[str]:
    raw_values: list[Any]
    if isinstance(value, list):
        raw_values = list(value)
    elif isinstance(value, str):
        raw_values = [value]
    else:
        raw_values = []
    out: list[str] = []
    for raw in raw_values:
        item = str(raw or "").strip()
        if item and item not in out:
            out.append(item)
    return out


def _normalize_domains(value: Any) -> list[str]:
    raw_values: list[Any]
    if isinstance(value, list):
        raw_values = list(value)
    elif isinstance(value, str):
        raw_values = [value]
    else:
        raw_values = []
    domains: list[str] = []
    for raw in raw_values:
        text = str(raw or "").strip().lower()
        if not text:
            continue
        if "://" in text:
            text = str(domain_from_url(text) or "").strip().lower()
        text = text.split("/", 1)[0].strip().lstrip(".")
        if text.startswith("www."):
            text = text[4:]
        if text and text not in domains:
            domains.append(text)
    return domains


def _tokens(value: str | None) -> list[str]:
    return [
        token
        for token in re.split(r"[\s,，。；;:：/|()（）\[\]{}]+", str(value or "").lower())
        if len(token.strip()) >= 2
    ]


def _item_haystack(item: dict[str, Any]) -> str:
    parts = [
        item.get("item_key"),
        item.get("name"),
        item.get("channel_key"),
        item.get("item_type"),
        item.get("description"),
        item.get("managed_by"),
    ]
    if isinstance(item.get("tags"), list):
        parts.extend(item.get("tags") or [])
    if isinstance(item.get("params"), dict):
        parts.extend(str(v) for v in dict(item.get("params") or {}).values())
    if isinstance(item.get("extra"), dict):
        parts.extend(str(v) for v in dict(item.get("extra") or {}).values())
    return " ".join(str(part or "").lower() for part in parts)


def _dedupe_text(values: list[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in out:
            out.append(text)
    return out
