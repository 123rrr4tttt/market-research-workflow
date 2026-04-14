"""Reddit数据适配器"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, List, Optional
from urllib.parse import quote

from .http_utils import fetch_html
from ..keyword_library import (
    clean_keywords,
    get_keywords as get_library_keywords,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RedditPost:
    """Reddit帖子数据结构"""
    title: str
    link: str
    summary: Optional[str] = None
    timestamp: Optional[datetime] = None
    username: Optional[str] = None
    subreddit: Optional[str] = None
    likes: int = 0
    comments: int = 0
    text: Optional[str] = None


class RedditAdapter:
    """Reddit数据适配器"""
    
    def __init__(self):
        self.base_url = "https://www.reddit.com"
    
    def fetch_posts(
        self,
        subreddit: str,
        keywords: Optional[List[str]] = None,
        limit: int = 20,
    ) -> Iterable[RedditPost]:
        """
        获取Reddit子论坛的帖子
        
        Args:
            subreddit: 子论坛名称
            keywords: 可选的关键词列表，用于过滤
            limit: 返回结果数量限制
        """
        try:
            # Reddit的JSON API（不需要认证，但有速率限制）
            # 使用真实的浏览器User-Agent可以避免403错误
            url = f"{self.base_url}/r/{subreddit}/hot.json?limit={limit}"
            logger.info(f"Fetching Reddit posts from r/{subreddit}, URL: {url}, keywords: {keywords}")
            
            # 使用简单的浏览器 User-Agent（curl 测试证明这样可以工作）
            # 如果配置了自定义 User-Agent，优先使用
            from ....settings.config import settings
            reddit_user_agent = settings.reddit_user_agent
            if reddit_user_agent:
                user_agent = reddit_user_agent
            else:
                # 使用与 curl 测试相同的简单浏览器 User-Agent
                user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            
            # 使用更完整的浏览器headers，避免被Reddit识别为机器人
            headers = {
                "User-Agent": user_agent,
                "Accept": "application/json",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
                "Referer": "https://www.reddit.com/",
            }
            logger.debug(f"Requesting Reddit API with headers: User-Agent={headers['User-Agent'][:50]}...")
            try:
                response_text, response = fetch_html(url, headers=headers)
            except Exception as e:
                logger.error(f"HTTP request failed for r/{subreddit}: {e}")
                # 如果请求失败，记录响应状态码（如果有）
                if hasattr(e, 'response') and e.response is not None:
                    logger.error(f"Response status: {e.response.status_code}")
                    logger.error(f"Response headers: {dict(e.response.headers)}")
                raise
            
            if not response_text:
                logger.warning(f"Empty response from Reddit API for r/{subreddit}")
                return []
            
            import json
            try:
                data = json.loads(response_text)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON from Reddit API for r/{subreddit}: {e}, response preview: {response_text[:200]}")
                return []
            
            total_posts_before_filter = 0
            filtered_by_keywords = 0
            emitted_posts = 0
            
            if "data" in data and "children" in data["data"]:
                children = data["data"]["children"]
                logger.info(f"Reddit API returned {len(children)} posts from r/{subreddit}")

                cleaned_input_keywords = clean_keywords(keywords or [])
                library_keywords = get_library_keywords("reddit")
                deduped_keywords = []
                seen_keywords = set()
                for kw in cleaned_input_keywords + library_keywords:
                    if kw and kw not in seen_keywords:
                        seen_keywords.add(kw)
                        deduped_keywords.append(kw)

                effective_keywords = deduped_keywords
                if not effective_keywords:
                    # Fallback to unfiltered mode when no domain keywords are configured.
                    logger.debug("No effective keywords for subreddit %s; use unfiltered mode", subreddit)
                    effective_keywords = None
                else:
                    logger.debug("Effective keywords for subreddit %s: %s", subreddit, effective_keywords)
                
                for child in children[:limit]:
                    post_data = child.get("data", {})
                    total_posts_before_filter += 1
                    
                    # 提取帖子信息
                    title = post_data.get("title", "")
                    permalink = post_data.get("permalink", "")
                    # 确保 permalink 存在且不为空
                    if permalink:
                        link = f"{self.base_url}{permalink}"
                    else:
                        # 如果没有 permalink，尝试使用 id 构建链接
                        post_id = post_data.get("id", "")
                        if post_id:
                            link = f"{self.base_url}/r/{subreddit}/comments/{post_id}/"
                        else:
                            logger.warning(f"Reddit post missing both permalink and id: {title[:50]}")
                            link = ""
                    
                    # 检查关键词过滤
                    # If keywords are available, apply filtering; otherwise keep all posts.
                    if effective_keywords:
                        title_lower = title.lower()
                        text_lower = (post_data.get("selftext", "") or "").lower()
                        full_text = f"{title_lower} {text_lower}"
                        normalized_full_text = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", full_text))
                        
                        # 改进的关键词匹配：支持部分匹配和分词匹配
                        # 1. 先尝试完整关键词匹配
                        # 2. 如果关键词很长，尝试分词匹配（提取关键词中的主要单词）
                        matched = False
                        for kw in effective_keywords:
                            # 完整匹配
                            if kw in normalized_full_text:
                                matched = True
                                break
                            if len(kw) > 10:
                                important_words = [w for w in kw.split() if len(w) > 3]
                                if len(important_words) >= 2:
                                    matched_words = sum(1 for w in important_words if w in normalized_full_text)
                                    if matched_words >= 2:
                                        matched = True
                                        break
                                elif len(important_words) == 1 and important_words[0] in normalized_full_text:
                                    matched = True
                                    break
                        
                        if not matched:
                            filtered_by_keywords += 1
                            logger.debug(f"Post filtered by keywords: {title[:50]}")
                            continue
                        else:
                            logger.debug(f"Post matched keywords: {title[:50]}")
                    
                    # 提取其他信息
                    selftext = post_data.get("selftext", "")
                    summary = selftext[:500] if selftext else None
                    
                    created_utc = post_data.get("created_utc")
                    timestamp = None
                    if created_utc:
                        try:
                            # Reddit的created_utc是Unix时间戳（秒）
                            if isinstance(created_utc, (int, float)):
                                timestamp = datetime.utcfromtimestamp(created_utc)
                            elif isinstance(created_utc, str):
                                # 如果是字符串，尝试转换
                                timestamp = datetime.utcfromtimestamp(float(created_utc))
                        except (ValueError, TypeError, OSError) as e:
                            logger.warning(f"Failed to parse Reddit timestamp {created_utc}: {e}")
                            pass
                    
                    username = post_data.get("author")
                    likes = post_data.get("ups", 0) or 0
                    comments = post_data.get("num_comments", 0) or 0
                    
                    post = RedditPost(
                        title=title,
                        link=link,
                        summary=summary,
                        timestamp=timestamp,
                        username=username,
                        subreddit=subreddit,
                        likes=likes,
                        comments=comments,
                        text=selftext,
                    )
                    emitted_posts += 1
                    yield post
            
            logger.info(
                "r/%s: total=%d, filtered_by_keywords=%d, final=%d",
                subreddit,
                total_posts_before_filter,
                filtered_by_keywords,
                emitted_posts,
            )
            return
            
        except Exception as exc:
            logger.error(f"Reddit fetch failed for r/{subreddit}: {exc}", exc_info=True)
            return
    
    def search_multiple_subreddits(
        self,
        subreddits: List[str],
        keywords: Optional[List[str]] = None,
        limit_per_subreddit: int = 20,
    ) -> Iterable[RedditPost]:
        """
        搜索多个子论坛
        
        Args:
            subreddits: 子论坛名称列表
            keywords: 可选的关键词列表
            limit_per_subreddit: 每个子论坛的结果数量限制
        """
        logger.info(f"Searching {len(subreddits)} subreddits: {subreddits}, keywords: {keywords}")
        total_posts = 0
        
        for idx, subreddit in enumerate(subreddits):
            try:
                # 在请求之间添加延迟，避免被 Reddit 限制
                if idx > 0:
                    import time
                    delay = 2.0  # 2秒延迟
                    logger.debug(f"Waiting {delay}s before next request...")
                    time.sleep(delay)
                
                fetched_count = 0
                for post in self.fetch_posts(subreddit, keywords, limit_per_subreddit):
                    fetched_count += 1
                    total_posts += 1
                    yield post
                logger.info(f"r/{subreddit}: fetched {fetched_count} posts")
            except Exception as exc:
                logger.error(f"Failed to fetch from r/{subreddit}: {exc}", exc_info=True)
                continue
        
        logger.info(f"Total posts collected from all subreddits: {total_posts}")
        return
    
    def discover_subreddits(
        self,
        keywords: List[str],
        max_results: int = 20,
        min_subscribers: int = 100,
    ) -> List[str]:
        """
        发现与关键词相关的子论坛
        
        使用多种策略发现相关子论坛：
        1. 使用Reddit搜索API搜索帖子，从结果中提取子论坛
        2. 使用子论坛搜索API（如果可用）
        3. 从关键词生成可能的子论坛名称
        
        Args:
            keywords: 搜索关键词列表
            max_results: 最多返回的子论坛数量
            min_subscribers: 最小订阅者数量（用于过滤）
            
        Returns:
            发现的子论坛名称列表（去重后）
        """
        discovered_subreddits: set[str] = set()
        
        if not keywords or len(keywords) == 0:
            logger.warning("No keywords provided for subreddit discovery")
            return []
        
        try:
            # 策略1: 使用Reddit搜索API搜索帖子，从结果中提取子论坛
            for keyword in keywords[:3]:  # 限制关键词数量，避免过多请求
                try:
                    import time
                    time.sleep(1.0)  # 请求间延迟
                    
                    # 使用Reddit搜索API
                    search_url = f"{self.base_url}/search.json?q={quote(keyword)}&limit=25&sort=relevance"
                    logger.info(f"Searching Reddit for subreddits with keyword: {keyword}")
                    
                    from ....settings.config import settings
                    reddit_user_agent = settings.reddit_user_agent if hasattr(settings, 'reddit_user_agent') and settings.reddit_user_agent else None
                    user_agent = reddit_user_agent or "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                    
                    headers = {
                        "User-Agent": user_agent,
                        "Accept": "application/json",
                        "Accept-Language": "en-US,en;q=0.9",
                        "Accept-Encoding": "gzip, deflate, br",
                        "Connection": "keep-alive",
                        "DNT": "1",
                        "Referer": "https://www.reddit.com/",
                        "Sec-Fetch-Dest": "empty",
                        "Sec-Fetch-Mode": "cors",
                        "Sec-Fetch-Site": "same-origin",
                    }
                    
                    response_text, response = fetch_html(search_url, headers=headers)
                    
                    if response_text:
                        import json
                        data = json.loads(response_text)
                        
                        if "data" in data and "children" in data["data"]:
                            for child in data["data"]["children"]:
                                post_data = child.get("data", {})
                                subreddit = post_data.get("subreddit", "")
                                subscribers = post_data.get("subreddit_subscribers", 0)
                                
                                if subreddit and subscribers >= min_subscribers:
                                    # 清理子论坛名称（去除r/前缀）
                                    subreddit_clean = subreddit.replace("r/", "").strip()
                                    if subreddit_clean:
                                        discovered_subreddits.add(subreddit_clean)
                                        logger.debug(f"Discovered subreddit: r/{subreddit_clean} ({subscribers} subscribers)")
                    
                except Exception as e:
                    logger.warning(f"Failed to discover subreddits for keyword '{keyword}': {e}")
                    continue
            
            # 策略2: 从关键词生成可能的子论坛名称
            # 例如: "lottery" -> ["lottery", "Lottery", "lotteries"]
            for keyword in keywords:
                keyword_clean = keyword.strip().lower()
                if keyword_clean:
                    # 直接使用关键词作为子论坛名
                    discovered_subreddits.add(keyword_clean)
                    # 首字母大写版本
                    discovered_subreddits.add(keyword_clean.capitalize())
                    # 复数形式（简单处理）
                    if not keyword_clean.endswith('s'):
                        discovered_subreddits.add(keyword_clean + 's')
            
            # 策略3: 组合关键词生成可能的子论坛名
            # 例如: ["powerball", "lottery"] -> ["powerballlottery", "powerball_lottery"]
            if len(keywords) >= 2:
                for i, kw1 in enumerate(keywords[:2]):
                    for kw2 in keywords[i+1:3]:
                        kw1_clean = kw1.strip().lower()
                        kw2_clean = kw2.strip().lower()
                        if kw1_clean and kw2_clean:
                            # 组合形式
                            discovered_subreddits.add(f"{kw1_clean}{kw2_clean}")
                            discovered_subreddits.add(f"{kw1_clean}_{kw2_clean}")
            
            # 转换为列表并限制数量
            result = list(discovered_subreddits)[:max_results]
            logger.info(f"Discovered {len(result)} subreddits: {result[:10]}...")  # 只显示前10个
            
            return result
            
        except Exception as exc:
            logger.error(f"Subreddit discovery failed: {exc}", exc_info=True)
            # 即使失败，也返回从关键词生成的子论坛
            fallback = []
            for keyword in keywords:
                keyword_clean = keyword.strip().lower()
                if keyword_clean:
                    fallback.append(keyword_clean)
            return fallback[:max_results]

