# Clue Chain Investigation Tool Index

Date: 2026-05-22
Status: `wave5_merged` / `verification_passed`

This directory is the current canonical development-plan entry for the Clue Chain / `链条` investigation tool. Wave5 has landed the first implementation slice and verification evidence; the feature remains in `CURRENT_DEV` as the active entry for follow-up hardening and live-provider work.

## Main Entry

- [01_clue-chain-investigation-tool-plan-2026-05-22.md](./01_clue-chain-investigation-tool-plan-2026-05-22.md) - product/domain plan, object model draft, API draft, frontend surface, and acceptance criteria.
- [02_wave5_worktree_execution_plan.md](./02_wave5_worktree_execution_plan.md) - Wave5 worktree plan tree, folder-status sync, merge order, and supervisor evidence summary.
- [03_wave5_integration_risk_review.md](./03_wave5_integration_risk_review.md) - pre-merge risk map and validation matrix.
- [04_wave5_implementation_evidence-2026-05-22.md](./04_wave5_implementation_evidence-2026-05-22.md) - implementation commits, acceptance mapping, and validation commands.

## Current Status

- Closure state: Wave5 implementation slice verified.
- Execution state: merged into `codex/devdocs-wave5-integration-2026-05-22`.
- Evidence state: backend/unit/integration/schema, frontend lint/e2e/topology, and diff hygiene gates are recorded in the evidence file.
- Canonical-copy rule: new Clue Chain planning/status documents must live in this directory or another declared `development/latest-dev-docs` sync target, not as an unindexed unique copy elsewhere.

## Supervisor Follow-Up

Residual work is limited to live-provider reliability, broader visual regression, and production graph-submit conflict handling. Do not move this plan to `ARCHIVE_CLOSED` until those follow-up scopes are either completed or explicitly split into successor plans.
