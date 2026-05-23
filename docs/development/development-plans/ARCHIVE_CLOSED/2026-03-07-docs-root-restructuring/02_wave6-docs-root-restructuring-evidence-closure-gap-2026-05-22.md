<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after docs-root topic archive migration.
> Previous source: `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-07-docs-root-restructuring/02_wave6-docs-root-restructuring-evidence-closure-gap-2026-05-22.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-07-docs-root-restructuring/02_wave6-docs-root-restructuring-evidence-closure-gap-2026-05-22.md`
> Migration batch: `docs-root-topic-archive-closed-2026-05-23`

# Wave6 Docs Root Restructuring Evidence And Closure Gap

> Date: 2026-05-22
> Worktree: `/Users/wangyiliang/market-research-workflow.worktrees/devdocs-wave6-docs-root-restructuring`
> Branch: `codex/devdocs-wave6-docs-root-restructuring`
> Status: not closed; doc-aligned; structure/link gate added

## Inputs Checked

- Original plan: [01_docs-root-restructuring-mapping-2026-03-07.md](./01_docs-root-restructuring-mapping-2026-03-07.md)
- Wave audit baseline: [dev-docs-folder-audit-2026-05-22](../../../automation-runs/dev-docs-folder-audit-2026-05-22/README.md)
- Gate tool added in this lane: [scripts/check_latest_dev_docs_structure.py](../../../../../scripts/check_latest_dev_docs_structure.py)

## Current Status

| State | Judgment | Evidence |
|---|---|---|
| 未封口 | Keep this topic in `CURRENT_DEV`. | The March plan is explicitly planning-only and no migration batch has moved authority from `development/latest-dev-docs` to the target `docs/` taxonomy. |
| 过时 | The baseline has drifted. | `frontend-modern` and development-plan category indexes now exist; `CURRENT_DEV/main/index.md` was added by prior waves; `docs/implementation` and `docs/governance` exist, while `docs/development` and `docs/architecture` are still absent. |
| 已封口 | The compatibility-entry structure baseline is now checkable. | The six active `development/latest-dev-docs` sections have `INDEX.md`, `main/index.md`, and `main/MERGED_*.md`, and their first local index link points to `main/`. |
| 需更新 | Closure should be recast as gated migration, not direct root rename. | The next executable step is target-root preparation plus one low-ambiguity inventory batch, with shared indexes updated only in an integration pass. |

## Minimum Development Plan

1. Keep `development/latest-dev-docs` as the compatibility entry until a migration batch has passed structure and link checks.
2. Use `scripts/check_latest_dev_docs_structure.py` as the minimum preflight for every docs-root restructuring batch.
3. Prepare missing target-root entrypoints in a future integration-safe lane: `docs/development/` and `docs/architecture/`.
4. Inventory only low-ambiguity sources first: `development-plans/CURRENT_DEV/`, explicit `A_ARCHITECTURE/`, explicit `F_PLAN/`, and stable runbook-like `E_OPS/`.
5. Do not move mixed `main/` trees or archive directories as a whole package; classify them file by file.
6. Update shared navigation files only after the batch is ready to integrate; this Wave6-3 lane intentionally did not edit `CURRENT_DEV/INDEX.md`, `development-plans/INDEX.md`, `README.md`, or `MERGED_OVERVIEW.md`.

## Verification Command

```bash
python3 scripts/check_latest_dev_docs_structure.py \
  --link-path development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-07-docs-root-restructuring \
  --link-path development/latest-dev-docs/automation-runs/dev-docs-folder-audit-2026-05-22/README.md
```

Expected result after this document is present:

```text
OK latest_dev_docs_structure=passed markdown_link_files=3 markdown_links=11
```

## Closure Gap

This topic can close only after a real migration batch exists and proves:

- the target root family is present and documented;
- authoritative and compatibility paths are separated;
- changed Markdown links pass the gate;
- scripts or docs that still point at `development/latest-dev-docs` are either intentionally compatibility-bound or updated in the same batch;
- shared top-level navigation is updated by the integration owner after conflicts are resolved.
