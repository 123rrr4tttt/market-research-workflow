# Clue Chain Successor Scopes

Date: 2026-05-22
Status: `partial` / `wave16_checked` / `external_blocked`

## What Is Closed

The original Clue Chain implementation entry has moved to [ARCHIVE_CLOSED](../../ARCHIVE_CLOSED/2026-05-22-clue-chain-investigation-tool/INDEX.md). Its closed surface is recorded in the [Wave16 closure split](../../ARCHIVE_CLOSED/2026-05-22-clue-chain-investigation-tool/05_wave16_closure_split-2026-05-22.md): backend service/store, typed API, deterministic source-library hop, fixture-gated external search, agent no-silent-promote guard, graph handoff payload generation, and mocked GraphPage review flow.

## Active Successor Scopes

| Scope | Status | Next development action | Minimum gate |
|---|---|---|---|
| Live provider reliability | `external_blocked` | Add opt-in live provider probes for SearXNG / YaCy / project search adapters, with provider trace and raw/normalized counts. | Default tests remain fixture-only; opt-in live probe records provider, query, retry outcome, duplicate count, and blocked reason. |
| Production graph-submit conflict handling | `conflict_boundary_open` | Decide whether Clue Chain graph output submits directly, stages as handoff, or routes through Graph Editing governance with `base_revision`. | Backend/API test for stale revision conflict envelope plus UI/client test that exposes conflict without destructive retry. |
| Broader UI / visual regression | `ui_matrix_open` | Extend beyond mocked happy/review path to blocked-provider, reviewed-candidate, dense graph, selected-node, and evidence-drawer states. | Existing GraphPage Clue Chain e2e plus one visual/runtime route check for blocked/provider and reviewed-candidate states. |

## Integration Rule

Do not reopen the archived implementation directory for new planning. Add new evidence to this successor directory unless the work is promoted into the relevant live-provider, graph-editing, or frontend migration topic.
