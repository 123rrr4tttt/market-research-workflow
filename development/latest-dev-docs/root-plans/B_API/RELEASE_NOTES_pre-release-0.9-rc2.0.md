# 预发布说明：v0.9-rc2.0（2026-02-26）

- 版本类型：`预发布（Pre-release）`
- 版本名称：`v0.9-rc2.0`
- 适用场景：团队联调、资源库/来源库稳定化验证、图谱与结构化回填验证

本版本附带 `demo_proj` 演示数据包与导入脚本，支持仓库内使用与前端直接下载：
- 数据包：`main/backend/seed_data/project_demo_proj_v0.9-rc2.0.sql`（前端下载：`/static/demo/project_demo_proj_v0.9-rc2.0.sql`）
- 导入脚本：`main/backend/scripts/load_demo_proj_seed.sh`（前端下载：`/static/demo/load_demo_proj_seed.sh`）

## 摘要

本版本聚焦“资源库（Resource Pool）+ 来源库（Source Library）+ 主干采集运行时（Collect Runtime）”稳定化，并补齐结构化信息提取、任务管理展示与图谱页面刷新问题。

## 本次重点更新

### 1. 来源库与 Handler 聚类稳定化

- `handler_key` 运行链路已稳定化为来源库 `item` 实体：
  - 自动生成/更新 `handler.cluster.<type>` 项（如 `handler.cluster.rss`、`handler.cluster.search_template`）
  - 统一走 `item_key` 通路执行（同步/异步都支持）
- 资源库页面新增“一键生成/更新 Handler 聚类”按钮：
  - 自动按 `site_entries.entry_type` 批量生成/刷新稳定来源项

## 2. 资源池入库与站点入口发现增强

- 站点入口发现支持批次化异步处理：
  - 先简化池子（合并明显重复站点入口）
  - 再分批执行发现任务
- 批内域名探测改为并发（线程池），显著减少全量发现耗时
- 任务进度可见（`/api/v1/process/{task_id}` 返回 `progress`）
- 入库侧增强关键词能力分类：
  - `supports_query_terms`
  - `keyword_mode`（`search/filter/none`）
- 自动探测增强：
  - 常见搜索路径探测（支持自动识别 `search_template`）
  - 已验证 `arxiv.org` 可自动发现搜索入口模板

## 3. 统一搜索与来源项执行增强

- `unified_search_by_item_payload()` 改为并行执行多个 `site_entries`
  - `handler.cluster.search_template` 不再串行逐条搜索
- 来源库 URL 路由增加关键词感知：
  - 有关键词时优先落到支持关键词的 channel（如 `search_template/rss/sitemap`）
  - 降低无意义回退到 `url_pool` 的概率

## 4. 主干采集运行时（Collect Runtime）统一化推进

- 主干统一采集执行骨架已覆盖首批通道：
  - `search.market`
  - `search.policy`
  - `source_library`
  - `url_pool`（通过来源库链路）
- 任务记录增加统一 `display_meta`
- 任务管理前端优先基于 `display_meta` 展示，兼容旧任务兜底
- 主干采集任务支持自动分批（无需模块侧手工分批）

## 5. 结构化信息提取统一化（主干）

- 明确是“统一结构化信息提取”，不是图谱预生成
- 主干新增统一结构化提取编排（基础层 + 特型叠加）：
  - 基础层：`entities_relations`
  - 特型层：`market / policy / sentiment`
- 已接入主干常见路径（市场/社媒/发现入库）

## 6. 数据管理：结构化信息重提取增强

- `/api/v1/admin/documents/re-extract` 扩展支持主干常见 `doc_type`
  - `market_info`
  - `policy_regulation`
  - `social_sentiment`
  - 等
- 支持分批重提取、补抓正文、空实体结果视为缺失：
  - `batch_size`
  - `fetch_missing_content`
  - `treat_empty_er_as_missing`
- 数据管理页新增按钮：
  - `重提取结构化信息（补齐）`
  - `重提取结构化信息（强制）`

## 7. 图谱与前端页面修复

- 修复图谱页面刷新报错：
  - `Cannot read properties of null (reading 'removeChild')`
  - 原因是 ECharts `dispose()` 与容器 `innerHTML` 清空顺序错误
- 修复任务管理页历史任务面板红底残留（错误样式未复位）

## 8. 已知问题 / 注意事项

- 部分站点入口（例如某些 Reddit RSS）会被目标站点拦截，任务会显示“已完成但含错误项”
- 图谱节点是否有实体连接，取决于来源文档是否有正文及实体提取结果
- `main/backend/.env` 中 `SERPER_API_KEY` 格式错误（引号未闭合）仍需手工修复，否则会影响部分搜索链路

## 8.7 状态同步补充（2026-02-27）

- 本说明不变更版本号，仅补充“第 8 节路线状态”同步口径。
- 根 README 的 `8.x` 已按当前工作区实现状态更新为：
  - `8.1 已完成`；
  - `8.2 已完成最小闭环（模板读取/保存/运行）`；
  - `8.4 / 8.7 / 8.8 进行中`；
  - `8.3 未开始`；
  - `8.5 / 8.6 部分完成`。
- 对应可执行清单与状态口径请以 `plans/status-8x-2026-02-27.md` 与 `main/backend/docs/README.md` 为准。

## 8.8 测试标准化与 CI 门禁增强（2026-03-01）

- 后端测试完成分层标准化：
  - `main/backend/tests/unit`
  - `main/backend/tests/integration`
  - `main/backend/tests/contract`
  - `main/backend/tests/e2e`
- 新增 `pytest` 严格 marker 约束（`main/backend/pytest.ini`）：
  - `unit / integration / contract / e2e / slow / external`
  - 启用 `--strict-markers`
- GitHub Actions 后端测试 workflow 升级为并行 job：
  - `unit-check`
  - `integration-check`
  - `contract-check`（PR 跳过，main/schedule/manual 执行）
  - `e2e-check`（PR 跳过，main/schedule/manual 执行）
  - `docker-check`（保留 compose 测试与失败诊断 artifact）
- 增加 `concurrency`（同一 ref 新运行取消旧运行）和 pip 缓存，加速 CI 反馈。
- 新增 `e2e` 冒烟用例，覆盖：
  - `/api/v1/health`
  - `/api/v1/health/deep`
  - `X-Project-Key` 请求头上下文与 header/query 优先级
- 本地分层验证（`main/backend`）：
  - `pytest -m unit -q`：18 passed
  - `pytest -m integration -q`：17 passed
  - `pytest -m contract -q`：8 passed
  - `pytest -m e2e -q`：4 passed
  - `pytest -q`：47 passed

## 推荐验证清单（v0.9-rc2.0）

1. 资源库页面一键生成/更新 Handler 聚类是否成功生成 `handler.cluster.*` 项
2. 运行 `handler.cluster.search_template` 是否能并行命中多个站点入口
3. 任务管理页是否正确展示 Handler 聚类任务与子任务汇总
4. 图谱页面刷新是否稳定（无 `removeChild` 报错）
5. 数据管理页“重提取结构化信息（补齐）”是否能分批补抓正文并回填结构化结果

## 说明

- 本版本为团队联调预发布，不建议作为长期稳定生产基线
- 发布目标是收敛资源库/来源库/结构化提取/图谱展示主链路问题，为下一版正式版本做准备
