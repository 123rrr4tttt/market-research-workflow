from __future__ import annotations

from typing import List, Dict, Set
import os
import logging

from duckduckgo_search import DDGS
from duckduckgo_search.exceptions import RatelimitException
from ..http.client import default_http_client
from urllib.parse import urlparse

from ..llm.provider import get_chat_model
from ...settings.config import settings

# Azure AI Search removed - it's for searching your own data, not web search

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


def search_sources(topic: str, language: str = "en", max_results: int = 10, provider: str = "auto") -> List[dict]:
    """搜索外部资源
    
    Args:
        topic: 搜索主题
        language: 语言 (en/zh)
        max_results: 最大结果数
        provider: 搜索服务提供商
            - "auto": 自动选择（DDG -> Google -> Serpstack -> SerpAPI）
            - "ddg": 仅使用 DuckDuckGo
            - "google": 仅使用 Google Custom Search
            - "serpstack": 仅使用 Serpstack
            - "serpapi": 仅使用 SerpAPI
    """
    keywords = generate_keywords(topic, language)
    logger.info("search_sources: start topic=%s lang=%s keywords=%s max=%d provider=%s", topic, language, keywords, max_results, provider)
    results: List[dict] = []
    seen_links: Set[str] = set()
    
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
                            for result in ddgs.text(keyword, safesearch="off", max_results=per_kw):
                                item = {
                                    "keyword": keyword,
                                    "title": result.get("title"),
                                    "link": result.get("href"),
                                    "snippet": result.get("body"),
                                    "source": result.get("source") or "ddg",
                                }
                                if _add_result_dedup(results, seen_links, item):
                                    pass
                                count += 1
                            logger.info("search_sources: ddg keyword=%s got %d", keyword, count)
                        except RatelimitException as e:
                            logger.warning("search_sources: ddg rate limited (202 Ratelimit) - DuckDuckGo 已限流，建议使用其他搜索服务: %s", e)
                            # DDG 被限流，返回已获取的结果（如果有）
                            break
                        except Exception as e:
                            logger.warning("search_sources: ddg keyword=%s failed: %s", keyword, e, exc_info=True)
                            continue
            except RatelimitException as e:
                logger.error("search_sources: ddg provider rate limited (202 Ratelimit) - DuckDuckGo 已限流，建议使用 Google/Serpstack/SerpAPI: %s", e)
                return results
            except Exception as e:
                logger.error("search_sources: ddg provider unavailable: %s", e, exc_info=True)
                return results
        
        elif provider == "serpstack":
            serpstack_key = os.getenv("SERPSTACK_KEY") or _settings.serpstack_key
            if not serpstack_key:
                logger.error("search_sources: serpstack key not configured")
                return results
            per_kw = max(1, max_results // max(1, len(keywords)))
            for keyword in keywords:
                try:
                    items = _serpstack_search(keyword, serpstack_key, per_kw)
                    for it in items:
                        it["keyword"] = keyword
                        _add_result_dedup(results, seen_links, it)
                    logger.info("search_sources: serpstack keyword=%s got %d", keyword, len(items))
                except Exception as e:
                    logger.warning("search_sources: serpstack keyword=%s failed: %s", keyword, e, exc_info=True)
                    continue
        
        elif provider == "google":
            from ...settings.config import settings as _settings
            google_api_key = os.getenv("GOOGLE_SEARCH_API_KEY") or _settings.google_search_api_key
            google_cse_id = os.getenv("GOOGLE_SEARCH_CSE_ID") or _settings.google_search_cse_id
            if not google_api_key or not google_cse_id:
                logger.error("search_sources: google search api_key/cse_id not configured")
                return results
            # Google API 每次最多返回10个结果，尝试多个关键词以获取更多结果
            per_kw = min(10, max(1, max_results // max(1, len(keywords)) + 2))  # 每个关键词尝试获取更多结果
            for keyword in keywords:
                if len(results) >= max_results:
                    break  # 已达到所需结果数
                try:
                    # 计算还需要的结果数
                    remaining = max_results - len(results)
                    items = _google_search(keyword, google_api_key, google_cse_id, min(per_kw, remaining))
                    for it in items:
                        it["keyword"] = keyword
                        _add_result_dedup(results, seen_links, it)
                    logger.info("search_sources: google keyword=%s got %d (total=%d)", keyword, len(items), len(results))
                except Exception as e:
                    logger.warning("search_sources: google keyword=%s failed: %s", keyword, e, exc_info=True)
                    continue
        
        elif provider == "serpapi":
            serp_key = os.getenv("SERPAPI_KEY") or os.getenv("SERPAPI_API_KEY") or _settings.serpapi_key
            if not serp_key:
                logger.error("search_sources: serpapi key not configured")
                return results
            per_kw = max(1, max_results // max(1, len(keywords)))
            for keyword in keywords:
                try:
                    items = _serpapi_search(keyword, serp_key, per_kw)
                    for it in items:
                        it["keyword"] = keyword
                        _add_result_dedup(results, seen_links, it)
                    logger.info("search_sources: serpapi keyword=%s got %d", keyword, len(items))
                except Exception as e:
                    logger.warning("search_sources: serpapi keyword=%s failed: %s", keyword, e, exc_info=True)
                    continue
        
        logger.info("search_sources: provider=%s total=%d", provider, len(results))
        return results
    
    # 自动模式：按优先级尝试
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
                            "source": result.get("source") or "ddg",
                        }
                        if _add_result_dedup(results, seen_links, item):
                            pass
                        count += 1
                    logger.info("search_sources: keyword=%s got %d", keyword, count)
                except RatelimitException as e:
                    logger.warning("search_sources: ddg rate limited (202 Ratelimit) - DuckDuckGo 已限流，将尝试其他搜索服务: %s", e)
                    # DDG 被限流，跳出循环，继续尝试其他搜索服务
                    break
                except Exception:
                    logger.warning("search_sources: keyword=%s failed", keyword, exc_info=True)
                    continue
    except RatelimitException as e:
        # search provider rate limited
        logger.warning("search_sources: ddg provider rate limited (202 Ratelimit) - DuckDuckGo 已限流，继续尝试其他搜索服务: %s", e)
        # continue to fallback providers
    except Exception:
        # search provider blocked/unavailable
        logger.warning("search_sources: ddg provider unavailable, continuing to fallback providers", exc_info=True)
        # continue to fallback providers

    # Fallback: 按优先级尝试多个免费搜索 API
    if len(results) == 0:
        from ...settings.config import settings as _settings
        
        # 1. 优先尝试 Google Custom Search（每天100次免费）
        google_api_key = os.getenv("GOOGLE_SEARCH_API_KEY") or _settings.google_search_api_key
        google_cse_id = os.getenv("GOOGLE_SEARCH_CSE_ID") or _settings.google_search_cse_id
        if google_api_key and google_cse_id:
            logger.info("search_sources: trying google custom search (free tier: 100/day)")
            # Google API 每次最多返回10个结果，尝试多个关键词以获取更多结果
            per_kw = min(10, max(1, max_results // max(1, len(keywords)) + 2))  # 每个关键词尝试获取更多结果
            for keyword in keywords:
                if len(results) >= max_results:
                    break  # 已达到所需结果数
                try:
                    # 计算还需要的结果数
                    remaining = max_results - len(results)
                    items = _google_search(keyword, google_api_key, google_cse_id, min(per_kw, remaining))
                    for it in items:
                        it["keyword"] = keyword
                        _add_result_dedup(results, seen_links, it)
                    if items:
                        logger.info("search_sources: google keyword=%s got %d (total=%d)", keyword, len(items), len(results))
                except Exception as e:
                    logger.warning("search_sources: google keyword=%s failed: %s", keyword, e)
                    continue
        
        # 2. 尝试 Serpstack（每月100次免费）
        if len(results) == 0:
            serpstack_key = os.getenv("SERPSTACK_KEY") or _settings.serpstack_key
            if serpstack_key:
                logger.info("search_sources: trying serpstack (free tier: 100/month)")
                per_kw = max(1, max_results // max(1, len(keywords)))
                for keyword in keywords:
                    try:
                        items = _serpstack_search(keyword, serpstack_key, per_kw)
                        for it in items:
                            it["keyword"] = keyword
                            _add_result_dedup(results, seen_links, it)
                        if items:
                            logger.info("search_sources: serpstack keyword=%s got %d", keyword, len(items))
                            break  # 成功获取结果，退出循环
                    except Exception as e:
                        logger.warning("search_sources: serpstack keyword=%s failed: %s", keyword, e)
                        continue
        
        # 3. 最后尝试 SerpAPI（如果配置了）
        if len(results) == 0:
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
                    except RatelimitException:
                        logger.warning("search_sources: ddg rate limited in site fallback, skipping")
                        break
                    except Exception:
                        continue
        except RatelimitException:
            logger.warning("search_sources: ddg rate limited in site fallback")
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


def _serpstack_search(keyword: str, api_key: str, limit: int) -> List[dict]:
    """Serpstack API: 每月100次免费请求
    注册地址: https://serpstack.com/
    """
    params = {
        "query": keyword,
        "access_key": api_key,
        "num": str(max(1, limit)),
    }
    data = default_http_client.get_json("http://api.serpstack.com/search", params=params)
    items: List[dict] = []
    for r in data.get("organic_results", [])[:limit]:
        items.append(
            {
                "title": r.get("title"),
                "link": r.get("url"),
                "snippet": r.get("snippet"),
                "source": "serpstack",
            }
        )
    return items


def _google_search(keyword: str, api_key: str, cse_id: str, limit: int) -> List[dict]:
    """Google Custom Search API: 每天100次免费请求
    注册地址: https://developers.google.com/custom-search/v1/overview
    需要:
    1. 在 Google Cloud Console 创建项目并启用 Custom Search API
    2. 创建 API Key
    3. 在 https://cse.google.com/cse/ 创建自定义搜索引擎，获取 Search Engine ID (cx)
    """
    params = {
        "q": keyword,
        "key": api_key,
        "cx": cse_id,
        "num": min(max(1, limit), 10),  # Google API 最多返回 10 个结果
    }
    try:
        data = default_http_client.get_json("https://www.googleapis.com/customsearch/v1", params=params)
        items: List[dict] = []
        for r in data.get("items", [])[:limit]:
            items.append(
                {
                    "title": r.get("title", ""),
                    "link": r.get("link", ""),
                    "snippet": r.get("snippet", ""),
                    "source": "google",
                }
            )
        return items
    except Exception as e:
        logger.warning("google_search: API error: %s", e)
        # 检查是否是配额超限
        if "quota" in str(e).lower() or "429" in str(e):
            logger.error("google_search: quota exceeded")
        return []


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

