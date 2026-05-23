# Wave12 Ingest Canary Handoff Evidence

Date: 2026-05-22
Scope: `2026-03-02-single-url-first-ingest-allocation-plan`

## status

`partial_single_url_canary_handoff_landed`

## contract advanced

The single URL compatibility lane now has a deterministic canary handoff envelope:

- Active path remains `url_pool.single_url_compat -> source_library URL routing -> frontdoor_ingress -> postprocess_frontdoor`.
- `postprocess_frontdoor` produces `data.canary_handoff` once the strict gate state is known.
- `_run_source_library_frontdoor_ingress` returns the same envelope as top-level `canary_handoff` for a single URL/frontdoor run.
- The envelope preserves source URL, entrypoint, `url_execution` source mode, route hint, fetch strategy, and router state when present.

## evidence

- `main/backend/tests/unit/test_ingest_canary_handoff_unittest.py::test_single_url_frontdoor_result_promotes_canary_handoff` covers the single URL result promotion.
- `main/backend/app/services/ingest/canary_handoff.py` keeps the handoff deterministic by excluding UUID and timestamp fields.
- `metrics_snapshot.guardrail_rollout` reuses the existing task-local metrics payload counters for canary visibility.

## remaining live-run gaps

partial remains because live canary was not run in this worker slice.

- No configured-service single URL canary was executed.
- No live inserted-valid ratio was inspected.
- No production rollout closure claim is made by this evidence.

## validation

```bash
python3 scripts/check_current_dev_wave12_plan.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_ingest_canary_handoff_contract.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_ingest_canary_handoff_unittest.py
git diff --check
```
