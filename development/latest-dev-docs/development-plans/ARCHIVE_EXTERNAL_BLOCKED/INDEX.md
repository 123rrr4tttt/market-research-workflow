# ARCHIVE_EXTERNAL_BLOCKED - 外部条件阻塞开发计划

更新时间：2026-05-22（PST）

本目录用于存放已经完成仓内确定性门禁、但剩余验收依赖外部运行时、公网 replay、生产数据、真实租户环境或人工 review 的开发计划。它们不继续占用 `CURRENT_DEV` 的 `partial` 指标；重新进入当前开发前，必须先补齐对应外部条件或开新主题。

## 迁入标准

- 仓内代码、fixture、manifest、readback 或 checker 已能重复验证当前边界
- 剩余 blocker 不可在当前仓库内用确定性测试闭合
- 目录继续留在 `CURRENT_DEV` 会让 `partial` 数虚高，并误导后续 agent 继续补小 gate
- 迁入记录必须写明外部条件、仓内已封证据、恢复条件和验证命令

## 外部阻塞目录

- [2026-03-02 Source Time Window Smart Timestamp Plan](./2026-03-02-source-time-window-smart-timestamp-plan/)
  状态：`external_blocked` / `wave21_checked`。仓内 source-time window、decision-log provenance、sample/provenance readback 已可重复验证；剩余条件是 production data semantic chain 的 live validation、coverage distribution 和 decision-log feature readback。
- [2026-03-04 R41 OpenClaw Autodispatch](./2026-03-04-r41-openclaw-autodispatch/README.md)
  状态：`external_blocked` / `wave21_checked`。仓内 mirror/runtime/handoff checker 已通过；剩余条件是外部 OpenClaw runtime 的真实执行闭环。
- [2026-03-05 Time Statistics Remediation Plan](./2026-03-05-time-statistics-remediation-plan/)
  状态：`external_blocked` / `wave21_checked`。仓内 OPE freshness、decision-log freshness、current-state 和 sample/provenance readback 已封住；剩余条件是生产 freshness/volume/alignment 证据。
- [2026-03-11 Source Library Three-Lane Architecture](./2026-03-11-source-library-three-lane-architecture/)
  状态：`external_blocked` / `wave21_checked`。仓内 deterministic review batch 1-4、legacy 410 replacement、relevance queue 与 taxonomy readiness 已可重复验证；剩余条件是 live source collection、public replay 与 completed human review。
- [2026-03-14 Search Chain Source-Library Mounting Audit](./2026-03-14-search-chain-source-library-mounting-audit/)
  状态：`external_blocked` / `wave21_checked`。仓内 mount governance 与 deterministic review batch 已封住；剩余条件是 public replay、human review 和真实治理动作读回。
- [2026-03-14 Source-Library Adapter Capability Remediation](./2026-03-14-source-library-adapter-capability-remediation/)
  状态：`external_blocked` / `wave21_checked`。仓内 parser-profile、taxonomy/review readiness 与 deterministic review batch 已封住；剩余条件是 public replay 与人工 relevance review。
- [2026-03-14 Time Semantics Density Merged Plan](./2026-03-14-time-semantics-density-merged-plan/README.md)
  状态：`external_blocked` / `wave21_checked`。仓内 target-overlap、OPE contract、decision-log contract 与 sample/provenance readback 已封住；剩余条件是 production semantic evidence 与 release gate 接入。

## 保留在 CURRENT_DEV 的相邻目录

- [2026-03-07 Docs Root Restructuring](../CURRENT_DEV/2026-03-07-docs-root-restructuring/01_docs-root-restructuring-mapping-2026-03-07.md)：`retained_partial`。剩余是 repo-local docs integration，不是外部条件。
- [2026-03-15 Frontend Three-Layer Rewrite](../CURRENT_DEV/2026-03-15-frontend-three-layer-rewrite/README.md)：`retained_partial`。剩余业务文案与兼容层迁移规模仍大。
- [2026-03-25 Source-Library Ingest Minimal Migration](../CURRENT_DEV/2026-03-25-source-library-ingest-minimal-migration/01_source-library-ingest-minimal-migration-plan-2026-03-25.md)：`retained_partial`。仍有 `python_library_cli_container_runners_not_enabled` 仓内 runner 范围 blocker。

## 返回

- [CURRENT_DEV](../CURRENT_DEV/INDEX.md) - 当前仍可作为现行入口的未封口开发计划
- [ARCHIVE_CLOSED](../ARCHIVE_CLOSED/INDEX.md) - 已收口开发计划
- [ARCHIVE_RETIRED](../ARCHIVE_RETIRED/INDEX.md) - 已退场 / 过时开发计划
