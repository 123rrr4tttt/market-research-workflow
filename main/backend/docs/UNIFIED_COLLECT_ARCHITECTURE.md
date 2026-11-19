# 统一采集架构设计

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

市场与政策法规采集共用下列请求字段；Reddit、商品指标和电商采集保留各自的请求结构：

```json
{
  "query_terms": ["关键词1", "关键词2"],
  "max_items": 20,
  "enable_extraction": true,
  "async_mode": false,
  "project_key": "xxx"
}
```

路由与各请求模型见[采集 API](../app/api/ingest.py)。

## 4. 固定来源 vs 广泛搜索

### 4.1 固定来源（来源库）

- **Google News**、**Reddit** 等为**固定来源**，通过来源库 channel 配置（如 `news.google.general`、`social.reddit`）
- 用户置入的网页 URL 也是固定来源
- 运行来源库项时，按 item 的 channel 调用对应适配器（抓取指定站点/API）

### 4.2 广泛搜索

- [发现 API](../app/api/discovery.py)和市场、政策法规采集默认使用 `provider="auto"`，不固定为 Google。
- [`search_sources`](../app/services/search/web.py) 在 `auto` 模式下先尝试配置好的 Serper，无结果时再按配置尝试 Google Custom Search、Serpstack 和 SerpAPI。SerpAPI 新闻补充、限站 DuckDuckGo 回退也由该函数决定。
- 需要固定通道时显式传入 `provider`。配置见[搜索服务运维说明](../../../ops/search-providers/README.md)。

### 4.3 当前实现

| 采集类型 | 实现 |
|----------|------|
| 政策法规/市场 | `/api/v1/ingest/policy/regulation`、`/api/v1/ingest/market`；省略 `provider` 时为 `auto` |
| 舆情 | Reddit API（固定来源） |
| 商品 | Stooq API + 指标 |

## 5. 来源库（特定搜索 / 固定来源）

- 来源库项 = 固定来源（Google News、Reddit、用户 URL 等）
- 实际可执行的通道由[来源库定义与配置](RESOURCE_LIBRARY_DEFINITION.md)决定。用户直接给出 URL 时也可使用 `/api/v1/ingest/url/single`。
- 运行项时：按 channel 调用适配器 → 抓取/搜索 → 入库

## 6. 子项目固定来源

- 某类「市场采集」若为**领域特化统计**（如某子项目的开奖/销量），应迁入对应子项目
- 作为子项目固定来源：子项目注册专属 channel（如 `{provider}.stats`）
- 通用网页搜索不依赖子项目的领域特化统计；子项目可通过来源库运行自己的固定来源项。
