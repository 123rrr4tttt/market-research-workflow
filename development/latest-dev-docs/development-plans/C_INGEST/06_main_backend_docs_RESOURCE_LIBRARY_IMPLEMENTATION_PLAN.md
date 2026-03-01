# 信息资源库功能实现计划

> 基于 `RESOURCE_LIBRARY_DEFINITION.md`，完成资源库管理、采集配置、采集页的职责划分与实现。

---

## Phase 1：资源库 Item 简化

**目标**：Item 只保留「来源集合 + 抓取适配」，移除具体采集参数。

### 1.1 数据模型

- **Item 保留**：`item_key`, `name`, `channel_key`, `extends_item_key`, `tags`, `description`, `enabled`
- **Item params 仅存来源**：
  - `url_pool`：`params.urls`（URL 列表）
  - `reddit`：`params.subreddits` 或 `params.base_subreddits`（子论坛列表，作为来源）
  - `google_news`：`params.keywords`（关键词作为来源，可空由采集页 override）
  - `policy`：`params.state`（州，作为来源）
  - `market`：来源由采集页 query_terms 提供，item 可空
- **移除**：`params.limit`, `params.start_offset` 等运行时参数 → 由采集页 override

### 1.2 前端表单

- **新增/覆盖 Item**：简化 params 输入
  - 按 `channel_key` 切换：仅展示该 channel 所需的「来源」字段
  - 例如 url_pool → 只填 urls；reddit → 只填 subreddits
- **新增 URL 来源项**：保持现状（已是简化形态）

### 1.3 后端

- `run_item_by_key` 的 params merge 顺序：`channel.default_params` + `item.params`（仅来源）+ `ingest_config`（结构）+ `override_params`（采集页）
- 各 channel handler 必须能接受「来源为空、由 override 补充」的情况

---

## Phase 2：采集配置（Ingest Config）

**目标**：统一管理需特定结构的访问（论坛结构、子论坛、平台等）及采集事件。

### 2.1 数据模型

- 新增表 `ingest_config`（或复用/扩展现有）：
  - `project_key`, `config_key`（如 `social_forum`, `reddit_default`）
  - `config_type`：`structure` | `schedule`
  - `payload`：JSONB，如 `{ "platforms": ["reddit"], "base_subreddits": [...], "enable_subreddit_discovery": true }`
- 或：项目级 JSON 配置文件，由 API 读写

### 2.2 API

- `GET /api/v1/ingest/config?project_key=xxx`：返回当前项目采集配置
- `POST /api/v1/ingest/config`：upsert 采集配置

### 2.3 前端（采集配置 Tab）

- 论坛结构：platforms、base_subreddits、enable_subreddit_discovery
- 采集事件/调度：占位，后续实现
- 其他结构配置：占位

### 2.4 运行时的 params 合并

- `run_item_by_key` 增加一步：读取 `ingest_config`，按 `config_key` 或 channel 类型注入结构参数
- 合并顺序：`channel.default_params` + `item.params` + `ingest_config.structure` + `override_params`

---

## Phase 3：采集页承载运行时参数

**目标**：采集页作为唯一运行时参数入口，全部通过 override_params 传递。

### 3.1 已有

- `buildOverrideParamsFromForm()` 已收集：limit、query_terms、start_offset、days_back、language、provider、enable_extraction
- 需补充：base_subreddits、platforms、enable_subreddit_discovery（若仍保留在采集页作为「本次运行」覆盖，否则从 ingest_config 读取）

### 3.2 策略

- **方案 A**：论坛结构只在 采集配置，采集页不展示；运行时从 ingest_config 读取
- **方案 B**：采集页保留论坛结构控件，作为本次运行的 override，优先级高于 ingest_config
- 建议：Phase 2 先实现 ingest_config 存储，采集页控件保留，buildOverrideParamsFromForm 继续传 base_subreddits 等，后续可切换为仅从 config 读

---

## Phase 4：Channel 定义与 Handler 对齐

**目标**：Channel = 可访问性适配，handler 只关心「如何访问」，参数由上层合并后传入。

### 4.1 检查项

- `url_pool`：已符合，params.urls 为来源，无其他必须参数
- `reddit`：需 subreddits 或 keywords，可由 item 或 override 提供
- `google_news`：需 keywords，可由 item 或 override 提供
- `policy`：需 state，应由 item 提供（来源）
- `market`：需 keywords/query_terms，由 override 提供

### 4.2 文档

- 更新 `RESOURCE_LIBRARY_DEFINITION.md`，补充各 channel 的「来源」字段说明
- 在 `INGEST_ARCHITECTURE.md` 中引用资源库定义

---

## Phase 5：资源库页面整理

**目标**：信息源库 Tab 聚焦「来源 + 适配」，采集配置 Tab 承载结构配置。

### 5.1 信息源库

- 通道列表、来源项列表：保持
- 新增 URL 来源项：保持
- 新增/覆盖 Item：按 Phase 1 简化，按 channel 展示对应来源字段

### 5.2 采集配置

- 论坛结构表单 + 保存
- 采集事件：占位
- 其他结构：占位

### 5.3 采集页

- 来源库查询、一般查询：保持
- 确保 buildOverrideParamsFromForm 覆盖所有运行时参数

---

## 实施顺序

| 阶段 | 内容 | 依赖 |
|------|------|------|
| 1.1 | ingest_config 表 + API + 采集配置 Tab 表单 | - |
| 1.2 | run_item_by_key 合并 ingest_config | 1.1 |
| 2.1 | Item 表单按 channel 简化（仅来源字段） | - |
| 2.2 | 各 channel handler 兼容「来源由 override 补充」 | - |
| 3.1 | 文档更新、联调验证 | 1.x, 2.x |

---

## 验收标准

1. Item 仅包含来源集合 + channel_key，无 limit/start_offset 等运行时参数
2. 论坛结构等在采集配置 Tab 管理，可保存、可被 run 时读取
3. 采集页表单参数全部通过 override_params 传入
4. 运行来源库项：merge 顺序正确，各 channel 可正常执行
