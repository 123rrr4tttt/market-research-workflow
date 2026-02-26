from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, List, Optional

from sqlalchemy.orm import Session

from ..job_logger import start_job, complete_job, fail_job
from ..projects import current_project_key
from ...models.base import SessionLocal
from ...models.entities import Document, Source
from .doc_type_mapper import normalize_doc_type
from .adapters.http_utils import fetch_html, make_html_parser
from .adapters.social_reddit import RedditAdapter, RedditPost
from .adapters.news_google import GoogleNewsAdapter, GoogleNewsItem
from ..http.client import default_http_client
from ...settings.config import settings
from ...subprojects.online_lottery.domain.news import (
    CALOTTERY_NEWS_URL,
    CALOTTERY_RETAILER_URL,
    DEFAULT_REDDIT_SUBREDDIT,
)


logger = logging.getLogger(__name__)
BATCH_COMMIT_SIZE = 100

@dataclass(slots=True)
class NewsItem:
    title: str
    link: str
    summary: str | None = None
    published_at: datetime | None = None


def collect_calottery_news(limit: int = 10) -> dict:
    job_id = start_job("calottery_news", {"limit": limit})
    try:
        html, _ = fetch_html(CALOTTERY_NEWS_URL)
        items = list(_extract_calottery_items(html))
        result = _persist_news_items(
            items=items[: max(limit, 0)],
            doc_type="official_update",
            source_name="California Lottery News",
            base_url="calottery.com",
            default_state="CA",
            job_type="calottery_news",
        )
        complete_job(job_id, result=result)
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("collect_calottery_news failed")
        fail_job(job_id, str(exc))
        raise


def collect_calottery_retailer_updates(limit: int = 10) -> dict:
    job_id = start_job("calottery_retailer_news", {"limit": limit})
    try:
        html, _ = fetch_html(CALOTTERY_RETAILER_URL)
        items = list(_extract_calottery_items(html))
        result = _persist_news_items(
            items=items[: max(limit, 0)],
            doc_type="retailer_update",
            source_name="California Lottery Retailer News",
            base_url="calottery.com",
            default_state="CA",
            job_type="calottery_retailer_news",
        )
        complete_job(job_id, result=result)
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("collect_calottery_retailer_updates failed")
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
    inserted = 0
    skipped = 0
    links: List[str] = []
    pending_inserts = 0

    with SessionLocal() as session:
        source = _get_or_create_source(session, source_name, kind, base_url)
        source_id = source.id
        for item in items:
            link = item.link.strip()
            if not link:
                continue
            links.append(link)
            if job_type:
                _maybe_append_to_resource_pool(link, job_type, {"source": source_name})
            existed = session.query(Document).filter(Document.uri == link).one_or_none()
            if existed:
                skipped += 1
                continue

            document = Document(
                source_id=source_id,
                state=default_state,
                doc_type=normalized_doc_type,
                title=item.title,
                summary=item.summary,
                publish_date=item.published_at.date() if item.published_at else None,
                uri=link,
            )
            session.add(document)
            inserted += 1
            pending_inserts += 1
            if pending_inserts >= BATCH_COMMIT_SIZE:
                session.commit()
                session.expunge_all()
                pending_inserts = 0

        if pending_inserts > 0:
            session.commit()

    return {
        "inserted": inserted,
        "skipped": skipped,
        "links": links,
        "doc_type": normalized_doc_type,
    }


def _get_or_create_source(session: Session, name: str, kind: str, base_url: str) -> Source:
    source = (
        session.query(Source)
        .filter(Source.name == name, Source.kind == kind)
        .first()
    )
    if source:
        return source

    source = Source(name=name, kind=kind, base_url=base_url)
    session.add(source)
    session.flush()
    return source


