from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, date, timezone
from typing import Iterable, List, Optional

from ..job_logger import start_job, complete_job, fail_job
from ..projects import current_project_key
from .doc_type_mapper import normalize_doc_type
from .adapters.http_utils import fetch_html, make_html_parser
from .adapters.social_reddit import RedditAdapter, RedditPost
from .adapters.news_google import GoogleNewsAdapter, GoogleNewsItem
from ..http.client import default_http_client
from ...settings.config import settings


logger = logging.getLogger(__name__)
BATCH_COMMIT_SIZE = 100
DEFAULT_REDDIT_SUBREDDIT = settings.default_reddit_subreddit

@dataclass(slots=True)
class NewsItem:
    title: str
    link: str
    summary: str | None = None
    published_at: datetime | None = None


def collect_official_news_updates(
    *,
    url: str,
    source_name: str,
    base_url: str,
    doc_type: str = "official_update",
    default_state: str | None = None,
    job_type: str = "official_news",
    title_fallback: str = "Official Update",
    limit: int = 10,
) -> dict:
    job_id = start_job(job_type, {"limit": limit, "source_name": source_name})
    try:
        html, _ = fetch_html(url)
        items = list(_extract_official_news_items(html, base_url=base_url, title_fallback=title_fallback))
        result = _persist_news_items(
            items=items[: max(limit, 0)],
            doc_type=doc_type,
            source_name=source_name,
            base_url=base_url,
            default_state=default_state,
            job_type=job_type,
        )
        complete_job(job_id, result=result)
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("collect_official_news_updates failed")
        fail_job(job_id, str(exc))
        raise


def collect_reddit_discussions(
    subreddit: str = DEFAULT_REDDIT_SUBREDDIT,
    limit: int = 20,
    keywords: Optional[List[str]] = None,
    subreddits: Optional[List[str]] = None,
) -> dict:
    """
    收集Reddit讨论帖
    
    Args:
        subreddit: 单个子论坛名称（向后兼容）
        limit: 每个子论坛的帖子数量限制
        keywords: 可选的关键词列表，用于过滤帖子
        subreddits: 可选的子论坛列表，如果提供则搜索多个子论坛
    """
    # 支持多子论坛或单个子论坛
    subreddit_list = subreddits if subreddits else [subreddit]
    job_id = start_job(
        "reddit_discussions",
        {"subreddits": subreddit_list, "limit": limit, "keywords": keywords},
    )
    
    try:
        adapter = RedditAdapter()
        
        # 如果只有一个子论坛，使用原有逻辑保持兼容性
        if len(subreddit_list) == 1:
            posts = list(adapter.fetch_posts(subreddit_list[0], keywords, limit))
            source_name = f"Reddit r/{subreddit_list[0]}"
        else:
            # 多个子论坛
            posts = adapter.search_multiple_subreddits(subreddit_list, keywords, limit)
            source_name = f"Reddit {len(subreddit_list)} subreddits"
        
        # 存储额外的Reddit数据到extracted_data
        result = _persist_reddit_items(
            posts=posts,
            doc_type="social_feed",
            source_name=source_name,
            base_url="reddit.com",
            default_state="CA",
            job_type="reddit_discussions",
        )
        complete_job(job_id, result=result)
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("collect_reddit_discussions failed")
        fail_job(job_id, str(exc))
        raise


def _maybe_append_to_resource_pool(link: str, job_type: str, source_ref: dict) -> None:
    """Append URL to resource pool if capture enabled for project + job_type."""
    project_key = (current_project_key() or "").strip()
    if not project_key:
        return
    try:
        from ..resource_pool import DefaultResourcePoolAppendAdapter
        DefaultResourcePoolAppendAdapter().append_url(
            link, source="ingest", source_ref=source_ref,
            project_key=project_key, job_type=job_type,
        )
    except Exception:  # noqa: BLE001
        pass


