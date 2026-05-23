# Reinvestigation Focused on Single-URL First Ingest Allocation Plan (2026-03-02)

Reference plan:
- `01_single-url-first-ingest-allocation-plan-2026-03-02.md`

Refresh date: 2026-05-22

This document replaces the earlier stale audit. The previous version cited `main/backend/app/services/ingest/single_url.py` and `main/backend/tests/unit/test_single_url_ingest_unittest.py`; those files do not exist in the current worktree. The plan domain remains valid, but its implementation has moved to the current source-library/frontdoor chain.

---

## A. Current Implementation Map

| Legacy plan term | Current code target | Current status |
| --- | --- | --- |
| `single_url` workflow | `main/backend/app/services/ingest/url_pool.py::ingest_url_via_source_library_frontdoor` | Implemented as compatibility entrypoint |
| one write-capable URL ingest primitive | synthetic source-library item `url_pool.single_url_compat` + `source_library.resolver.run_item_with_url_routing(..., execution_layer="terminal_output_only")` | Implemented |
| meaningful gate | `main/backend/app/services/ingest/meaningful_gate.py` called from `postprocess_frontdoor.py` | Implemented |
| stable frontdoor envelope | `frontdoor_contract.py`, `frontdoor_ingress.py`, `postprocess_frontdoor.py` | Implemented, with some status vocabulary split between ingress/postprocess |
| source-library candidate-only path | `collect_runtime/adapters/source_library.py::to_source_library_response` runs postprocess with `run_writer=False` | Implemented |
| search-template fan-out before URL execution | `source_library/resolver.py` + `resource_pool/unified_search.py` handler-cluster path | Implemented with graceful degrade when no candidates |

Wave3-H delta:
- The active entry map is now pinned by an additional pool/frontdoor regression: `collect_urls_from_pool` must pass the current target into synchronous and threaded `_run_single_target` calls so each target keeps its own `source_search_contract`.
- The fixed case covers two source-library pool search templates with different query parameter contracts. Before the fix, the sync/thread branch could reuse the last target context for all pool targets.
- Evidence and lane status are recorded at [automation-runs/ingest-frontdoor-closure/2026-05-22/README.md](../../../automation-runs/ingest-frontdoor-closure/2026-05-22/README.md).

---

## B. Phase-1 Core Re-check

### B1) URL execution compatibility path

Status: `Implemented`

Evidence:
- `url_pool.py` builds `url_pool.single_url_compat` and calls source-library URL routing in terminal-output-only mode.
- The routed record is converted to a frontdoor ingress envelope with `ingress_type=source_library`, `entrypoint=ingest.url_pool`, and `source_mode=url_execution`.
- `run_postprocess_frontdoor(..., run_writer=True)` is the only writer hop in this path.
- Added contract test:
  - `main/backend/tests/unit/test_ingest_frontdoor_context_unittest.py::test_ingest_url_via_source_library_frontdoor_uses_source_library_bridge_and_postprocess_writer`

### B2) Candidate-only source-library bridge

Status: `Implemented`

Evidence:
- `collect_runtime/adapters/source_library.py::to_source_library_response` builds `terminal_output -> frontdoor_ingress -> postprocess_frontdoor`.
- That bridge uses `run_writer=False`, so source-library terminal records are exposed as authority output/compat projection rather than direct document writes.

### B3) Low-value and content quality guardrails

Status: `Implemented`

Evidence:
- `meaningful_gate.py` owns `url_policy_check` and `content_quality_check`.
- `postprocess_frontdoor.py` evaluates quality before writer dispatch and sets `dispatch_plan.run_writer=false` on reject/defer paths.

### B4) Result shape and counters

Status: `Mostly Implemented`

Evidence:
- URL execution returns `status`, `inserted`, `inserted_valid`, `skipped`, `rejected_count`, `rejection_breakdown`, `degradation_flags`, `single_write_workflow`, and `source_library_collect_only`.
- The new focused unit test pins those fields for the compatibility path.

Gap:
- Outer job/task state can still differ from inner result status in broader dashboards. This is outside this lane's write boundary.

---

## C. Remaining Gaps

Not closed by this lane:
- Real browser/crawler-first execution for all high-JS domains is still broader fetch-router work.
- Official API routing still depends on source-library adapter maturity.
- Frontend tri-state display is intentionally out of scope for this lane.
- Broader job/dashboard status can still represent outer task state differently from inner frontdoor `success/degraded_success/failed` admission state.

No longer current:
- Any implementation instruction that names `main/backend/app/services/ingest/single_url.py`.
- Any validation command that names `main/backend/tests/unit/test_single_url_ingest_unittest.py`.

---

## D. Updated Minimal Verification

Targeted lane gate:

```bash
cd main/backend
python3.11 -m pytest -q tests/unit/test_ingest_frontdoor_context_unittest.py tests/unit/test_frontdoor_orchestrator_unittest.py tests/unit/test_postprocess_frontdoor_unittest.py
```

Supplementary contract gate when time allows:

```bash
cd main/backend
python3.11 -m pytest -q tests/core_business/test_ingest_core_contract.py tests/unit/test_source_library_handler_cluster_frontdoor_unittest.py
```

---

## E. Final Verdict

The plan is not obsolete, but the file-level map was obsolete. The current implementation should be described as:

`legacy single-url contract -> url_pool/source_library terminal-output bridge -> frontdoor ingress -> postprocess quality gate -> terminal writer`.

This document is now `需更新 -> 已更新` for the lane-6 scope. It should not be archived as `已封口` yet because the broader fetch-router and dashboard status gaps remain open.
