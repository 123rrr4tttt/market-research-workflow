# Clue Chain Successor Scopes

Date: 2026-05-22
Status: `external_blocked` / `wave16_checked` / `wave22_checked` / `wave26_checked`

## What Is Closed

The original Clue Chain implementation entry has moved to [ARCHIVE_CLOSED](../../ARCHIVE_CLOSED/2026-05-22-clue-chain-investigation-tool/INDEX.md). Its closed surface is recorded in the [Wave16 closure split](../../ARCHIVE_CLOSED/2026-05-22-clue-chain-investigation-tool/05_wave16_closure_split-2026-05-22.md): backend service/store, typed API, deterministic source-library hop, fixture-gated external search, agent no-silent-promote guard, graph handoff payload generation, and mocked GraphPage review flow.

## Active Successor Scopes

| Scope | Status | Next development action | Minimum gate |
|---|---|---|---|
| Live provider reliability | `external_blocked` | Add opt-in live provider probes for SearXNG / YaCy / project search adapters, with provider trace and raw/normalized counts. | Default tests remain fixture-only; opt-in live probe records provider, query, retry outcome, duplicate count, and blocked reason. |

## Repo-Local Gates Closed In Wave26

| Scope | Status | Evidence |
|---|---|---|
| Production graph-submit conflict handling | `conflict_boundary_closed` | `build_graph_submit_bridge_envelope` stages Clue Chain graph output without mutating graph state; `test_clue_chain_graph_integration_unittest.py` covers staged and stale revision conflict envelopes; `test_workflow_graph_curated_service_unittest.py` covers Clue Chain bridge stale revision matching curated submit conflict without extra audit; `graphpage.spec.ts` covers visible `submit_conflict` and one submit attempt. |
| Broader UI / visual regression | `ui_matrix_closed` | `graph-clue-chain.spec.ts` now covers selected-node seeds, dense graph fallback seeds, blocked provider attribution, evidence drawer details, reviewed-candidate disabled actions, and non-happy path UI states. |

## Integration Rule

Do not reopen the archived implementation directory for new planning. This successor directory is archived as `external_blocked`; reopen only when live provider reliability evidence is available, or open a new provider-specific topic.
