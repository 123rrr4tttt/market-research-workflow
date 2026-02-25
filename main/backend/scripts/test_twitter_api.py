#!/usr/bin/env python3
"""测试Twitter API适配器"""
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.services.ingest.adapters.social_twitter import TwitterAdapter
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def test_twitter_adapter_init():
    """测试Twitter适配器初始化"""
    print("=" * 60)
    print("测试1: Twitter适配器初始化")
    print("=" * 60)
    
    try:
        adapter = TwitterAdapter()
        print("✓ Twitter适配器初始化成功")
        return adapter
    except Exception as e:
        print(f"✗ 初始化失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_search_tweets(adapter):
    """测试搜索推文"""
    print("\n" + "=" * 60)
    print("测试2: 搜索推文")
    print("=" * 60)
    
    if not adapter:
        print("跳过测试（适配器未初始化）")
        return
    
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
                print(f"    点赞: {post.likes}, 转发: {post.retweets}, 回复: {post.replies}")
        except Exception as e:
            print(f"  ✗ 错误: {e}")
            import traceback
            traceback.print_exc()


def test_keyword_filtering(adapter):
    """测试关键词过滤"""
    print("\n" + "=" * 60)
    print("测试3: 关键词过滤")
    print("=" * 60)
    
    if not adapter:
        print("跳过测试（适配器未初始化）")
        return
    
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
                print(f"       用户: @{post.username}, 点赞: {post.likes}")
    except Exception as e:
        print(f"  ✗ 错误: {e}")
        import traceback
        traceback.print_exc()


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("Twitter API适配器测试")
    print("=" * 60 + "\n")
    
    adapter = test_twitter_adapter_init()
    
    if adapter:
        test_search_tweets(adapter)
        test_keyword_filtering(adapter)
    
    print("\n" + "=" * 60)
    print("所有测试完成！")
    print("=" * 60)
    
    return 0 if adapter else 1


if __name__ == "__main__":
    sys.exit(main())