def _persist_news_items(
    *,
    items: Iterable[NewsItem],
    doc_type: str,
    source_name: str,
    base_url: str,
    default_state: str | None,
    kind: str = "news",
    job_type: str | None = None,
) -> dict:
    normalized_doc_type = normalize_doc_type(doc_type)
    links: List[str] = []
    for item in items:
        link = item.link.strip()
        if not link:
            continue
        links.append(link)
        if job_type:
            _maybe_append_to_resource_pool(link, job_type, {"source": source_name})
    ingest_result = _dispatch_links_to_single_url(
        links=links,
        query_terms=[],
    )

    return {
        "inserted": int(ingest_result.get("inserted") or 0),
        "inserted_valid": int(ingest_result.get("inserted_valid") or 0),
        "skipped": int(ingest_result.get("skipped") or 0),
        "queued": int(ingest_result.get("queued") or 0),
        "links": links,
        "doc_type": normalized_doc_type,
        "single_write_workflow": "single_url",
        "enforced_body_only": True,
    }


def _dispatch_links_to_single_url(*, links: List[str], query_terms: List[str]) -> dict:
    if not links:
        return {"inserted": 0, "inserted_valid": 0, "skipped": 0, "queued": 0}
    from .url_pool import collect_urls_from_list

    project_key = (current_project_key() or "").strip() or None
    return collect_urls_from_list(
        links,
        project_key=project_key,
        query_terms=list(query_terms or []),
        extra_params={
            "dispatch_mode": "inline",
            "single_url_frontdoor_enabled": True,
            "front_door_owner": "ingest.news",
            "frontdoor_route_decision": "front_door_url_routing",
            "frontdoor_write_mode": "front_door_url_routing",
            "frontdoor_execution_mode": "url_routing",
        },
        enable_extraction=True,
    )


def _extract_official_news_items(
    html: str,
    *,
    base_url: str,
    title_fallback: str = "Official Update",
) -> Iterable[NewsItem]:
    parser = make_html_parser(html)
    selectors = [
        ".news-release-card",
        "article.news-card",
        "div.news-card",
        "li.news-list__item",
    ]
    seen = set()
    for selector in selectors:
        for node in parser.css(selector):
            link_node = node.css_first("a")
            if link_node is None:
                continue
            href = link_node.attributes.get("href") or ""
            if not href or href in seen:
                continue
            seen.add(href)
            title = link_node.text(strip=True) or title_fallback
            summary_node = node.css_first("p")
            summary = summary_node.text(strip=True) if summary_node else None
            date_node = node.css_first("time")
            published = _parse_date_safe(date_node.attributes.get("datetime")) if date_node else None
            yield NewsItem(title=title, link=_normalize_url(href, base_url=base_url), summary=summary, published_at=published)

    # fallback: generic anchors on page
    for link_node in parser.css("a"):
        href = link_node.attributes.get("href") or ""
        if not href or href in seen:
            continue
        if "news" not in href.lower() and "press" not in href.lower():
            continue
        seen.add(href)
        title = link_node.text(strip=True) or title_fallback
        yield NewsItem(title=title, link=_normalize_url(href, base_url=base_url))


def _parse_date_safe(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    iso_candidates = [
        text,
        text.replace("z", "Z"),
        text.replace(" ", "T"),
    ]
    if text.endswith("Z") or text.endswith("z"):
        iso_candidates.append(text[:-1] + "+00:00")
    if text.endswith("+0000"):
        iso_candidates.append(text[:-5] + "+00:00")
    if len(text) >= 5 and (text[-5] in ("+", "-")) and text[-3] != ":" and text[-4:].isdigit():
        iso_candidates.append(f"{text[:-5]}{text[-5:-3]}:{text[-2:]}")

    for candidate in iso_candidates:
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            continue

    for fmt in (
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%m/%d/%Y",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%a, %d %b %Y %H:%M:%S %z",
    ):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _publish_date(value: datetime | None) -> date | None:
    if not value:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).date()
    return value.date()


def _normalize_url(href: str, *, base_url: str) -> str:
    href = href.strip()
    if href.startswith("http://") or href.startswith("https://"):
        return href
    normalized_base = base_url.strip().rstrip("/")
    if not normalized_base.startswith("http://") and not normalized_base.startswith("https://"):
        normalized_base = f"https://{normalized_base}"
    return f"{normalized_base}{href}" if href.startswith("/") else f"{normalized_base}/{href}"


