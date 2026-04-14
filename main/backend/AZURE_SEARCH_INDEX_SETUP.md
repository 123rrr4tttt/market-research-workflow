# Azure Search 索引字段配置指南

> 最后更新：2026-02 | 配置写入 `main/backend/.env`

## 当前索引状态

索引名称：`index1761979777378`

当前字段：
- `id` (Edm.String, Key) ✅

## 需要添加的字段

为了支持有效的搜索功能，索引需要添加以下字段：

### 必需字段

1. **title** (Edm.String, Searchable)
   - 用途：文档标题
   - 配置：Searchable, Analyzer: en.microsoft

2. **url** (Edm.String, Filterable)
   - 用途：文档链接
   - 配置：Filterable

3. **content** (Edm.String, Searchable)
   - 用途：文档内容/摘要
   - 配置：Searchable, Analyzer: en.microsoft

### 可选字段（推荐）

4. **name** (Edm.String, Searchable)
   - 用途：备用标题字段
   - 配置：Searchable, Analyzer: en.microsoft

5. **link** (Edm.String, Filterable)
   - 用途：备用链接字段
   - 配置：Filterable

6. **snippet** (Edm.String, Searchable)
   - 用途：文档摘要片段
   - 配置：Searchable, Analyzer: en.microsoft

7. **description** (Edm.String, Searchable)
   - 用途：文档描述
   - 配置：Searchable, Analyzer: en.microsoft

## 在 Azure Portal 中添加字段

### 步骤

1. 访问 https://portal.azure.com
2. 搜索并打开 "lotto" Search Service
3. 点击左侧菜单的 "Indexes"
4. 找到并点击索引 `index1761979777378`
5. 点击 "Edit" 按钮
6. 在 "Fields" 部分，点击 "Add field"
7. 为每个字段填写：
   - **Field name**: 字段名称（如 `title`）
   - **Type**: Edm.String
   - **Key**: false（只有 `id` 是 Key）
   - **Retrievable**: true
   - **Filterable**: 根据需要（url 和 link 设为 true）
   - **Searchable**: 根据需要（title, content, snippet 等设为 true）
   - **Analyzer**: 对于 Searchable 字段，选择 "en.microsoft"
8. 添加完所有字段后，点击 "Save"

### 字段配置详情

| 字段名 | Type | Key | Retrievable | Filterable | Searchable | Analyzer |
|--------|------|-----|-------------|------------|------------|----------|
| id | Edm.String | ✅ | ✅ | ✅ | ❌ | - |
| title | Edm.String | ❌ | ✅ | ❌ | ✅ | en.microsoft |
| name | Edm.String | ❌ | ✅ | ❌ | ✅ | en.microsoft |
| url | Edm.String | ❌ | ✅ | ✅ | ❌ | - |
| link | Edm.String | ❌ | ✅ | ✅ | ❌ | - |
| content | Edm.String | ❌ | ✅ | ❌ | ✅ | en.microsoft |
| snippet | Edm.String | ❌ | ✅ | ❌ | ✅ | en.microsoft |
| description | Edm.String | ❌ | ✅ | ❌ | ✅ | en.microsoft |

## 验证索引配置

添加字段后，可以运行测试脚本验证：

```bash
cd backend
source .venv311/bin/activate
python3 scripts/test_azure_search_index.py
```

## 上传数据到索引

索引创建并配置字段后，需要上传数据。可以使用以下方法：

### 方法一：使用 Python SDK

```python
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential

endpoint = "https://lotto.search.windows.net"
api_key = "your_api_key"
index_name = "index1761979777378"

credential = AzureKeyCredential(api_key)
search_client = SearchClient(endpoint=endpoint, index_name=index_name, credential=credential)

# 上传文档
documents = [
    {
        "id": "1",
        "title": "Document Title",
        "url": "https://example.com",
        "content": "Document content here..."
    }
]

search_client.upload_documents(documents=documents)
```

### 方法二：使用 Azure Portal

1. 在索引页面，点击 "Documents"
2. 点击 "Upload documents"
3. 上传 JSON 格式的文档数据

## 注意事项

⚠️ **重要**：Azure Search 不支持直接向现有索引添加字段。如果需要添加字段：

1. **选项 A**：重新创建索引（会删除现有数据）
2. **选项 B**：创建新索引，迁移数据，然后删除旧索引

如果索引中已有重要数据，建议：
- 先备份数据
- 创建新索引并添加所有需要的字段
- 将数据迁移到新索引
- 更新配置使用新索引名称

## 测试搜索功能

配置完成后，测试搜索：

```bash
cd backend
source .venv311/bin/activate
python3 -c "
from app.services.search.web import search_sources
results = search_sources('test query', 'en', max_results=5, provider='azure_search')
print(f'Found {len(results)} results')
for r in results:
    print(f\"- {r.get('title', 'N/A')}: {r.get('link', 'N/A')}\")
"
```


