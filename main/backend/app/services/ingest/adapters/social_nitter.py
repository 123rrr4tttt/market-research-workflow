"""Nitter (Twitter替代前端) 数据适配器"""
from __future__ import annotations

import json
import logging
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, List, Optional, TypeGuard
from urllib.parse import quote

from functorial_kit import Failure

from ..retry_policy import RateGate, RequestScope
from .http_utils import HttpFetchError, HttpFetchFailureReason, RequestOutcome, request_html

logger = logging.getLogger(__name__)


def _is_object_dict(value: object) -> TypeGuard[dict[object, object]]:
    return isinstance(value, dict)


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _object_dict(value: object) -> dict[str, object] | None:
    if not _is_object_dict(value):
        return None
    result: dict[str, object] = {}
    for key, item in value.items():
        if isinstance(key, str):
            result[key] = item
    return result


def _string(data: dict[str, object], *keys: str) -> str:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return str(value)
    return ""


def _integer(data: dict[str, object], *keys: str) -> int:
    for key in keys:
        value = data.get(key)
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            try:
                return int(float(value))
            except ValueError:
                continue
    return 0


def _tweet_records(payload: object) -> list[dict[str, object]]:
    root = _object_dict(payload)
    if root is None:
        return []
    raw_tweets = root.get("tweets")
    if not _is_object_list(raw_tweets):
        timeline = _object_dict(root.get("timeline"))
        raw_tweets = timeline.get("tweets") if timeline is not None else None
    if not _is_object_list(raw_tweets):
        return []
    records: list[dict[str, object]] = []
    for value in raw_tweets:
        record = _object_dict(value)
        if record is not None:
            records.append(record)
    return records


@dataclass(slots=True)
class TwitterPost:
    """Twitter/Nitter帖子数据结构"""
    title: str  # 推文内容（作为标题）
    link: str  # 推文链接
    summary: Optional[str] = None  # 推文内容（完整）
    timestamp: Optional[datetime] = None
    username: Optional[str] = None
    likes: int = 0
    retweets: int = 0
    replies: int = 0
    text: Optional[str] = None


