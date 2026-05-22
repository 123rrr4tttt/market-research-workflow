# Wave4 Integration Risk Review

Run date: 2026-05-22 PST

Status: pre-merge sidecar review. This file reviews the Wave3 integrated state and the planned Wave4 branch tree before supervisor merge. It is not implementation evidence for any Wave4 lane.

## Inputs

- [wave3-worktree-plan-2026-05-22.md](./wave3-worktree-plan-2026-05-22.md)
- [API_SCHEMA_INVENTORY_2026-05-22.md](../../backend-docs/B_API/API_SCHEMA_INVENTORY_2026-05-22.md)
- [graph-handoff-evidence/2026-05-22](../graph-handoff-evidence/2026-05-22/README.md)
- [source-library-live-probes/2026-05-22](../source-library-live-probes/2026-05-22/README.md)
- [frontend-topology-theme/2026-05-22](../frontend-topology-theme/2026-05-22/README.md)

## Planned Wave4 Lanes Reviewed

| Lane branch | Integration risk | Merge note |
|---|---|---|
| `codex/devdocs-wave4-schema-auth-agent-web` | Auth redirects, SSE/stream endpoints, and app web routes may not be JSON envelope routes. Typing them blindly can misrepresent runtime behavior. | Require explicit exemption notes for redirects, streams, and static/non-JSON routes; do not count them as schema closed unless the generated inventory reflects the intended response kind. |
| `codex/devdocs-wave4-schema-discovery-project` | `discovery.py` and `project_customization.py` are currently part of the 46 untyped 200 surface. They may introduce new schema components and runtime envelope assumptions. | Merge with focused route tests, then regenerate the schema inventory only after all schema lanes land. |
| `codex/devdocs-wave4-schema-workflow-dynamic` | This lane overlaps the same `workflow_graph.py` module that GraphPage curated-consumer work may exercise. Dynamic compile/run/template routes have broad payloads and should not be over-narrowed. | Prefer conservative schemas plus runtime tests for compile/run/template/replay. Merge before frontend GraphPage closure if it changes API contract shape. |
| `codex/devdocs-wave4-schema-writing-search-small` | `writing.py` may overlap both schema work and writing/search UI/API consumers. `writing/export/markdown` should stay non-JSON unless the route behavior changes. | Preserve the Wave3 non-JSON markdown decision; run writing/search focused tests and schema inventory contract after regeneration. |
| `codex/devdocs-wave4-graphpage-curated-consumer` | GraphPage closure depends on UI ownership, API client wiring, and backend handoff routes proven in Wave3. It can conflict with workflow dynamic schema changes and frontend runtime visual evidence. | Merge after relevant workflow schema changes, then require GraphPage e2e that proves draft submit or an explicit alternative UI owner. |
| `codex/devdocs-wave4-source-library-replay-scaleout` | Wave3 public live probe covered only four controlled targets; the 45-site replay and term-fallback relevance review remain open. | Do not mark source-library dirty-source closure complete unless scaleout evidence records per-site pass/fail/relevance-review outcomes. |
| `codex/devdocs-wave4-frontdoor-router-hardening` | Likely overlaps source-library replay through URL collection, high-JS/browser-render routing, and dashboard/frontdoor state semantics. | Keep frontdoor router evidence separate from source-library replay evidence; closure requires route-level behavior plus focused regressions. |
| `codex/devdocs-wave4-frontend-runtime-visual` | This lane can become stale if GraphPage curated-consumer changes UI after visual screenshots are captured. | Run after GraphPage UI changes or rerun after merging them. Static topology gate from Wave3 is not a substitute for runtime/visual evidence. |
| `codex/devdocs-wave4-docs-status-sync` | Shared docs indexes are expected to conflict with most evidence-producing lanes. | Merge last and reconcile by union: preserve every landed artifact, gate result, and residual blocker. |

## Likely Conflict Points

1. `development/latest-dev-docs/README.md`, `MERGED_OVERVIEW.md`, and the audit README will be edited by docs-status sync and by evidence lanes. Resolve manually by preserving every Wave4 evidence link and avoiding premature `已封口` claims.
2. `API_SCHEMA_INVENTORY_2026-05-22.md` is generated. No schema lane should be treated as final until the supervisor regenerates it once after all schema branches land.
3. `main/backend/app/api/workflow_graph.py` is shared by schema-dynamic work and GraphPage consumer validation. API contract edits should land before frontend e2e/visual gates are treated as final.
4. `main/backend/app/api/writing.py` and `main/backend/app/contracts/schemas/writing.py` may be touched by both schema and writing/search work. Keep markdown export as an explicit non-JSON case unless implementation changes.
5. Source-library replay and frontdoor hardening may both touch collection/routing evidence and CURRENT_DEV status language. Keep their blockers separate: dirty-source scaleout is not the same proof as high-JS/browser/API routing.
6. Frontend visual evidence and GraphPage curated-consumer are order-sensitive. If GraphPage changes after screenshots, rerun visual/e2e before marking frontend graph closure.

## Missing Gates To Require Before Supervisor Closure

| Area | Required gate before closure |
|---|---|
| Schema lanes | Regenerate `API_SCHEMA_INVENTORY_2026-05-22.md`; run `test_api_schema_inventory_contract_unittest.py`; record remaining untyped routes or explicit exemptions. |
| Python changes | Run `py_compile` on changed Python files and focused pytest for changed API/service modules. |
| Workflow graph | Run workflow graph API/integration tests after schema-dynamic and GraphPage consumer changes are both merged. |
| GraphPage consumer | Run frontend lint plus `tests/e2e/graphpage.spec.ts` or a narrower replacement that proves curated draft submit/handoff ownership. |
| Frontend runtime visual | Capture current visual/runtime evidence after all GraphPage UI changes; static `check:topology-platform` alone is insufficient. |
| Source-library replay | Run skip-safe default gate and, only when the lane permits network, the public/scaleout replay with recorded per-target classifications. |
| Frontdoor router | Run focused ingest/frontdoor/source-library regressions and record high-JS/browser-render/API route cases separately from source-library relevance review. |
| Docs integration | Run changed Markdown link check and `git diff --check` after docs-status sync is merged last. |

## Residual Blocker Criteria

- API schema closure: do not claim global schema closure unless untyped 200 routes are reduced to zero or every remaining route is documented as an intentional non-JSON, stream, redirect, static, or legacy dynamic exemption.
- Graph closure: Wave3 proves backend handoff; Wave4 must prove the first frontend consumer or explicitly name a different owner. Without that, GraphPage remains `需更新`.
- Source-library closure: a four-target public probe is not enough for the historical 45-site dirty-source replay. Term-fallback hits must remain `relevance_review` until reviewed or excluded.
- Frontdoor closure: the `single_url.py` drift is repaired, but high-JS/browser-render routing, official API route maturity, and dashboard tri-state alignment still need evidence.
- Frontend topology closure: the Wave3 static contract is current but does not prove runtime rendering, canvas nonblank state, or rapid graph mode switching.
- Docs closure: only move CURRENT_DEV topics to closed/archive when the implementation evidence and the named acceptance gate both exist in the repo.

## Recommended Merge Order

1. Schema lanes that only add response models: auth/agent/web, discovery/project, writing/search/small.
2. Workflow dynamic schema lane, because GraphPage consumer depends on the final workflow graph API shape.
3. Regenerate the API schema inventory once and run schema contract gates.
4. Backend behavior lanes: frontdoor router hardening and source-library replay scaleout.
5. GraphPage curated consumer.
6. Frontend runtime visual, after GraphPage UI settles.
7. Docs status sync last, with manual union of all evidence links and residual blockers.

