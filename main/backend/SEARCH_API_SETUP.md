# 免费搜索 API 配置指南

> 最后更新：2026-02 | 配置写入 `main/backend/.env`

## 概述

项目已集成多个免费搜索 API 替代方案，按优先级自动降级使用：

1. **Serper.dev** - 稳定、接入简单 ⭐⭐ 推荐
2. **DuckDuckGo** (DDG) - 免费但有限制（兜底）
3. **Google Custom Search** - 新客户可能不可用（常见 403）
4. **Serpstack** - 每月100次免费请求
5. **SerpAPI** - 付费服务（如果已配置）

## 免费方案对比

| API | 免费额度 | 申请难度 | 推荐度 |
|-----|---------|---------|--------|
| **Serper.dev** | 通常有免费额度（以官网为准） | 简单 | ⭐⭐⭐ |
| **Google Custom Search** | 100次/天 | 中等 | ⭐⭐⭐ |
| **Serpstack** | 100次/月 | 简单 | ⭐⭐ |
| DuckDuckGo | 无限制（但易被限流） | 无需申请 | ⭐ |
| SerpAPI | 付费 | 简单 | ⭐⭐⭐（付费） |

## 方案一：Serper.dev（推荐，稳定）

### 特点
- ✅ 接入简单（无需 CSE / cx）
- ✅ 稳定性通常优于非官方 DDG
- ⚠️ 属于第三方聚合服务，按配额计费/限额（以官网为准）

### 配置方法

在 `.env` 文件中添加：
```bash
SERPER_API_KEY=your_serper_api_key_here
```

## 方案二：Google Custom Search（历史方案）

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

**方式一：API Key**（传统方式）
在 `.env` 文件中添加：
```bash
GOOGLE_SEARCH_API_KEY=your_google_api_key_here
GOOGLE_SEARCH_CSE_ID=your_search_engine_id_here
```

**方式二：OAuth 2.0（Service Account）**（若 API Key 返回 403 可尝试）
1. 在 Google Cloud Console 创建 Service Account，下载 JSON 密钥
2. 在 `.env` 中设置：
```bash
GOOGLE_APPLICATION_CREDENTIALS=/path/to/your-service-account.json
GOOGLE_SEARCH_CSE_ID=your_search_engine_id_here
```
3. 确保 Service Account 所在项目已启用 Custom Search API
4. OAuth 优先于 API Key：若同时配置，将使用 OAuth

### 注意事项

- 免费额度：每天100次请求
- 每个请求最多返回10个结果
- 建议在创建自定义搜索引擎时，选择 "Search the entire web" 以搜索所有网站
- API Key 可以设置使用限制，建议限制为只允许 Custom Search API

### 403 "PERMISSION_DENIED" 排查

若返回 `This project does not have the access to Custom Search JSON API`，请依次检查：

1. **启用 Custom Search API**  
   - [Google Cloud Console](https://console.cloud.google.com/) → APIs & Services → Library  
   - 搜索并启用 **Custom Search API**（不是 Programmable Search Engine）

2. **关联计费**  
   - APIs & Services → Billing  
   - 确认项目已关联计费账号（免费额度仍需计费账号）

3. **API Key 与项目一致**  
   - API Key 必须来自**同一项目**，且该项目已启用 Custom Search API

4. **Programmable Search Engine 设置**  
   - 打开 [cse.google.com](https://cse.google.com/cse/) → 编辑你的搜索引擎  
   - 设置 → 勾选 **"Allow XML/JSON results"**

5. **用官方工具验证**  
   - 打开 [Custom Search JSON API 文档](https://developers.google.com/custom-search/v1/reference/rest/v1/cse/list)  
   - 点击 "Try this API"，填入你的 `key` 和 `cx`，执行请求  
   - 若此处也返回 403，说明问题在 Google Cloud 配置，而非本应用

6. **尝试 OAuth（Service Account）**  
   - 若 API Key 持续 403，可改用 OAuth：创建 Service Account，设置 `GOOGLE_APPLICATION_CREDENTIALS` 指向 JSON 密钥路径  
   - 详见上方「方式二：OAuth 2.0」

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

1. **Serper.dev** - 优先使用（如已配置）
2. **Google Custom Search** - Serper 未配置/失败时尝试（但新客户可能不可用）
3. **Serpstack** - Google 失败或未配置时使用（如已配置）
4. **SerpAPI** - 最后降级方案（如已配置）
5. **DuckDuckGo** - 兜底（免费但易被限流）

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

