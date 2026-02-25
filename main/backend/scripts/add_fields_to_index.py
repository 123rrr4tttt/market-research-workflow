#!/usr/bin/env python3
"""
为 Azure Search 索引添加搜索所需字段的脚本

注意：需要 Admin Key 才能修改索引结构
"""

import os
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchFieldDataType,
    SimpleField,
    SearchableField,
)
from azure.core.credentials import AzureKeyCredential
from app.settings.config import settings

def add_fields_to_index(index_name: str = "index1761979777378"):
    """为索引添加搜索所需的字段"""
    
    endpoint = settings.azure_search_endpoint.rstrip("/")
    api_key = settings.azure_search_key
    
    if not endpoint or not api_key:
        print("❌ Error: Azure Search endpoint or API key not configured")
        return False
    
    print(f"🔗 Connecting to Azure Search: {endpoint}")
    print(f"📋 Index: {index_name}\n")
    
    try:
        credential = AzureKeyCredential(api_key)
        index_client = SearchIndexClient(endpoint=endpoint, credential=credential)
        
        # 获取现有索引
        print("📖 Reading existing index...")
        index = index_client.get_index(index_name)
        
        print(f"   Current fields ({len(index.fields)}):")
        existing_field_names = set()
        for field in index.fields:
            print(f"     - {field.name} ({field.type})")
            existing_field_names.add(field.name.lower())
        
        # 定义需要添加的字段
        fields_to_add = []
        
        if "title" not in existing_field_names:
            fields_to_add.append(
                SearchableField(name="title", type=SearchFieldDataType.String, analyzer_name="en.microsoft")
            )
        
        if "name" not in existing_field_names:
            fields_to_add.append(
                SearchableField(name="name", type=SearchFieldDataType.String, analyzer_name="en.microsoft")
            )
        
        if "url" not in existing_field_names:
            fields_to_add.append(
                SimpleField(name="url", type=SearchFieldDataType.String, filterable=True)
            )
        
        if "link" not in existing_field_names:
            fields_to_add.append(
                SimpleField(name="link", type=SearchFieldDataType.String, filterable=True)
            )
        
        if "content" not in existing_field_names:
            fields_to_add.append(
                SearchableField(name="content", type=SearchFieldDataType.String, analyzer_name="en.microsoft")
            )
        
        if "snippet" not in existing_field_names:
            fields_to_add.append(
                SearchableField(name="snippet", type=SearchFieldDataType.String, analyzer_name="en.microsoft")
            )
        
        if "description" not in existing_field_names:
            fields_to_add.append(
                SearchableField(name="description", type=SearchFieldDataType.String, analyzer_name="en.microsoft")
            )
        
        if not fields_to_add:
            print("\n✅ All required fields already exist!")
            return True
        
        print(f"\n➕ Adding {len(fields_to_add)} field(s)...")
        for field in fields_to_add:
            print(f"   - {field.name} ({field.type})")
        
        # 添加新字段到现有索引
        index.fields.extend(fields_to_add)
        
        # 更新索引（Azure Search 不支持直接添加字段，需要重新创建）
        # 注意：这会删除现有数据！
        print("\n⚠️  WARNING: Azure Search does not support adding fields to existing indexes.")
        print("   You need to recreate the index, which will DELETE all existing data!")
        print("\n   Please use Azure Portal to add fields:")
        print("   1. Go to https://portal.azure.com")
        print("   2. Open 'lotto' Search Service")
        print("   3. Go to 'Indexes' → Select 'index1761979777378'")
        print("   4. Click 'Edit'")
        print("   5. Add the following fields:")
        for field in fields_to_add:
            field_type = "Edm.String"
            if hasattr(field, 'analyzer_name'):
                print(f"      - {field.name}: {field_type} (Searchable, Analyzer: en.microsoft)")
            else:
                print(f"      - {field.name}: {field_type} (Filterable)")
        print("   6. Click 'Save'")
        
        return False
        
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Error: {error_msg}")
        
        if "api key" in error_msg.lower() or "authentication" in error_msg.lower():
            print("\n⚠️  The API key may not have admin permissions.")
            print("   Please use a Primary or Secondary admin key.")
        elif "not found" in error_msg.lower():
            print(f"\n⚠️  Index '{index_name}' not found.")
        
        return False


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Add fields to Azure Search index")
    parser.add_argument("--index-name", default="index1761979777378", help="Index name")
    
    args = parser.parse_args()
    add_fields_to_index(args.index_name)


