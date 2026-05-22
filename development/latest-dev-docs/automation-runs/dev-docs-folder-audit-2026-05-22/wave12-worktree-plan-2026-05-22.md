# Wave12 Worktree Plan (2026-05-22)

Status: seeded by supervisor after Wave11 integration.

Wave11 left `CURRENT_DEV` at `partial=35`, `not_closed=0`, `no_closure_claim=0`. Wave12 continues the folder-by-folder audit and implementation pass. The selected slices are chosen from current `partial` rows that still carry live-runtime, productionization, `doc_stale`, `doc_drift`, `external_gap`, or broader consumer-surface gaps.

This wave does not archive directories. It lands repo-controlled contracts, code paths, tests, and topic-local evidence, then lets the supervisor synchronize shared indexes once after all worker branches are reviewed.

Worker branches must not edit shared navigation indexes; the supervisor integration lane owns final status/index sync.

Forbidden shared indexes for workers:

- `development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md`
- `development/latest-dev-docs/development-plans/CURRENT_DEV/STATUS_AUDIT_2026-04-07.md`
- `development/latest-dev-docs/development-plans/INDEX.md`
- `development/latest-dev-docs/README.md`
- `development/latest-dev-docs/MERGED_OVERVIEW.md`

## Current Audit Summary

| Status | Count | Wave12 treatment |
|---|---:|---|
| `partial` | 35 | Continue implementation, retain explicit blockers, do not claim full closure without matching evidence |
| `not_closed` | 0 | No current rows |
| `no_closure_claim` | 0 | No current rows |

High-priority audit labels in the current queue:

- `doc_stale`: time-statistics remediation needs current code/evidence reconciliation before stronger closure language.
- `doc_drift`: graph 3D / graph node / `MERGED_OVERVIEW` need new evidence or refreshed status text.
- `external_gap` / `external_blocked`: R41 OpenClaw, crawler public replay, and provider/runtime availability need explicit bounded gates instead of optimistic closure.
- `live runtime gap`: search/vector provider quality, live DB graph rollout, live scheduler/canary, and source-library live replay remain outside prior deterministic gates.

## Branch Matrix

| Branch | Worktree | Topic Slice | Owned Write Scope |
|---|---|---|---|
| `codex/devdocs-wave12-vector-provider-readiness` | `devdocs-wave12-vector-provider-readiness` | Open-source platform / global vectorization / local open search / OSS node provider readiness | search/vector provider readiness code, `ops/search-lab` or local-index checks, focused tests, topic-local evidence |
| `codex/devdocs-wave12-graph-live-smoke-gate` | `devdocs-wave12-graph-live-smoke-gate` | Graph 3D / graph node DB rollout / graph editing smoke and live-readiness boundary | graph persistence/projection/frontend smoke gates, graph tests, topic-local evidence |
| `codex/devdocs-wave12-ingest-canary-handoff` | `devdocs-wave12-ingest-canary-handoff` | Ingest platform / single URL / meaningful guardrails canary handoff | ingest frontdoor/guardrail/canary metrics code, tests, topic-local evidence |
| `codex/devdocs-wave12-time-density-log-contract` | `devdocs-wave12-time-density-log-contract` | Source-time / time statistics / time-density decision-log contract | stats/document-query time code, decision-log or freshness gates, tests, topic-local evidence |
| `codex/devdocs-wave12-source-library-review-queue` | `devdocs-wave12-source-library-review-queue` | Source-library adapter / mounting audit / three-lane / minimal migration review queue | source-library governance/relevance-review queue code, tests, topic-local evidence |
| `codex/devdocs-wave12-frontend-business-string-audit` | `devdocs-wave12-frontend-business-string-audit` | Dual frontend / i18n theme / three-layer rewrite business-string audit | frontend audit script, module shell or i18n/theme tests, topic-local evidence |
| `codex/devdocs-wave12-typed-knowledge-persistence-api` | `devdocs-wave12-typed-knowledge-persistence-api` | Typed knowledge organization / writing workbench persistence and API boundary | typed-knowledge and writing service/API contracts, tests, topic-local evidence |
| `codex/devdocs-wave12-docs-root-content-plan` | `devdocs-wave12-docs-root-content-plan` | Docs root restructuring / `MERGED_OVERVIEW` / follow-up folderization content plan | docs-root manifests/checkers and topic-local evidence only; no broad move without supervisor merge |
| `codex/devdocs-wave12-openclaw-autodispatch-gate` | `devdocs-wave12-openclaw-autodispatch-gate` | R41 OpenClaw autodispatch external-gap gate and retained no-op evidence | R41 checker/evidence code and topic-local docs; no edits to external OpenClaw workspace |

## Non-Selected Current Rows

All 35 `partial` rows were considered. Rows not explicitly named above remain active and should keep their current status until a later wave lands stronger evidence. Crawler public replay and parallel worker runtime stay `external_blocked` unless the worker can prove the real external condition in the same branch.

## Integration Rule

Workers return:

- `结果`
- `改动文件`
- `验证状态`
- `风险`

The supervisor merges clean worker branches, updates shared indexes once, then reruns status evidence, link checks, the Wave12 plan gate, and focused test/checker gates.
