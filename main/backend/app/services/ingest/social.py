"""社交媒体数据摄取任务"""
from __future__ import annotations

import logging
from typing import List, Optional, Protocol, TypeGuard, runtime_checkable

from sqlalchemy.orm import Session
from selectolax.parser import HTMLParser

from ..job_logger import start_job, complete_job, fail_job
from ..collect_runtime.display_meta import build_display_meta
from ..collect_runtime.contracts import CollectRequest, CollectResult
from ..search.candidate_contracts import Candidate
from ...models.base import SessionLocal
from ...models.entities import Document, Source
from .provider_ports import get_reddit_adapter
from ..resource_pool.http_port import fetch_html, make_html_parser
from ..keyword_generation import generate_social_keywords
from .content_cleaner import normalize_content_for_ingest
from .frontdoor_ingress import build_frontdoor_ingress_envelope
from .doc_type_mapper import normalize_doc_type
from .postprocess_frontdoor import run_postprocess_frontdoor
from .keyword_library import (
    store_keywords as store_social_keywords,
    get_keywords as get_social_keywords,
    clean_keywords as clean_social_keywords,
)

logger = logging.getLogger(__name__)
BATCH_COMMIT_SIZE = 100


@runtime_checkable
class _SupportsIntValue(Protocol):
    def __int__(self) -> int: ...


def _is_object_dict(value: object) -> TypeGuard[dict[object, object]]:
    return isinstance(value, dict)


def _as_str_object_dict(value: object) -> dict[str, object]:
    if not _is_object_dict(value):
        # kit:boundary owner=ingest.social_frontdoor.writer_contract class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=ingest.operation.failure witness=test:test_social_frontdoor_writer_shape_guards_preserve_invalid_payload_failures
        raise TypeError("frontdoor writer data requires mapping")
    items: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            # kit:boundary owner=ingest.social_frontdoor.writer_contract class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=ingest.operation.failure witness=test:test_social_frontdoor_writer_shape_guards_preserve_invalid_payload_failures
            raise TypeError("frontdoor writer data requires string keys")
        items[key] = item
    return items


class _PolicyHtmlNode(Protocol):
    def text(self, *, separator: str, strip: bool) -> str: ...


def _find_policy_html_node(parser: HTMLParser, selector: str) -> _PolicyHtmlNode | None:
    return parser.css_first(selector)


def _policy_html_body(parser: HTMLParser) -> _PolicyHtmlNode | None:
    return parser.body


class _ResourcePoolAppendPort(Protocol):
    def append_url(
        self,
        url: str,
        source: str,
        source_ref: dict[str, object],
        *,
        project_key: str,
        job_type: str,
    ) -> None: ...


def _append_resource_pool_url(
    port: _ResourcePoolAppendPort,
    *,
    url: str,
    keyword: str | None,
    project_key: str,
) -> None:
    port.append_url(
        url,
        source="ingest",
        source_ref={"keyword": keyword} if keyword is not None else {},
        project_key=project_key,
        job_type="policy_regulation",
    )