def _persist_reddit_items(
    *,
    posts: Iterable[RedditPost],
    doc_type: str,
    source_name: str,
    base_url: str,
    default_state: str | None,
    job_type: str | None = None,
) -> dict:
    """Store reddit links via single_url body-fetch pipeline (no URL-only docs)."""
    normalized_doc_type = normalize_doc_type(doc_type)
    links: List[str] = []
    query_terms: list[str] = []
    for post in posts:
        link = post.link.strip()
        if not link:
            continue
        links.append(link)
        if job_type:
            _maybe_append_to_resource_pool(link, job_type, {"subreddit": post.subreddit})
        subreddit = str(post.subreddit or "").strip()
        if subreddit:
            query_terms.append(subreddit)

    ingest_result = _dispatch_links_to_single_url(
        links=links,
        query_terms=query_terms,
    )

    return {
        "inserted": int(ingest_result.get("inserted") or 0),
        "inserted_valid": int(ingest_result.get("inserted_valid") or 0),
        "skipped": int(ingest_result.get("skipped") or 0),
        "queued": int(ingest_result.get("queued") or 0),
        "links": links,
        "doc_type": normalized_doc_type,
        "single_write_workflow": "single_url",
        "enforced_body_only": True,
    }


def _parse_reddit_payload(payload: object) -> List[NewsItem]:
    """旧版解析函数，保留用于向后兼容"""
    items: List[NewsItem] = []
    if not isinstance(payload, dict):
        return items
    data = payload.get("data")
    if not isinstance(data, dict):
        return items
    children = data.get("children")
    if not isinstance(children, list):
        return items
    for child in children:
        if not isinstance(child, dict):
            continue
        cdata = child.get("data")
        if not isinstance(cdata, dict):
            continue
        permalink = cdata.get("permalink")
        if not isinstance(permalink, str):
            continue
        title = cdata.get("title") or "Reddit discussion"
        summary = cdata.get("selftext") or cdata.get("selftext_html")
        created_utc = cdata.get("created_utc")
        published = None
        if isinstance(created_utc, (int, float)):
            published = datetime.utcfromtimestamp(created_utc)
        items.append(
            NewsItem(
                title=str(title),
                link=f"https://www.reddit.com{permalink}",
                summary=str(summary) if summary else None,
                published_at=published,
            )
        )
    return items


def collect_google_news(keywords: List[str], limit: int = 20) -> dict:
    """
    收集Google News新闻
    
    Args:
        keywords: 搜索关键词列表
        limit: 每个关键词的结果数量限制
    """
    job_id = start_job("google_news", {"keywords": keywords, "limit": limit})
    try:
        adapter = GoogleNewsAdapter()
        news_items = adapter.search_multiple_keywords(keywords, limit)
        
        result = _persist_google_news_items(
            items=news_items,
            doc_type="news",
            source_name="Google News",
            base_url="news.google.com",
            default_state=None,  # Google News可能涉及多个州
            job_type="google_news",
        )
        complete_job(job_id, result=result)
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("collect_google_news failed")
        fail_job(job_id, str(exc))
        raise


def _persist_google_news_items(
    *,
    items: Iterable[GoogleNewsItem],
    doc_type: str,
    source_name: str,
    base_url: str,
    default_state: str | None,
    job_type: str | None = None,
) -> dict:
    """Store Google News links via single_url body-fetch pipeline (no URL-only docs)."""
    normalized_doc_type = normalize_doc_type(doc_type)
    links: List[str] = []
    query_terms: list[str] = []
    for item in items:
        link = item.link.strip()
        if not link:
            continue
        links.append(link)
        if job_type:
            _maybe_append_to_resource_pool(link, job_type, {"keyword": item.keyword})
        kw = str(item.keyword or "").strip()
        if kw:
            query_terms.append(kw)

    ingest_result = _dispatch_links_to_single_url(
        links=links,
        query_terms=query_terms,
    )

    return {
        "inserted": int(ingest_result.get("inserted") or 0),
        "inserted_valid": int(ingest_result.get("inserted_valid") or 0),
        "skipped": int(ingest_result.get("skipped") or 0),
        "queued": int(ingest_result.get("queued") or 0),
        "links": links,
        "doc_type": normalized_doc_type,
        "single_write_workflow": "single_url",
        "enforced_body_only": True,
    }
