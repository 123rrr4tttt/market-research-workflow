from __future__ import annotations

from typing import List, Dict, Set, Optional
from datetime import datetime, timedelta
import os
import logging
import time

from duckduckgo_search import DDGS
from duckduckgo_search.exceptions import RatelimitException
from ..http.client import default_http_client
from urllib.parse import urlparse
from sqlalchemy import select

from ..llm.provider import get_chat_model
from ..llm.config_loader import get_llm_config, format_prompt_template
from ...settings.config import settings
from ...models.base import SessionLocal
from ...models.entities import Document

# Azure AI Search removed - it's for searching your own data, not web search

logger = logging.getLogger(__name__)


_BILINGUAL_LANG_MODES = {"bi", "bilingual", "zh-en", "zh_en", "both", "multi", "multilingual"}


def _base_language(language: str) -> str:
    lang = (language or "").strip().lower()
    if lang.startswith("zh"):
        return "zh"
    if lang.startswith("en"):
        return "en"
    return "en"


def _is_bilingual_mode(language: str) -> bool:
    return (language or "").strip().lower() in _BILINGUAL_LANG_MODES


def _dedup_keywords(items: List[str]) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for raw in items:
        kw = str(raw or "").strip()
        if not kw or kw in seen:
            continue
        seen.add(kw)
        out.append(kw)
    return out


def generate_keywords(topic: str, language: str = "zh") -> List[str]:
    if _is_bilingual_mode(language):
        # Keep bilingual support in prompt-generation layer only (no search execution routing).
        if settings.llm_provider == "openai" and not settings.openai_api_key:
            return _dedup_keywords(generate_keywords(topic, "zh") + generate_keywords(topic, "en"))
        try:
            prompt = (
                "你是一名搜索关键词生成助手。请基于用户主题输出 6~10 个中英文混合的搜索关键词。"
                "要求同时包含中文和英文关键词，每行一个关键词，不要解释，尽量覆盖政策、市场、产业链、技术与销售/财报相关角度。\n"
                "主题：" + topic
            )
            model = get_chat_model()
            response = model.invoke(prompt)
            text = response.content if hasattr(response, "content") else str(response)
            keywords = _dedup_keywords([line.strip("- ") for line in text.splitlines() if line.strip("- ").strip()])
            if keywords:
                logger.info("generate_keywords: llm bilingual keywords=%s", keywords)
                return keywords
        except Exception:
            logger.warning("generate_keywords: llm bilingual failed, fallback to zh+en", exc_info=True)
        return _dedup_keywords(generate_keywords(topic, "zh") + generate_keywords(topic, "en"))

    # If no valid provider/key configured, skip LLM and use fallback keywords
    if settings.llm_provider == "openai" and not settings.openai_api_key:
        logger.info("generate_keywords: using fallback (no OPENAI key), topic=%s lang=%s", topic, language)
        return [
            topic,
            *( [
                f"{topic} regulation",
                f"{topic} market",
                f"{topic} sales report",
                f"{topic} supply chain",
            ] if language.lower().startswith("en") else [
                f"{topic} 政策",
                f"{topic} 市场",
                f"{topic} 销售 报告",
                f"{topic} 产业链",
            ])
        ]
    try:
        # 尝试从数据库读取配置
        config = get_llm_config("keyword_generation")
        
        if config and config.get("user_prompt_template"):
            # 使用配置的提示词
            language_str = "英文" if language.lower().startswith("en") else "中文"
            prompt = format_prompt_template(
                config["user_prompt_template"],
                language=language_str,
                topic=topic
            )
            model = get_chat_model(
                model=config.get("model"),
                temperature=config.get("temperature"),
                max_tokens=config.get("max_tokens"),
                top_p=config.get("top_p"),
                presence_penalty=config.get("presence_penalty"),
                frequency_penalty=config.get("frequency_penalty"),
            )
        else:
            # 使用默认提示词（向后兼容）
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
            f"{topic} supply chain",
        ]
    else:
        return [
            topic,
            f"{topic} 政策",
            f"{topic} 市场",
            f"{topic} 销售 报告",
            f"{topic} 产业链",
        ]


