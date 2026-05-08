# Wave 0 Baseline Freeze Task Pool

Updated: 2026-04-07 PST

## Purpose

This file is the kickoff pack for the first exploration wave of the
parallel-agent orchestration topic.

Wave 0 does not implement features. It freezes:

1. the real executable task pool
2. the ownership split for later coding waves
3. the topics that should be excluded from near-term implementation

## Shared Rule

Every Wave 0 subagent must read:

- [../INDEX.md](../INDEX.md)
- [../STATUS_AUDIT_2026-04-07.md](../STATUS_AUDIT_2026-04-07.md)
- [./01_parallel-agent-wave-orchestration-plan-2026-04-07.md](./01_parallel-agent-wave-orchestration-plan-2026-04-07.md)

Every Wave 0 subagent returns only:

- `结果`
- `改动文件`
- `验证状态`
- `风险`
- `下一阻塞`

## Agent A. Reliability And Quality Baseline

- 目标:
  - freeze current gaps around ingest quality, frontdoor cleaning,
    search candidate quality, `project_key`, testing, and observability
- 边界:
  - backend quality and reliability only
- 验收:
  - one gap list
  - one must-close-first list
  - one validation-gate recommendation
- 禁止项:
  - do not redesign source-library runtime boundaries
- 推荐入口:
  - `backend-core/main/STANDARD_INGEST_WORKFLOWS_2026-03-02.md`
  - `backend-core/main/TEST_SCENARIO_MATRIX.md`
  - `backend-core/E_OPS/OBSERVABILITY_RELIABILITY_BASELINE_2026-03-04.md`

## Agent B. Source-Library / Ingest Mainline Baseline

- 目标:
  - freeze the current state of three-lane, adapter remediation,
    consumer modularization, and external item work
- 边界:
  - source-library, ingest, frontdoor, consumer-side modularization
- 验收:
  - one lane split for Wave 2
  - one blocker list for `AT-EXT-*`
- 禁止项:
  - do not reopen Wave 1 gate design
- 推荐入口:
  - `2026-03-11-source-library-three-lane-architecture/`
  - `2026-03-14-source-library-adapter-capability-remediation/`
  - `2026-03-25-source-library-ingest-minimal-migration/`

## Agent C. Frontend Modern Baseline

- 目标:
  - freeze the current half-refactor state of hot pages and shell
- 边界:
  - `WritingWorkbenchPage`, `GraphPage`, shell/platform edges
- 验收:
  - one page-scope split for Wave 3
  - one shell-scope split for Wave 3
- 禁止项:
  - do not redesign backend contracts from frontend analysis
- 推荐入口:
  - `2026-03-15-frontend-three-layer-rewrite/`
  - `2026-03-07-frontend-i18n-theme-modularization/`
  - `main/frontend-modern/src/pages`

## Agent D. LLM / Writing / Graph / Typed-Knowledge Baseline

- 目标:
  - freeze the current state of writing loop, LLM platformization,
    graph editing/reporting, and typed knowledge organization
- 边界:
  - writing, llm platform, graph handoff, typed knowledge
- 验收:
  - one contract dependency order for Wave 4
  - one do-not-mix list across these themes
- 禁止项:
  - do not absorb frontend shell refactor into this lane
- 推荐入口:
  - `2026-03-07-writing-workbench-evolution/`
  - `2026-03-07-llm-service-and-agent-platformization/`
  - `2026-03-07-graph-editing-and-reporting/`

## Agent E. Documentation Governance Baseline

- 目标:
  - freeze the documentation drift list and remove non-actionable topics
    from the near-term pool
- 边界:
  - `CURRENT_DEV`, top-level dev-doc navigation, status drift
- 验收:
  - one active-topic list
  - one excluded-topic list
  - one navigation update recommendation
- 禁止项:
  - do not move directories between archive states in Wave 0
- 推荐入口:
  - `development/latest-dev-docs/README.md`
  - `development/latest-dev-docs/MERGED_OVERVIEW.md`
  - `development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md`

## Wave 0 Exit Gate

Wave 0 is complete only when:

1. one shared executable task pool exists
2. placeholder and retired topics are excluded from near-term coding
3. every later coding lane has a clear owner boundary
4. no Wave 1 or Wave 2 worker needs to rediscover basic repo topology
