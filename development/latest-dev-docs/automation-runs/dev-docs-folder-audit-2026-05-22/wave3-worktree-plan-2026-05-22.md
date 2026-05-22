# Wave3 Worktree Plan Skeleton

Run date: 2026-05-22 PST

Status: planned / pending. This file is a coordination skeleton for Wave3 and does not claim completion for any lane.

## Inputs

- [development/latest-dev-docs/README.md](../../README.md)
- [development/latest-dev-docs/MERGED_OVERVIEW.md](../../MERGED_OVERVIEW.md)
- [audit README](./README.md)
- [wave2-worktree-plan-2026-05-22.md](./wave2-worktree-plan-2026-05-22.md)

## Baseline

- Baseline branch: `codex/devdocs-supervisor-seed` after Wave2 integration at `11090eb`.
- Planned integration branch: `codex/devdocs-wave3-integration-2026-05-22`.
- Worktree root: `/Users/wangyiliang/market-research-workflow.worktrees`.
- Supervisor rule: each agent edits only its assigned worktree, does not push, runs the lane gate, and returns `结果/改动文件/验证状态/风险/commit`.
- Status rule: this skeleton uses `planned` only. The supervisor should replace each lane status after merging the actual branch evidence.

## Wave3 Branch Matrix

| Lane | Planned branch | Worktree | Status | Write range | Acceptance gate | Merge order |
|---|---|---|---|---|---|---:|
| A | `codex/devdocs-wave3-lancedb-benchmark` | `wave3-lancedb-benchmark` | planned | `ops/search-lab/**`, `development/latest-dev-docs/automation-runs/local-index-*`, `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-05-14-global-vectorization-general-foundation/**` | deterministic keyword/vector/hybrid benchmark artifact; local_index focused tests or runtime smoke; changed-doc links; `git diff --check` | 2 |
| B | `codex/devdocs-wave3-local-index-evidence-contract` | `wave3-local-index-evidence-contract` | planned | `main/backend/app/services/local_index/**`, `main/backend/tests/**/local_index*`, `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-05-14-global-vectorization-general-foundation/**` | embedding/ranking evidence contract or explicit blocker; focused unit tests; changed-doc links; `git diff --check` | 3 |
| C | `codex/devdocs-wave3-search-provider-closure-replay` | `wave3-search-provider-closure-replay` | planned | `main/backend/app/services/search/**`, `main/backend/tests/**/search*`, `ops/search-lab/**`, `development/latest-dev-docs/automation-runs/search-provider-*`, `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-05-14-local-open-search-provider-isolation/**` | explicit provider trace replay with SearXNG/YaCy evidence or environment blocker separated; search provider tests; changed-doc links; `git diff --check` | 4 |
| D | `codex/devdocs-wave3-backend-response-models` | `wave3-backend-response-models` | planned | `main/backend/app/api/**`, `main/backend/app/schemas/**`, `main/backend/tests/contract/**`, `development/latest-dev-docs/backend-docs/B_API/**` | reduce untyped OpenAPI 200 responses for selected high-value routes; schema inventory contract passes; changed-doc links; `git diff --check` | 5 |
| E | `codex/devdocs-wave3-schema-inventory-refresh` | `wave3-schema-inventory-refresh` | planned | `main/backend/scripts/generate_api_schema_inventory.py`, `main/backend/tests/contract/**schema_inventory*`, `development/latest-dev-docs/backend-docs/B_API/**` | regenerated schema inventory with remaining untyped count and exclusions; contract tests pass; changed-doc links; `git diff --check` | 8 |
| F | `codex/devdocs-wave3-graph-workflow-evidence` | `wave3-graph-workflow-evidence` | planned | `main/backend/**graph**`, `main/frontend-modern/src/**graph**`, `main/frontend-modern/tests/e2e/**`, `development/latest-dev-docs/automation-runs/graph-*`, `development/latest-dev-docs/development-plans/CURRENT_DEV/*graph*/**` | curated workflow graph evidence pack; graph-focused backend/frontend gate; changed-doc links; `git diff --check` | 6 |
| G | `codex/devdocs-wave3-graph-writing-handoff` | `wave3-graph-writing-handoff` | planned | `main/backend/app/api/**writing**`, `main/backend/app/services/**writing**`, `main/frontend-modern/src/**writing**`, `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-07-graph-editing-and-reporting/**`, `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-07-writing-workbench-evolution/**` | graph-to-writing/reporting handoff contract evidence; focused backend/frontend tests where touched; changed-doc links; `git diff --check` | 7 |
| H | `codex/devdocs-wave3-source-library-live-replay` | `wave3-source-library-live-replay` | planned | `main/backend/scripts/source_library_real_probes.py`, `main/backend/tests/**source_library**`, `development/latest-dev-docs/automation-runs/source-library-*`, `development/latest-dev-docs/development-plans/CURRENT_DEV/*source-library*/**` | public live-site replay artifact or anti-bot/network blocker recorded separately from deterministic fixture gates; source_library focused tests; changed-doc links; `git diff --check` | 9 |
| I | `codex/devdocs-wave3-frontend-launcher-production-gates` | `wave3-frontend-launcher-production-gates` | planned | `scripts/gates/**`, `main/frontend-modern/**`, `ops/**`, `development/latest-dev-docs/automation-runs/storybook-launcher-*`, `development/latest-dev-docs/ops-frontend/**` | Storybook/frontend/launcher production-safe gate evidence; destructive macOS bundle rebuild either safely dry-run gated or explicitly deferred; changed-doc links; `git diff --check` | 10 |
| J | `codex/devdocs-wave3-index-sync` | `wave3-index-sync` | planned | `development/latest-dev-docs/README.md`, `development/latest-dev-docs/MERGED_OVERVIEW.md`, `development/latest-dev-docs/automation-runs/dev-docs-folder-audit-2026-05-22/**` | plan skeleton added; changed-doc links; `git diff --check` | 1 |

## Dependency Notes

- Lane J should merge first to seed the skeleton only; the final supervisor pass should update this file after actual lane merges.
- Lanes A and B are independent but both touch the vectorization topic. If both update the same `CURRENT_DEV` files, merge A first, then reconcile B against A's benchmark/evidence wording.
- Lane E should merge after D so the schema inventory refresh can reflect any response-model remediation.
- Lane G should merge after F when possible, because the handoff evidence should refer to the curated graph workflow package if it lands.
- Lanes C, H, and I are independent runtime/evidence lanes. Their environment blockers must be recorded separately from deterministic test failures.

## Planned Supervisor Fill-In Fields

After Wave3 integration, replace this section with actual evidence:

| Lane | Commit | Result | Gate evidence | Residual blocker |
|---|---:|---|---|---|
| A | pending | pending | pending | pending |
| B | pending | pending | pending | pending |
| C | pending | pending | pending | pending |
| D | pending | pending | pending | pending |
| E | pending | pending | pending | pending |
| F | pending | pending | pending | pending |
| G | pending | pending | pending | pending |
| H | pending | pending | pending | pending |
| I | pending | pending | pending | pending |
| J | pending | pending | pending | pending |

## Minimum Integration Checklist

1. Confirm each lane returned `结果/改动文件/验证状态/风险/commit`.
2. Merge in the order shown in the branch matrix, pausing for manual reconciliation on shared documentation files.
3. Run changed-doc Markdown link check after each documentation merge batch.
4. Run `git diff --check main...HEAD` or the supervisor branch equivalent before final commit.
5. Update [development/latest-dev-docs/README.md](../../README.md), [MERGED_OVERVIEW.md](../../MERGED_OVERVIEW.md), and this file from `planned` to actual integrated status only after evidence is merged.
