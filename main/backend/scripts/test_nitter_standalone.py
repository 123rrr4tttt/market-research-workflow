#!/usr/bin/env python3
"""独立测试Nitter适配器（不依赖项目结构）"""
import sys
import os
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, List, Optional
from urllib.parse import quote
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import requests

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


@dataclass
class TwitterPost:
    """Twitter/Nitter帖子数据结构"""
    title: str
    link: str
    summary: Optional[str] = None
    timestamp: Optional[datetime] = None
    username: Optional[str] = None
    likes: int = 0
    retweets: int = 0
    replies: int = 0
    text: Optional[str] = None


class NitterAdapter:
    """Nitter数据适配器 - Twitter的替代前端，无需认证"""
    
    DEFAULT_INSTANCES = [
        "https://nitter.net",
        "https://nitter.it",
        "https://nitter.pussthecat.org",
        "https://nitter.privacydev.net",
    ]
    
    def __init__(self, instance_url: Optional[str] = None):
        self.instance_url = instance_url or self.DEFAULT_INSTANCES[0]
        self._tested_instances: List[str] = []
    
    def _get_available_instance(self) -> str:
        """获取可用的Nitter实例"""
        if self.instance_url in self._tested_instances:
            return self.instance_url
        
        instances_to_test = [self.instance_url] + [
            inst for inst in self.DEFAULT_INSTANCES if inst != self.instance_url
        ]
        
        for instance in instances_to_test:
            try:
                test_url = f"{instance}/"
                headers = {
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                    "Accept": "text/html,application/xhtml+xml",
                }
                response = requests.get(test_url, headers=headers, timeout=10.0)
                
                if response.status_code == 200:
                    logger.info(f"Nitter instance available: {instance}")
                    self.instance_url = instance
                    self._tested_instances.append(instance)
                    return instance
            except Exception as e:
                logger.debug(f"Nitter instance {instance} not available: {e}")
                continue
        
        logger.warning(f"All Nitter instances tested, using default: {self.instance_url}")
        return self.instance_url
    
    def fetch_user_tweets(
        self,
        username: str,
        keywords: Optional[List[str]] = None,
        limit: int = 20,
    ) -> Iterable[TwitterPost]:
        """获取指定用户的推文"""
        try:
            instance = self._get_available_instance()
            rss_url = f"{instance}/{username}/rss"
            logger.info(f"Fetching tweets from @{username} via Nitter, URL: {rss_url}")
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept": "application/rss+xml,application/xml,text/xml,*/*",
            }
            
            try:
                response = requests.get(rss_url, headers=headers, timeout=15.0)
                response.raise_for_status()
                response_text = response.text
            except Exception as e:
                logger.error(f"HTTP request failed for @{username}: {e}")
                raise
            
            if not response_text:
                logger.warning(f"Empty response from Nitter RSS for @{username}")
                return []
            
            # 调试：打印响应内容的前500字符
            logger.debug(f"Response content type: {response.headers.get('Content-Type', 'unknown')}")
            logger.debug(f"Response preview: {response_text[:500]}")
            
            try:
                root = ET.fromstring(response_text)
            except ET.ParseError as e:
                logger.error(f"Failed to parse RSS XML from Nitter for @{username}: {e}")
                return []
            
            posts = []
            items = root.findall(".//item")
            logger.info(f"Nitter RSS returned {len(items)} tweets from @{username}")
            
            effective_keywords = []
            if keywords:
                effective_keywords = [kw.lower().strip() for kw in keywords if kw and kw.strip()]
            
            for item in items[:limit * 2]:
                title_elem = item.find("title")
                link_elem = item.find("link")
                description_elem = item.find("description")
                pub_date_elem = item.find("pubDate")
                
                if not title_elem or not link_elem:
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
                        continue
                
                timestamp = None
                if pub_date_elem is not None and pub_date_elem.text:
                    try:
                        timestamp = parsedate_to_datetime(pub_date_elem.text)
                    except Exception as e:
                        logger.debug(f"Failed to parse RSS date {pub_date_elem.text}: {e}")
                
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
            
            logger.info(f"@{username}: final={len(posts)} tweets")
            return posts
            
        except Exception as exc:
            logger.error(f"Nitter fetch failed for @{username}: {exc}", exc_info=True)
            return []
    
    def search_tweets(
        self,
        query: str,
        keywords: Optional[List[str]] = None,
        limit: int = 20,
    ) -> Iterable[TwitterPost]:
        """搜索推文"""
        try:
            instance = self._get_available_instance()
            search_url = f"{instance}/search/rss?f=tweets&q={quote(query)}"
            logger.info(f"Searching tweets via Nitter, query: {query}, URL: {search_url}")
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept": "application/rss+xml,application/xml,text/xml,*/*",
            }
            
            try:
                response = requests.get(search_url, headers=headers, timeout=15.0)
                response.raise_for_status()
                response_text = response.text
            except Exception as e:
                logger.error(f"HTTP request failed for search '{query}': {e}")
                raise
            
            if not response_text:
                logger.warning(f"Empty response from Nitter search for '{query}'")
                return []
            
            try:
                root = ET.fromstring(response_text)
            except ET.ParseError as e:
                logger.error(f"Failed to parse RSS XML from Nitter search: {e}")
                return []
            
            posts = []
            items = root.findall(".//item")
            logger.info(f"Nitter search returned {len(items)} tweets for query '{query}'")
            
            effective_keywords = []
            if keywords:
                effective_keywords = [kw.lower().strip() for kw in keywords if kw and kw.strip()]
            
            for item in items[:limit * 2]:
                title_elem = item.find("title")
                link_elem = item.find("link")
                description_elem = item.find("description")
                pub_date_elem = item.find("pubDate")
                
                if not title_elem or not link_elem:
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
                        continue
                
                timestamp = None
                if pub_date_elem is not None and pub_date_elem.text:
                    try:
                        timestamp = parsedate_to_datetime(pub_date_elem.text)
                    except Exception:
                        pass
                
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