class NitterAdapter:
    """Nitter数据适配器 - Twitter的替代前端，无需认证"""
    
    # 常用的Nitter公共实例列表
    DEFAULT_INSTANCES = [
        "https://nitter.net",
        "https://nitter.it",
        "https://nitter.pussthecat.org",
        "https://nitter.privacydev.net",
    ]
    _REQUEST_SCOPE = RequestScope(provider="nitter")
    _RATE_GATE = RateGate(
        rate_limit_interval_seconds=2.0,
        backoff_base_seconds=1.5,
        backoff_max_seconds=60.0,
        sleeper=time.sleep,
    )
    
    def __init__(self, instance_url: Optional[str] = None):
        """
        初始化Nitter适配器
        
        Args:
            instance_url: Nitter实例URL，如果为None则自动选择可用实例
        """
        self.instance_url = instance_url or self.DEFAULT_INSTANCES[0]
        self._tested_instances: List[str] = []
        self.last_failures: tuple[Failure, ...] = ()
    
    def _request_html(self, url: str, headers: dict[str, str], *, timeout: float, retries: int = 3) -> RequestOutcome:
        return request_html(
            url,
            scope=self._REQUEST_SCOPE,
            headers=headers,
            timeout=timeout,
            retries=retries,
            retry_gate=self._RATE_GATE,
        )

    @staticmethod
    def _raise_request_failure(url: str, outcome: RequestOutcome) -> None:
        failure = outcome.failures[-1]
        context = failure.context or {}
        status_value = context.get("status_code")
        status_code = status_value if isinstance(status_value, int) else None
        retryable = context.get("retryable") is True
        raise HttpFetchError(
            failure.message,
            reason=(
                HttpFetchFailureReason.HTTP_STATUS
                if status_code is not None
                else HttpFetchFailureReason.TRANSPORT
            ),
            url=url,
            status_code=status_code,
            retryable=retryable,
        )

    def _get_available_instance(self) -> str:
        """
        获取可用的Nitter实例
        
        Returns:
            可用的实例URL
        """
        # 如果已经测试过当前实例且可用，直接返回
        if self.instance_url in self._tested_instances:
            return self.instance_url
        
        # 测试所有实例，找到第一个可用的
        instances_to_test = [self.instance_url] + [
            inst for inst in self.DEFAULT_INSTANCES if inst != self.instance_url
        ]
        
        for instance in instances_to_test:
            try:
                # 测试实例是否可用（访问主页）
                test_url = f"{instance}/"
                headers = {
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                    "Accept": "text/html,application/xhtml+xml",
                }
                outcome = self._request_html(test_url, headers=headers, timeout=10.0, retries=1)
                self.last_failures = outcome.failures
                response = outcome.response
                if outcome.ok and response is not None and response.status_code == 200:
                    logger.info(f"Nitter instance available: {instance}")
                    self.instance_url = instance
                    self._tested_instances.append(instance)
                    return instance
            except Exception as e:
                logger.debug(f"Nitter instance {instance} not available: {e}")
                continue
        
        # 如果所有实例都不可用，返回默认实例（让调用者处理错误）
        logger.warning(f"All Nitter instances tested, using default: {self.instance_url}")
        return self.instance_url
    
    def fetch_user_tweets(
        self,
        username: str,
        keywords: Optional[List[str]] = None,
        limit: int = 20,
    ) -> Iterable[TwitterPost]:
        """
        获取指定用户的推文
        
        Args:
            username: Twitter用户名（不含@）
            keywords: 可选的关键词列表，用于过滤
            limit: 返回结果数量限制
        """
        try:
            instance = self._get_available_instance()
            
            # 优先尝试JSON格式，如果失败则尝试RSS
            json_url = f"{instance}/{username}.json"
            rss_url = f"{instance}/{username}/rss"
            
            logger.info(f"Fetching tweets from @{username} via Nitter, trying JSON first: {json_url}, keywords: {keywords}")
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept": "application/json,application/rss+xml,application/xml,*/*",
            }
            
            response_text = None
            response = None
            use_json = True
            
            # 先尝试JSON格式
            try:
                outcome = self._request_html(json_url, headers=headers, timeout=15.0)
                self.last_failures = outcome.failures
                response_text = outcome.text
                response = outcome.response
                if (
                    outcome.ok
                    and response is not None
                    and response.status_code == 200
                    and response_text
                ):
                    try:
                        raw_data: object = json.loads(response_text)
                        _tweet_records(raw_data)
                        # 如果成功解析JSON，使用JSON格式
                        logger.info(f"Successfully fetched JSON from Nitter for @{username}")
                    except json.JSONDecodeError:
                        # JSON解析失败，尝试RSS
                        use_json = False
                        logger.info(f"JSON parse failed, trying RSS for @{username}")
                else:
                    use_json = False
            except Exception as e:
                logger.debug(f"JSON request failed for @{username}, trying RSS: {e}")
                use_json = False
            
            # 如果JSON失败，尝试RSS
            if not use_json:
                try:
                    headers["Accept"] = "application/rss+xml,application/xml,text/xml,*/*"
                    outcome = self._request_html(rss_url, headers=headers, timeout=15.0)
                    self.last_failures = outcome.failures
                    response_text = outcome.text
                    response = outcome.response
                    if not outcome.ok:
                        self._raise_request_failure(rss_url, outcome)
                except Exception as e:
                    logger.error(f"Both JSON and RSS requests failed for @{username}: {e}")
                    raise
            
            if not response_text:
                logger.warning(f"Empty response from Nitter for @{username}")
                return []
            
            # 根据格式解析数据
            if use_json:
                try:
                    raw_data = json.loads(response_text)
                    return self._parse_json_tweets(raw_data, username, keywords, limit)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse JSON from Nitter for @{username}: {e}")
                    return []
            else:
                # 解析RSS XML
                try:
                    root = ET.fromstring(response_text)
                    return self._parse_rss_tweets(root, username, keywords, limit)
                except ET.ParseError as e:
                    logger.error(f"Failed to parse RSS XML from Nitter for @{username}: {e}")
                    return []

        except Exception as e:
            logger.error(f"Failed to fetch tweets from Nitter for @{username}: {e}", exc_info=True)
            return []

    def _parse_json_tweets(
        self,
        data: object,
        username: str,
        keywords: Optional[List[str]],
        limit: int,
    ) -> List[TwitterPost]:
        """解析JSON格式的推文数据"""
        posts: list[TwitterPost] = []
        total_posts_before_filter = 0
        filtered_by_keywords = 0
        
        # Nitter JSON格式：通常包含tweets数组
        tweets = _tweet_records(data)
        
        logger.info(f"Nitter JSON returned {len(tweets)} tweets from @{username}")
        
        effective_keywords = []
        if keywords:
            effective_keywords = [kw.lower().strip() for kw in keywords if kw and kw.strip()]
        
        for tweet_data in tweets[:limit * 2]:
            total_posts_before_filter += 1
            
            # 提取推文字段（根据Nitter JSON格式调整）
            text = _string(tweet_data, "text", "tweetText")
            tweet_id = _string(tweet_data, "id", "tweetId")
            date_str = _string(tweet_data, "date", "dateText")
            
            # 构建链接
            link = f"{self.instance_url}/{username}/status/{tweet_id}" if tweet_id else ""
            
            # 关键词过滤
            if effective_keywords:
                text_lower = text.lower()
                normalized_text = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", text_lower))
                
                matched = False
                for kw in effective_keywords:
                    if kw in normalized_text:
                        matched = True
                        break
                
                if not matched:
                    filtered_by_keywords += 1
                    continue
            
            # 解析时间戳
            timestamp = None
            if date_str:
                try:
                    from dateutil import parser as date_parser
                    timestamp = date_parser.parse(date_str)
                except Exception:
                    try:
                        from email.utils import parsedate_to_datetime
                        timestamp = parsedate_to_datetime(date_str)
                    except Exception:
                        pass
            
            # 提取互动数据
            likes = _integer(tweet_data, "likes", "likeCount")
            retweets = _integer(tweet_data, "retweets", "retweetCount")
            replies = _integer(tweet_data, "replies", "replyCount")
            
            post = TwitterPost(
                title=text[:200] if text else "",  # 使用推文前200字符作为标题
                link=link,
                summary=text,
                timestamp=timestamp,
                username=username,
                likes=likes,
                retweets=retweets,
                replies=replies,
                text=text,
            )
            posts.append(post)
            
            if len(posts) >= limit:
                break
        
        logger.info(f"@{username}: total={total_posts_before_filter}, filtered_by_keywords={filtered_by_keywords}, final={len(posts)}")
        return posts
    
    def _parse_rss_tweets(
        self,
        root: ET.Element,
        username: str,
        keywords: Optional[List[str]],
        limit: int,
    ) -> List[TwitterPost]:
        """解析RSS格式的推文数据"""
        posts: list[TwitterPost] = []
        total_posts_before_filter = 0
        filtered_by_keywords = 0
        
        items = root.findall(".//item")
        logger.info(f"Nitter RSS returned {len(items)} tweets from @{username}")
        
        effective_keywords = []
        if keywords:
            effective_keywords = [kw.lower().strip() for kw in keywords if kw and kw.strip()]
        
        for item in items[:limit * 2]:
            total_posts_before_filter += 1
            
            title_elem = item.find("title")
            link_elem = item.find("link")
            description_elem = item.find("description")
            pub_date_elem = item.find("pubDate")
            
            if title_elem is None or link_elem is None:
                continue
            
            title = title_elem.text or ""
            link = link_elem.text or ""
            description = description_elem.text or "" if description_elem is not None else ""
            
            if effective_keywords:
                text_lower = f"{title} {description}".lower()
                normalized_text = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", text_lower))
                
                matched = False
                for kw in effective_keywords:
                    if kw in normalized_text:
                        matched = True
                        break
                
                if not matched:
                    filtered_by_keywords += 1
                    continue
            
            timestamp = None
            if pub_date_elem is not None and pub_date_elem.text:
                try:
                    from email.utils import parsedate_to_datetime
                    timestamp = parsedate_to_datetime(pub_date_elem.text)
                except Exception:
                    pass
            
            username_from_link = username
            if link:
                match = re.search(r"/([^/]+)/status/", link)
                if match:
                    username_from_link = match.group(1)
            
            post = TwitterPost(
                title=title,
                link=link,
                summary=description,
                timestamp=timestamp,
                username=username_from_link,
                likes=0,
                retweets=0,
                replies=0,
                text=description,
            )
            posts.append(post)
            
            if len(posts) >= limit:
                break
        
        logger.info(f"@{username}: total={total_posts_before_filter}, filtered_by_keywords={filtered_by_keywords}, final={len(posts)}")
        return posts
    
    def search_tweets(
        self,
        query: str,
        keywords: Optional[List[str]] = None,
        limit: int = 20,
    ) -> Iterable[TwitterPost]:
        """
        搜索推文
        
        Args:
            query: 搜索查询词
            keywords: 可选的关键词列表，用于进一步过滤
            limit: 返回结果数量限制
        """
        try:
            instance = self._get_available_instance()
            
            # Nitter的搜索RSS接口
            search_url = f"{instance}/search/rss?f=tweets&q={quote(query)}"
            logger.info(f"Searching tweets via Nitter, query: {query}, URL: {search_url}")
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept": "application/rss+xml,application/xml,text/xml,*/*",
            }
            
            try:
                outcome = self._request_html(search_url, headers=headers, timeout=15.0)
                self.last_failures = outcome.failures
                response_text = outcome.text
                if not outcome.ok:
                    self._raise_request_failure(search_url, outcome)
            except Exception as e:
                logger.error(f"HTTP request failed for search '{query}': {e}")
                raise
            
            if not response_text:
                logger.warning(f"Empty response from Nitter search for '{query}'")
                return []
            
            # 解析RSS XML（与fetch_user_tweets类似）
            try:
                root = ET.fromstring(response_text)
            except ET.ParseError as e:
                logger.error(f"Failed to parse RSS XML from Nitter search: {e}")
                return []
            
            posts: list[TwitterPost] = []
            items = root.findall(".//item")
            logger.info(f"Nitter search returned {len(items)} tweets for query '{query}'")
            
            # 关键词过滤（如果提供了额外的关键词）
            effective_keywords = []
            if keywords:
                effective_keywords = [kw.lower().strip() for kw in keywords if kw and kw.strip()]
            
            for item in items[:limit * 2]:
                title_elem = item.find("title")
                link_elem = item.find("link")
                description_elem = item.find("description")
                pub_date_elem = item.find("pubDate")
                
                if title_elem is None or link_elem is None:
                    continue
                
                title = title_elem.text or ""
                link = link_elem.text or ""
                description = description_elem.text or "" if description_elem is not None else ""
                
                # 额外关键词过滤
                if effective_keywords:
                    text_lower = f"{title} {description}".lower()
                    normalized_text = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", text_lower))
                    
                    matched = False
                    for kw in effective_keywords:
                        if kw in normalized_text:
                            matched = True
                            break
                    
                    if not matched:
                        continue
                
                # 解析时间戳
                timestamp = None
                if pub_date_elem is not None and pub_date_elem.text:
                    try:
                        from email.utils import parsedate_to_datetime
                        timestamp = parsedate_to_datetime(pub_date_elem.text)
                    except Exception:
                        pass
                
                # 从链接中提取用户名
                username = None
                if link:
                    match = re.search(r"/([^/]+)/status/", link)
                    if match:
                        username = match.group(1)
                
                post = TwitterPost(
                    title=title,
                    link=link,
                    summary=description,
                    timestamp=timestamp,
                    username=username,
                    likes=0,
                    retweets=0,
                    replies=0,
                    text=description,
                )
                posts.append(post)
                
                if len(posts) >= limit:
                    break
            
            logger.info(f"Search '{query}': final={len(posts)} tweets")
            return posts
            
        except Exception as exc:
            logger.error(f"Nitter search failed for '{query}': {exc}", exc_info=True)
            return []
    
    def search_multiple_queries(
        self,
        queries: List[str],
        keywords: Optional[List[str]] = None,
        limit_per_query: int = 20,
    ) -> Iterable[TwitterPost]:
        """
        搜索多个查询词
        
        Args:
            queries: 查询词列表
            keywords: 可选的关键词列表，用于进一步过滤
            limit_per_query: 每个查询的结果数量限制
        """
        all_posts: List[TwitterPost] = []
        logger.info(f"Searching {len(queries)} queries: {queries}, keywords: {keywords}")
        
        failures: list[Failure] = []
        for query in queries:
            try:
                posts = list(self.search_tweets(query, keywords, limit_per_query))
                logger.info(f"Query '{query}': fetched {len(posts)} tweets")
                all_posts.extend(posts)
                failures.extend(self.last_failures)
            except Exception as exc:
                logger.error(f"Failed to search for '{query}': {exc}", exc_info=True)
                continue
        
        self.last_failures = tuple(failures)
        logger.info(f"Total tweets collected from all queries: {len(all_posts)}")
        return all_posts
