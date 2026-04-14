#!/usr/bin/env python3
"""
测试 Azure Search 索引连接和常见索引名称
"""

import os
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import ResourceNotFoundError
from app.settings.config import settings

def test_index(index_name: str) -> bool:
    """测试索引是否存在且可访问"""
    endpoint = settings.azure_search_endpoint.rstrip("/")
    api_key = settings.azure_search_key
    
    if not endpoint or not api_key:
        return False
    
    try:
        credential = AzureKeyCredential(api_key)
        search_client = SearchClient(endpoint=endpoint, index_name=index_name, credential=credential)
        
        # 尝试执行一个空搜索来验证索引是否存在
        results = search_client.search(search_text="*", top=1)
        list(results)  # 触发实际请求
        return True
    except ResourceNotFoundError:
        return False
    except Exception:
        return False

if __name__ == "__main__":
    endpoint = settings.azure_search_endpoint.rstrip("/")
    api_key = settings.azure_search_key
    
    print(f"🔗 Azure Search Service: {endpoint}")
    print(f"🔑 API Key: {'Set' if api_key else 'Not set'}\n")
    
    if not endpoint or not api_key:
        print("❌ Azure Search not configured")
        sys.exit(1)
    
    # 常见的索引名称
    common_index_names = [
        "web-search",
        "websearch",
        "search",
        "documents",
        "docs",
        "content",
        "index",
        "default",
    ]
    
    # 也检查配置的索引名称
    configured_index = os.getenv("AZURE_SEARCH_INDEX_NAME") or settings.azure_search_index_name
    if configured_index and configured_index not in common_index_names:
        common_index_names.insert(0, configured_index)
    
    print("🔍 Testing common index names...\n")
    
    found_indexes = []
    for index_name in common_index_names:
        print(f"  Testing '{index_name}'...", end=" ")
        if test_index(index_name):
            print("✅ Found!")
            found_indexes.append(index_name)
        else:
            print("❌ Not found")
    
    print()
    if found_indexes:
        print(f"✅ Found {len(found_indexes)} accessible index(es):")
        for idx in found_indexes:
            print(f"   - {idx}")
        print(f"\n💡 Set AZURE_SEARCH_INDEX_NAME={found_indexes[0]} to use it")
    else:
        print("❌ No accessible indexes found")
        print("\n💡 Please:")
        print("   1. Check indexes in Azure Portal: https://portal.azure.com")
        print("   2. Create an index if none exists")
        print("   3. Set AZURE_SEARCH_INDEX_NAME environment variable with the correct index name")


