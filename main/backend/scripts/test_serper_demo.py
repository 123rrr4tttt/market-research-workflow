#!/usr/bin/env python3
"""Test Serper web search in demo subproject context (embodied ai topic)."""
from pathlib import Path
import os
import sys

# Load .env before any app imports
backend_dir = Path(__file__).resolve().parent.parent
env_file = backend_dir / ".env"
if env_file.exists():
    from dotenv import load_dotenv
    load_dotenv(env_file)
    print(f"Loaded .env from {env_file}")

# Ensure backend is on path and cwd for .env
sys.path.insert(0, str(backend_dir))
os.chdir(backend_dir)

import os
from app.services.search.web import search_sources
from app.services.discovery.application import DiscoveryApplicationService

def main():
    topic = "embodied ai"
    print(f"=== Serper 网页搜索测试 (demo 主题: {topic}) ===\n")
    
    # 1. Search only
    results = search_sources(
        topic, "en",
        max_results=5,
        provider="serper",
        exclude_existing=False,
    )
    print(f"1. 搜索阶段: 找到 {len(results)} 个结果")
    for r in results[:5]:
        print(f"   - {r.get('title', '')[:55]}... ({r.get('source')})")
        print(f"     {r.get('link', '')[:75]}...")
    
    if not results:
        print("   (无结果，请检查 SERPER_API_KEY 是否配置)")
        return 1
    
    # 2. Full discovery flow (search + store) - requires DB/ES + migrations
    try:
        discovery = DiscoveryApplicationService.build_default()
        body = discovery.run_search(
            topic=topic,
            language="en",
            max_results=3,
            provider="serper",
            exclude_existing=False,
            persist=True,
        )
        stored = body.get("stored", {})
        print(f"\n2. 完整流程 (搜索+落库): 新增={stored.get('inserted', 0)}, 更新={stored.get('updated', 0)}")
        print(f"   provider_used: {body.get('provider_used', '?')}")
    except Exception as e:
        print(f"\n2. 落库阶段跳过 (需 PostgreSQL/ES 及 migrations): {type(e).__name__}")
    
    print("\n=== 测试完成 ===")
    return 0

if __name__ == "__main__":
    sys.exit(main())