def _required_str(data: dict[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        # kit:boundary owner=ingest.social_frontdoor.writer_contract class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=ingest.operation.failure witness=test:test_social_frontdoor_writer_shape_guards_preserve_invalid_payload_failures
        raise TypeError(f"frontdoor writer data requires string {key}")
    return value


def _optional_str(data: dict[str, object], key: str) -> str | None:
    value = data.get(key)
    if value is None or isinstance(value, str):
        return value
    # kit:boundary owner=ingest.social_frontdoor.writer_contract class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=ingest.operation.failure witness=test:test_social_frontdoor_writer_shape_guards_preserve_invalid_payload_failures
    raise TypeError(f"frontdoor writer data requires optional string {key}")


def _required_str_object_dict(data: dict[str, object], key: str) -> dict[str, object]:
    value = data.get(key)
    if value is None:
        # kit:boundary owner=ingest.social_frontdoor.writer_contract class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=ingest.operation.failure witness=test:test_social_frontdoor_writer_shape_guards_preserve_invalid_payload_failures
        raise TypeError(f"frontdoor writer data requires mapping {key}")
    return _as_str_object_dict(value)


def _as_count(value: object) -> int:
    if not value:
        return 0
    if isinstance(value, str):
        return int(value)
    if isinstance(value, _SupportsIntValue):
        return int(value)
    # kit:boundary owner=ingest.social_frontdoor.writer_contract class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=ingest.operation.failure witness=test:test_social_frontdoor_writer_shape_guards_preserve_invalid_payload_failures
    raise TypeError("frontdoor writer count is not convertible to integer")


def _extract_policy_body_text(html: str) -> str:
    try:
        parser = make_html_parser(html)
        for selector in ("article", "main article", "[role='main'] article", "main"):
            node = _find_policy_html_node(parser, selector)
            if node is None:
                continue
            text = str(node.text(separator="\n", strip=True) or "").strip()
            if len(text) >= 120:
                return normalize_content_for_ingest(text)
        body = _policy_html_body(parser)
        if body is None:
            return ""
        text = str(body.text(separator="\n", strip=True) or "").strip()
        return normalize_content_for_ingest(text)
        return ""
    except Exception:
        return ""


def collect_user_social_sentiment(
    keywords: List[str],
    platforms: Optional[List[str]] = None,
    limit: int = 20,
    enable_extraction: bool = True,
    enable_subreddit_discovery: bool = True,
    base_subreddits: Optional[List[str]] = None,
) -> dict[str, object]:
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
        extraction_ok = 0
        extraction_empty = 0
        extraction_fallback = 0
        
        with SessionLocal() as session:
            # 处理Reddit平台
            if "reddit" in platforms:
                adapter = get_reddit_adapter()
                
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
                _get_or_create_source(session, "Reddit Social Sentiment", "social", "reddit.com")
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
                    
                    ingress_envelope = build_frontdoor_ingress_envelope(
                        ingress_type="discovery",
                        entrypoint="ingest.social_sentiment",
                        source_mode="protocol_search",
                        project_key=None,
                        source_ref={"url": link, "locator": link},
                        collection_payload={
                            "document_candidate": {
                                "source_name": "Reddit Social Sentiment",
                                "source_kind": "social",
                                "source_base_url": "reddit.com",
                                "state": None,
                                "doc_type": normalized_doc_type,
                                "title": post.title,
                                "summary": post.summary,
                                "publish_date": post.timestamp.date() if post.timestamp else None,
                                "content": post.text or post.summary,
                                "text_hash": None,
                                "uri": link,
                                "status": None,
                                "extracted_data_base": extracted_data,
                            },
                            "terminal_context": {
                                "platform": "reddit",
                                "ingestion_entrypoint": "ingest.social_sentiment",
                                "source_mode": "protocol_search",
                                "quality_score": 0.0,
                                "degradation_flags": [],
                                "http_status": None,
                                "capability_profile": {},
                                "light_filter": {},
                            },
                            "extraction_plan": {
                                "enabled": bool(enable_extraction),
                                "include_market": False,
                                "include_policy": False,
                                "include_sentiment": True,
                                "include_company": True,
                                "include_product": True,
                                "include_operation": True,
                            },
                        },
                        raw_snapshot={"link": link, "title": post.title, "subreddit": post.subreddit},
                    )
                    frontdoor_result = run_postprocess_frontdoor(
                        ingress_envelope=ingress_envelope,
                        run_writer=True,
                    )
                    result_data = frontdoor_result.get("data")
                    writer_result: object = result_data.get("writer_result") if _is_object_dict(result_data) else None
                    normalized_result: object = result_data.get("normalized_payload") if _is_object_dict(result_data) else None
                    extracted: object = normalized_result.get("extracted_data") if _is_object_dict(normalized_result) else None
                    structured_status_value = extracted.get("structured_extraction_status") if _is_object_dict(extracted) else None
                    structured_status = str(structured_status_value or "skipped").strip().lower()
                    if structured_status == "ok":
                        extraction_ok += 1
                    elif structured_status == "failed":
                        extraction_empty += 1
                    else:
                        extraction_fallback += 1
                    if _is_object_dict(writer_result):
                        inserted += _as_count(writer_result.get("inserted"))
                        skipped += _as_count(writer_result.get("skipped"))

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
        
        result: dict[str, object] = {
            "inserted": inserted,
            "skipped": skipped,
            "links": links,
            "doc_type": normalized_doc_type,
            "extraction_stats": {
                "enabled": bool(enable_extraction),
                "ok": extraction_ok,
                "empty": extraction_empty,
                "fallback": extraction_fallback,
            },
        }
        logger.info(f"Social sentiment collection completed: inserted={inserted}, skipped={skipped}, links_count={len(links)}")
        complete_job(job_id, result=result)
        return result
        
    except Exception as exc:  # noqa: BLE001
        logger.exception("collect_user_social_sentiment failed")
        fail_job(job_id, str(exc))
        # kit:boundary owner=ingest.social_sentiment class=SHELL_BOUNDARY_EXCEPTION failure_family=ingest.operation.failure witness=test:test_latest_service_a_ingest_shell_boundaries_reraise_original_errors
        raise


def collect_policy_and_regulation(
    keywords: List[str],
    limit: int = 20,
    enable_extraction: bool = True,
    provider: str = "google",
    start_offset: int | None = None,
    days_back: int | None = None,
    language: str = "en",
    project_key: str | None = None,
) -> dict[str, object]:
    """
    收集政策法规相关新闻，通过搜索 API（默认 Google Custom Search）。

    Args:
        keywords: 搜索关键词列表
        limit: 结果数量限制
        enable_extraction: 是否启用LLM结构化提取
        provider: 搜索服务，默认 google（Google Custom Search）
    """
    from ..projects import current_project_key
    from ..search.candidate_contracts import CandidateSearchRequest
    from ..search.facets import POLICY_FACET
    from .search_and_ingest import (
        SearchAndIngestSpec,
        SearchIngestPorts,
        SearchIngestSource,
        SearchIngestTarget,
        run_search_and_ingest,
    )
    from .url_pool import collect_urls_from_list

    job_id = start_job(
        "policy_regulation",
        {"keywords": keywords, "limit": limit, "provider": provider},
    )

    try:
        normalized_doc_type = normalize_doc_type("policy_regulation")
        effective_project = (project_key or current_project_key() or "").strip() or None
        request = CandidateSearchRequest(
            topic=" ".join(keywords),
            keywords=tuple(keywords),
            max_results=limit,
            provider=provider,
            exclude_existing=False,
            start_offset=start_offset,
            days_back=days_back,
            language=language,
            project_ref=effective_project,
            source_ref="policy",
        )
        spec = SearchAndIngestSpec(
            facet=POLICY_FACET,
            request=request,
            project_key=effective_project,
            target=SearchIngestTarget(
                doc_type=normalized_doc_type,
                extraction_enabled=bool(enable_extraction),
                extraction_flags={
                    "include_market": False,
                    "include_policy": True,
                    "include_sentiment": False,
                    "include_company": True,
                    "include_product": True,
                    "include_operation": True,
                },
            ),
            source=SearchIngestSource(
                name="Search API Policy",
                kind="search",
                base_url="search",
                entrypoint="ingest.policy_regulation",
            ),
            missing_body="route",
            retention="resource_pool" if effective_project else "none",
            legacy_projectless=effective_project is None,
            legacy_payload_shape=True,
        )

        def fetch_body(link: str) -> str | None:
            html, _ = fetch_html(link, timeout=8.0, retries=1)
            return _extract_policy_body_text(html).strip()

        def retain_candidate(candidate: Candidate) -> None:
            if effective_project:
                from ..resource_pool import DefaultResourcePoolAppendAdapter

                _append_resource_pool_url(
                    DefaultResourcePoolAppendAdapter(),
                    url=candidate.resource_uri,
                    keyword=candidate.keyword,
                    project_key=effective_project,
                )

        def write_frontdoor(data: dict[str, object]) -> dict[str, object]:
            ingress_envelope = build_frontdoor_ingress_envelope(
                ingress_type="discovery",
                entrypoint=_required_str(data, "entrypoint"),
                source_mode=_required_str(data, "source_mode"),
                project_key=_optional_str(data, "project_key"),
                source_ref=_required_str_object_dict(data, "source_ref"),
                collection_payload=_required_str_object_dict(data, "collection_payload"),
                raw_snapshot=_required_str_object_dict(data, "raw_snapshot"),
            )
            frontdoor_result = run_postprocess_frontdoor(
                ingress_envelope=ingress_envelope,
                run_writer=True,
            )
            body = frontdoor_result.get("data")
            if _is_object_dict(body):
                writer_result = body.get("writer_result")
                if _is_object_dict(writer_result):
                    return _as_str_object_dict(writer_result)
            return {}

        def route_missing(urls: list[str]) -> dict[str, object]:
            routed: object = collect_urls_from_list(
                urls,
                project_key=effective_project,
                query_terms=list(keywords or []),
                extra_params={
                    "dispatch_mode": "inline",
                    "front_door_owner": "ingest.policy_regulation",
                    "frontdoor_route_decision": "front_door_url_routing",
                    "frontdoor_write_mode": "front_door_url_routing",
                    "frontdoor_execution_mode": "url_routing",
                },
                enable_extraction=enable_extraction,
            )
            if _is_object_dict(routed):
                return _as_str_object_dict(routed)
            return {}

        with SessionLocal() as session:
            _get_or_create_source(session, "Search API Policy", "search", "search")

            collection = run_search_and_ingest(
                spec,
                SearchIngestPorts(
                    exists=lambda link: session.query(Document).filter(Document.uri == link).first() is not None,
                    fetch_text=fetch_body,
                    write=write_frontdoor,
                    route_missing=route_missing,
                    retain=retain_candidate if effective_project else None,
                ),
            )

        inserted = collection.inserted
        skipped = collection.skipped
        links = list(collection.links)

        logger.info(
            "Policy regulation collection fetched=%d inserted=%d skipped=%d",
            len(collection.bundle.candidates),
            inserted,
            skipped,
        )

        result: dict[str, object] = {
            "inserted": inserted,
            "skipped": skipped,
            "links": links,
            "doc_type": normalized_doc_type,
        }
        result["display_meta"] = build_display_meta(
            CollectRequest(
                channel="search.policy",
                project_key=effective_project,
                query_terms=list(keywords or []),
                limit=limit,
                provider=provider,
                language=language,
                source_context={"summary": "法规来源"},
            ),
            CollectResult(
                channel="search.policy",
                inserted=inserted,
                skipped=skipped,
                updated=0,
                status="completed",
            ),
            summary="法规来源",
        )
        complete_job(job_id, result=result)
        return result

    except Exception as exc:
        logger.exception("collect_policy_and_regulation failed")
        fail_job(job_id, str(exc))
        # kit:boundary owner=ingest.policy_regulation class=SHELL_BOUNDARY_EXCEPTION failure_family=ingest.operation.failure witness=test:test_latest_service_a_ingest_shell_boundaries_reraise_original_errors
        raise


def _get_or_create_source(session: Session, name: str, kind: str, base_url: str) -> Source:
    """获取或创建Source"""

    # 使用first()而不是one_or_none()，避免重复记录导致的错误
    source = (
        session.query(Source)
        .filter(Source.name == name, Source.kind == kind)
        .first()
    )
    if source:
        return source
    
    source = Source(**{"name": name, "kind": kind, "base_url": base_url})
    session.add(source)
    session.flush()
    return source
