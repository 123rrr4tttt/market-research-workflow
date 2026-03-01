# 统一采集架构设计

> 最后更新：2026-02 | 文档索引：`docs/README.md`

> 注：文档中的「某子项目」为泛指；`online_lottery` 仅为子项目示例之一，主干不显式依赖具体子项目。

## 1. 设计目标

将采集功能重构为**横向按信息侧重、纵向按搜索范围**的统一结构：

- **横向**：政策 | 市场 | 商品 | 舆情（四种信息侧重，几乎同构）
- **纵向**：广泛搜索（网页搜索） + 特定搜索（来源库，用户置入的网页）

## 2. 架构示意

```
                    横向：信息侧重
        ┌──────────┬──────────┬──────────┬──────────┐
        │  政策    │  市场    │  商品    │  舆情    │
        │ policy   │ market   │ commodity│ sentiment│
        └────┬─────┴────┬─────┴────┬─────┴────┬─────┘
             │          │          │          │
  纵向       │          │          │          │
  广泛搜索   │  query_terms + max_items + enable_extraction
  (网页搜索) │  各类型特化参数（如 sentiment 的 platforms/base_subreddits）
             │          │          │          │
  特定搜索   │          │          │          │
  (来源库)   │  用户置入的 URL / 固定来源
             │          │          │          │
        └────┴──────────┴──────────┴──────────┘
```

## 3. 统一 API 形态

四种采集类型共享同一请求结构：

```json
{
  "query_terms": ["关键词1", "关键词2"],
  "max_items": 20,
  "enable_extraction": true,
  "async_mode": false,
  "project_key": "xxx"
}
```

各类型特化参数通过 `extra_params` 或独立字段传递（如 sentiment 的 `platforms`、`base_subreddits`）。

## 4. 固定来源 vs 广泛搜索

### 4.1 固定来源（来源库）

- **Google News**、**Reddit** 等为**固定来源**，通过来源库 channel 配置（如 `news.google.general`、`social.reddit`）
- 用户置入的网页 URL 也是固定来源
- 运行来源库项时，按 item 的 channel 调用对应适配器（抓取指定站点/API）

### 4.2 广泛搜索（默认 Google Custom Search）

- 广泛搜索 = 按关键词在互联网上检索，使用 `search_sources`（`web.py`）
- **默认**：Google Custom Search API（`provider="google"`），需配置 `GOOGLE_SEARCH_API_KEY` + `GOOGLE_SEARCH_CSE_ID`
- 回退：Serpstack → SerpAPI → DuckDuckGo（当 Google 未配置或失败时）
- 政策/市场采集已切换为 `search_sources`，默认使用 Google CSE

### 4.3 当前实现

| 采集类型 | 实现 |
|----------|------|
| 政策/市场 | `search_sources`，默认 `provider="google"` |
| 舆情 | Reddit API（固定来源） |
| 商品 | Stooq API + 指标 |

## 5. 来源库（特定搜索 / 固定来源）

- 来源库项 = 固定来源（Google News、Reddit、用户 URL 等）
- channel 类型：`google_news`、`reddit`、`web_url`（用户置入网页）
- 运行项时：按 channel 调用适配器 → 抓取/搜索 → 入库

## 6. 子项目固定来源

- 某类「市场采集」若为**领域特化统计**（如某子项目的开奖/销量），应迁入对应子项目
- 作为子项目固定来源：子项目注册专属 channel（如 `{provider}.stats`）
- 主干仅暴露通用网页搜索类采集，子项目通过来源库运行其固定来源项

## 7. 实施阶段

1. ✅ 领域特化统计迁入子项目：子项目注册 stats channel 与 ingest 服务
2. ✅ 新建通用市场采集（网页搜索）：`collect_market_info`，`/ingest/market` 改为 web search
3. ⏸ 统一四种采集 API 结构（政策/市场/舆情已同构，商品/电商保留特化）
4. ⏸ 新增 web_url 来源库 channel（用户置入网页）
