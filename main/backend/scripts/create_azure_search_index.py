#!/usr/bin/env python3
"""
Azure AI Search 索引创建脚本

用于创建或验证 Azure Search 索引，索引包含 web 搜索所需的字段。
"""

import os
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SimpleField,
    SearchFieldDataType,
    SearchableField,
)
from azure.core.credentials import AzureKeyCredential
from app.settings.config import settings

def create_web_search_index(index_name: str = "web-search"):
    """创建用于 web 搜索的 Azure Search 索引"""
    
    endpoint = settings.azure_search_endpoint.rstrip("/")
    api_key = settings.azure_search_key
    
    if not endpoint or not api_key:
        print("❌ Error: Azure Search endpoint or API key not configured")
        print(f"   Endpoint: {endpoint or 'Not set'}")
        print(f"   API Key: {'Set' if api_key else 'Not set'}")
        print("\nPlease set AZURE_SEARCH_ENDPOINT and AZURE_SEARCH_KEY")
        return False
    
    print(f"🔗 Connecting to Azure Search: {endpoint}")
    print(f"📋 Index name: {index_name}\n")
    
    try:
        credential = AzureKeyCredential(api_key)
        index_client = SearchIndexClient(endpoint=endpoint, credential=credential)
        
        # 检查索引是否已存在
        try:
            existing_index = index_client.get_index(index_name)
            print(f"✅ Index '{index_name}' already exists!")
            print(f"   Fields: {len(existing_index.fields)}")
            for field in existing_index.fields:
                print(f"     - {field.name} ({field.type})")
            return True
        except Exception as e:
            if "not found" not in str(e).lower():
                raise
        
        # 创建索引定义
        print(f"📝 Creating index '{index_name}'...")
        
        fields = [
            SimpleField(name="id", type=SearchFieldDataType.String, key=True, filterable=True),
            SearchableField(name="title", type=SearchFieldDataType.String, analyzer_name="en.microsoft"),
            SearchableField(name="name", type=SearchFieldDataType.String, analyzer_name="en.microsoft"),
            SimpleField(name="url", type=SearchFieldDataType.String, filterable=True),
            SimpleField(name="link", type=SearchFieldDataType.String, filterable=True),
            SearchableField(name="content", type=SearchFieldDataType.String, analyzer_name="en.microsoft"),
            SearchableField(name="snippet", type=SearchFieldDataType.String, analyzer_name="en.microsoft"),
            SearchableField(name="description", type=SearchFieldDataType.String, analyzer_name="en.microsoft"),
        ]
        
        index = SearchIndex(name=index_name, fields=fields)
        
        created_index = index_client.create_index(index)
        print(f"✅ Index '{index_name}' created successfully!")
        print(f"   Fields: {len(created_index.fields)}")
        return True
        
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Error: {error_msg}")
        
        if "api key" in error_msg.lower() or "authentication" in error_msg.lower():
            print("\n⚠️  The API key may not have admin permissions.")
            print("   Please use a Primary or Secondary admin key from Azure Portal.")
            print("   Steps:")
            print("   1. Go to https://portal.azure.com")
            print("   2. Navigate to your Search Service 'lotto'")
            print("   3. Go to 'Keys' section")
            print("   4. Copy 'Primary admin key' or 'Secondary admin key'")
            print("   5. Set AZURE_SEARCH_KEY environment variable")
        elif "not found" in error_msg.lower():
            print("\n⚠️  Resource not found. Please check:")
            print(f"   - Endpoint: {endpoint}")
            print(f"   - Service name: lotto")
        else:
            print("\nPlease check your Azure Search configuration.")
        
        return False


def list_indexes():
    """列出所有索引"""
    endpoint = settings.azure_search_endpoint.rstrip("/")
    api_key = settings.azure_search_key
    
    if not endpoint or not api_key:
        print("❌ Error: Azure Search endpoint or API key not configured")
        return
    
    try:
        credential = AzureKeyCredential(api_key)
        index_client = SearchIndexClient(endpoint=endpoint, credential=credential)
        
        print(f"🔗 Connecting to Azure Search: {endpoint}\n")
        print("📋 Available indexes:")
        
        indexes = list(index_client.list_indexes())
        if indexes:
            for idx in indexes:
                print(f"  ✅ {idx.name}")
                print(f"     Fields: {len(idx.fields)}")
                field_names = [f.name for f in idx.fields]
                print(f"     Field names: {', '.join(field_names[:10])}")
                if len(field_names) > 10:
                    print(f"     ... and {len(field_names) - 10} more")
        else:
            print("  (No indexes found)")
            
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Error listing indexes: {error_msg}")
        
        if "api key" in error_msg.lower():
            print("\n⚠️  Cannot list indexes - API key may not have admin permissions.")
            print("   Try creating the index manually in Azure Portal or use Azure CLI:")
            print("   az search index list --service-name lotto --resource-group lotto")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Azure Search Index Management")
    parser.add_argument("--create", action="store_true", help="Create web-search index")
    parser.add_argument("--list", action="store_true", help="List all indexes")
    parser.add_argument("--index-name", default="web-search", help="Index name (default: web-search)")
    
    args = parser.parse_args()
    
    if args.list:
        list_indexes()
    elif args.create:
        create_web_search_index(args.index_name)
    else:
        print("Azure Search Index Management Tool")
        print("\nUsage:")
        print("  python scripts/create_azure_search_index.py --list          # List all indexes")
        print("  python scripts/create_azure_search_index.py --create        # Create web-search index")
        print("  python scripts/create_azure_search_index.py --create --index-name my-index  # Create custom index")
        print("\nOr use Azure CLI:")
        print("  az search index list --service-name lotto --resource-group lotto")
        print("  az search index show --name web-search --service-name lotto --resource-group lotto")