def _extract_calottery_items(html: str) -> Iterable[NewsItem]:
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
            title = link_node.text(strip=True) or "California Lottery Update"
            summary_node = node.css_first("p")
            summary = summary_node.text(strip=True) if summary_node else None
            date_node = node.css_first("time")
            published = _parse_date_safe(date_node.attributes.get("datetime")) if date_node else None
            yield NewsItem(title=title, link=_normalize_url(href), summary=summary, published_at=published)

    # fallback: generic anchors on page
    for link_node in parser.css("a"):
        href = link_node.attributes.get("href") or ""
        if not href or href in seen:
            continue
        if "news" not in href.lower() and "press" not in href.lower():
            continue
        seen.add(href)
        title = link_node.text(strip=True) or "California Lottery Update"
        yield NewsItem(title=title, link=_normalize_url(href))


def _parse_date_safe(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _normalize_url(href: str) -> str:
    href = href.strip()
    if href.startswith("http://") or href.startswith("https://"):
        return href
    return f"https://www.calottery.com{href}" if href.startswith("/") else f"https://www.calottery.com/{href}"


def _persist_reddit_items(
    *,
    posts: Iterable[RedditPost],
    doc_type: str,
    source_name: str,
    base_url: str,
    default_state: str | None,
    job_type: str | None = None,
) -> dict:
    """存储Reddit帖子数据，包含完整的结构化信息"""
    normalized_doc_type = normalize_doc_type(doc_type)
    inserted = 0
    skipped = 0
    links: List[str] = []
    pending_inserts = 0

    with SessionLocal() as session:
        source = _get_or_create_source(session, source_name, "social", base_url)
        source_id = source.id
        for post in posts:
            link = post.link.strip()
            if not link:
                continue
            links.append(link)
            if job_type:
                _maybe_append_to_resource_pool(link, job_type, {"subreddit": post.subreddit})
            existed = session.query(Document).filter(Document.uri == link).one_or_none()
            if existed:
                skipped += 1
                continue

            # 构建extracted_data，包含Reddit的完整信息
            extracted_data = {
                "platform": "reddit",
                "username": post.username,
                "subreddit": post.subreddit,
                "likes": post.likes,
                "comments": post.comments,
                "text": post.text,
            }

            document = Document(
                source_id=source_id,
                state=default_state,
                doc_type=normalized_doc_type,
                title=post.title,
                summary=post.summary,
                publish_date=post.timestamp.date() if post.timestamp else None,
                uri=link,
                extracted_data=extracted_data,
            )
            session.add(document)
            inserted += 1
            pending_inserts += 1
            if pending_inserts >= BATCH_COMMIT_SIZE:
                session.commit()
                session.expunge_all()
                pending_inserts = 0

        if pending_inserts > 0:
            session.commit()

    return {
        "inserted": inserted,
        "skipped": skipped,
        "links": links,
        "doc_type": normalized_doc_type,
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
    """存储Google News数据"""
    normalized_doc_type = normalize_doc_type(doc_type)
    inserted = 0
    skipped = 0
    links: List[str] = []
    pending_inserts = 0

    with SessionLocal() as session:
        source = _get_or_create_source(session, source_name, "news", base_url)
        source_id = source.id
        for item in items:
            link = item.link.strip()
            if not link:
                continue
            links.append(link)
            if job_type:
                _maybe_append_to_resource_pool(link, job_type, {"keyword": item.keyword})
            existed = session.query(Document).filter(Document.uri == link).one_or_none()
            if existed:
                skipped += 1
                continue

            # 构建extracted_data
            extracted_data = {
                "platform": "google_news",
                "source": item.source,
                "keyword": item.keyword,
            }

            document = Document(
                source_id=source_id,
                state=default_state,
                doc_type=normalized_doc_type,
                title=item.title,
                summary=item.summary,
                publish_date=item.date.date() if item.date else None,
                uri=link,
                extracted_data=extracted_data,
            )
            session.add(document)
            inserted += 1
            pending_inserts += 1
            if pending_inserts >= BATCH_COMMIT_SIZE:
                session.commit()
                session.expunge_all()
                pending_inserts = 0

        if pending_inserts > 0:
            session.commit()

    return {
        "inserted": inserted,
        "skipped": skipped,
        "links": links,
        "doc_type": normalized_doc_type,
    }

