"""Twitter/X官方API数据适配器"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, List, Optional
from urllib.parse import unquote

logger = logging.getLogger(__name__)

try:
    import tweepy
    TWEEPY_AVAILABLE = True
except ImportError:
    TWEEPY_AVAILABLE = False
    logger.warning("tweepy library not installed. Install it with: pip install tweepy")


@dataclass
class TwitterPost:
    """Twitter帖子数据结构"""
    title: str  # 推文内容（作为标题）
    link: str  # 推文链接
    summary: Optional[str] = None  # 推文内容（完整）
    timestamp: Optional[datetime] = None
    username: Optional[str] = None
    likes: int = 0
    retweets: int = 0
    replies: int = 0
    text: Optional[str] = None


class TwitterAdapter:
    """Twitter/X官方API数据适配器"""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        bearer_token: Optional[str] = None,
        access_token: Optional[str] = None,
        access_token_secret: Optional[str] = None,
    ):
        """
        初始化Twitter适配器
        
        Args:
            api_key: Twitter API Key (Consumer Key)
            api_secret: Twitter API Secret (Consumer Secret)
            bearer_token: Twitter Bearer Token (用于只读操作)
            access_token: Twitter Access Token
            access_token_secret: Twitter Access Token Secret
        """
        if not TWEEPY_AVAILABLE:
            raise ImportError("tweepy library is required. Install it with: pip install tweepy")
        
        # 从配置中获取凭证（如果未提供）
        if not any([api_key, bearer_token]):
            from ....settings.config import settings
            api_key = api_key or settings.twitter_api_key
            api_secret = api_secret or settings.twitter_api_secret
            bearer_token = bearer_token or settings.twitter_bearer_token
            access_token = access_token or settings.twitter_access_token
            access_token_secret = access_token_secret or settings.twitter_access_token_secret
        
        if not bearer_token and not (api_key and api_secret and access_token and access_token_secret):
            raise ValueError("Twitter API credentials are required. Provide either bearer_token or (api_key, api_secret, access_token, access_token_secret)")
        
        # 创建API客户端
        # 优先使用OAuth 1.0a认证（更可靠，支持更多操作）
        if api_key and api_secret and access_token and access_token_secret:
            self.client = tweepy.Client(
                consumer_key=api_key,
                consumer_secret=api_secret,
                access_token=access_token,
                access_token_secret=access_token_secret,
                wait_on_rate_limit=True,
            )
            logger.info("Using OAuth 1.0a authentication")
        elif bearer_token:
            # 备用：使用Bearer Token（如果OAuth凭证不可用）
            bearer_token = unquote(bearer_token)
            self.client = tweepy.Client(
                bearer_token=bearer_token,
                wait_on_rate_limit=True,
            )
            logger.info("Using Bearer Token authentication")
        else:
            raise ValueError("Insufficient Twitter API credentials provided")
        
        logger.info("Twitter API client initialized successfully")
    
    def search_tweets(
        self,
        query: str,
        keywords: Optional[List[str]] = None,
        limit: int = 20,
        max_results: int = 100,
    ) -> Iterable[TwitterPost]:
        """
        搜索推文
        
        Args:
            query: 搜索查询词
            keywords: 可选的关键词列表，用于进一步过滤
            limit: 返回结果数量限制
            max_results: 每次API调用返回的最大结果数（10-100）
        """
        try:
            if not query or not query.strip():
                logger.warning("Empty search query provided")
                return []
            
            logger.info(f"Searching tweets via Twitter API, query: {query}, keywords: {keywords}")
            
            # Twitter API v2搜索
            tweets = self.client.search_recent_tweets(
                query=query,
                max_results=min(max_results, 100),  # Twitter API限制最多100条
                tweet_fields=['created_at', 'author_id', 'public_metrics', 'text'],
                expansions=['author_id'],
                user_fields=['username', 'name'],
            )
            
            if not tweets.data:
                logger.info(f"No tweets found for query: {query}")
                return []
            
            # 获取用户信息映射
            users = {}
            if tweets.includes and 'users' in tweets.includes:
                for user in tweets.includes['users']:
                    users[user.id] = user
            
            posts = []
            effective_keywords = []
            if keywords:
                effective_keywords = [kw.lower().strip() for kw in keywords if kw and kw.strip()]
            
            for tweet in tweets.data:
                # 提取推文信息
                text = tweet.text or ""
                
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
                        continue
                
                # 获取用户信息
                username = None
                if tweet.author_id and tweet.author_id in users:
                    user = users[tweet.author_id]
                    username = user.username
                
                # 提取互动数据
                metrics = tweet.public_metrics or {}
                likes = metrics.get('like_count', 0) or 0
                retweets = metrics.get('retweet_count', 0) or 0
                replies = metrics.get('reply_count', 0) or 0
                
                # 构建推文链接
                tweet_id = tweet.id
                if username:
                    link = f"https://twitter.com/{username}/status/{tweet_id}"
                else:
                    link = f"https://twitter.com/i/web/status/{tweet_id}"
                
                post = TwitterPost(
                    title=text[:200] if text else "",  # 使用推文前200字符作为标题
                    link=link,
                    summary=text,
                    timestamp=tweet.created_at,
                    username=username,
                    likes=likes,
                    retweets=retweets,
                    replies=replies,
                    text=text,
                )
                posts.append(post)
                
                if len(posts) >= limit:
                    break
            
            logger.info(f"Search '{query}': found {len(posts)} tweets (from {len(tweets.data)} total)")
            return posts
            
        except tweepy.TooManyRequests:
            logger.error("Twitter API rate limit exceeded")
            return []
        except tweepy.Unauthorized:
            logger.error("Twitter API authentication failed or insufficient permissions. Search may require paid API tier.")
            logger.error("Check your API credentials and subscription level.")
            return []
        except tweepy.Forbidden:
            logger.error("Twitter API access forbidden. Search functionality may require paid API tier.")
            return []
        except Exception as exc:
            logger.error(f"Twitter search failed for '{query}': {exc}", exc_info=True)
            return []
    
    def get_user_tweets(
        self,
        username: str,
        keywords: Optional[List[str]] = None,
        limit: int = 20,
        max_results: int = 100,
    ) -> Iterable[TwitterPost]:
        """
        获取指定用户的推文
        
        Args:
            username: Twitter用户名（不含@）
            keywords: 可选的关键词列表，用于过滤
            limit: 返回结果数量限制
            max_results: 每次API调用返回的最大结果数（5-100）
        """
        try:
            # 先获取用户ID
            user = self.client.get_user(username=username)
            if not user.data:
                logger.warning(f"User @{username} not found")
                return []
            
            user_id = user.data.id
            
            logger.info(f"Fetching tweets from @{username} (ID: {user_id}) via Twitter API, keywords: {keywords}")
            
            # 获取用户推文
            tweets = self.client.get_users_tweets(
                id=user_id,
                max_results=min(max_results, 100),
                tweet_fields=['created_at', 'public_metrics', 'text'],
            )
            
            if not tweets.data:
                logger.info(f"No tweets found for user @{username}")
                return []
            
            posts = []
            effective_keywords = []
            if keywords:
                effective_keywords = [kw.lower().strip() for kw in keywords if kw and kw.strip()]
            
            for tweet in tweets.data:
                text = tweet.text or ""
                
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
                        continue
                
                # 提取互动数据
                metrics = tweet.public_metrics or {}
                likes = metrics.get('like_count', 0) or 0
                retweets = metrics.get('retweet_count', 0) or 0
                replies = metrics.get('reply_count', 0) or 0
                
                # 构建推文链接
                tweet_id = tweet.id
                link = f"https://twitter.com/{username}/status/{tweet_id}"
                
                post = TwitterPost(
                    title=text[:200] if text else "",
                    link=link,
                    summary=text,
                    timestamp=tweet.created_at,
                    username=username,
                    likes=likes,
                    retweets=retweets,
                    replies=replies,
                    text=text,
                )
                posts.append(post)
                
                if len(posts) >= limit:
                    break
            
            logger.info(f"@{username}: found {len(posts)} tweets (from {len(tweets.data)} total)")
            return posts
            
        except tweepy.TooManyRequests:
            logger.error("Twitter API rate limit exceeded")
            return []
        except tweepy.Unauthorized:
            logger.error("Twitter API authentication failed. Check your credentials.")
            return []
        except tweepy.NotFound:
            logger.warning(f"User @{username} not found")
            return []
        except Exception as exc:
            logger.error(f"Twitter fetch failed for @{username}: {exc}", exc_info=True)
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
        
        for idx, query in enumerate(queries):
            try:
                # Twitter API会自动处理速率限制（wait_on_rate_limit=True）
                # 但为了安全，仍然添加小延迟
                if idx > 0:
                    import time
                    delay = 1.0  # 1秒延迟
                    logger.debug(f"Waiting {delay}s before next request...")
                    time.sleep(delay)
                
                posts = list(self.search_tweets(query, keywords, limit_per_query))
                logger.info(f"Query '{query}': fetched {len(posts)} tweets")
                all_posts.extend(posts)
            except Exception as exc:
                logger.error(f"Failed to search for '{query}': {exc}", exc_info=True)
                continue
        
        logger.info(f"Total tweets collected from all queries: {len(all_posts)}")
        return all_posts

