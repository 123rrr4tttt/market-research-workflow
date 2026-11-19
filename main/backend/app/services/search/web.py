from __future__ import annotations

from collections.abc import Callable
from collections.abc import Mapping
from typing import List, Optional, Protocol, Set, TypeGuard
from datetime import datetime
import os
import logging
import re
import math

from duckduckgo_search import DDGS
from duckduckgo_search.exceptions import RatelimitException
from ..http.client import default_http_client
from urllib.parse import urljoin, urlparse, parse_qsl, urlencode, urlunparse
from sqlalchemy import select

from ..keyword_generation import dedup_keywords, generate_keywords
from ..ingest.retry_policy import RateGate, RequestScope
from ...settings.config import settings
from ...models.base import SessionLocal
from ...models.entities import Material
from .candidate_contracts import FailureKind, ProviderObservation, ProviderStatus

# Azure AI Search removed - it's for searching your own data, not web search

logger = logging.getLogger(__name__)

SearchResult = dict[str, object]
ObservationRecord = dict[str, str | int | bool | None]
ProviderCall = Callable[[], list[SearchResult]]

_TRACKING_QUERY_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "utm_name",
    "utm_reader",
    "gclid",
    "fbclid",
    "msclkid",
    "ref",
    "spm",
    "fromsource",
    "sc_source",
}

_NUMERIC_INTENT_KEYWORDS = {
    "sales",
    "revenue",
    "earnings",
    "market",
    "quarter",
    "report",
    "data",
    "stats",
    "volume",
    "jackpot",
    "ticket",
    "prize",
}

_TRUSTED_DOMAINS = {
    "reuters.com",
    "www.reuters.com",
    "bloomberg.com",
    "www.bloomberg.com",
    "wsj.com",
    "www.wsj.com",
    "ft.com",
    "www.ft.com",
    "sec.gov",
    "www.sec.gov",
    "govinfo.gov",
    "www.nasdaq.com",
}


class SearchRequestPort(Protocol):
    def request_json(
        self,
        url: str,
        *,
        scope: RequestScope,
        headers: dict[str, str] | None = None,
    params: Mapping[str, str | int] | None = None,
    ) -> object:
        ...


_SEARCH_REQUEST_PORT: SearchRequestPort | None = None
SEARCH_RATE_GATE = RateGate(
    rate_limit_interval_seconds=1.0,
    backoff_base_seconds=2.0,
    backoff_max_seconds=8.0,
)


def set_search_request_port(port: SearchRequestPort) -> None:
    globals()["_SEARCH_REQUEST_PORT"] = port


def _search_scope(provider: str, *, account: str | None = None) -> RequestScope:
    return RequestScope(provider=f"search:{provider}", account=account)


def _request_search_json(
    url: str,
    *,
    scope: RequestScope,
    headers: dict[str, str] | None = None,
        params: Mapping[str, str | int] | None = None,
) -> object:
    port = _SEARCH_REQUEST_PORT
    if port is None:
        # kit:boundary owner=search.request_port class=PROGRAMMER_DEFECT failure_family=none witness=test:test_search_web_dynamic_boundaries_preserve_failure_paths
        raise RuntimeError("search request port is not configured")
    return port.request_json(
        url,
        scope=scope,
        headers=headers,
        params=params,
    )


def _acquire_sdk_search_gate(provider: str) -> bool:
    return SEARCH_RATE_GATE.acquire(_search_scope(provider)).acquired


def _base_language(language: str) -> str:
    lang = (language or "").strip().lower()
    if lang.startswith("zh"):
        return "zh"
    if lang.startswith("en"):
        return "en"
    return "en"


def _canonicalize_url(url: str) -> str:
    try:
        parsed = urlparse(url)
        query = [
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if key.lower() not in _TRACKING_QUERY_PARAMS
        ]
        canonical_query = urlencode(query)
        return urlunparse((
            parsed.scheme or "https",
            parsed.netloc,
            parsed.path,
            parsed.params,
            canonical_query,
            "",
        ))
    except Exception:
        return url


def _contains_numeric_intent(text: str) -> bool:
    if not text:
        return False
    lowered = text.lower()
    if re.search(r"\d", lowered):
        return True
    return any(token in lowered for token in _NUMERIC_INTENT_KEYWORDS)


def _result_text(item: SearchResult, key: str) -> str:
    value = item.get(key)
    if not value:
        return ""
    if isinstance(value, str):
        return value
    # kit:boundary owner=search.provider_payload class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=search.failure witness=test:test_search_web_dynamic_boundaries_preserve_failure_paths
    raise TypeError(f"search result field {key!r} must be text")


def _relevance_score(item: SearchResult) -> float:
    value = item.get("relevance_score")
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0


def _json_object(value: object) -> dict[str, object]:
    normalized = _json_dict(value)
    if normalized is not None:
        return normalized
    # kit:boundary owner=search.provider_payload class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=search.failure witness=test:test_search_web_dynamic_boundaries_preserve_failure_paths
    raise TypeError("search provider response must be a JSON object")


def _is_json_dict(value: object) -> TypeGuard[dict[object, object]]:
    return isinstance(value, dict)


def _is_json_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _json_dict(value: object) -> dict[str, object] | None:
    if not _is_json_dict(value):
        return None
    result: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            return None
        result[key] = item
    return result


