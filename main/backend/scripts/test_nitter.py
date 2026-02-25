#!/usr/bin/env python3
"""测试Nitter适配器"""
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.services.ingest.adapters.social_nitter import NitterAdapter
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


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
    test_usernames = ["elonmusk", "jack", "twitter"]
    
    for username in test_usernames:
        print(f"\n测试用户: @{username}")
        try:
            posts = list(adapter.fetch_user_tweets(username, limit=5))
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
            posts = list(adapter.search_tweets(query, limit=5))
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
    
    print()


def test_keyword_filtering():
    """测试关键词过滤"""
    print("=" * 60)
    print("测试4: 关键词过滤")
    print("=" * 60)
    
    adapter = NitterAdapter()
    
    query = "lottery"
    keywords = ["powerball", "winner"]
    
    print(f"搜索查询: {query}")
    print(f"过滤关键词: {keywords}")
    
    try:
        posts = list(adapter.search_tweets(query, keywords=keywords, limit=10))
        print(f"  获取到 {len(posts)} 条匹配的推文")
        
        if posts:
            print(f"\n  前3条推文:")
            for i, post in enumerate(posts[:3], 1):
                print(f"    {i}. {post.title[:80]}")
    except Exception as e:
        print(f"  ✗ 错误: {e}")
    
    print()


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("Nitter适配器测试")
    print("=" * 60 + "\n")
    
    try:
        test_nitter_instance()
        test_user_tweets()
        test_search()
        test_keyword_filtering()
        
        print("=" * 60)
        print("所有测试完成！")
        print("=" * 60)
        
    except Exception as e:
        logger.exception("测试失败")
        print(f"\n✗ 测试失败: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

