# Atomic Task List: Crawler Source Expansion (2026-03-07)

## 定位

本任务清单用于把来源扩张、新型抓取能力和质量治理要求整理成后续可继续细化的主题文档。

## 全局规则

- 先确认现有来源缺口，再谈新增来源。
- 先定义统一接入边界，再谈具体外部项目。
- 质量治理与去重规则必须同一阶段写清。

## Task A1: Confirm Source Baseline

- 目标: 盘点现有来源类型、来源空白和优先级。
- 输出:
  - one source inventory summary
  - one priority gap list
- 验收:
  - 至少说明一类最需要补的来源

## Task A2: Freeze Source Adapter Boundary

- 目标: 明确新型爬虫或来源接入器的统一边界。
- 验收:
  - 至少一个接入样例
  - 不同来源类型能放在同一接口口径下讨论

## Task A3: Define Quality Governance

- 目标: 明确质量评估、去重、稳定性检查的最低规则。
- 验收:
  - 至少一个质量检查点
  - 至少一个去重或冲突处理点

## Task A4: Define Minimal Validation

- 目标: 预留后续实现的最小验证步骤。
- 验收:
  - 至少一个新来源接入验证
  - 至少一个来源到下游 ingest 的连接验证
