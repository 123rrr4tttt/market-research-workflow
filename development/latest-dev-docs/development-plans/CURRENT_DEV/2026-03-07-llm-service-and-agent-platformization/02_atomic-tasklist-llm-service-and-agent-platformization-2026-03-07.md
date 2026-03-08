# Atomic Task List: LLM Service and Agent Platformization (2026-03-07)

## 定位

本任务清单用于把多模型接入、agent 能力和长期框架接入要求整理成后续可继续细化的主题文档。

## 全局规则

- 先确认现有模型服务基线，再定义平台化增量。
- 模型服务层和业务能力层要分开写。
- 长期框架接入只先写阶段策略，不提前写重。

## Task A1: Confirm LLM Baseline

- 目标: 盘点现有模型接入、配置、调用方式与 openclaw 相关上下文。
- 输出:
  - one baseline summary
  - one platformization gap list
- 验收:
  - 当前能力与目标增量区分清楚

## Task A2: Freeze Service Layer Boundary

- 目标: 明确 provider、capability、route、trace 等统一服务层视图。
- 验收:
  - 至少一个统一抽象样例
  - 与具体业务主题边界明确

## Task A3: Clarify Agent Position

- 目标: 明确 agent 在平台中优先落在哪类场景和接口。
- 验收:
  - 至少一个 agent 使用场景
  - 至少一个长期框架阶段策略

## Task A4: Define Minimal Validation

- 目标: 预留后续实现的最小验证步骤。
- 验收:
  - 至少一个多模型接入验证
  - 至少一个 agent 或 trace 相关验证
