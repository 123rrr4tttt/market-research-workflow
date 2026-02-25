"""社交媒体数据摄取任务"""
from __future__ import annotations

import logging
from typing import List, Optional

from sqlalchemy.orm import Session

from ..job_logger import start_job, complete_job, fail_job
from ...models.base import SessionLocal
from ...models.entities import Document
from .adapters.social_reddit import RedditAdapter
from ..llm.extraction import extract_structured_sentiment, extract_policy_info
from ..keyword_generation import generate_social_keywords
from .doc_type_mapper import normalize_doc_type
from .keyword_library import (
    store_keywords as store_social_keywords,
    get_keywords as get_social_keywords,
    clean_keywords as clean_social_keywords,
)

logger = logging.getLogger(__name__)
BATCH_COMMIT_SIZE = 100


def collect_user_social_sentiment(
    keywords: List[str],
    platforms: Optional[List[str]] = None,
    limit: int = 20,
    enable_extraction: bool = True,
    enable_subreddit_discovery: bool = True,
    base_subreddits: Optional[List[str]] = None,
) -> dict:
    """
    收集用户社交媒体情感数据
    
    Args:
        keywords: 搜索关键词列表
        platforms: 平台列表（目前只支持"reddit"）
        limit: 每个关键词的结果数量限制
        enable_extraction: 是否启用LLM结构化提取
        enable_subreddit_discovery: 是否启用子论坛发现功能（默认True）
        base_subreddits: 基础子论坛列表（如果为None，使用默认列表）
        
    Returns:
        包含插入和跳过数量的字典
    """
    platforms = platforms or ["reddit"]
    job_id = start_job(
        "social_sentiment",
        {"keywords": keywords, "platforms": platforms, "limit": limit, "enable_subreddit_discovery": enable_subreddit_discovery},
    )
    
    try:
        normalized_doc_type = normalize_doc_type("social_sentiment")
        inserted = 0
        skipped = 0
        links: List[str] = []
        fetched_posts = 0
        pending_inserts = 0
        
        with SessionLocal() as session:
            # 处理Reddit平台
            if "reddit" in platforms:
                adapter = RedditAdapter()
                
                # 基础子论坛列表（默认值）
                if base_subreddits is None:
                    base_subreddits = ["economics", "stocks", "investing", "supplychain"]
                
                # 子论坛列表（将用于搜索）
                subreddits = list(base_subreddits)  # 复制列表，避免修改原始列表
                
                # 如果启用了子论坛发现且有关键词，先发现相关子论坛
                if enable_subreddit_discovery and keywords and len(keywords) > 0:
                    logger.info(f"Discovering subreddits for keywords: {keywords}")
                    try:
                        # 步骤1: 使用LLM生成搜索关键词和子论坛关键词（一次调用）
                        # 从关键词中提取主题（使用第一个关键词或合并）
                        topic = " ".join(keywords[:3])  # 使用前3个关键词作为主题
                        logger.info(f"Generating combined keywords for topic: {topic}")
                        
                        try:
                            # 调用合并的关键词生成函数，一次生成两种关键词
                            keyword_result = generate_social_keywords(
                                topic=topic,
                                language="en",  # Reddit子论坛通常使用英文
                                platform="reddit",
                                base_keywords=keywords,  # 使用原始关键词作为基础
                                return_combined=True,  # 返回合并格式
                            )
                            
                            # 从返回结果中提取两种关键词
                            if isinstance(keyword_result, dict):
                                search_keywords = keyword_result.get("search_keywords", keywords)
                                subreddit_keywords = keyword_result.get("subreddit_keywords", [])
                                logger.info(f"Generated {len(search_keywords)} search keywords and {len(subreddit_keywords)} subreddit keywords")
                            else:
                                # 向后兼容：如果返回的是列表，使用原始逻辑
                                logger.warning("Keyword generation returned list instead of dict, using original keywords")
                                search_keywords = keywords
                                subreddit_keywords = []
                            
                            # 如果没有生成子论坛关键词，使用原始关键词
                            if not subreddit_keywords:
                                logger.warning("No subreddit keywords generated, using original keywords for discovery")
                                subreddit_keywords = keywords
                            
                            # 更新搜索关键词（用于后续搜索帖子）
                            if search_keywords:
                                search_keywords = list(search_keywords) + [kw for kw in keywords if kw not in search_keywords]
                        except Exception as e:
                            logger.warning(f"Failed to generate combined keywords, using original keywords: {e}")
                            search_keywords = keywords
                            subreddit_keywords = keywords
                        
                        # 步骤2: 使用子论坛关键词发现子论坛
                        discovered_subreddits = adapter.discover_subreddits(
                            keywords=subreddit_keywords,
                            max_results=15,  # 最多发现15个新子论坛
                            min_subscribers=100,  # 最小订阅者数量
                        )
                        
                        # 步骤3: 更新搜索关键词（用于后续搜索帖子）
                        keywords = search_keywords
                        
                        if discovered_subreddits:
                            # 合并发现的子论坛（去重）
                            for subreddit in discovered_subreddits:
                                if subreddit not in subreddits:
                                    subreddits.append(subreddit)
                            
                            logger.info(f"Subreddit discovery completed. Total subreddits: {len(subreddits)} (base: {len(base_subreddits)}, discovered: {len(discovered_subreddits)})")
                        else:
                            logger.warning("No subreddits discovered, using base subreddits only")
                    except Exception as e:
                        logger.warning(f"Subreddit discovery failed, using base subreddits only: {e}")
                        # 继续使用基础子论坛列表
                
                # 使用关键词库统一管理过滤关键词
                if keywords:
                    stored_keywords = store_social_keywords("reddit", keywords)
                    if stored_keywords:
                        logger.debug("Stored %d keywords into reddit keyword library", len(stored_keywords))

                library_keywords = get_social_keywords("reddit")
                if library_keywords:
                    search_keywords = library_keywords
                else:
                    search_keywords = clean_social_keywords(keywords or [])
                source = _get_or_create_source(session, "Reddit Social Sentiment", "social", "reddit.com")
                source_id = source.id

                for post in adapter.search_multiple_subreddits(subreddits, search_keywords, limit):
                    fetched_posts += 1
                    link = post.link.strip()
                    if not link:
                        logger.warning(f"Skipping post with empty link: {post.title[:50] if post.title else 'No title'}")
                        continue
                    
                    links.append(link)
                    logger.debug(f"Added link to list: {link}")
                    
                    # 检查是否已存在（使用first()避免重复记录错误）
                    existed = session.query(Document).filter(Document.uri == link).first()
                    if existed:
                        skipped += 1
                        continue
 
                    has_text = bool(post.text and post.text.strip())
                    has_summary = bool(post.summary and post.summary.strip())
                    if not (has_text or has_summary):
                        skipped += 1
                        logger.debug("Skipping post without body content: %s", post.title[:50] if post.title else "No title")
                        continue

                    # 提取结构化情感信息
                    extracted_data = {
                        "platform": "reddit",
                        "username": post.username,
                        "subreddit": post.subreddit,
                        "likes": post.likes,
                        "comments": post.comments,
                        "text": post.text,
                    }
                    
                    if enable_extraction:
                        sentiment_info = extract_structured_sentiment(post.text)
                        if sentiment_info:
                            extracted_data["sentiment"] = sentiment_info
                            
                            # 从sentiment中提取keywords（使用key_phrases作为关键词）
                            if sentiment_info.get("key_phrases"):
                                extracted_data["keywords"] = sentiment_info["key_phrases"]
                        
                        # 提取实体和关系（用于图谱构建）
                        from ..extraction.extract import extract_entities_relations
                        er_data = extract_entities_relations(post.text)
                        if er_data and er_data.get("entities"):
                            extracted_data["entities"] = er_data["entities"]
                    
                    document = Document(
                        source_id=source_id,
                        state=None,
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

                logger.info(
                    "Found %d Reddit posts for keywords: %s (searched with: %s)",
                    fetched_posts,
                    keywords,
                    search_keywords,
                )
                if fetched_posts == 0:
                    logger.warning("No posts found after filtering. This could mean:")
                    logger.warning("  1. Reddit API returned no data")
                    logger.warning("  2. All posts were filtered by keywords: %s", keywords)
                    logger.warning("  3. API request failed")

            if pending_inserts > 0:
                session.commit()
        
        result = {
            "inserted": inserted,
            "skipped": skipped,
            "links": links,
            "doc_type": normalized_doc_type,
        }
        logger.info(f"Social sentiment collection completed: inserted={inserted}, skipped={skipped}, links_count={len(links)}")
        complete_job(job_id, result=result)
        return result
        
    except Exception as exc:  # noqa: BLE001
        logger.exception("collect_user_social_sentiment failed")
        fail_job(job_id, str(exc))
        raise


def collect_policy_and_regulation(
    keywords: List[str],
    limit: int = 20,
    enable_extraction: bool = True,
    provider: str = "google",
    start_offset: int | None = None,
    days_back: int | None = None,
    language: str = "en",
) -> dict:
    """
    收集政策法规相关新闻，通过搜索 API（默认 Google Custom Search）。

    Args:
        keywords: 搜索关键词列表
        limit: 结果数量限制
        enable_extraction: 是否启用LLM结构化提取
        provider: 搜索服务，默认 google（Google Custom Search）
    """
    from ..search.web import search_sources

    job_id = start_job(
        "policy_regulation",
        {"keywords": keywords, "limit": limit, "provider": provider},
    )

    try:
        normalized_doc_type = normalize_doc_type("policy_regulation")
        results = search_sources(
            topic=" ".join(keywords),
            max_results=limit,
            provider=provider,
            exclude_existing=False,
            keywords=keywords,
            start_offset=start_offset,
            days_back=days_back,
            language=language,
        )

        inserted = 0
        skipped = 0
        links: List[str] = []
        pending_inserts = 0

        with SessionLocal() as session:
            source = _get_or_create_source(session, "Search API Policy", "search", "search")
            source_id = source.id

            for item in results:
                link = (item.get("link") or "").strip()
                if not link:
                    continue
                links.append(link)

                existed = session.query(Document).filter(Document.uri == link).first()
                if existed:
                    skipped += 1
                    continue

                title = item.get("title") or ""
                snippet = item.get("snippet") or ""

                extracted_data = {
                    "platform": item.get("source") or provider,
                    "keyword": item.get("keyword"),
                }
                if enable_extraction:
                    text_to_extract = f"{title}\n\n{snippet}"
                    policy_info = extract_policy_info(text_to_extract)
                    if policy_info:
                        extracted_data["policy"] = policy_info

                document = Document(
                    source_id=source_id,
                    state=None,
                    doc_type=normalized_doc_type,
                    title=title,
                    summary=snippet,
                    publish_date=None,
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

        logger.info(
            "Policy regulation collection fetched=%d inserted=%d skipped=%d",
            len(results),
            inserted,
            skipped,
        )

        result = {
            "inserted": inserted,
            "skipped": skipped,
            "links": links,
            "doc_type": normalized_doc_type,
        }
        complete_job(job_id, result=result)
        return result

    except Exception as exc:
        logger.exception("collect_policy_and_regulation failed")
        fail_job(job_id, str(exc))
        raise


def _get_or_create_source(session: Session, name: str, kind: str, base_url: str):
    """获取或创建Source"""
    from ...models.entities import Source
    
    # 使用first()而不是one_or_none()，避免重复记录导致的错误
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

