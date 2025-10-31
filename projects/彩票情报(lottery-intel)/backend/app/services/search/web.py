from __future__ import annotations

from typing import List, Dict, Set
import os
import logging

from duckduckgo_search import DDGS
from ..http.client import default_http_client
from urllib.parse import urlparse

from ..llm.provider import get_chat_model
from ...settings.config import settings

logger = logging.getLogger(__name__)


def generate_keywords(topic: str, language: str = "zh") -> List[str]:
    # If no valid provider/key configured, skip LLM and use fallback keywords
    if settings.llm_provider == "openai" and not settings.openai_api_key:
        logger.info("generate_keywords: using fallback (no OPENAI key), topic=%s lang=%s", topic, language)
        return [
            topic,
            *( [
                f"{topic} regulation",
                f"{topic} market",
                f"{topic} sales report",
                f"{topic} lottery policy",
            ] if language.lower().startswith("en") else [
                f"{topic} 政策",
                f"{topic} 市场",
                f"{topic} 销售 报告",
                f"{topic} 彩票 法规",
            ])
        ]
    try:
        prompt = (
            "你是一名搜索关键词生成助手。请基于用户主题，输出 3~5 个多样化的" +
            ("英文" if language.lower().startswith("en") else "中文") +
            "搜索关键词。每行一个关键词，尽量包含与政策、市场或行情相关的词。\n主题：" + topic
        )
        model = get_chat_model()
        response = model.invoke(prompt)
        text = response.content if hasattr(response, "content") else str(response)
        keywords: List[str] = []
        for line in text.splitlines():
            line = line.strip("- ")
            if line:
                keywords.append(line)
        if keywords:
            logger.info("generate_keywords: llm keywords=%s", keywords)
            return keywords
    except Exception:
        # Fallback without LLM (no key / provider error)
        logger.warning("generate_keywords: llm failed, fallback to static keywords", exc_info=True)

    if language.lower().startswith("en"):
        return [
            topic,
            f"{topic} regulation",
            f"{topic} market",
            f"{topic} sales report",
            f"{topic} lottery policy",
        ]
    else:
        return [
            topic,
            f"{topic} 政策",
            f"{topic} 市场",
            f"{topic} 销售 报告",
            f"{topic} 彩票 法规",
        ]


def search_sources(topic: str, language: str = "en", max_results: int = 10) -> List[dict]:
    keywords = generate_keywords(topic, language)
    logger.info("search_sources: start topic=%s lang=%s keywords=%s max=%d", topic, language, keywords, max_results)
    results: List[dict] = []
    seen_links: Set[str] = set()
    try:
        with DDGS() as ddgs:
            per_kw = max(1, max_results // max(1, len(keywords)))
            for keyword in keywords:
                try:
                    count = 0
                    for result in ddgs.text(keyword, safesearch="off", max_results=per_kw):
                        item = {
                            "keyword": keyword,
                            "title": result.get("title"),
                            "link": result.get("href"),
                            "snippet": result.get("body"),
                            "source": result.get("source"),
                        }
                        if _add_result_dedup(results, seen_links, item):
                            pass
                        count += 1
                    logger.info("search_sources: keyword=%s got %d", keyword, count)
                except Exception:
                    logger.warning("search_sources: keyword=%s failed", keyword, exc_info=True)
                    continue
    except Exception:
        # search provider blocked/unavailable
        logger.error("search_sources: ddg provider unavailable", exc_info=True)
        # continue to fallback providers

    # Fallback: SerpAPI
    if len(results) == 0:
        from ...settings.config import settings as _settings
        serp_key = os.getenv("SERPAPI_KEY") or os.getenv("SERPAPI_API_KEY") or _settings.serpapi_key
        if serp_key:
            logger.info("search_sources: fallback serpapi")
            per_kw = max(1, max_results // max(1, len(keywords)))
            for keyword in keywords:
                try:
                    items = _serpapi_search(keyword, serp_key, per_kw)
                    for it in items:
                        it["keyword"] = keyword
                        _add_result_dedup(results, seen_links, it)
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
                    items = _serpapi_search_news(keyword, serp_key, per_kw)
                    for it in items:
                        it["keyword"] = keyword
                        _add_result_dedup(results, seen_links, it)
                except Exception:
                    continue

    # Fallback: site:calottery.com on DDG
    if len(results) == 0:
        site_kw = [f"site:calottery.com {k}" for k in keywords]
        try:
            with DDGS() as ddgs:
                for keyword in site_kw:
                    try:
                        for result in ddgs.text(keyword, safesearch="off", max_results=2):
                            item = {
                                "keyword": keyword,
                                "title": result.get("title"),
                                "link": result.get("href"),
                                "snippet": result.get("body"),
                                "source": result.get("source"),
                            }
                            _add_result_dedup(results, seen_links, item)
                    except Exception:
                        continue
        except Exception:
            logger.warning("search_sources: site search fallback failed", exc_info=True)

    logger.info("search_sources: total=%d", len(results))
    return results


def _serpapi_search(keyword: str, api_key: str, limit: int) -> List[dict]:
    params = {
        "q": keyword,
        "engine": "google",
        "api_key": api_key,
        "num": str(max(1, limit)),
    }
    data = default_http_client.get_json("https://serpapi.com/search.json", params=params)
    items: List[dict] = []
    for r in data.get("organic_results", [])[:limit]:
        items.append(
            {
                "title": r.get("title"),
                "link": r.get("link"),
                "snippet": r.get("snippet"),
                "source": "serpapi",
            }
        )
    return items


def _serpapi_search_news(keyword: str, api_key: str, limit: int) -> List[dict]:
    params = {
        "q": keyword,
        "engine": "google",
        "api_key": api_key,
        "tbm": "nws",
        "num": str(max(1, limit)),
    }
    data = default_http_client.get_json("https://serpapi.com/search.json", params=params)
    items: List[dict] = []
    for r in data.get("news_results", [])[:limit]:
        items.append(
            {
                "title": r.get("title"),
                "link": r.get("link"),
                "snippet": r.get("snippet") or r.get("source"),
                "source": "serpapi_news",
            }
        )
    return items


def _add_result_dedup(results: List[dict], seen_links: Set[str], item: Dict[str, str]) -> bool:
    link = (item.get("link") or "").strip()
    if not link or link in seen_links:
        return False
    seen_links.add(link)
    # 附加域名信息，方便前端展示多样性
    try:
        host = urlparse(link).netloc
        item.setdefault("domain", host)
    except Exception:
        pass
    results.append(item)
    return True