def _json_list(value: object) -> list[object] | None:
    return value if _is_json_list(value) else None


def _json_rows(value: object) -> list[object]:
    if _is_json_list(value):
        return value
    # kit:boundary owner=search.provider_payload class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=search.failure witness=test:test_search_web_dynamic_boundaries_preserve_failure_paths
    raise TypeError("search provider response rows must be a JSON array")


def _required_json_dict(value: object) -> dict[str, object]:
    normalized = _json_dict(value)
    if normalized is None:
        # kit:boundary owner=search.provider_payload class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=search.failure witness=test:test_search_web_dynamic_boundaries_preserve_failure_paths
        raise TypeError("search provider row must be a JSON object")
    return normalized


def _score_search_result(item: SearchResult, *, topic: str, keywords: List[str]) -> float:
    title = _result_text(item, "title").lower()
    snippet = _result_text(item, "snippet").lower()
    link = (_result_text(item, "canonical_link") or _result_text(item, "link")).lower()
    source = _result_text(item, "source").lower()
    candidate = " ".join([title, snippet, link])

    score = 0.0
    for keyword in {topic, *keywords}:
        if keyword and keyword.lower() in candidate:
            score += 1.8

    if _contains_numeric_intent(candidate):
        score += 1.6

    domain = _extract_domain(_result_text(item, "canonical_link") or _result_text(item, "link"))
    if domain and domain.lower() in _TRUSTED_DOMAINS:
        score += 2.0

    if source in {"serpapi", "serpstack", "serper", "google", "ddg"}:
        score += 0.3

    if not title:
        score -= 0.6
    if not snippet:
        score -= 0.3
    return round(score, 3)


def _extract_domain(url: str) -> str:
    try:
        return urlparse(url).netloc
    except Exception:
        return ""


def filter_existing(results: List[SearchResult]) -> List[SearchResult]:
    """过滤已入库的文档"""
    urls = [
        _result_text(r, "canonical_link") or _result_text(r, "link")
        for r in results
        if _result_text(r, "canonical_link") or _result_text(r, "link")
    ]
    if not urls:
        return results
    
    with SessionLocal() as session:
        existing_urls = {
            row[0] for row in session.execute(
                select(Material.uri).where(Material.uri.in_(urls))
            ).all()
        }
    
    filtered = [
        r for r in results
        if (_result_text(r, "canonical_link") or _result_text(r, "link")) not in existing_urls
    ]
    logger.info("filter_existing: input=%d existing=%d filtered=%d", len(results), len(existing_urls), len(filtered))
    return filtered


