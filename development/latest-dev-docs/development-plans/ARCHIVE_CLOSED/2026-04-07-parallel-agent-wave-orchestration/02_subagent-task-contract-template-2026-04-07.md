# Subagent Task Contract Template

Updated: 2026-04-07 PST

## Purpose

This template is the default kickoff contract for high-autonomy,
mid-constraint subagent work in this repository.

The goal is to avoid two failure modes:

1. the main agent over-specifies local implementation and removes
   subagent initiative
2. the main agent sends only a task label and the worker drifts away
   from the repo's actual topic contracts

## Required Fixed Fields

Every subagent task contract must include:

- `任务 ID`
- `任务标题`
- `所属主题路径`
- `所属波次`
- `子 Agent`
- `目标`
- `边界`
- `禁止项`
- `推荐入口`
- `验收`
- `结果`
- `改动文件`
- `验证状态`
- `风险`
- `下一阻塞`

## Section Order

1. task metadata
2. goal
3. inputs and dependencies
4. boundaries
5. execution rules
6. acceptance and validation
7. fixed return format

## Usage Rules

1. the main agent should provide only the minimum contract needed to keep
   the worker inside the right boundary
2. the worker must read topic-local plan / atomic / reference documents
   itself
3. the worker should stop on blocker instead of inventing new
   cross-topic structure
4. ownership must be explicit when the worker is allowed to edit files

## Markdown Template

```md
# [HIGH-AUTONOMY/MID-CONSTRAINT] Subagent Task Contract

## 1. 任务基本信息
- 任务 ID:
- 任务标题:
- 所属主题路径:
- 所属波次:
- 子 Agent:

## 2. 目标
- 目标:
- 成果:
  - 

## 3. 输入与依赖
- 来源真相:
  - Plan:
  - Atomic:
  - Reference:
- 输入:
  - 
- 依赖:
  - 

## 4. 边界
- 包含:
  - 
- 不包含:
  - 
- 禁止项:
  - 
- 推荐入口:
  - 

## 5. 执行规则
- 并行前提:
  - 
- 写入边界（ownership）:
  - 
- 冲突控制:
  - 与以下任务/文件同波次禁止并行:
  - 

## 6. 验收标准
- 可观测交付:
  - 
- 最小验证:
  - 
- 完成判定:
  - 完成:
  - 阻塞:
  - 通过标准:
  - 

## 7. 固定回报
- 结果:
- 改动文件:
- 验证状态:
- 风险:
- 下一阻塞:
```

## Minimum Review Checklist

Before a contract is sent to a worker, the main agent should verify:

1. the worker has a topic root path
2. the worker has no overlapping write scope with another live worker
3. the worker has a minimum validation rule
4. the worker is not being asked to redesign adjacent themes
