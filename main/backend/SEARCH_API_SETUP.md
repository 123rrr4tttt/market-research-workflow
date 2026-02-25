# 免费搜索 API 配置指南

## 概述

项目已集成多个免费搜索 API 替代方案，按优先级自动降级使用：

1. **DuckDuckGo** (DDG) - 免费但有限制
2. **Google Custom Search** - 每天100次免费请求 ⭐⭐ 最推荐
3. **Serpstack** - 每月100次免费请求 ⭐ 推荐
4. **SerpAPI** - 付费服务（如果已配置）

## 免费方案对比

| API | 免费额度 | 申请难度 | 推荐度 |
|-----|---------|---------|--------|
| **Google Custom Search** | 100次/天 | 中等 | ⭐⭐⭐ |
| **Serpstack** | 100次/月 | 简单 | ⭐⭐ |
| DuckDuckGo | 无限制（但易被限流） | 无需申请 | ⭐ |
| SerpAPI | 付费 | 简单 | ⭐⭐⭐（付费） |

## 方案一：Google Custom Search（推荐，功能强大）

### 特点
- ✅ 每天100次免费请求（每月约3000次）
- ✅ Google 官方服务，稳定可靠
- ✅ 搜索结果质量高
- ⚠️ 需要 Google Cloud 账号
- ⚠️ 需要创建自定义搜索引擎

### 申请步骤

1. **创建 Google Cloud 项目**：
   - 访问 https://console.cloud.google.com/
   - 创建新项目或选择现有项目
   - 启用 "Custom Search API"

2. **获取 API Key**：
   - 在 Google Cloud Console 中，进入 "APIs & Services" > "Credentials"
   - 点击 "Create credentials" > "API key"
   - 复制生成的 API Key
   - （可选）限制 API Key 的使用范围以提高安全性

3. **创建自定义搜索引擎**：
   - 访问 https://cse.google.com/cse/
   - 点击 "Add" 创建新的搜索引擎
   - 在 "Sites to search" 中输入 `*`（搜索整个网络）或指定网站
   - 点击 "Create" 后，复制 **Search Engine ID** (cx)

### 配置方法

在 `.env` 文件中添加：
```bash
GOOGLE_SEARCH_API_KEY=your_google_api_key_here
GOOGLE_SEARCH_CSE_ID=your_search_engine_id_here
```

或在配置页面设置 `GOOGLE_SEARCH_API_KEY` 和 `GOOGLE_SEARCH_CSE_ID`。

### 注意事项

- 免费额度：每天100次请求
- 每个请求最多返回10个结果
- 建议在创建自定义搜索引擎时，选择 "Search the entire web" 以搜索所有网站
- API Key 可以设置使用限制，建议限制为只允许 Custom Search API

## 方案二：Serpstack（推荐新手）

### 特点
- ✅ 每月100次免费请求
- ✅ 申请简单，立即生效
- ✅ API 格式简单，类似 SerpAPI

### 申请步骤

1. 访问 https://serpstack.com/
2. 点击 "Sign Up" 注册账号
3. 登录后进入 Dashboard
4. 复制 **Access Key**

### 配置方法

在 `.env` 文件中添加：
```bash
SERPSTACK_KEY=your_access_key_here
```

或在配置页面设置 `SERPSTACK_KEY`。

## 方案三：SerpAPI（付费，功能强大）

### 特点
- ✅ 功能强大，支持多种搜索引擎
- ✅ API 格式简单，稳定可靠
- ⚠️ 付费服务

### 申请步骤

1. 访问 https://serpapi.com/
2. 注册账号并选择套餐
3. 在 Dashboard 中复制 **API Key**

### 配置方法

在 `.env` 文件中添加：
```bash
SERPAPI_KEY=your_serpapi_key_here
```

或在配置页面设置 `SERPAPI_KEY`。

## 使用优先级

系统会按以下顺序自动尝试：

1. **DuckDuckGo** - 首先尝试（如果未被限流）
2. **Google Custom Search** - DDG 失败时优先使用（如已配置，每天100次免费）
3. **Serpstack** - Google 失败或未配置时使用（如已配置，每月100次免费）
4. **SerpAPI** - 最后降级方案（付费，如已配置）

## 测试配置

配置完成后，可以通过以下方式测试：

```bash
# 在项目根目录运行
cd backend
source .venv311/bin/activate
python3 -c "
from app.services.search.web import search_sources
results = search_sources('California lottery', 'en', max_results=3)
print(f'找到 {len(results)} 个结果')
for r in results:
    print(f\"- {r['title']} ({r['source']})\")
"
```

## 注意事项

1. **Google Custom Search** 免费额度：每天100次（每月约3000次），推荐优先配置
2. **Serpstack** 免费额度：每月100次，适合轻度使用
3. **SerpAPI** 是付费服务，功能最强大但需要付费
4. 如果 API 调用失败，系统会自动降级到下一个可用方案
5. 建议优先配置 **Google Custom Search**，提供最多的免费额度

## 查看当前使用的搜索源

在搜索结果中，每个结果会显示 `source` 字段：
- `ddg` - DuckDuckGo
- `google` - Google Custom Search
- `serpstack` - Serpstack
- `serpapi` - SerpAPI

## 故障排查

如果搜索失败，检查：
1. API Key 是否正确配置
2. 是否超出免费额度限制
3. 网络连接是否正常
4. 查看后端日志了解详细错误信息

