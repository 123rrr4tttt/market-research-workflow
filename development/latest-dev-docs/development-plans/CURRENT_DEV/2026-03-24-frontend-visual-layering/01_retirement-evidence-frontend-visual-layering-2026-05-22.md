# Frontend Visual Layering Placeholder Retirement Evidence (2026-05-22)

## Decision

`2026-03-24-frontend-visual-layering` should retire as a standalone
`CURRENT_DEV` topic. It should not receive a new minimum plan, because the
distinct scope that can be audited now belongs to:

- the active [Frontend Three-Layer Rewrite](../2026-03-15-frontend-three-layer-rewrite/README.md);
- the [frontend topology/theme contract evidence](../../../automation-runs/frontend-topology-theme/2026-05-22/README.md);
- the [frontend runtime visual evidence](../../../automation-runs/frontend-runtime-visual/2026-05-22/README.md).

## Inputs Checked

| Input | Finding | Outcome |
| --- | --- | --- |
| Placeholder path | No tracked file existed before this retirement record; the directory was only represented as a placeholder in `CURRENT_DEV/INDEX.md`. | Cannot remain in the no-closure placeholder bucket. |
| `CURRENT_DEV/INDEX.md` | Listed `2026-03-24 Frontend Visual Layering` in the no-closure placeholder bucket with no path in the snapshot. | Replace with this retirement record. |
| `2026-03-15-frontend-three-layer-rewrite` | Defines A/B/C layers, kernel boundaries, visual semantics, route grouping, and remaining container/view gaps. | Owns future architecture work. |
| `frontend-topology-theme/2026-05-22` | Verifies module topology, surface placement, shell i18n, and theme token groups through `check:topology-platform`. | Owns static contract evidence. |
| `frontend-runtime-visual/2026-05-22` | Verifies runtime theme token application, Layer A/B/C shell routes, cross-layer navigation, non-overlapping desktop shell regions, and visual screenshots. | Owns runtime visual evidence. |

## Evidence Map

| Visual-layering question | Current owner | Evidence |
| --- | --- | --- |
| Which product layers exist? | `2026-03-15-frontend-three-layer-rewrite` | A/workbench, B/visualization, C/management, plus shared platform kernel. |
| Do topology and theme contracts exist? | `frontend-topology-theme/2026-05-22` | `KernelModuleKey` / `moduleManifest` coverage, placement baseline, i18n catalogs, and light/dark/brand token groups. |
| Do layers render through real runtime routes? | `frontend-runtime-visual/2026-05-22` | Settings/admin, workbench/writing, and visualization/dashboard routes are exercised in a Playwright gate. |
| Is there remaining frontend work? | `2026-03-15-frontend-three-layer-rewrite` | `AppShell` compatibility-only retirement and heavy page container/view depth remain open. |

## Why Not Add A New Minimum Plan Here

Adding a new plan in this placeholder would duplicate the existing three-layer
rewrite topic. The remaining work is not "visual layering" as a separate scope;
it is the known closure depth of the active rewrite:

1. reduce `AppShell` to compatibility-only duties;
2. split `WritingWorkbenchPage` and `GraphPage` container/view responsibilities;
3. keep runtime visual checks alongside static topology/theme checks.

Those items should stay in the active rewrite entry so the frontend closure path
has one owner and one evidence chain.

## Current Status

This directory exists only to make the former placeholder auditable and to remove
the empty-directory placeholder status. It is not an implementation queue.
