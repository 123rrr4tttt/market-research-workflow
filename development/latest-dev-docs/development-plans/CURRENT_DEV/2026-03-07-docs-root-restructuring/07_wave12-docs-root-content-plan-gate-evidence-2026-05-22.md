# Wave12 Docs Root Content Plan Gate Evidence

> Date: 2026-05-22
> Worktree: `/Users/wangyiliang/market-research-workflow.worktrees/devdocs-wave12-docs-root-content-plan`
> Branch: `codex/devdocs-wave12-docs-root-content-plan`
> Status: partial; content-plan gate added; shared indexes intentionally unchanged

## Inputs Checked

- Wave12 plan: [wave12-worktree-plan-2026-05-22.md](../../../automation-runs/dev-docs-folder-audit-2026-05-22/wave12-worktree-plan-2026-05-22.md)
- Wave11 navigation evidence: [06_wave11-docs-root-navigation-promotion-evidence-2026-05-22.md](./06_wave11-docs-root-navigation-promotion-evidence-2026-05-22.md)
- Development content plan: [docs/development/latest-dev-docs-content-plan.json](../../../../../docs/development/latest-dev-docs-content-plan.json)
- Architecture content plan: [docs/architecture/latest-dev-docs-content-plan.json](../../../../../docs/architecture/latest-dev-docs-content-plan.json)
- Content-plan checker: [scripts/checkers/check_docs_root_content_plan.py](../../../../../scripts/checkers/check_docs_root_content_plan.py)
- Follow-up folderization evidence: [04_status-evidence-and-minimum-dev-plan-2026-05-22.md](../2026-03-07-后续安排/04_status-evidence-and-minimum-dev-plan-2026-05-22.md)

## Result

| State | Judgment | Evidence |
|---|---|---|
| 未封口 | Keep docs-root restructuring in `CURRENT_DEV`. | This batch does not move source content and does not update shared navigation indexes. |
| 已推进 | The first content-plan gate is now machine-checkable. | `docs/development` and `docs/architecture` each have a content-plan manifest tied back to their migration manifests. |
| 漂移留存 | `MERGED_OVERVIEW` drift remains an integration blocker, not a local edit in this worker branch. | Every content-plan entry and unsafe-move record includes the `MERGED_OVERVIEW_drift` blocker. |
| 后续安排 | Folderization remains a separate directory-local lane. | The existing folderization checker still reports hard failures `0` and content gaps `5`; this branch records the boundary but does not rewrite topic files. |

## Content Plan Gate

The new checker validates the following contract for each docs-root content-plan entry:

- the plan points at a known migration manifest entry;
- the source is still under `development/latest-dev-docs`;
- `source_authority` is `development/latest-dev-docs`;
- `target_root` stays under the declared docs root and exists;
- the `shim` is the existing target README from the migration manifest;
- `mode` is `shim_only`;
- `source_remains_authoritative` is `true`;
- `move_allowed` is `false`;
- blockers include `shared_navigation_sync` and `MERGED_OVERVIEW_drift`;
- every migration manifest entry has exactly one content-plan entry.

## Remaining Unsafe Moves

This gate records the remaining unsafe broad moves instead of performing them:

| Root | Plan entries | Unsafe move records | Main blocker |
|---|---:|---:|---|
| `docs/development` | 7 | 5 | shared navigation, `MERGED_OVERVIEW` drift, topic status sync, mixed-tree classification |
| `docs/architecture` | 5 | 5 | shared navigation, `MERGED_OVERVIEW` drift, file-level classification |

The broad-move boundary is intentional. `development/latest-dev-docs` remains the readable compatibility root until a supervisor-owned integration pass updates shared navigation and reruns link checks.

## MERGED_OVERVIEW Boundary

This worker branch does not edit `development/latest-dev-docs/MERGED_OVERVIEW.md`. The new content-plan gate advances drift handling by making `MERGED_OVERVIEW_drift` a required blocker on every planned content move. A later integration worker can now fail fast if a move is marked safe while shared overview drift is still unresolved.

## Follow-up Folderization Boundary

The follow-up folderization lane already has a read-only checker and local evidence. This branch treats that lane as adjacent evidence only:

- no edits to `2026-03-07-后续安排` topic files;
- no edits to shared indexes;
- no attempt to close downstream implementation tasks from the docs-root worker branch.

## Validation

```bash
python3 scripts/check_current_dev_wave12_plan.py
python3 scripts/checkers/check_docs_root_content_plan.py
python3 scripts/check_latest_dev_docs_structure.py \
  --link-path docs/development \
  --link-path docs/architecture \
  --link-path development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-07-docs-root-restructuring \
  --link-path development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-07-后续安排/04_status-evidence-and-minimum-dev-plan-2026-05-22.md
git diff --check
```
