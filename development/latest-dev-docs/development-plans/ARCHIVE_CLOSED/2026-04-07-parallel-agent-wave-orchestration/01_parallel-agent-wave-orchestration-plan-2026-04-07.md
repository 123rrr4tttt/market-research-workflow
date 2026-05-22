# Parallel Agent Wave Orchestration Plan

Updated: 2026-04-07 PST

## Purpose

This file turns the current repo-wide development direction into a
wave-based parallel execution plan where subagents do the local
interpretation work and the main agent only freezes boundaries,
conflict rules, and gates.

This is not a greenfield taskboard. It assumes:

1. the current source of truth lives in `development/latest-dev-docs`
2. most themes are already `partial` or `not_closed`
3. later implementation should consume topic-local plans instead of
   rebuilding design from scratch

## Mandatory Shared Context

Every subagent must inherit these entrypoints:

- [../../../README.md](../../../README.md)
- [../INDEX.md](../INDEX.md)
- [../../CURRENT_DEV/STATUS_AUDIT_2026-04-07.md](../../CURRENT_DEV/STATUS_AUDIT_2026-04-07.md)
- `/Users/wangyiliang/market-research-workflow/README.md`
- `/Users/wangyiliang/market-research-workflow/main/backend/app`
- `/Users/wangyiliang/market-research-workflow/main/frontend-modern/src`

The main agent should not replace these with a long custom briefing.

## Global Agent Contract

Each subagent kickoff must contain only:

- `目标`
- `边界`
- `验收`
- `禁止项`
- `推荐入口`

Each subagent must then:

1. read the linked topic documents and local code itself
2. derive the concrete implementation shape from the repo
3. stop when blocked by conflict, missing contract, or ownership overlap
4. return only:
   - `结果`
   - `改动文件`
   - `验证状态`
   - `风险`
   - `下一阻塞`

## Parallelism Ceiling

- analysis wave: up to `6` parallel subagents
- coding wave: up to `4` writing subagents + `1` reviewer subagent
- ownership rule: only one writing subagent may own the same high-conflict
  file set at a time

## Wave Layout

### Wave 0. Baseline Freeze And Task Ownership

Goal:

- build one repo-grounded execution pool
- exclude placeholders, retired topics, and doc-only noise from the
  near-term implementation set

Workers:

- Agent A: reliability and quality baseline
- Agent B: source-library / ingest baseline
- Agent C: frontend modern baseline
- Agent D: LLM / writing / graph / typed-knowledge baseline
- Agent E: documentation governance baseline

Exit gate:

- one shared executable task pool exists
- placeholder topics such as `2026-03-24-frontend-visual-layering`
  are excluded from implementation waves

### Wave 1. Foundation Closure

Goal:

- close the reliability base before business expansion

Lanes:

- Lane 1A: ingest quality and frontdoor cleaning
- Lane 1B: multi-tenant boundary and runtime governance
- Lane 1C: unified search enhancement
- Lane 1D: test and gate upgrade
- Lane 1E: API envelope convergence

Required order inside the wave:

1. unify search follows:
   - same-domain and tracking filtering
   - RSS / Atom hardening
   - sitemapindex recursion
   - fine-grained `source_ref` write-back
2. gate upgrade cannot be treated as optional documentation work

Exit gate:

- input quality
- tenant boundary
- contract shape
- regression gate

All four must be green before later waves start.

### Wave 2. Source-Library / Ingest Mainline Closure

Goal:

- close the repo's current main backend corridor

Lanes:

- Lane 2A: source-library three-lane and adapter remediation
- Lane 2B: data-structured and consumer modularization
- Lane 2C: external project powered item

Execution rule:

- `2A` and `2B` may start in parallel
- `2C` must wait for the boundary freeze from `2A`
- reviewer coverage is mandatory for backward compatibility

### Wave 3. Frontend Modern Convergence

Goal:

- reduce the remaining half-refactor state in hot pages and shell glue

Lanes:

- Lane 3A: `WritingWorkbenchPage`
- Lane 3B: `GraphPage`
- Lane 3C: shell and cross-page platform edges

Execution rule:

- `WritingWorkbenchPage` and `GraphPage` own page-level write scopes
- shell work must not reopen page-local product contracts

### Wave 4. LLM / Writing / Graph / Typed-Knowledge Platform Closure

Goal:

- freeze the shared platform boundary after frontend page edges are stable

Lanes:

- Lane 4A: LLM platformization
- Lane 4B: writing evolution
- Lane 4C: typed knowledge and graph reporting

Execution rule:

- analysis may run in parallel
- implementation freezes behind the `4A` contract vocabulary

### Wave 5. Business Expansion

Goal:

- resume business-facing capability growth on top of closed contracts

Candidates:

- Perplexity / external semantic retrieval
- RAG and reporting closure
- company / product / commerce object ingestion
- crawler source expansion
- ingest digestion and long-cycle automation

Rule:

- no lane in Wave 5 may reopen foundational contracts from Waves 1-4

## Validation Gates

### Wave 1 Gate

- backend unit / integration / contract
- frontdoor / postprocess regression
- scenario-matrix critical cases
- observability smoke

### Wave 2 Gate

- source-library resolver / item / frontdoor / runtime regression
- minimum integration checks for new item execution corridors

### Wave 3 Gate

- `npm run lint`
- Storybook state-matrix review
- Playwright runtime smoke
- hot-page real-state regression

### Wave 4 Gate

- writing API regression
- LLM action regression
- workflow graph LLM node regression
- graph handoff contract verification

### Wave 5 Gate

- end-to-end chain:
  `ingest -> discovery/search -> writing/report`

## Do-Not-Parallelize Rules

The following should stay serialized inside their own topic roots:

1. any two tasks rewriting the same high-conflict API contract
2. any two tasks rewriting the same hot page container
3. `external project powered item` runtime work before source-library
   boundary freeze
4. Wave 5 feature work before Wave 1 regression gates are green

## Immediate Next Use

1. use [03_wave0-baseline-freeze-task-pool-2026-04-07.md](./03_wave0-baseline-freeze-task-pool-2026-04-07.md)
   as the kickoff pack for the first exploration wave
2. use
   [02_subagent-task-contract-template-2026-04-07.md](./02_subagent-task-contract-template-2026-04-07.md)
   for every subagent assignment
3. once Wave 0 is complete, create lane-local execution documents inside
   the original topic roots instead of cloning this plan into new folders
