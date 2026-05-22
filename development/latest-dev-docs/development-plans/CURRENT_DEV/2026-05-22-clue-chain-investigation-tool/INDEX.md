# Clue Chain Investigation Tool Index

Date: 2026-05-22
Status: `wave16_closure_split` / `repo_slice_closed` / `successors_required`

This directory is the current canonical development-plan entry for the Clue Chain / `链条` investigation tool. Wave5 has landed the first implementation slice and verification evidence. Wave16 splits that completed repo-controlled slice from the remaining live-provider, UI matrix, and production graph-submit conflict work.

## Main Entry

- [01_clue-chain-investigation-tool-plan-2026-05-22.md](./01_clue-chain-investigation-tool-plan-2026-05-22.md) - product/domain plan, object model draft, API draft, frontend surface, and acceptance criteria.
- [02_wave5_worktree_execution_plan.md](./02_wave5_worktree_execution_plan.md) - Wave5 worktree plan tree, folder-status sync, merge order, and supervisor evidence summary.
- [03_wave5_integration_risk_review.md](./03_wave5_integration_risk_review.md) - pre-merge risk map and validation matrix.
- [04_wave5_implementation_evidence-2026-05-22.md](./04_wave5_implementation_evidence-2026-05-22.md) - implementation commits, acceptance mapping, and validation commands.
- [05_wave16_closure_split-2026-05-22.md](./05_wave16_closure_split-2026-05-22.md) - topic-local split: closed repo slice, successor plans, and Wave16 API fixture/no-mutation contract guard.

## Current Status

- Closure state: Wave5 implementation slice verified; Wave16 marks the repo-controlled implementation surface as closed.
- Execution state: merged into `codex/devdocs-wave5-integration-2026-05-22`.
- Evidence state: backend/unit/integration/schema, frontend lint/e2e/topology, diff hygiene gates, and the Wave16 fixture-gated API contract guard are recorded in the evidence files.
- Canonical-copy rule: new Clue Chain planning/status documents must live in this directory or another declared `development/latest-dev-docs` sync target, not as an unindexed unique copy elsewhere.

## Supervisor Follow-Up

Residual work is now split into three successor scopes: live-provider reliability, broader visual regression, and production graph-submit conflict handling. The original Wave5 implementation entry is a topic-local archive candidate only after the integration branch records those successor scopes in shared indexes or successor directories; this worker branch does not migrate or edit shared indexes.
