from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, List

from sqlalchemy.orm import Session

from ..job_logger import start_job, complete_job, fail_job
from ...models.base import SessionLocal
from ...models.entities import Document, Source
from .adapters.http_utils import fetch_html, make_html_parser
from ..http.client import default_http_client
from ...settings.config import settings


logger = logging.getLogger(__name__)

CALOTTERY_NEWS_URL = "https://www.calottery.com/news-releases"
CALOTTERY_RETAILER_URL = "https://www.calottery.com/retailer/retailer-news"


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
        )
        complete_job(job_id, result=result)
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("collect_calottery_retailer_updates failed")
        fail_job(job_id, str(exc))
        raise


def collect_reddit_discussions(subreddit: str = "Lottery", limit: int = 20) -> dict:
    job_id = start_job("reddit_discussions", {"subreddit": subreddit, "limit": limit})
    try:
        headers = {"User-Agent": settings.reddit_user_agent or "LotteryIntelBot/0.1"}
        url = f"https://www.reddit.com/r/{subreddit}/new.json"
        payload = default_http_client.get_json(url, params={"limit": str(limit)}, headers=headers)
        items = _parse_reddit_payload(payload)
        result = _persist_news_items(
            items=items,
            doc_type="social_feed",
            source_name=f"Reddit r/{subreddit}",
            base_url="reddit.com",
            default_state="CA",
            kind="social",
        )
        complete_job(job_id, result=result)
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("collect_reddit_discussions failed")
        fail_job(job_id, str(exc))
        raise


def _persist_news_items(
    *,
    items: Iterable[NewsItem],
    doc_type: str,
    source_name: str,
    base_url: str,
    default_state: str | None,
    kind: str = "news",
) -> dict:
    inserted = 0
    skipped = 0
    links: List[str] = []

    with SessionLocal() as session:
        source = _get_or_create_source(session, source_name, kind, base_url)
        for item in items:
            link = item.link.strip()
            if not link:
                continue
            links.append(link)
            existed = session.query(Document).filter(Document.uri == link).one_or_none()
            if existed:
                skipped += 1
                continue

            document = Document(
                source_id=source.id,
                state=default_state,
                doc_type=doc_type,
                title=item.title,
                summary=item.summary,
                publish_date=item.published_at.date() if item.published_at else None,
                uri=link,
            )
            session.add(document)
            inserted += 1

        session.commit()

    return {
        "inserted": inserted,
        "skipped": skipped,
        "links": links,
        "doc_type": doc_type,
    }


def _get_or_create_source(session: Session, name: str, kind: str, base_url: str) -> Source:
    source = (
        session.query(Source)
        .filter(Source.name == name, Source.kind == kind)
        .one_or_none()
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


def _parse_reddit_payload(payload: object) -> List[NewsItem]:
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


