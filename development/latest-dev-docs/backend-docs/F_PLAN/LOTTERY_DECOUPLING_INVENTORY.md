# 彩票耦合点清单（解耦基线）

> 最后更新：2026-02 | 文档索引：`docs/README.md`

**当前状态**：`subprojects/online_lottery` 与 `project_customization/projects/online_lottery` 已存在，部分领域逻辑已迁入；ingest 层仍保留彩票专属入口与默认值，待逐步转发至子项目。

## 高优先级（直接影响业务行为）

- `main/backend/app/services/ingest/market.py`
  - 州与玩法分发直接写死在 `ADAPTERS` / `CA_GAME_MAP`。
  - `CA`、`NY`、`TX` 与彩票适配器耦合，属于在线彩票项目领域逻辑。
- `main/backend/app/services/ingest/news.py`
  - `collect_calottery_news` / `collect_calottery_retailer_updates` 为彩票专属流程。
  - `collect_reddit_discussions` 默认 `subreddit="Lottery"`。
- `main/backend/app/services/ingest/keyword_library.py`
  - 过滤词集合 `_LOTTERY_TOKENS` 为彩票领域策略，不应位于骨架层默认行为。
- `main/backend/app/api/ingest.py`
  - 暴露 `/news/calottery` 和 `/news/calottery/retailer` 专属接口。

## 中优先级（可配置项与呈现层）

- `信息源库/global/channels/default-channels.json`
  - 默认值使用 `Lottery`、`lottery regulation`、`CA`。
- `信息源库/global/items/default-items.json`
  - 默认 item key 与参数采用彩票语义。
- `main/frontend/templates/app.html`
  - 侧栏菜单静态写死，项目差异无法按映射动态切换。

## 迁移目标

- 迁入 `main/backend/app/subprojects/online_lottery`
  - 领域常量（关键词、默认 subreddit、默认州、玩法映射）
  - 彩票专属服务拼装（news/market/policy/social）
- 迁入 `main/backend/app/project_customization/projects/online_lottery`
  - workflow/menu/llm/fields 映射
  - 项目级 source library 文件映射

## 兼容策略

- 保留现有 API 名称与函数签名，函数体改为转发到 `online_lottery` 项目服务。
- 通过 `project_customization` fallback 保证非彩票项目行为稳定。
