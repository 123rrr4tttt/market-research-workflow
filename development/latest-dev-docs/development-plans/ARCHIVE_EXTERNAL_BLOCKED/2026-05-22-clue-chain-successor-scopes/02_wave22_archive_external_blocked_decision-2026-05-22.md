# Wave22 Archive External Blocked Decision

Date: 2026-05-22
Status: `wave22_checked` / `superseded_by_wave26`

## Superseded By Wave26

Wave22 correctly kept this directory in `CURRENT_DEV` because two repo-local blockers were still open at that time. Wave26 closed those two blockers with backend conflict tests and frontend UI matrix tests, so this document is now historical readback rather than the current classification.

Current classification is recorded in [03_wave26_graph_submit_conflict_and_ui_matrix_closure-2026-05-23.md](./03_wave26_graph_submit_conflict_and_ui_matrix_closure-2026-05-23.md).

## Decision

Do not migrate `2026-05-22-clue-chain-successor-scopes` to `ARCHIVE_EXTERNAL_BLOCKED` in Wave22.

The successor directory contains one true external blocker, but it also keeps two repo-local successor blockers that are not sealed by the current evidence set:

- production graph-submit conflict handling for Clue Chain output;
- broader Clue Chain UI / visual regression coverage.

Therefore the correct Wave22 state is retained CURRENT_DEV, not external-blocked archive.

## Evidence Checked

### Closed Predecessor

The predecessor is closed for the Wave5 repo-controlled implementation slice only. The Wave16 split records backend service/store, typed API, deterministic source-library hop, fixture-gated external-search hop, agent guard, graph handoff payload generation, frontend API wiring, and a mocked GraphPage review flow as closed.

Residuals explicitly remain split out as successor work:

- live provider reliability;
- production graph-submit conflict handling;
- broader UI / visual regression.

### Successor Scope Document

The successor entry still lists three active scopes:

| Scope | Current status | Wave22 readback |
|---|---|---|
| Live provider reliability | `external_blocked` | External/provider condition remains valid for archive-external style handling. |
| Production graph-submit conflict handling | `conflict_boundary_open` | Repo-local blocker remains open for Clue Chain-specific submit/conflict envelope and UI/client no-destructive-retry behavior. |
| Broader UI / visual regression | `ui_matrix_open` | Repo-local blocker remains open for blocked-provider, reviewed-candidate, dense graph, selected-node, and evidence-drawer visual/runtime states. |

### Graph-Submit / Conflict Evidence

Current graph evidence is useful but not sufficient to close the Clue Chain successor:

- `graph-handoff-evidence` proves backend route-level draft, submit, evidence-pack, reporting/writing handoff, persistence, list, and replay, but records GraphPage UI ownership as open.
- `graphpage-curated-consumer` proves the first GraphPage curated draft/submit/sync UI consumer, but keeps full data-source migration, temporary/cyclic submit rejection, and reporting/writing handoff UI out of scope.
- `wave20-graph-editing-audit-conflict` proves deterministic stale rollback conflict readback in repo-local fixtures, but keeps GraphPage live audit/rollback UI and live tenant DB audit durability open.
- The Graph Editing and Reporting topic itself says not to archive because conflict-specific frontend handling and clue-chain-to-curated mapping remain open.

This does not satisfy the Clue Chain successor minimum gate: stale revision conflict envelope plus UI/client proof that conflict is visible and not retried destructively for Clue Chain graph output.

### UI / Visual Evidence

Current frontend visual evidence is also useful but not sufficient:

- Wave5 Clue Chain e2e proves a mocked create/expand/review/evidence-drawer path.
- `graph-visual-evidence` proves mocked GraphPage canvas/Storybook visual reachability and force3d canvas visibility, not Clue Chain blocked-provider/reviewed-candidate matrix coverage.
- `frontend-runtime-visual` proves shell/theme/locale route layout with mocked backend and does not change `GraphPage.tsx`.
- The current `graph-clue-chain.spec.ts` remains one mocked happy/review path. It includes a fixture-gated blocker string and promoted candidate assertion, but it is not a visual/runtime matrix for blocked provider, reviewed candidate, dense graph, selected-node, and evidence drawer states.

This does not satisfy the Clue Chain successor minimum gate: GraphPage Clue Chain e2e plus one visual/runtime route check for blocked/provider and reviewed-candidate states.

## Result

`2026-05-22-clue-chain-successor-scopes` should remain in CURRENT_DEV as a Wave22 priority candidate with repo-local blockers open.

Recommended topic-local label:

```text
partial / wave16_checked / wave22_checked / repo_local_blockers_open
```

Recommended supervisor/index action, if a shared-index lane later updates indexes:

```text
Do not move to ARCHIVE_EXTERNAL_BLOCKED until the Clue Chain graph-submit conflict gate and Clue Chain UI/visual matrix gate have dedicated evidence.
```

## Minimum Next Gates

1. Add a Clue Chain graph-submit conflict gate:
   - backend/API stale `base_revision` or equivalent conflict envelope for Clue Chain graph output;
   - frontend/client test showing the conflict message and preventing destructive retry.
2. Add a Clue Chain UI/visual matrix gate:
   - blocked-provider state;
   - reviewed/promoted or rejected candidate state;
   - evidence drawer visible state;
   - selected-node and dense-graph route state, or a documented split if covered by another graph visual lane.
3. Keep live provider reliability as external-blocked only after the repo-local gates above are separately closed or moved into their owning topics.

## Validation

Readback-only decision; no shared index edits.

Checked paths:

- `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-05-22-clue-chain-investigation-tool/04_wave5_implementation_evidence-2026-05-22.md`
- `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-05-22-clue-chain-investigation-tool/05_wave16_closure_split-2026-05-22.md`
- `development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/2026-05-22-clue-chain-successor-scopes/01_clue-chain-successor-scopes-2026-05-22.md`
- `development/latest-dev-docs/automation-runs/graph-handoff-evidence/2026-05-22/README.md`
- `development/latest-dev-docs/automation-runs/graphpage-curated-consumer/2026-05-22/README.md`
- `development/latest-dev-docs/automation-runs/wave20-graph-editing-audit-conflict/2026-05-22/README.md`
- `development/latest-dev-docs/automation-runs/graph-visual-evidence/2026-05-22/README.md`
- `development/latest-dev-docs/automation-runs/frontend-runtime-visual/2026-05-22/README.md`
- `development/latest-dev-docs/automation-runs/frontend-topology-theme/2026-05-22/README.md`
- `main/frontend-modern/tests/e2e/graph-clue-chain.spec.ts`
