# Wave13 Worktree Plan (2026-05-22)

Status: seeded by supervisor after Wave12 integration.

Wave12 left `CURRENT_DEV` at `partial=35`, `not_closed=0`, `no_closure_claim=0`. Wave13 continues the folder-by-folder audit and implementation pass, with emphasis on rows that still lack Wave12 evidence or still carry live-provider, live-scheduler, public-replay, `doc_stale`, `doc_drift`, or consumer-surface gaps.

This wave does not archive directories by default. It lands repo-controlled contracts, code paths, tests, and topic-local evidence. The supervisor integration lane owns shared index synchronization after all worker branches are reviewed.

Worker branches must not edit shared navigation indexes.

Forbidden shared indexes for workers:

- `development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md`
- `development/latest-dev-docs/development-plans/CURRENT_DEV/STATUS_AUDIT_2026-04-07.md`
- `development/latest-dev-docs/development-plans/INDEX.md`
- `development/latest-dev-docs/README.md`
- `development/latest-dev-docs/MERGED_OVERVIEW.md`

## Current Audit Summary

| Status | Count | Wave13 treatment |
|---|---:|---|
| `partial` | 35 | Continue implementation, retain explicit blockers, do not claim full closure without matching evidence |
| `not_closed` | 0 | No current rows |
| `no_closure_claim` | 0 | No current rows |

High-priority audit labels in the current queue:

- `doc_stale`: time-statistics remediation needs current code/evidence reconciliation before stronger closure language.
- `doc_drift`: graph 3D / graph node / `MERGED_OVERVIEW` need refreshed evidence or status text before closure language.
- `external_gap` / `external_blocked`: R41 OpenClaw, crawler public replay, provider runtime availability, and worker runtime availability need explicit bounded gates instead of optimistic closure.
- `live runtime gap`: search/vector provider quality, live DB graph rollout, live scheduler/canary, source-library live replay, and AgentCore live provider availability remain outside prior deterministic gates.

## Branch Matrix

| Branch | Worktree | Topic Slice | Owned Write Scope |
|---|---|---|---|
| `codex/devdocs-wave13-llm-crawler-high-js-replay` | `devdocs-wave13-llm-crawler-high-js-replay` | LLM crawler unified frontdoor high-JS/public replay boundary | LLM crawler/frontdoor replay readiness code, checker/tests, topic-local evidence |
| `codex/devdocs-wave13-symbolic-search-provider-quality` | `devdocs-wave13-symbolic-search-provider-quality` | Agent symbolic batch search live provider quality boundary | symbolic search quality/readiness code, provider-quality fixtures, focused tests, topic-local evidence |
| `codex/devdocs-wave13-structured-data-api-migration` | `devdocs-wave13-structured-data-api-migration` | Data structured service modularization API/search endpoint migration | structured document/query/search endpoint boundary code, checker/tests, topic-local evidence |
| `codex/devdocs-wave13-consumer-dashboard-extraction` | `devdocs-wave13-consumer-dashboard-extraction` | Consumer-side modularization admin/dashboard extraction | consumer facade/dashboard/admin extraction code or static contract checker, tests, topic-local evidence |
| `codex/devdocs-wave13-agentcore-live-provider-readiness` | `devdocs-wave13-agentcore-live-provider-readiness` | LLM service and Agent platform live provider availability | AgentCore provider readiness contract/checker, tests, topic-local evidence |
| `codex/devdocs-wave13-long-cycle-scheduler-readiness` | `devdocs-wave13-long-cycle-scheduler-readiness` | Ingest digestion long-cycle automation live scheduler boundary | scheduler readiness/dry-run code, checker/tests, topic-local evidence |
| `codex/devdocs-wave13-crawler-public-replay-gate` | `devdocs-wave13-crawler-public-replay-gate` | Crawler source expansion public replay / 45-site external boundary | crawler replay manifest/checker code, tests, topic-local evidence |
| `codex/devdocs-wave13-abstract-folderization-closure` | `devdocs-wave13-abstract-folderization-closure` | Abstract planning folderization retained current entry | folderization status/evidence docs, optional checker, topic-local evidence only |
| `codex/devdocs-wave13-merged-overview-drift-gate` | `devdocs-wave13-merged-overview-drift-gate` | CURRENT_DEV `MERGED_OVERVIEW` drift reconciliation | current-dev `MERGED_OVERVIEW/` topic docs/checker/evidence; no top-level `MERGED_OVERVIEW.md` edits in worker |

## Non-Selected Current Rows

All 35 `partial` rows were considered. Rows not explicitly named above remain active and keep their current status until a later wave lands stronger evidence. Graph live DB/WebGL, provider-live quality, and external replay conditions remain `partial`/blocked unless a worker proves the real condition in the same branch.

## Integration Rule

Workers return:

- `结果`
- `改动文件`
- `验证状态`
- `风险`

The supervisor merges clean worker branches, updates shared indexes once, then reruns status evidence, link checks, the Wave13 plan gate, and focused test/checker gates.