def generate_topic_keywords(
    topic: str,
    *,
    topic_focus: str,
    language: str = "zh",
    base_keywords: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Generate topic-focused search keywords (company/product/operation) for collection.

    This is collection-layer keyword expansion, separate from structured extraction prompts.
    """
    focus = str(topic_focus or "").strip().lower()
    if focus not in {"company", "product", "operation"}:
        return {"search_keywords": [], "topic_hints": []}

    base = [str(x).strip() for x in (base_keywords or []) if str(x).strip()]
    if not base:
        base = [topic]

    # Cheap deterministic fallback extensions
    zh_suffix = {
        "company": ["公司", "企业", "品牌", "合作", "供应链", "渠道"],
        "product": ["产品", "型号", "品类", "参数", "发布", "应用场景"],
        "operation": ["经营", "商业模式", "运营模式", "电商", "平台", "渠道策略"],
    }
    en_suffix = {
        "company": ["company", "brand", "partnership", "supply chain", "channel"],
        "product": ["product", "model", "category", "specs", "launch", "use case"],
        "operation": ["operation", "business model", "ecommerce", "platform", "channel strategy"],
    }
    hints = (zh_suffix if _base_language(language) == "zh" else en_suffix).get(focus, [])
    fallback = _dedup_keywords([f"{kw} {s}" for kw in base[:4] for s in hints[:4]])

    try:
        if settings.llm_provider == "openai" and not settings.openai_api_key:
            return {"search_keywords": fallback[:12], "topic_hints": hints[:8]}
        prompt = (
            "你是一名专题搜索关键词生成助手。请基于主题和专题方向生成 6~12 个用于检索的关键词。"
            "只返回 JSON，格式为 {\"search_keywords\":[],\"topic_hints\":[]}。\n"
            f"主题: {topic}\n专题: {focus}\n语言: {language}\n已有基础关键词: {base[:10]}\n"
            "要求：关键词偏检索用途，不要输出结构化字段；topic_hints 是主题提示词，可更抽象。"
        )
        model = get_chat_model()
        response = model.invoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        data = None
        try:
            from ..extraction.json_utils import extract_json_payload as _extract_json
            data = _extract_json(content)
        except Exception:
            data = None
        if isinstance(data, dict):
            search_kw = _dedup_keywords([str(x).strip() for x in (data.get("search_keywords") or []) if str(x).strip()])
            topic_hints = _dedup_keywords([str(x).strip() for x in (data.get("topic_hints") or []) if str(x).strip()])
            if search_kw:
                return {"search_keywords": search_kw[:12], "topic_hints": topic_hints[:12]}
    except Exception:
        logger.warning("generate_topic_keywords: llm failed, fallback", exc_info=True)
    return {"search_keywords": fallback[:12], "topic_hints": hints[:8]}


def filter_existing(results: List[dict]) -> List[dict]:
    """过滤已入库的文档"""
    urls = [r.get("link") for r in results if r.get("link")]
    if not urls:
        return results
    
    with SessionLocal() as session:
        existing_urls = {
            row[0] for row in session.execute(
                select(Document.uri).where(Document.uri.in_(urls))
            ).all()
        }
    
    filtered = [r for r in results if r.get("link") not in existing_urls]
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
) -> List[dict]:
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
    
    keywords = generate_keywords(topic, language)
    # 如果关键词生成失败，使用topic本身作为关键词
    if not keywords:
        keywords = [topic]
        logger.warning("search_sources: keyword generation failed, using topic as keyword: %s", topic)
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

        elif provider == "serper":
            serper_key = os.getenv("SERPER_API_KEY") or getattr(_settings, "serper_api_key", None)
            if not serper_key:
                logger.error("search_sources: serper key not configured")
                return results
            per_kw = max(1, max_results // max(1, len(keywords)))
            for keyword in keywords:
                try:
                    items = _serper_search(keyword, serper_key, per_kw, language=language)
                    for it in items:
                        it["keyword"] = keyword
                        _add_result_dedup(results, seen_links, it)
                    logger.info("search_sources: serper keyword=%s got %d", keyword, len(items))
                except Exception as e:
                    logger.warning("search_sources: serper keyword=%s failed: %s", keyword, e, exc_info=True)
                    continue
        
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
            google_oauth_token = _get_google_oauth_token()
            google_configured = google_cse_id and (google_api_key or google_oauth_token)
            if not google_configured:
                logger.warning("search_sources: google not configured (need CSE_ID + API_KEY or GOOGLE_APPLICATION_CREDENTIALS), falling back to ddg")
                # Fallback to DDG when Google CSE not configured
                try:
                    with DDGS() as ddgs:
                        per_kw = max(1, max_results // max(1, len(keywords)))
                        for keyword in keywords:
                            try:
                                for result in ddgs.text(keyword, safesearch="off", max_results=per_kw):
                                    item = {
                                        "keyword": keyword,
                                        "title": result.get("title"),
                                        "link": result.get("href"),
                                        "snippet": result.get("body"),
                                        "source": "ddg",
                                    }
                                    _add_result_dedup(results, seen_links, item)
                                logger.info("search_sources: ddg fallback keyword=%s got results", keyword)
                            except (RatelimitException, Exception) as e:
                                logger.warning("search_sources: ddg fallback keyword=%s failed: %s", keyword, e)
                                continue
                except (RatelimitException, Exception) as e:
                    logger.warning("search_sources: ddg fallback failed: %s", e)
            else:
                # Google API: OAuth 优先于 API Key；batch requests with delay
                auth_kw = {"oauth_token": google_oauth_token} if google_oauth_token else {"api_key": google_api_key}
                if google_oauth_token:
                    logger.info("search_sources: using Google OAuth (GOOGLE_APPLICATION_CREDENTIALS)")
                for i, keyword in enumerate(keywords):
                    if len(results) >= max_results:
                        break
                    if i > 0:
                        time.sleep(1.0)  # delay between keywords
                    try:
                        remaining = max_results - len(results)
                        items = _google_search(keyword, google_cse_id, remaining, start_offset, **auth_kw)
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
                items = _serper_search(keyword, serper_key, min(per_kw, remaining), language=language)
                for it in items:
                    it["keyword"] = keyword
                    _add_result_dedup(results, seen_links, it)
            except Exception as e:
                logger.warning("search_sources: serper keyword=%s failed: %s", keyword, e, exc_info=True)
                continue

    # 2. 尝试 Google Custom Search（若可用，支持分页）
    google_api_key = os.getenv("GOOGLE_SEARCH_API_KEY") or _settings.google_search_api_key
    google_cse_id = os.getenv("GOOGLE_SEARCH_CSE_ID") or _settings.google_search_cse_id
    google_oauth_token = _get_google_oauth_token()
    if len(results) == 0 and google_cse_id and (google_api_key or google_oauth_token):
        auth_kw = {"oauth_token": google_oauth_token} if google_oauth_token else {"api_key": google_api_key}
        logger.info("search_sources: auto mode - using google custom search (OAuth=%s)", bool(google_oauth_token))
        for i, keyword in enumerate(keywords):
            if len(results) >= max_results:
                break
            if i > 0:
                time.sleep(1.0)  # delay between keywords
            try:
                remaining = max_results - len(results)
                items = _google_search(keyword, google_cse_id, remaining, start_offset, **auth_kw)
                for it in items:
                    it["keyword"] = keyword
                    _add_result_dedup(results, seen_links, it)
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
        
        # 4. 最后尝试 SerpAPI（如果配置了）
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

    # 过滤已存在的文档
    if exclude_existing:
        results = filter_existing(results)
    
    # 时间排序（简单实现：按URL域名排序，实际中可以根据搜索结果的时间戳排序）
    # 注意：大部分搜索API不返回精确的时间戳，这里先简单处理
    
    logger.info("search_sources: total=%d exclude_existing=%s", len(results), exclude_existing)
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


def _serper_search(keyword: str, api_key: str, limit: int, *, language: str = "en") -> List[dict]:
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
    data = default_http_client.post_json(
        "https://google.serper.dev/search",
        json=payload,
        headers={
            "X-API-KEY": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )

    items: List[dict] = []
    for r in (data.get("organic") or [])[:limit]:
        items.append(
            {
                "title": r.get("title"),
                "link": r.get("link"),
                "snippet": r.get("snippet") or r.get("description"),
                "source": "serper",
            }
        )
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
        credentials = service_account.Credentials.from_service_account_file(
            creds_path, scopes=[_CSE_OAUTH_SCOPE]
        )
        credentials.refresh(google.auth.transport.requests.Request())
        return credentials.token
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
) -> List[dict]:
    """Google Custom Search API: 每天100次免费请求
    支持 API Key 或 OAuth 2.0（Service Account）认证。
    支持分页获取多页结果（通过start参数）
    注册地址: https://developers.google.com/custom-search/v1/overview

    认证方式（二选一）:
    1. API Key: GOOGLE_SEARCH_API_KEY
    2. OAuth: GOOGLE_APPLICATION_CREDENTIALS 指向 Service Account JSON 路径
    """
    items: List[dict] = []
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
        headers: Dict[str, str] = {"Accept": "application/json"}

        if oauth_token:
            headers["Authorization"] = f"Bearer {oauth_token}"
        elif api_key:
            params["key"] = api_key
        else:
            logger.error("_google_search: neither api_key nor oauth_token provided")
            return []

        try:
            data = default_http_client.get_json(
                "https://www.googleapis.com/customsearch/v1",
                params=params,
                headers=headers,
            )
            page_items = data.get("items", [])

            if not page_items:
                logger.info("google_search: no more results at page %d (start=%d)", page + 1, start_index)
                break

            for r in page_items:
                items.append(
                    {
                        "title": r.get("title", ""),
                        "link": r.get("link", ""),
                        "snippet": r.get("snippet", ""),
                        "source": "google",
                    }
                )
            logger.info("google_search: page %d (start=%d) got %d results (total=%d)",
                       page + 1, start_index, len(page_items), len(items))
            if len(page_items) < num_results:
                break

        except Exception as e:
            logger.warning("google_search: API error at page %d (start=%d): %s", page + 1, start_index, e)
            if "quota" in str(e).lower() or "429" in str(e):
                logger.error("google_search: quota exceeded")
            if page == 0:
                return []
            break
    
    return items[:limit]  # 确保不超过请求的限制


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
