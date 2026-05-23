# Wave8-2 Fetch Router Gap Cluster Evidence

Date: 2026-05-22
Scope: `2026-03-02-single-url-first-ingest-allocation-plan`

## status:

`closed_narrow_runtime_contract`

## gap:

The frontdoor/router gap for the legacy single-url lane is closed for the narrow compatibility contract:

- stale targets `single_url.py` and `test_single_url_ingest_unittest.py` remain retired.
- the active compatibility primitive is `url_pool.single_url_compat`.
- final document writes are only reached through source-library URL routing plus `frontdoor_ingress -> postprocess_frontdoor`.
- the generated frontdoor `source_ref` preserves URL, locator, domain, ingress type, and `url_execution` mode.

Remaining work is no longer a blocker for this topic's current contract: broader high-JS live fetch capacity and official API adapter rollout can proceed as separate lanes.

## evidence:

- `main/backend/app/services/ingest/url_pool.py::_run_source_library_frontdoor_ingress` owns the compatibility path and invokes source-library URL routing in terminal-output-only mode.
- `main/backend/app/services/ingest/frontdoor_ingress.py::build_frontdoor_ingress_envelope` normalizes `source_ref` with URL, locator, domain, ingress type, entrypoint, source mode, and project key.
- `main/backend/tests/unit/test_ingest_frontdoor_context_unittest.py::test_ingest_url_via_source_library_frontdoor_uses_source_library_bridge_and_postprocess_writer` asserts `url_pool.single_url_compat`, `terminal_output_only`, `run_writer=True`, and the frontdoor `source_ref`.
- `main/backend/scripts/check_fetch_router_gap_closure.py` includes this topic in its per-topic `status/gap/evidence` output.

## validation:

```bash
cd main/backend
python3.11 -m pytest -q \
  tests/unit/test_ingest_frontdoor_context_unittest.py \
  tests/unit/test_fetch_router_gap_closure_check_unittest.py
cd ../..
python3.11 main/backend/scripts/check_fetch_router_gap_closure.py
git diff --check
```
