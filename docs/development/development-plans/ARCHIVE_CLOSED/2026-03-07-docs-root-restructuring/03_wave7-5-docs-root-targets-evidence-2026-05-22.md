<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after docs-root topic archive migration.
> Previous source: `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-07-docs-root-restructuring/03_wave7-5-docs-root-targets-evidence-2026-05-22.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-07-docs-root-restructuring/03_wave7-5-docs-root-targets-evidence-2026-05-22.md`
> Migration batch: `docs-root-topic-archive-closed-2026-05-23`

# Wave7-5 Docs Root Targets Evidence

> Date: 2026-05-22
> Worktree: `/Users/wangyiliang/market-research-workflow.worktrees/devdocs-wave7-docs-root-targets`
> Branch: `codex/devdocs-wave7-docs-root-targets`
> Status: partial; target roots prepared; shared indexes intentionally unchanged

## Inputs Checked

- Original plan: [01_docs-root-restructuring-mapping-2026-03-07.md](./01_docs-root-restructuring-mapping-2026-03-07.md)
- Wave6 closure gap: [02_wave6-docs-root-restructuring-evidence-closure-gap-2026-05-22.md](./02_wave6-docs-root-restructuring-evidence-closure-gap-2026-05-22.md)
- Structure/link gate: [scripts/check_latest_dev_docs_structure.py](../../../../../scripts/check_latest_dev_docs_structure.py)
- Prepared target roots:
  - [docs/development](../../../../../docs/development/README.md)
  - [docs/architecture](../../../../../docs/architecture/README.md)

## Result

| State | Judgment | Evidence |
|---|---|---|
| Not closed blocker removed | The topic is no longer blocked on missing `docs/development` and `docs/architecture` root entrypoints. | Both target roots now have README entrypoints with purpose, compatibility path, routing rules, adjacent roots, and minimum promotion rules. |
| Partial, not closed | No authoritative file migration happened in this lane. | The current readable compatibility entry remains `development/latest-dev-docs`; shared navigation files were left untouched by scope. |
| Closable evidence exists | A migration-prep batch now has concrete files and link-checkable evidence. | This evidence links the original plan, Wave6 gap, validation script, and two target root entrypoints. |

## Compatibility Path

`development/latest-dev-docs` remains the compatibility entry until an integration batch updates the shared navigation and proves the changed links. The new roots are target entrypoints, not duplicate authoritative copies of the current development-doc snapshot.

## Change Summary

- Added `docs/development/README.md` as the target root for active plans, execution history, stage evidence, and development archives.
- Added `docs/architecture/README.md` as the target root for long-lived structure, system constraints, and target-state topology.
- Preserved existing `docs/implementation/` and `docs/governance/` roles as adjacent destinations.
- Did not edit shared total indexes:
  - `development/latest-dev-docs/README.md`
  - `development/latest-dev-docs/MERGED_OVERVIEW.md`
  - `development/latest-dev-docs/development-plans/INDEX.md`
  - `development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md`

## Status Movement

Move this topic from `not_closed` to `partial / target-root-prepared` in the next shared-index integration pass.

It is not fully closed because the first low-ambiguity migration batch has not moved authoritative content into the new roots. It is now closable because the previously missing target root family exists and can be validated without relying on prose-only intent.

## Minimum Next Step

1. Pick one low-ambiguity source family, preferably explicit `A_ARCHITECTURE/` or `F_PLAN/` material.
2. Move or index only that batch under the matching target root.
3. Update shared navigation in the same integration lane.
4. Run:

```bash
python3 scripts/check_latest_dev_docs_structure.py \
  --link-path docs/development \
  --link-path docs/architecture \
  --link-path development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-07-docs-root-restructuring
```

5. Run `git diff --check`.