def test_nitter_instance():
    """测试Nitter实例可用性"""
    print("=" * 60)
    print("测试1: Nitter实例可用性")
    print("=" * 60)
    
    adapter = NitterAdapter()
    instance = adapter._get_available_instance()
    print(f"✓ 可用实例: {instance}")
    print()


def test_user_tweets():
    """测试获取用户推文"""
    print("=" * 60)
    print("测试2: 获取用户推文")
    print("=" * 60)
    
    adapter = NitterAdapter()
    
    # 测试几个知名账号
    test_usernames = ["elonmusk", "jack"]
    
    for username in test_usernames:
        print(f"\n测试用户: @{username}")
        try:
            posts = list(adapter.fetch_user_tweets(username, limit=3))
            print(f"  获取到 {len(posts)} 条推文")
            
            if posts:
                print(f"  第一条推文:")
                post = posts[0]
                print(f"    标题: {post.title[:100]}")
                print(f"    链接: {post.link}")
                print(f"    时间: {post.timestamp}")
                print(f"    用户名: {post.username}")
        except Exception as e:
            print(f"  ✗ 错误: {e}")
            import traceback
            traceback.print_exc()
    
    print()


def test_search():
    """测试搜索功能"""
    print("=" * 60)
    print("测试3: 搜索推文")
    print("=" * 60)
    
    adapter = NitterAdapter()
    
    test_queries = ["lottery", "Powerball"]
    
    for query in test_queries:
        print(f"\n搜索查询: {query}")
        try:
            posts = list(adapter.search_tweets(query, limit=3))
            print(f"  获取到 {len(posts)} 条推文")
            
            if posts:
                print(f"  第一条推文:")
                post = posts[0]
                print(f"    标题: {post.title[:100]}")
                print(f"    链接: {post.link}")
                print(f"    时间: {post.timestamp}")
                print(f"    用户名: {post.username}")
        except Exception as e:
            print(f"  ✗ 错误: {e}")
            import traceback
            traceback.print_exc()
    
    print()


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("Nitter适配器测试（独立版本）")
    print("=" * 60 + "\n")
    
    try:
        test_nitter_instance()
        test_user_tweets()
        test_search()
        
        print("=" * 60)
        print("所有测试完成！")
        print("=" * 60)
        
    except Exception as e:
        logger.exception("测试失败")
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