def search_sources(
    topic: str, 
    language: str = "en", 
    max_results: int = 10, 
    provider: str = "auto",
    days_back: Optional[int] = None,
    exclude_existing: bool = True,
    start_offset: Optional[int] = None,
    keywords_override: Optional[List[str]] = None,
    observation_sink: Optional[List[ObservationRecord]] = None,
    occurrence_sink: Optional[List[ObservationRecord]] = None,
) -> List[SearchResult]:
    """搜索外部资源
    
    Args:
        topic: 搜索主题
        language: 语言 (en/zh)
        max_results: 最大结果数
        provider: 搜索服务提供商
            - "auto": 自动选择（Serper -> Google(若可用) -> Serpstack -> SerpAPI -> DDG）
            - "ddg": 仅使用 DuckDuckGo
            - "google": 仅使用 Google Custom Search
            - "serper": 仅使用 Serper.dev（推荐）
            - "serpstack": 仅使用 Serpstack
            - "serpapi": 仅使用 SerpAPI
            - "searxng": 仅使用本地/自托管 SearXNG（显式 provider，不进入 auto）
            - "yacy": 仅使用本地/自托管 YaCy（显式 provider，不进入 auto）
        days_back: 可选，只搜索最近N天的内容（添加到关键词中）
        exclude_existing: 是否排除已入库的文档（默认True）
    """
    # 时间过滤：添加时间关键词
    if days_back:
        year = datetime.now().year
        if language.lower().startswith("en"):
            topic = f"{topic} {year} recent latest"
        else:
            topic = f"{topic} {year} 最新 最近"
        logger.info("search_sources: added time keywords days_back=%d topic=%s", days_back, topic)
    
    keywords = dedup_keywords(keywords_override) if keywords_override is not None else generate_keywords(topic, language)
    # 如果关键词生成失败，使用topic本身作为关键词
    if not keywords:
        keywords = [topic]
        logger.warning("search_sources: keyword generation failed, using topic as keyword: %s", topic)
    logger.info("search_sources: start topic=%s lang=%s keywords=%s max=%d provider=%s", topic, language, keywords, max_results, provider)
    results: List[SearchResult] = []
    seen_links: Set[str] = set()

    def _observe(name: str, keyword: str | None, status: ProviderStatus, count: int = 0, error: Exception | None = None) -> ProviderObservation:
        kind: FailureKind | None = None
        if status == "not_configured":
            kind = "not_configured"
        elif error is not None:
            detail = str(error).lower()
            kind = "rate_limited" if isinstance(error, RatelimitException) or "rate limit" in detail or "quota" in detail or "429" in detail else ("timeout" if isinstance(error, TimeoutError) or "timeout" in detail or "timed out" in detail else "exception")
        route = ("auto:" if provider == "auto" else "explicit:") + name
        if provider == "google" and name == "ddg":
            route = "fallback:ddg"
        observed = ProviderObservation(provider=name, route=route, keyword=keyword, status=status, returned_count=count, failure_kind=kind, error_type=type(error).__name__ if error else None, error_message=str(error) if error else None)
        if observation_sink is not None:
            record: ObservationRecord = {
                "provider": observed.provider,
                "route": observed.route,
                "keyword": observed.keyword,
                "status": observed.status,
                "returned_count": observed.returned_count,
                "failure_kind": observed.failure_kind,
                "error_type": observed.error_type,
                "error_message": observed.error_message,
            }
            observation_sink.append(record)
        return observed

    def _observed_call(name: str, keyword: str, call: ProviderCall):
        start = len(observation_sink) if observation_sink is not None else 0
        try:
            items = call()
        except Exception as exc:
            logger.warning("search_sources: %s keyword=%s failed: %s", name, keyword, exc, exc_info=True)
            return _observe(name, keyword, "failed", error=exc)
        internal_failure = observation_sink is not None and any(
            row["status"] == "failed" for row in observation_sink[start:]
        )
        if items or not internal_failure:
            _observe(name, keyword, "completed", len(items))
        return items

    def _call_google(keyword: str, cse_id: str, limit: int, auth_kw: dict[str, str]):
        if observation_sink is None:
            return _google_search(
                keyword,
                cse_id,
                limit,
                start_offset,
                api_key=auth_kw.get("api_key"),
                oauth_token=auth_kw.get("oauth_token"),
            )
        def notify_google_error(exc: Exception) -> None:
            _observe("google", keyword, "failed", error=exc)
        return _google_search(
            keyword,
            cse_id,
            limit,
            start_offset,
            api_key=auth_kw.get("api_key"),
            oauth_token=auth_kw.get("oauth_token"),
            on_error=notify_google_error,
        )

    
    # 如果指定了特定提供商，直接使用
    if provider != "auto":
        from ...settings.config import settings as _settings
        
        if provider == "ddg":
            try:
                with DDGS() as ddgs:
                    per_kw = max(1, max_results // max(1, len(keywords)))
                    for keyword in keywords:
                        try:
                            count = 0
                            if not _acquire_sdk_search_gate("ddg"):
                                logger.warning("search_sources: ddg keyword=%s denied by request gate", keyword)
                                _observe("ddg", keyword, "failed")
                                continue
                            for result in ddgs.text(keyword, safesearch="off", max_results=per_kw):
                                item: SearchResult = {
                                    "keyword": keyword,
                                    "title": result.get("title"),
                                    "link": result.get("href"),
                                    "snippet": result.get("body"),
                                    "source": result.get("source") or "ddg",
                                }
                                if _add_result_dedup(results, seen_links, item, occurrence_sink=occurrence_sink, request_provider=provider, branch_provider="ddg"):
                                    pass
                                count += 1
                            logger.info("search_sources: ddg keyword=%s got %d", keyword, count)
                            _observe("ddg", keyword, "completed", count)
                        except RatelimitException as e:
                            logger.warning("search_sources: ddg rate limited (202 Ratelimit) - DuckDuckGo 已限流，建议使用其他搜索服务: %s", e)
                            _observe("ddg", keyword, "failed", error=e)
                            # DDG 被限流，返回已获取的结果（如果有）
                            break
                        except Exception as e:
                            logger.warning("search_sources: ddg keyword=%s failed: %s", keyword, e, exc_info=True)
                            _observe("ddg", keyword, "failed", error=e)
                            continue
            except RatelimitException as e:
                logger.error("search_sources: ddg provider rate limited (202 Ratelimit) - DuckDuckGo 已限流，建议使用 Google/Serpstack/SerpAPI: %s", e)
                _observe("ddg", None, "failed", error=e)
                return results
            except Exception as e:
                logger.error("search_sources: ddg provider unavailable: %s", e, exc_info=True)
                _observe("ddg", None, "failed", error=e)
                return results

        elif provider == "serper":
            serper_key = os.getenv("SERPER_API_KEY") or getattr(_settings, "serper_api_key", None)
            if not serper_key:
                logger.error("search_sources: serper key not configured")
                _observe("serper", None, "not_configured")
                return results
            per_kw = max(1, max_results // max(1, len(keywords)))
            for keyword in keywords:
                try:
                    items = _observed_call("serper", keyword, lambda: _serper_search(keyword, serper_key, per_kw, language=language))
                    if isinstance(items, ProviderObservation):
                        continue
                    for it in items:
                        it["keyword"] = keyword
                        _add_result_dedup(results, seen_links, it, occurrence_sink=occurrence_sink, request_provider=provider)
                    logger.info("search_sources: serper keyword=%s got %d", keyword, len(items))
                except Exception as e:
                    logger.warning("search_sources: serper keyword=%s failed: %s", keyword, e, exc_info=True)
                    continue
        
        elif provider == "serpstack":
            serpstack_key = os.getenv("SERPSTACK_KEY") or _settings.serpstack_key
            if not serpstack_key:
                logger.error("search_sources: serpstack key not configured")
                _observe("serpstack", None, "not_configured")
                return results
            per_kw = max(1, max_results // max(1, len(keywords)))
            for keyword in keywords:
                try:
                    items = _observed_call("serpstack", keyword, lambda: _serpstack_search(keyword, str(serpstack_key), per_kw))
                    if isinstance(items, ProviderObservation):
                        continue
                    for it in items:
                        it["keyword"] = keyword
                        _add_result_dedup(results, seen_links, it, occurrence_sink=occurrence_sink, request_provider=provider)
                    logger.info("search_sources: serpstack keyword=%s got %d", keyword, len(items))
                except Exception as e:
                    logger.warning("search_sources: serpstack keyword=%s failed: %s", keyword, e, exc_info=True)
                    continue
        
        elif provider == "google":
            from ...settings.config import settings as _settings
            google_api_key = os.getenv("GOOGLE_SEARCH_API_KEY") or _settings.google_search_api_key or ""
            google_cse_id = os.getenv("GOOGLE_SEARCH_CSE_ID") or _settings.google_search_cse_id or ""
            google_oauth_token = _get_google_oauth_token()
            google_configured = google_cse_id and (google_api_key or google_oauth_token)
            if not google_configured:
                logger.warning("search_sources: google not configured (need CSE_ID + API_KEY or GOOGLE_APPLICATION_CREDENTIALS), falling back to ddg")
                _observe("google", None, "not_configured")
                # Fallback to DDG when Google CSE not configured
                try:
                    with DDGS() as ddgs:
                        per_kw = max(1, max_results // max(1, len(keywords)))
                        for keyword in keywords:
                            try:
                                for result in ddgs.text(keyword, safesearch="off", max_results=per_kw):
                                    item: SearchResult = {
                                        "keyword": keyword,
                                        "title": result.get("title"),
                                        "link": result.get("href"),
                                        "snippet": result.get("body"),
                                        "source": "ddg",
                                    }
                                    _add_result_dedup(results, seen_links, item, occurrence_sink=occurrence_sink, request_provider=provider, branch_provider="ddg")
                                logger.info("search_sources: ddg fallback keyword=%s got results", keyword)
                                _observe("ddg", keyword, "completed")
                            except (RatelimitException, Exception) as e:
                                logger.warning("search_sources: ddg fallback keyword=%s failed: %s", keyword, e)
                                _observe("ddg", keyword, "failed", error=e)
                                continue
                except (RatelimitException, Exception) as e:
                    logger.warning("search_sources: ddg fallback failed: %s", e)
                    _observe("ddg", None, "failed", error=e)
            else:
                # Google API: OAuth 优先于 API Key；batch requests with delay
                auth_kw: dict[str, str] = {"oauth_token": google_oauth_token} if google_oauth_token else {"api_key": google_api_key}
                if google_oauth_token:
                    logger.info("search_sources: using Google OAuth (GOOGLE_APPLICATION_CREDENTIALS)")
                for keyword in keywords:
                    if len(results) >= max_results:
                        break
                    try:
                        remaining = max_results - len(results)
                        items = _observed_call("google", keyword, lambda: _call_google(keyword, google_cse_id, remaining, auth_kw))
                        if isinstance(items, ProviderObservation):
                            continue
                        for it in items:
                            it["keyword"] = keyword
                            _add_result_dedup(results, seen_links, it, occurrence_sink=occurrence_sink, request_provider=provider)
                        logger.info("search_sources: google keyword=%s got %d (total=%d)", keyword, len(items), len(results))
                    except Exception as e:
                        logger.warning("search_sources: google keyword=%s failed: %s", keyword, e, exc_info=True)
                        continue
        
        elif provider == "serpapi":
            serp_key = os.getenv("SERPAPI_KEY") or os.getenv("SERPAPI_API_KEY") or _settings.serpapi_key
            if not serp_key:
                logger.error("search_sources: serpapi key not configured")
                _observe("serpapi", None, "not_configured")
                return results
            per_kw = max(1, max_results // max(1, len(keywords)))
            for keyword in keywords:
                try:
                    items = _observed_call("serpapi", keyword, lambda: _serpapi_search(keyword, str(serp_key), per_kw))
                    if isinstance(items, ProviderObservation):
                        continue
                    for it in items:
                        it["keyword"] = keyword
                        _add_result_dedup(results, seen_links, it, occurrence_sink=occurrence_sink, request_provider=provider)
                    logger.info("search_sources: serpapi keyword=%s got %d", keyword, len(items))
                except Exception as e:
                    logger.warning("search_sources: serpapi keyword=%s failed: %s", keyword, e, exc_info=True)
                    continue

        elif provider == "searxng":
            base_url = os.getenv("SEARXNG_BASE_URL", "http://127.0.0.1:8088").strip()
            per_kw = max(1, max_results // max(1, len(keywords)))
            for keyword in keywords:
                try:
                    items = _observed_call("searxng", keyword, lambda: _searxng_search(keyword, base_url, per_kw, language=language))
                    if isinstance(items, ProviderObservation):
                        continue
                    for it in items:
                        it["keyword"] = keyword
                        _add_result_dedup(results, seen_links, it, occurrence_sink=occurrence_sink, request_provider=provider)
                    logger.info("search_sources: searxng keyword=%s got %d", keyword, len(items))
                except Exception as e:
                    logger.warning("search_sources: searxng keyword=%s failed: %s", keyword, e, exc_info=True)
                    continue

        elif provider == "yacy":
            base_url = os.getenv("YACY_BASE_URL", "http://127.0.0.1:8090").strip()
            resource_mode = os.getenv("YACY_RESOURCE_MODE", "local").strip() or "local"
            per_kw = max(1, max_results // max(1, len(keywords)))
            for keyword in keywords:
                try:
                    items = _observed_call("yacy", keyword, lambda: _yacy_search(keyword, base_url, per_kw, resource_mode=resource_mode))
                    if isinstance(items, ProviderObservation):
                        continue
                    for it in items:
                        it["keyword"] = keyword
                        _add_result_dedup(results, seen_links, it, occurrence_sink=occurrence_sink, request_provider=provider)
                    logger.info("search_sources: yacy keyword=%s resource=%s got %d", keyword, resource_mode, len(items))
                except Exception as e:
                    logger.warning("search_sources: yacy keyword=%s failed: %s", keyword, e, exc_info=True)
                    continue
        
        logger.info("search_sources: provider=%s total=%d", provider, len(results))
        return results
    
    # 自动模式：优先使用 Google Custom Search（支持分页，每天100次免费）
    from ...settings.config import settings as _settings
    
    # 1. 优先尝试 Serper.dev（稳定、接入简单）
    serper_key = os.getenv("SERPER_API_KEY") or getattr(_settings, "serper_api_key", None)
    if serper_key:
        logger.info("search_sources: auto mode - using serper.dev")
        per_kw = max(1, max_results // max(1, len(keywords)))
        for keyword in keywords:
            if len(results) >= max_results:
                break
            try:
                remaining = max_results - len(results)
                items = _observed_call("serper", keyword, lambda: _serper_search(keyword, serper_key, min(per_kw, remaining), language=language))
                if isinstance(items, ProviderObservation):
                    continue
                for it in items:
                    it["keyword"] = keyword
                    _add_result_dedup(results, seen_links, it, occurrence_sink=occurrence_sink, request_provider=provider)
            except Exception as e:
                logger.warning("search_sources: serper keyword=%s failed: %s", keyword, e, exc_info=True)
                continue

    # 2. 尝试 Google Custom Search（若可用，支持分页）
    google_api_key = os.getenv("GOOGLE_SEARCH_API_KEY") or _settings.google_search_api_key or ""
    google_cse_id = os.getenv("GOOGLE_SEARCH_CSE_ID") or _settings.google_search_cse_id or ""
    google_oauth_token = _get_google_oauth_token()
    if len(results) == 0 and google_cse_id and (google_api_key or google_oauth_token):
        auth_kw: dict[str, str] = {"oauth_token": google_oauth_token} if google_oauth_token else {"api_key": google_api_key}
        logger.info("search_sources: auto mode - using google custom search (OAuth=%s)", bool(google_oauth_token))
        for keyword in keywords:
            if len(results) >= max_results:
                break
            try:
                remaining = max_results - len(results)
                items = _observed_call("google", keyword, lambda: _call_google(keyword, google_cse_id, remaining, auth_kw))
                if isinstance(items, ProviderObservation):
                    continue
                for it in items:
                    it["keyword"] = keyword
                    _add_result_dedup(results, seen_links, it, occurrence_sink=occurrence_sink, request_provider=provider)
                if items:
                    logger.info("search_sources: google keyword=%s got %d (total=%d)", keyword, len(items), len(results))
            except Exception as e:
                logger.warning("search_sources: google keyword=%s failed: %s", keyword, e)
                continue
    
    # Fallback: 如果前面失败，尝试其他搜索服务
    if len(results) == 0:
        # 3. 尝试 Serpstack（每月100次免费）
        serpstack_key = os.getenv("SERPSTACK_KEY") or _settings.serpstack_key
        if serpstack_key:
            logger.info("search_sources: trying serpstack (free tier: 100/month)")
            per_kw = max(1, max_results // max(1, len(keywords)))
            for keyword in keywords:
                try:
                    items = _observed_call("serpstack", keyword, lambda: _serpstack_search(keyword, str(serpstack_key), per_kw))
                    if isinstance(items, ProviderObservation):
                        continue
                    for it in items:
                        it["keyword"] = keyword
                        _add_result_dedup(results, seen_links, it, occurrence_sink=occurrence_sink, request_provider=provider)
                    if items:
                        logger.info("search_sources: serpstack keyword=%s got %d", keyword, len(items))
                        break  # 成功获取结果，退出循环
                except Exception as e:
                    logger.warning("search_sources: serpstack keyword=%s failed: %s", keyword, e)
                    continue
        
        # 4. 最后尝试 SerpAPI（如果配置了）
        if len(results) == 0:
            serp_key = os.getenv("SERPAPI_KEY") or os.getenv("SERPAPI_API_KEY") or _settings.serpapi_key
            if serp_key:
                logger.info("search_sources: fallback serpapi")
                per_kw = max(1, max_results // max(1, len(keywords)))
                for keyword in keywords:
                    try:
                        items = _observed_call("serpapi", keyword, lambda: _serpapi_search(keyword, str(serp_key), per_kw))
                        if isinstance(items, ProviderObservation):
                            continue
                        for it in items:
                            it["keyword"] = keyword
                            _add_result_dedup(results, seen_links, it, occurrence_sink=occurrence_sink, request_provider=provider)
                        logger.info("search_sources: serpapi keyword=%s got %d", keyword, len(items))
                    except Exception:
                        logger.warning("search_sources: serpapi keyword=%s failed", keyword, exc_info=True)
                        continue

    # SerpAPI 新闻通道（增加媒体多样性）
    if len(results) < max_results:
        from ...settings.config import settings as _settings
        serp_key = os.getenv("SERPAPI_KEY") or os.getenv("SERPAPI_API_KEY") or _settings.serpapi_key
        if serp_key:
            logger.info("search_sources: serpapi news enrichment")
            per_kw = max(1, max_results // max(1, len(keywords)))
            for keyword in keywords[:3]:  # 控制请求量
                try:
                    items = _observed_call("serpapi_news", keyword, lambda: _serpapi_search_news(keyword, str(serp_key), per_kw))
                    if isinstance(items, ProviderObservation):
                        continue
                    for it in items:
                        it["keyword"] = keyword
                        _add_result_dedup(results, seen_links, it, occurrence_sink=occurrence_sink, request_provider=provider)
                except Exception:
                    continue

    # Fallback: generic market research sources on DDG
    if len(results) == 0:
        site_kw = [
            f"site:reuters.com {k}" for k in keywords
        ] + [
            f"site:bloomberg.com {k}" for k in keywords
        ] + [
            f"site:wsj.com {k}" for k in keywords
        ]
        try:
            with DDGS() as ddgs:
                for keyword in site_kw:
                    try:
                        if not _acquire_sdk_search_gate("ddg"):
                            logger.warning("search_sources: ddg site keyword=%s denied by request gate", keyword)
                            _observe("ddg", keyword, "failed")
                            continue
                        for result in ddgs.text(keyword, safesearch="off", max_results=2):
                            item: SearchResult = {
                                "keyword": keyword,
                                "title": result.get("title"),
                                "link": result.get("href"),
                                "snippet": result.get("body"),
                                "source": result.get("source"),
                            }
                            _add_result_dedup(results, seen_links, item, occurrence_sink=occurrence_sink, request_provider=provider, branch_provider="ddg")
                        _observe("ddg", keyword, "completed")
                    except RatelimitException as e:
                        logger.warning("search_sources: ddg rate limited in site fallback, skipping")
                        _observe("ddg", keyword, "failed", error=e)
                        break
                    except Exception as e:
                        _observe("ddg", keyword, "failed", error=e)
                        continue
        except RatelimitException as e:
            logger.warning("search_sources: ddg rate limited in site fallback")
            _observe("ddg", None, "failed", error=e)
        except Exception as e:
            logger.warning("search_sources: site search fallback failed", exc_info=True)
            _observe("ddg", None, "failed", error=e)

    # 过滤已存在的文档
    if exclude_existing:
        results = filter_existing(results)
        
    # 结果重排：以数字相关性、可信来源与主题匹配优先
    for item in results:
        try:
            item["relevance_score"] = _score_search_result(item, topic=topic, keywords=keywords)
        except Exception as e:
            logger.warning("search_sources: scoring failed for %s: %s", item.get("link"), e)
            item.setdefault("relevance_score", 0.0)
    results.sort(key=_relevance_score, reverse=True)
    if len(results) > max_results:
        results = results[:max_results]

    logger.info("search_sources: total=%d exclude_existing=%s", len(results), exclude_existing)
    return results


def _serpapi_search(keyword: str, api_key: str, limit: int) -> List[SearchResult]:
    params = {
        "q": keyword,
        "engine": "google",
        "api_key": api_key,
        "num": str(max(1, limit)),
    }
    response = _request_search_json(
        "https://serpapi.com/search.json",
        scope=_search_scope("serpapi"),
        headers={"Accept": "application/json"},
        params=params,
    )
    data = _json_object(response)
    items: List[SearchResult] = []
    for row in _json_rows(data.get("organic_results", []))[:limit]:
        row = _required_json_dict(row)
        item: SearchResult = {
            "title": row.get("title"),
            "link": row.get("link"),
            "snippet": row.get("snippet"),
            "source": "serpapi",
        }
        items.append(item)
    return items


def _serpapi_search_news(keyword: str, api_key: str, limit: int) -> List[SearchResult]:
    params = {
        "q": keyword,
        "engine": "google",
        "api_key": api_key,
        "tbm": "nws",
        "num": str(max(1, limit)),
    }
    response = _request_search_json(
        "https://serpapi.com/search.json",
        scope=_search_scope("serpapi", account="news"),
        headers={"Accept": "application/json"},
        params=params,
    )
    data = _json_object(response)
    items: List[SearchResult] = []
    for row in _json_rows(data.get("news_results", []))[:limit]:
        row = _required_json_dict(row)
        snippet = row.get("snippet") or row.get("source")
        item: SearchResult = {
            "title": row.get("title"),
            "link": row.get("link"),
            "snippet": snippet,
            "source": "serpapi_news",
        }
        items.append(item)
    return items


def _serpstack_search(keyword: str, api_key: str, limit: int) -> List[SearchResult]:
    """Serpstack API: 每月100次免费请求
    注册地址: https://serpstack.com/
    """
    params = {
        "query": keyword,
        "access_key": api_key,
        "num": str(max(1, limit)),
    }
    response = _request_search_json(
        "http://api.serpstack.com/search",
        scope=_search_scope("serpstack"),
        headers={"Accept": "application/json"},
        params=params,
    )
    data = _json_object(response)
    items: List[SearchResult] = []
    for row in _json_rows(data.get("organic_results", []))[:limit]:
        row = _required_json_dict(row)
        item: SearchResult = {
            "title": row.get("title"),
            "link": row.get("url"),
            "snippet": row.get("snippet"),
            "source": "serpstack",
        }
        items.append(item)
    return items


def _serper_search(keyword: str, api_key: str, limit: int, *, language: str = "en") -> List[SearchResult]:
    """Serper.dev Google Search API (POST JSON).

    Docs: https://serper.dev/
    """
    hl = "en"
    lang = (language or "").lower()
    if lang.startswith("zh"):
        hl = "zh-cn"

    payload = {
        "q": keyword,
        "num": int(max(1, limit)),
        "hl": hl,
    }
    if not _acquire_sdk_search_gate("serper"):
        logger.warning("_serper_search: request gate denied provider=serper keyword=%s", keyword)
        return []
    response: object = default_http_client.post_json(
        "https://google.serper.dev/search",
        json=payload,
        headers={
            "X-API-KEY": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )

    data = _json_object(response)
    items: List[SearchResult] = []
    for row in _json_rows(data.get("organic", []))[:limit]:
        row = _required_json_dict(row)
        snippet = row.get("snippet") or row.get("description")
        item: SearchResult = {
            "title": row.get("title"),
            "link": row.get("link"),
            "snippet": snippet,
            "source": "serper",
        }
        items.append(item)
    return items


def _searxng_search(keyword: str, base_url: str, limit: int, *, language: str = "en") -> List[SearchResult]:
    url = urljoin(base_url.rstrip("/") + "/", "search")
    try:
        max_pages = max(1, min(10, int(os.getenv("SEARXNG_MAX_PAGES", "5"))))
    except ValueError:
        max_pages = 5
    desired_pages = max(1, min(max_pages, math.ceil(max(1, limit) / 10)))
    items: List[SearchResult] = []
    for page_no in range(1, desired_pages + 1):
        params = {
            "q": keyword,
            "format": "json",
            "pageno": page_no,
            "language": _base_language(language),
        }
        response = _request_search_json(
            url,
            scope=_search_scope("searxng"),
            headers={"Accept": "application/json"},
            params=params,
        )
        data = _json_object(response)
        rows = _json_rows(data.get("results", []))
        if not rows:
            break
        for row in rows:
            row = _required_json_dict(row)
            link = str(row.get("url") or row.get("link") or row.get("parsed_url") or "").strip()
            if not link:
                continue
            snippet = row.get("content") or row.get("snippet") or row.get("description")
            item: SearchResult = {
                "title": row.get("title"),
                "link": link,
                "snippet": snippet,
                "source": "searxng",
                "provider_route": "explicit:searxng",
                "provider_family": "local_open_search",
                "provider_auto_included": False,
                "rank": len(items) + 1,
                "backend_trace": {
                    "provider": "searxng",
                    "provider_route": "explicit:searxng",
                    "provider_family": "local_open_search",
                    "auto_included": False,
                    "pageno": page_no,
                },
                "raw": {
                    "engine": row.get("engine"),
                    "engines": row.get("engines"),
                    "category": row.get("category"),
                    "publishedDate": row.get("publishedDate"),
                    "pageno": page_no,
                },
            }
            items.append(item)
            if len(items) >= limit:
                break
        if len(items) >= limit:
            break
    return items


def _yacy_search(keyword: str, base_url: str, limit: int, *, resource_mode: str = "local") -> List[SearchResult]:
    url = urljoin(base_url.rstrip("/") + "/", "yacysearch.json")
    resource = resource_mode if resource_mode in {"local", "global"} else "local"
    params = {
        "query": keyword,
        "resource": resource,
        "maximumRecords": max(1, limit),
    }
    response = _request_search_json(
        url,
        scope=_search_scope("yacy"),
        headers={"Accept": "application/json"},
        params=params,
    )
    data = _json_object(response)
    rows: list[object] = []
    channel_rows = _json_list(data.get("channels"))
    if channel_rows:
        first = _json_dict(channel_rows[0])
        if first is not None:
            rows = _json_rows(first.get("items") or first.get("results") or [])
    if not rows:
        rows = _json_rows(data.get("items") or data.get("results") or [])

    items: List[SearchResult] = []
    for rank, row in enumerate(rows[:limit], start=1):
        row = _json_dict(row)
        if row is None:
            continue
        link = str(row.get("link") or row.get("url") or row.get("sku") or "").strip()
        if not link:
            continue
        snippet = row.get("description") or row.get("snippet") or row.get("text")
        item: SearchResult = {
            "title": row.get("title"),
            "link": link,
            "snippet": snippet,
            "source": "yacy",
            "provider_route": "explicit:yacy",
            "provider_family": "local_open_search",
            "provider_auto_included": False,
            "rank": rank,
            "backend_trace": {
                "provider": "yacy",
                "provider_route": "explicit:yacy",
                "provider_family": "local_open_search",
                "auto_included": False,
                "resource": resource,
            },
            "raw": {
                "resource": resource,
                "origin": row.get("publisher") or row.get("host") or row.get("domain"),
                "pubDate": row.get("pubDate"),
                "size": row.get("size"),
            },
        }
        items.append(item)
    return items


_CSE_OAUTH_SCOPE = "https://www.googleapis.com/auth/cse"


def _get_google_oauth_token() -> Optional[str]:
    """Get OAuth 2.0 access token from service account (GOOGLE_APPLICATION_CREDENTIALS)."""
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not creds_path or not os.path.isfile(creds_path):
        return None
    try:
        import google.auth.transport.requests
        from google.oauth2 import service_account
        credentials_loader = getattr(service_account, "Credentials").from_service_account_file
        credentials: object = credentials_loader(
            creds_path, scopes=[_CSE_OAUTH_SCOPE]
        )
        refresh = getattr(credentials, "refresh", None)
        if callable(refresh):
            refresh(google.auth.transport.requests.Request())
        token = getattr(credentials, "token", None)
        return token if isinstance(token, str) else None
    except Exception as e:
        logger.warning("_get_google_oauth_token failed: %s", e, exc_info=True)
        return None


def _google_search(
    keyword: str,
    cse_id: str,
    limit: int,
    start_offset: Optional[int] = None,
    *,
    api_key: Optional[str] = None,
    oauth_token: Optional[str] = None,
    on_error: Callable[[Exception], None] | None = None,
) -> List[SearchResult]:
    """Google Custom Search API: 每天100次免费请求
    支持 API Key 或 OAuth 2.0（Service Account）认证。
    支持分页获取多页结果（通过start参数）
    注册地址: https://developers.google.com/custom-search/v1/overview

    认证方式（二选一）:
    1. API Key: GOOGLE_SEARCH_API_KEY
    2. OAuth: GOOGLE_APPLICATION_CREDENTIALS 指向 Service Account JSON 路径
    """
    items: List[SearchResult] = []
    max_results_per_page = 10  # Google API 每页最多返回 10 个结果

    # 如果指定了start_offset，从该位置开始；否则从1开始
    initial_start = start_offset if start_offset is not None else 1
    max_pages = (limit + max_results_per_page - 1) // max_results_per_page

    for page in range(max_pages):
        if len(items) >= limit:
            break

        start_index = initial_start + page * max_results_per_page
        remaining = limit - len(items)
        num_results = min(max_results_per_page, remaining)

        params = {
            "q": keyword,
            "cx": cse_id,
            "num": num_results,
            "start": start_index,
            "alt": "json",
        }
        headers: dict[str, str] = {"Accept": "application/json"}

        if oauth_token:
            headers["Authorization"] = f"Bearer {oauth_token}"
        elif api_key:
            params["key"] = api_key
        else:
            logger.error("_google_search: neither api_key nor oauth_token provided")
            return []

        try:
            response = _request_search_json(
                "https://www.googleapis.com/customsearch/v1",
                scope=_search_scope(
                    "google",
                    account="oauth" if oauth_token else "api-key",
                ),
                headers=headers,
                params=params,
            )
            data = _json_object(response)
            page_items = _json_rows(data.get("items", []))

            if not page_items:
                logger.info("google_search: no more results at page %d (start=%d)", page + 1, start_index)
                break

            for row in page_items:
                row = _required_json_dict(row)
                item: SearchResult = {
                    "title": row.get("title", ""),
                    "link": row.get("link", ""),
                    "snippet": row.get("snippet", ""),
                    "source": "google",
                }
                items.append(item)
            logger.info("google_search: page %d (start=%d) got %d results (total=%d)",
                       page + 1, start_index, len(page_items), len(items))
            if len(page_items) < num_results:
                break

        except Exception as e:
            logger.warning("google_search: API error at page %d (start=%d): %s", page + 1, start_index, e)
            if on_error is not None:
                on_error(e)
            if "quota" in str(e).lower() or "429" in str(e):
                logger.error("google_search: quota exceeded")
            if page == 0:
                return []
            break
    
    return items[:limit]  # 确保不超过请求的限制


def _add_result_dedup(results: List[SearchResult], seen_links: Set[str], item: SearchResult, *, occurrence_sink: Optional[List[ObservationRecord]] = None, request_provider: str = "auto", branch_provider: str | None = None) -> bool:
    link = _result_text(item, "link")
    if not link:
        return False

    canonical_link = _canonicalize_url(link)
    if occurrence_sink is not None:
        source = branch_provider or _result_text(item, "source") or request_provider
        route = str(item.get("provider_route") or (("auto:" if request_provider == "auto" else "explicit:") + source))
        if request_provider == "google" and source == "ddg":
            route = "fallback:ddg"
        supplied_rank = item.get("rank")
        original_rank = supplied_rank if isinstance(supplied_rank, int) and supplied_rank > 0 else 1 + sum(
            1 for row in occurrence_sink
            if row["provider"] == source and row["keyword"] == item.get("keyword") and row["route"] == route
        )
        keyword = item.get("keyword")
        occurrence_record: ObservationRecord = {
            "resource_uri": canonical_link,
            "keyword": keyword if isinstance(keyword, str) else None,
            "provider": source,
            "route": route,
            "original_rank": original_rank,
            "retained": canonical_link not in seen_links,
        }
        occurrence_sink.append(occurrence_record)
    if canonical_link in seen_links:
        return False
    seen_links.add(canonical_link)
    item["link"] = canonical_link
    item["canonical_link"] = canonical_link

    # 附加域名信息，方便前端展示多样性
    try:
        host = _extract_domain(canonical_link)
        item.setdefault("domain", host)
    except Exception:
        pass

    item["relevance_score"] = 0.0
    results.append(item)
    return True
