#!/usr/bin/env python3
"""独立测试Twitter API适配器"""
import sys
import os
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List
from urllib.parse import unquote

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

try:
    import tweepy
    TWEEPY_AVAILABLE = True
except ImportError:
    TWEEPY_AVAILABLE = False
    logger.error("tweepy library not installed. Install it with: pip install tweepy")
    sys.exit(1)


@dataclass
class TwitterPost:
    """Twitter帖子数据结构"""
    title: str
    link: str
    summary: Optional[str] = None
    timestamp: Optional[datetime] = None
    username: Optional[str] = None
    likes: int = 0
    retweets: int = 0
    replies: int = 0
    text: Optional[str] = None


def test_twitter_api():
    """测试Twitter API"""
    print("=" * 60)
    print("Twitter API测试")
    print("=" * 60)
    
    # 从环境变量或直接设置凭证
    import os
    from dotenv import load_dotenv
    
    # 加载.env文件
    env_file = os.path.join(os.path.dirname(__file__), '..', '.env')
    load_dotenv(env_file)
    
    api_key = os.getenv('TWITTER_API_KEY')
    api_secret = os.getenv('TWITTER_API_SECRET')
    bearer_token = os.getenv('TWITTER_BEARER_TOKEN')
    access_token = os.getenv('TWITTER_ACCESS_TOKEN')
    access_token_secret = os.getenv('TWITTER_ACCESS_TOKEN_SECRET')
    
    if not bearer_token and not (api_key and api_secret):
        print("✗ Twitter API凭证未设置")
        print("请设置以下环境变量:")
        print("  - TWITTER_BEARER_TOKEN (推荐)")
        print("  或")
        print("  - TWITTER_API_KEY 和 TWITTER_API_SECRET")
        return False
    
    # 创建API客户端（优先使用OAuth 1.0a）
    try:
        if api_key and api_secret and access_token and access_token_secret:
            client = tweepy.Client(
                consumer_key=api_key,
                consumer_secret=api_secret,
                access_token=access_token,
                access_token_secret=access_token_secret,
                wait_on_rate_limit=True,
            )
            print("✓ 使用OAuth 1.0a初始化Twitter API客户端")
        elif bearer_token:
            bearer_token = unquote(bearer_token)
            client = tweepy.Client(
                bearer_token=bearer_token,
                wait_on_rate_limit=True,
            )
            print("✓ 使用Bearer Token初始化Twitter API客户端")
        else:
            print("✗ 缺少必要的API凭证")
            return False
    except Exception as e:
        print(f"✗ 初始化失败: {e}")
        return False
    
    # 测试1: 搜索推文
    print("\n" + "=" * 60)
    print("测试1: 搜索推文")
    print("=" * 60)
    
    try:
        query = "lottery"
        print(f"搜索查询: {query}")
        
        tweets = client.search_recent_tweets(
            query=query,
            max_results=10,
            tweet_fields=['created_at', 'author_id', 'public_metrics', 'text'],
            expansions=['author_id'],
            user_fields=['username', 'name'],
        )
        
        if not tweets.data:
            print("  未找到推文")
        else:
            print(f"  找到 {len(tweets.data)} 条推文")
            
            # 获取用户信息
            users = {}
            if tweets.includes and 'users' in tweets.includes:
                for user in tweets.includes['users']:
                    users[user.id] = user
            
            # 显示前3条
            for i, tweet in enumerate(tweets.data[:3], 1):
                username = None
                if tweet.author_id and tweet.author_id in users:
                    username = users[tweet.author_id].username
                
                metrics = tweet.public_metrics or {}
                print(f"\n  推文 {i}:")
                print(f"    内容: {tweet.text[:100]}...")
                print(f"    用户: @{username}" if username else "    用户: 未知")
                print(f"    时间: {tweet.created_at}")
                print(f"    点赞: {metrics.get('like_count', 0)}, 转发: {metrics.get('retweet_count', 0)}")
    except tweepy.TooManyRequests:
        print("  ⚠ API速率限制")
    except tweepy.Unauthorized:
        print("  ✗ 认证失败，请检查凭证")
    except Exception as e:
        print(f"  ✗ 错误: {e}")
        import traceback
        traceback.print_exc()
    
    # 测试2: 获取用户推文
    print("\n" + "=" * 60)
    print("测试2: 获取用户推文")
    print("=" * 60)
    
    try:
        username = "elonmusk"  # 测试用的知名账号
        print(f"获取用户: @{username}")
        
        # 先获取用户ID
        user = client.get_user(username=username)
        if not user.data:
            print("  用户未找到")
        else:
            user_id = user.data.id
            print(f"  用户ID: {user_id}")
            
            # 获取推文
            tweets = client.get_users_tweets(
                id=user_id,
                max_results=5,
                tweet_fields=['created_at', 'public_metrics', 'text'],
            )
            
            if not tweets.data:
                print("  该用户没有推文")
            else:
                print(f"  找到 {len(tweets.data)} 条推文")
                
                # 显示第一条
                tweet = tweets.data[0]
                metrics = tweet.public_metrics or {}
                print(f"\n  最新推文:")
                print(f"    内容: {tweet.text[:100]}...")
                print(f"    时间: {tweet.created_at}")
                print(f"    点赞: {metrics.get('like_count', 0)}, 转发: {metrics.get('retweet_count', 0)}")
    except tweepy.TooManyRequests:
        print("  ⚠ API速率限制")
    except tweepy.Unauthorized:
        print("  ✗ 认证失败，请检查凭证")
    except tweepy.NotFound:
        print("  ✗ 用户未找到")
    except Exception as e:
        print(f"  ✗ 错误: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)
    
    return True


if __name__ == "__main__":
    success = test_twitter_api()
    sys.exit(0 if success else 1)

