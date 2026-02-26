# 信息资源库定义

> 最后更新：2026-02 | 文档索引：`docs/README.md`

## 1. 核心概念

### 1.1 Item（来源项）

**定义**：特定类型的信息来源集合。

- 一个 item 是一组信息源的聚合（如 URL 列表、子论坛列表、关键词集合等）
- item 只描述**来源是什么**，不描述**怎么访问**的具体参数
- 通过 `channel_key` 关联到可访问性适配器

### 1.2 Channel（通道）

**定义**：信息来源的可访问性适配。

- 网页抓取工具、API 客户端、JSON 访问类型等
- 负责将「来源」转换为可执行的采集请求
- 例如：`url_pool`（URL 抓取）、`reddit`（Reddit API）、`google_news`（新闻 API）

**各通道的「来源」字段**（item.params 或 override_params 中提供）：

| channel_key | 来源字段 | 说明 |
|-------------|----------|------|
| `reddit` | `subreddits` | 子论坛列表（或 `base_subreddits`） |
| `google_news` | `keywords` | 关键词列表 |
| `policy` | `state` | 州/地区标识 |
| `market` | 来自 override | 关键词/查询词由采集页 override_params 提供 |
| `url_pool` | `urls` | URL 列表；若无则从资源池按 scope/domain/source 拉取 |

### 1.3 来源采集（Source Collection）

**定义**：在一个 item 中，对每个来源（如 URL）发送符合 channel 的参数，通过 channel 进行信息采集。

```
item（来源集合）
    → 遍历 item 中的每个来源
    → 构造符合 channel 的请求参数
    → 通过 channel（适配器）执行采集
    → 入库
```

## 2. 职责边界

| 模块 | 职责 |
|------|------|
| **资源库** | 来源集合、可访问性适配（channel）、资源可访问性 |
| **采集配置** | 需特定结构的访问（论坛结构、子论坛、平台等）、采集事件与调度 |
| **采集页** | 运行时参数（limit、时间范围、语言等）、触发执行 |

## 3. 数据流

```
资源库：item + channel
    ↓
采集配置：结构参数（若需要）
    ↓
采集页：运行时参数（override_params）
    ↓
run_item_by_key：merge 后通过 channel 执行
```

## 4. 方式 B：URL→Channel 路由

当 item 的 `params.urls` 存在且非空时，采用 **URL→Channel 路由** 模式：

- 每个 URL 按 `url_channel_routing` 配置解析出对应的 `channel_key`
- 配置位于 `ingest_config`（config_key: `url_channel_routing`），payload 格式：

  ```json
  {
    "rules": [
      { "pattern": "default", "channel_key": "url_pool" },
      { "pattern": "reddit.com", "channel_key": "reddit" },
      { "pattern": "default", "path_suffix": ".xml", "channel_key": "generic_web.rss" },
      { "pattern": "default", "path_contains": "sitemap", "channel_key": "generic_web.sitemap" }
    ]
  }
  ```

- 规则按顺序匹配；先匹配 domain，再匹配 path 约束（若有）：
  - `pattern`：`"default"`（匹配全部）、前缀（如 `"news."`）、包含（如 `"reddit.com"`）
  - `path_contains`（可选）：URL path 须包含该子串
  - `path_suffix`（可选）：URL path 须以该后缀结尾（如 `".xml"`、`"/feed"`）
  - `path_prefix`（可选）：URL path 须以该前缀开头
- 工具型 channel 示例：`generic_web.rss`、`generic_web.sitemap`、`generic_web.search_template`、`official_access.api`
- 未匹配时回退到 `url_pool`
