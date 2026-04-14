# 结构化提取与图谱元素对齐说明

> 最后更新：2026-02 | 文档索引：`docs/README.md`

## 1. 不一致点概览

| 类别 | 结构化提取输出 | 图谱适配器期望 | 不一致说明 |
|------|----------------|----------------|------------|
| **社媒 (social)** | `sentiment`, `keywords`, `entities_relations` | `platform`, `text`, `username`, `subreddit`, `sentiment` | 非 Reddit 来源（如 news 分类为 social_sentiment）无 `platform`，`normalize_document` 返回 None，无法入图 |
| **市场 (market)** | `market` (state, game, sales_volume...), `entities_relations.entities` | `market`, `entities` (text/type/canonical_name) | `graph_doc_types.market` 默认含 `["market"]` 不含 `market_info`；实体用 `text` 可兼容 |
| **政策 (policy)** | `policy`, `entities_relations` | `policy`, `entities`, `relations` | 结构基本一致 |
| **demo_proj 配置** | - | `graph_node_types.market`: Segment, `graph_edge_types`: HAS_SEGMENT | 已修复：builder 使用通用 Segment/HAS_SEGMENT |

## 2. 详细说明

### 2.1 社媒图谱

- **RedditAdapter**：要求 `platform == "reddit"`，否则返回 None。
- **normalize_document**：`platform` 为空或未注册适配器时返回 None。
- **问题**：来自 news、market_web 等且被分类为 `social_sentiment` 的文档，`platform` 为 `google_news` 等，无对应适配器，无法入社媒图谱。

### 2.2 市场图谱

- **MarketAdapter**：从 `extracted_data.market` 读取，有 fallback。
- **graph_doc_types**：`online_lottery` 的 `market` 为 `["market","news","official_update","retailer_update"]`，未包含 `market_info`，导致 `market_info` 文档不入市场图谱。
- **实体**：提取为 `entities_relations.entities`，格式 `{text, type, span}`，builder 使用 `entity.get("text")`、`entity.get("type")`，可兼容。

### 2.3 通用元素（Builder 对齐）

- 图谱 builder 使用通用元素：`Segment` 节点、`HAS_SEGMENT` 边。
- 各子项目适配进通用：demo 的 segment、lottery 的 game 均映射到 `market_data.game`，由 builder 统一创建 Segment 节点。
- 配置与 builder 一致。

## 3. 已实施的修复

1. **Builder**：统一使用 `Segment` / `HAS_SEGMENT` 作为通用元素格。
2. **online_lottery**：`graph_doc_types.market` 增加 `market_info`。
3. **GenericSocialAdapter**：支持无 `platform` 或未注册平台的社媒文档，使用 `platform="generic"` 作为 fallback。
