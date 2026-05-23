from __future__ import annotations

import base64
import re
from typing import Any
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from ..extraction.json_utils import extract_json_payload
from ..http.client import default_http_client
from ..skill_runtime import invoke_skill
from .external_project import (
    EXTERNAL_PROJECT_CHANNEL_KEY,
    EXTERNAL_PROJECT_MANIFEST_KEY,
    EXTERNAL_PROJECT_MANIFEST_CONTRACT_VERSION,
    normalize_external_project_manifest,
    validate_external_http_url,
)
from .external_project_registry import list_external_project_provider_bindings

_DEFAULT_SUMMARY_CHAR_LIMIT = 6000
_GITHUB_API_BASE = "https://api.github.com/repos"
_DEFAULT_SITEMAP_PATHS = (
    "/sitemap.xml",
    "/sitemap_index.xml",
    "/sitemap-index.xml",
    "/news-sitemap.xml",
)
_DEFAULT_RSS_PATHS = (
    "/rss",
    "/rss.xml",
    "/feed",
    "/feed.xml",
    "/atom.xml",
)
_URL_PATTERN = re.compile(r"https?://[^\s<>'\"`]+", re.IGNORECASE)


def synthesize_external_project_item(
    *,
    project_link: str,
    item_key: str | None = None,
    display_name: str | None = None,
    description: str | None = None,
    tags: list[str] | None = None,
    hints: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_link = validate_external_http_url(project_link, field_name="project_link")

    project_context = collect_external_project_context(project_link=normalized_link, hints=hints)
    if not _has_meaningful_evidence(project_context):
        raise ValueError("unable to collect enough external project evidence for manifest synthesis")
    resolved_item_key = _resolve_item_key(item_key=item_key, project_link=normalized_link)
    resolved_display_name = _resolve_display_name(display_name=display_name, project_link=normalized_link)
    manifest = synthesize_external_project_manifest(
        project_link=normalized_link,
        item_key=resolved_item_key,
        display_name=resolved_display_name,
        project_context=project_context,
        hints=hints,
    )

    return {
        "item_key": resolved_item_key,
        "name": resolved_display_name,
        "channel_key": EXTERNAL_PROJECT_CHANNEL_KEY,
        "description": str(description or "").strip() or f"Registered external project item for {resolved_display_name}.",
        "params": {},
        "tags": list(tags or []),
        "enabled": True,
        "item_type": "user_defined",
        "extra": {
            EXTERNAL_PROJECT_MANIFEST_KEY: manifest,
        },
        "registration_context": {
            **project_context,
            "provider_binding": dict((manifest.get("provider_binding") or {})),
        },
    }


def synthesize_external_project_manifest(
    *,
    project_link: str,
    item_key: str,
    display_name: str,
    project_context: dict[str, Any],
    hints: dict[str, Any] | None = None,
) -> dict[str, Any]:
    deterministic_manifest = _build_manifest_from_context(
        project_link=project_link,
        item_key=item_key,
        display_name=display_name,
        project_context=project_context,
        hints=hints,
    )
    if deterministic_manifest is not None:
        return deterministic_manifest

    prompt = _build_manifest_prompt(
        project_link=project_link,
        item_key=item_key,
        display_name=display_name,
        project_context=project_context,
        hints=hints,
    )
    invoked = invoke_skill(
        skill_id="workflow.llm_call",
        payload={
            "prompt": prompt,
            "temperature": 0.0,
            "max_tokens": 1200,
        },
        context={
            "actor_role": "orchestration_runtime",
            "permissions": ["workflow.llm_call"],
            "trace_id": f"source-library.external-project.{item_key}",
            "consumer": "source_library.external_project.registration",
        },
    )
    result = invoked.get("result") if isinstance(invoked, dict) else None
    text = ""
    if isinstance(result, dict):
        text = str(result.get("text") or "").strip()
    else:
        text = str(result or "").strip()
    payload = extract_json_payload(text)
    if not isinstance(payload, dict):
        raise ValueError("LLM did not return a valid external project manifest JSON object")
    payload.setdefault("contract_version", EXTERNAL_PROJECT_MANIFEST_CONTRACT_VERSION)
    payload.setdefault("item_key", item_key)
    payload.setdefault("display_name", display_name)
    payload.setdefault("project_link", project_link)
    manifest = normalize_external_project_manifest(
        payload,
        item_key=item_key,
        display_name=display_name,
    )
    return manifest


def _build_manifest_from_context(
    *,
    project_link: str,
    item_key: str,
    display_name: str,
    project_context: dict[str, Any],
    hints: dict[str, Any] | None,
) -> dict[str, Any] | None:
    candidates = project_context.get("endpoint_candidates")
    if not isinstance(candidates, list):
        return None

    high_confidence = [
        dict(candidate)
        for candidate in candidates
        if isinstance(candidate, dict) and str(candidate.get("confidence") or "").strip().lower() == "high"
    ]
    if not high_confidence:
        return None

    chosen = high_confidence[0]
    execution_mode = str(chosen.get("execution_mode") or "").strip().lower()
    runner_ref = str(chosen.get("runner_ref") or "").strip()
    if execution_mode not in {"rss_feed", "sitemap", "http_api"} or not runner_ref:
        return None

    payload: dict[str, Any] = {
        "contract_version": EXTERNAL_PROJECT_MANIFEST_CONTRACT_VERSION,
        "item_key": item_key,
        "display_name": display_name,
        "project_link": project_link,
        "source_kind": str((hints or {}).get("source_kind") or "").strip() or _infer_source_kind(execution_mode),
        "source_scope": str((hints or {}).get("source_scope") or "").strip() or _infer_source_scope(project_context),
        "capabilities": _default_capabilities_for_mode(execution_mode),
        "accepted_inputs": {
            "query_terms": True,
            "urls": False,
            "domains": False,
            "date_range": execution_mode == "http_api",
            "max_items": True,
        },
        "execution_mode": execution_mode,
        "runner_ref": runner_ref,
        "normalization": {
            "record_kind": "article_metadata",
            "frontdoor_strategy": "records_only_defer",
        },
        "limits": {
            "default_max_items": 20,
            "max_items_cap": 100,
            "request_timeout_ms": 30000,
        },
        "refresh_policy": {
            "manifest_ttl_minutes": 60,
            "probe_ttl_minutes": 1440,
        },
        "provenance": {
            "discovered_by": "context_probe",
            "source_refs": [project_link, runner_ref],
        },
    }
    if execution_mode == "http_api":
        payload["runtime_config"] = {
            "method": "GET",
            "query_param_map": {"query_terms": "q", "max_items": "limit"},
            "records_path": "items",
            "record_mapping": {
                "url": "url",
                "title": "title",
                "summary": "summary",
                "artifact_url": "pdf_url",
            },
        }

    return normalize_external_project_manifest(
        payload,
        item_key=item_key,
        display_name=display_name,
    )


def _default_capabilities_for_mode(execution_mode: str) -> dict[str, bool]:
    if execution_mode == "article_extractor":
        return {
            "candidate_urls": True,
            "article_metadata": True,
            "article_body": True,
            "pdf_artifact": False,
        }
    if execution_mode == "http_api":
        return {
            "candidate_urls": True,
            "article_metadata": True,
            "article_body": False,
            "pdf_artifact": True,
        }
    return {
        "candidate_urls": True,
        "article_metadata": True,
        "article_body": False,
        "pdf_artifact": False,
    }


def _infer_source_kind(execution_mode: str) -> str:
    mapping = {
        "rss_feed": "feed_aggregator",
        "sitemap": "site_extractor",
        "http_api": "api_provider",
        "article_extractor": "article_extraction_stack",
        "python_library": "python_library_wrapper",
        "cli_or_container": "cli_or_container_wrapper",
    }
    return mapping.get(execution_mode, "external_project")


def _infer_source_scope(project_context: dict[str, Any]) -> str:
    source = str(project_context.get("source") or "").strip().lower()
    if source == "github":
        return "project_repo"
    return "external_site"


def collect_external_project_context(*, project_link: str, hints: dict[str, Any] | None = None) -> dict[str, Any]:
    project_link = validate_external_http_url(project_link, field_name="project_link")
    github_repo = _parse_github_repo(project_link)
    if github_repo is not None:
        return _collect_github_context(project_link=project_link, hints=hints, repo=github_repo)
    return _collect_generic_context(project_link=project_link, hints=hints)


def _collect_github_context(
    *,
    project_link: str,
    hints: dict[str, Any] | None,
    repo: tuple[str, str],
) -> dict[str, Any]:
    owner, name = repo
    summary_parts: list[dict[str, Any]] = []
    discovery_seeds: list[dict[str, Any]] = []

    repo_meta = _safe_get_json(f"{_GITHUB_API_BASE}/{owner}/{name}")
    if isinstance(repo_meta, dict):
        repo_evidence = {
            "kind": "github_repo",
            "name": repo_meta.get("full_name"),
            "description": repo_meta.get("description"),
            "homepage": repo_meta.get("homepage"),
            "topics": repo_meta.get("topics"),
            "default_branch": repo_meta.get("default_branch"),
        }
        summary_parts.append(repo_evidence)
        discovery_seeds.append(repo_evidence)

    readme_meta = _safe_get_json(f"{_GITHUB_API_BASE}/{owner}/{name}/readme")
    if isinstance(readme_meta, dict):
        readme_text = _decode_github_content(readme_meta)
        if readme_text:
            readme_evidence = {"kind": "readme", "content": _truncate_text(readme_text)}
            summary_parts.append(readme_evidence)
            discovery_seeds.append(readme_evidence)

    for config_name in ("package.json", "pyproject.toml", "setup.py"):
        file_meta = _safe_get_json(f"{_GITHUB_API_BASE}/{owner}/{name}/contents/{config_name}")
        if isinstance(file_meta, dict):
            file_text = _decode_github_content(file_meta)
            if file_text:
                config_evidence = {"kind": config_name, "content": _truncate_text(file_text, limit=2000)}
                summary_parts.append(config_evidence)
                discovery_seeds.append(config_evidence)

    endpoint_candidates = _collect_endpoint_candidates(
        project_link=project_link,
        evidence=discovery_seeds,
        homepage_url=str((repo_meta or {}).get("homepage") or "").strip() or None,
    )

    return {
        "source": "github",
        "project_link": project_link,
        "repo": {"owner": owner, "name": name},
        "hints": dict(hints or {}),
        "evidence": summary_parts,
        "endpoint_candidates": endpoint_candidates,
        "preferred_execution_modes": _summarize_execution_modes(endpoint_candidates),
    }


def _collect_generic_context(*, project_link: str, hints: dict[str, Any] | None) -> dict[str, Any]:
    text = _safe_get_text(project_link)
    summary = _summarize_html_or_text(text)
    discovered_urls = _extract_urls_from_html(project_link, text)
    endpoint_candidates = _collect_endpoint_candidates(
        project_link=project_link,
        evidence=[
            {
                "kind": "page_summary",
                "content": summary,
                "urls": discovered_urls,
            }
        ],
    )
    return {
        "source": "generic",
        "project_link": project_link,
        "hints": dict(hints or {}),
        "evidence": [
            {
                "kind": "page_summary",
                "content": _truncate_text(summary),
                "urls": discovered_urls,
            }
        ],
        "endpoint_candidates": endpoint_candidates,
        "preferred_execution_modes": _summarize_execution_modes(endpoint_candidates),
    }


def _build_manifest_prompt(
    *,
    project_link: str,
    item_key: str,
    display_name: str,
    project_context: dict[str, Any],
    hints: dict[str, Any] | None,
) -> str:
    allowed_execution_modes = ["rss_feed", "sitemap", "http_api", "article_extractor", "python_library", "cli_or_container"]
    provider_registry = list_external_project_provider_bindings()
    contract_example = {
        "contract_version": EXTERNAL_PROJECT_MANIFEST_CONTRACT_VERSION,
        "item_key": item_key,
        "display_name": display_name,
        "project_link": project_link,
        "source_kind": "...",
        "source_scope": "...",
        "capabilities": {
            "candidate_urls": True,
            "article_metadata": False,
            "article_body": False,
            "pdf_artifact": False,
        },
        "accepted_inputs": {
            "query_terms": True,
            "urls": False,
            "domains": False,
            "date_range": False,
            "max_items": True,
        },
        "execution_mode": "rss_feed",
        "runner_ref": "https://...",
        "normalization": {
            "record_kind": "candidate_url",
            "frontdoor_strategy": "records_only_defer",
        },
        "limits": {
            "default_max_items": 20,
            "max_items_cap": 100,
            "request_timeout_ms": 30000,
        },
        "refresh_policy": {
            "manifest_ttl_minutes": 60,
            "probe_ttl_minutes": 1440,
        },
        "provenance": {
            "discovered_by": "llm_probe",
            "source_refs": ["https://..."],
        },
        "runtime_config": {
            "method": "GET",
            "headers": {},
            "query_param_map": {},
            "records_path": None,
            "record_mapping": {},
            "json_body": {},
        },
    }
    return (
        "You are synthesizing a stable external source-library manifest.\n"
        "Output JSON only. No markdown. No explanation.\n"
        "Choose the safest bounded runtime path based on evidence.\n"
        "Never invent unsupported capabilities.\n"
        "Prefer candidate_urls/article_metadata over article_body unless the evidence is explicit.\n"
        f"Allowed execution_mode values: {_safe_json(allowed_execution_modes)}.\n"
        "Prefer endpoint_candidates and preferred_execution_modes from evidence when they are present.\n"
        "Use this provider registry for bounded runtime selection. "
        "Do not invent provider families or adapter refs outside this list.\n"
        f"Provider registry:\n{_safe_json(provider_registry)}\n"
        "Use high-confidence explicit URLs ahead of convention-derived URLs.\n"
        "If runner_ref is unknown, infer the narrowest stable endpoint from evidence. "
        "Do not return placeholders or empty strings.\n"
        "Use this exact contract shape:\n"
        f"{_safe_json(contract_example)}\n"
        "Evidence:\n"
        f"{_safe_json(project_context)}\n"
        "Hints:\n"
        f"{_safe_json(dict(hints or {}))}\n"
    )


def _parse_github_repo(project_link: str) -> tuple[str, str] | None:
    parts = urlsplit(str(project_link or "").strip())
    if parts.netloc.lower() != "github.com":
        return None
    segments = [segment for segment in parts.path.split("/") if segment]
    if len(segments) < 2:
        return None
    return segments[0], segments[1]


def _safe_get_json(url: str) -> dict[str, Any] | None:
    try:
        payload = default_http_client.get_json(url, headers={"Accept": "application/vnd.github+json"}, timeout=15.0)
    except Exception:
        return None
    return dict(payload) if isinstance(payload, dict) else None


def _safe_get_text(url: str) -> str:
    try:
        return default_http_client.get_text(url, timeout=15.0)
    except Exception:
        return ""


def _decode_github_content(payload: dict[str, Any]) -> str:
    content = str(payload.get("content") or "").strip()
    encoding = str(payload.get("encoding") or "").strip().lower()
    if not content:
        return ""
    if encoding == "base64":
        try:
            return base64.b64decode(content).decode("utf-8", "ignore")
        except Exception:
            return ""
    return content


def _summarize_html_or_text(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    lowered = raw.lower()
    if "<html" in lowered or "<body" in lowered:
        soup = BeautifulSoup(raw, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = soup.get_text("\n", strip=True)
    else:
        text = raw
    return _truncate_text("\n".join(line.strip() for line in text.splitlines() if line.strip()))


def _extract_urls_from_html(base_url: str, raw_html: str) -> list[str]:
    text = str(raw_html or "").strip()
    if not text:
        return []
    lowered = text.lower()
    urls: list[str] = []
    if "<html" not in lowered and "<body" not in lowered:
        return urls
    try:
        soup = BeautifulSoup(text, "html.parser")
    except Exception:
        return urls
    for tag in soup.find_all(["a", "link"]):
        href = str(tag.get("href") or "").strip()
        if not href:
            continue
        candidate = _normalize_discovered_url(href, base_url=base_url)
        if candidate and candidate not in urls:
            urls.append(candidate)
    return urls


def _resolve_item_key(*, item_key: str | None, project_link: str) -> str:
    explicit = str(item_key or "").strip()
    if explicit:
        return explicit
    parts = urlsplit(project_link)
    host = str(parts.netloc or "").lower().replace(".", "_")
    path_segments = [segment for segment in parts.path.split("/") if segment]
    suffix = "_".join(path_segments[:2]) if path_segments else "project"
    raw = f"external.{host}.{suffix}".lower()
    normalized = "".join(ch if ch.isalnum() or ch in {"_", ".", "-"} else "_" for ch in raw)
    return normalized[:128]


def _resolve_display_name(*, display_name: str | None, project_link: str) -> str:
    explicit = str(display_name or "").strip()
    if explicit:
        return explicit
    github_repo = _parse_github_repo(project_link)
    if github_repo is not None:
        return github_repo[1]
    host = str(urlsplit(project_link).netloc or "").strip()
    return host or "External Project"


def _has_meaningful_evidence(project_context: dict[str, Any] | None) -> bool:
    evidence = project_context.get("evidence") if isinstance(project_context, dict) else None
    if not isinstance(evidence, list) or not evidence:
        return False
    for item in evidence:
        if not isinstance(item, dict):
            continue
        for key, value in item.items():
            if key == "kind":
                continue
            if isinstance(value, str) and value.strip():
                return True
            if isinstance(value, (list, dict)) and value:
                return True
    return False


def _collect_endpoint_candidates(
    *,
    project_link: str,
    evidence: list[dict[str, Any]] | None,
    homepage_url: str | None = None,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    explicit_urls: list[tuple[str, str]] = []

    for item in evidence or []:
        if not isinstance(item, dict):
            continue
        source_kind = str(item.get("kind") or "evidence").strip() or "evidence"
        for raw_url in _extract_urls_from_evidence(item):
            explicit_urls.append((raw_url, source_kind))

    for raw_url, source_kind in explicit_urls:
        classified = _classify_endpoint_candidate(raw_url)
        if classified is None:
            continue
        mode, reason = classified
        key = (mode, raw_url)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(
            {
                "execution_mode": mode,
                "runner_ref": raw_url,
                "reason": f"explicit_{source_kind}_{reason}",
                "confidence": "high",
            }
        )

    for seed_url in _candidate_base_urls(project_link=project_link, homepage_url=homepage_url, explicit_urls=[url for url, _ in explicit_urls]):
        for path, mode, reason in _derived_probe_paths(seed_url):
            key = (mode, path)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(
                {
                    "execution_mode": mode,
                    "runner_ref": path,
                    "reason": reason,
                    "confidence": "medium",
                }
            )

    candidates.sort(key=_endpoint_candidate_sort_key)
    return candidates[:12]


def _extract_urls_from_evidence(item: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    for key, value in item.items():
        if key == "kind":
            continue
        if isinstance(value, str):
            for candidate in _URL_PATTERN.findall(value):
                normalized = _normalize_discovered_url(candidate)
                if normalized and normalized not in urls:
                    urls.append(normalized)
        elif isinstance(value, list):
            for entry in value:
                if not isinstance(entry, str):
                    continue
                normalized = _normalize_discovered_url(entry)
                if normalized and normalized not in urls:
                    urls.append(normalized)
    return urls


def _candidate_base_urls(*, project_link: str, homepage_url: str | None, explicit_urls: list[str]) -> list[str]:
    bases: list[str] = []
    for raw in [homepage_url, project_link, *explicit_urls]:
        normalized = _normalize_base_origin(raw)
        if normalized and normalized not in bases:
            bases.append(normalized)
    return bases


def _normalize_base_origin(value: str | None) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        normalized = validate_external_http_url(raw, field_name="base_url")
    except Exception:
        return None
    parts = urlsplit(normalized)
    origin = f"{parts.scheme}://{parts.netloc}"
    return origin


def _derived_probe_paths(base_url: str) -> list[tuple[str, str, str]]:
    derived: list[tuple[str, str, str]] = []
    for path in _DEFAULT_RSS_PATHS:
        derived.append((urljoin(base_url, path), "rss_feed", "derived_convention_rss"))
    for path in _DEFAULT_SITEMAP_PATHS:
        derived.append((urljoin(base_url, path), "sitemap", "derived_convention_sitemap"))
    derived.append((urljoin(base_url, "/api"), "http_api", "derived_convention_http_api"))
    derived.append((urljoin(base_url, "/api/search"), "http_api", "derived_convention_http_api"))
    return derived


def _normalize_discovered_url(value: str, *, base_url: str | None = None) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if base_url and raw.startswith("/"):
        raw = urljoin(base_url, raw)
    try:
        return validate_external_http_url(raw, field_name="discovered_url")
    except Exception:
        return None


def _classify_endpoint_candidate(url: str) -> tuple[str, str] | None:
    parts = urlsplit(str(url or "").strip())
    path = str(parts.path or "").strip().lower()
    query = str(parts.query or "").strip().lower()
    host = str(parts.netloc or "").strip().lower()
    combined = " ".join(part for part in (host, path, query) if part)
    if not combined:
        return None
    if "sitemap" in combined or path.endswith(".xml.gz"):
        return "sitemap", "sitemap_marker"
    if any(token in combined for token in ("/rss", "rss.xml", "/feed", "feed.xml", "atom.xml", "format=rss", "format=atom")):
        return "rss_feed", "feed_marker"
    if any(token in combined for token in ("openapi", "swagger", "/api/", "graphql", "api.", "/api?", "/api")):
        return "http_api", "api_marker"
    return None


def _summarize_execution_modes(candidates: list[dict[str, Any]] | None) -> list[str]:
    ordered: list[str] = []
    for row in candidates or []:
        mode = str((row or {}).get("execution_mode") or "").strip()
        if mode and mode not in ordered:
            ordered.append(mode)
    return ordered


def _endpoint_candidate_sort_key(candidate: dict[str, Any]) -> tuple[int, int, str]:
    confidence = str(candidate.get("confidence") or "").strip().lower()
    mode = str(candidate.get("execution_mode") or "").strip().lower()
    mode_rank = {"rss_feed": 0, "sitemap": 1, "http_api": 2}.get(mode, 9)
    confidence_rank = 0 if confidence == "high" else 1
    return confidence_rank, mode_rank, str(candidate.get("runner_ref") or "")


def _truncate_text(value: str, *, limit: int = _DEFAULT_SUMMARY_CHAR_LIMIT) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit]


def _safe_json(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
