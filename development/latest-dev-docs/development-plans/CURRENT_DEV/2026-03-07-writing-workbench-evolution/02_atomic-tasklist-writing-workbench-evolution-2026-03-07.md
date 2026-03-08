# Atomic Task List: Writing Workbench Evolution (2026-03-07)

## 定位

本任务清单用于把“写作工作台增强需求”整理成后续可继续展开的主题文档，不在这里提前写成完整实施方案。

## 全局规则

- 先复用已有写作工作台设计文档，再补本主题增量。
- 先冻结主链，再讨论扩展能力。
- 图谱、LLM、模板、导出能力要写清边界，不混写。

## Task A1: Confirm Baseline and Delta

- 目标: 明确现有写作工作台文档已经覆盖了什么，本主题新增的增量是什么。
- 输入:
  - `2026-03-07-builtin-writing-workbench-design/*`
  - `抽象规划.md`
- 输出:
  - one baseline summary
  - one delta scope list
- 验收:
  - 不与已有文档重复写同一层内容

## Task A2: Freeze Minimum Writing Flow

- 目标: 明确写作主链最小闭环。
- 输出:
  - 文档打开/编辑
  - 资料卡或图谱联动
  - LLM 动作
  - 内容回写
- 验收:
  - 至少一条完整主链被明确写出

## Task A3: Clarify Extension Boundaries

- 目标: 分别明确模板编辑、图谱小窗、多格式导出属于哪个阶段。
- 验收:
  - 第一阶段与后续阶段边界清楚
  - 不把所有扩展能力塞进同一批次

## Task A4: Define Minimal Validation

- 目标: 为后续实现预留最小验证步骤。
- 验收:
  - 至少一条流程验证
  - 至少一条模板或导出验证
