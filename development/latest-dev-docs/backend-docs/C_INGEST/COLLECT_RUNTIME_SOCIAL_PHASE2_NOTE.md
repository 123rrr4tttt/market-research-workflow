# 统一采集执行通道：`social.py`（待迁移）保留说明

## 目的
记录当前主干统一采集执行通道重构的边界与下一步方向，明确 **`main/backend/app/services/ingest/social.py` 尚未纳入 `collect_runtime`**，避免后续误判为已完成。

## 当前状态（截至本次改动）
- 已接入统一执行骨架（`collect_runtime`）的首批通道：
  - `market`
  - `policy/regulation`
  - `source-library/run`
  - `url_pool`（通过来源库 URL 类适配链路）
- `process/list`、`process/history` 已开始透传/展示 `display_meta`（向后兼容）
- 任务管理前端已优先读取 `display_meta`，旧任务名分支作为兜底

## 尚未完成（本说明重点）
- `main/backend/app/services/ingest/social.py` 的社交采集/舆情采集执行链路 **尚未迁移** 到 `collect_runtime`
- 当前 `social.py` 仍保留原执行框架（仅做了与 `display_meta` 相关的兼容增强时，不代表已完成统一通道改造）

## 为什么暂缓 `social.py`
- 社交采集包含平台差异（如 subreddit/平台发现、平台参数、联想词/社交关键词生成）更复杂
- 需要在适配器层保留特化逻辑，但不能破坏主干统一协议
- 若直接“套骨架”但不先抽清平台差异，容易造成协议假统一、实际仍分叉

## 下一阶段（Phase 6）迁移原则
- 只在主干新增 `social` 适配器（例如 `collect_runtime/adapters/social.py`）
- 保持对外 API 路径与请求字段语义不变（可增字段，不破坏旧字段）
- 分项目仅提供提示词/规则/handler，不接管执行协议
- 统一由主干写入：
  - `CollectRequest`
  - `CollectResult`
  - `display_meta`
  - 任务生命周期记录（开始/完成/失败）

## `social.py` 迁移完成的验收标志（后续）
- `social/sentiment` 等社交采集入口通过 `collect_runtime` 执行
- `EtlJobRun.params.display_meta.channel` 对社交任务稳定输出（如 `social.sentiment`）
- `process` 页面无需按任务名特判即可正确展示社交任务摘要与结果统计

## 注意（架构边界）
- 本说明仅记录方向与边界，不改变当前 API 协议
- 不允许通过分项目定制覆盖主干统一执行协议
