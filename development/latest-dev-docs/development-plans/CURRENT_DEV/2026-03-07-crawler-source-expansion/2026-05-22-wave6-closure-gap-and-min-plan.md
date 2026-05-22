# Wave6-2 Crawler Source Expansion Closure Gap And Minimum Plan

Date: 2026-05-22
Branch: `codex/devdocs-wave6-crawler-source-expansion`
Scope: `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-07-crawler-source-expansion/`

## Closure Decision

Overall status: `not_closed`.

The original 2026-03-07 plan is now an outdated status snapshot rather than an accurate task state. A1-A3 have enough code/test evidence to treat as evidence-closed inside this topic, but A4-A6 still need updated source-layer policy and replay closure before the topic can move out of `CURRENT_DEV`. Shared navigation files are intentionally not edited in this lane.

## Evidence Anchors

Code and contract anchors:

- [source_library/types.py](../../../../../main/backend/app/services/source_library/types.py): `SourceTier`, `SourceOnboardingPriority`, `derive_source_tiering`, `default_source_layer_boundary`, `FrontDoorExecutionProtocol`.
- [collect_runtime/contracts.py](../../../../../main/backend/app/services/collect_runtime/contracts.py): `CollectRequest`, `CollectResult`.
- [crawlers/base.py](../../../../../main/backend/app/services/crawlers/base.py): `CrawlerDispatchRequest`, `CrawlerDispatchResult`.
- [collect_runtime/adapters/source_library.py](../../../../../main/backend/app/services/collect_runtime/adapters/source_library.py): source-library terminal, ingress, postprocess, authority-output compatibility path.
- [crawlers/bridge.py](../../../../../main/backend/app/services/crawlers/bridge.py): provider dispatch and poll bridge.
- [clue_chains/source_library_expansion.py](../../../../../main/backend/app/services/clue_chains/source_library_expansion.py): deterministic read-only source-library expansion hop and replay manifest.

Test and evidence anchors:

- [test_source_library_resolver_unittest.py](../../../../../main/backend/tests/unit/test_source_library_resolver_unittest.py): source tiering propagation into channels and middle-layer protocol.
- [test_source_library_runner_gray_rollout_unittest.py](../../../../../main/backend/tests/unit/test_source_library_runner_gray_rollout_unittest.py): runtime channel tiering and layer boundary metadata.
- [test_collect_runtime_source_library_adapter_unittest.py](../../../../../main/backend/tests/unit/test_collect_runtime_source_library_adapter_unittest.py): source-library authority output and frontdoor ingress projection.
- [test_crawler_management_bridge_unittest.py](../../../../../main/backend/tests/unit/test_crawler_management_bridge_unittest.py): crawler submit/poll bridge.
- [source-library-real-probes/2026-05-22](../../../automation-runs/source-library-real-probes/2026-05-22/README.md): deterministic local fixture for source-library site-entry and transport fallback.
- [source-library-live-probes/2026-05-22](../../../automation-runs/source-library-live-probes/2026-05-22/README.md): four-target public live probe with relevance-review separation.
- [source-library-replay-scaleout/2026-05-22](../../../automation-runs/source-library-replay-scaleout/2026-05-22/README.md): 45-site historical manifest and no-network replay gate.
- [ingest-frontdoor-closure/2026-05-22](../../../automation-runs/ingest-frontdoor-closure/2026-05-22/README.md): current source-library/frontdoor URL ingest map.

## Status Matrix

| Task | Current status | Reason | Closure gap |
| --- | --- | --- | --- |
| A1 baseline inventory and layer map | `closed` | API, source-library, collect-runtime, crawler contracts, and crawler bridge anchors exist. | None for this phase. |
| A2 source tiering and priority model | `closed` | Tiering enums, normalization, resolver propagation, and unit assertions exist. | None for this phase. |
| A3 layer responsibilities and onboarding boundary | `closed` | Runtime channel metadata now records source catalog, normalized execution, provider dispatch, discovery, and ingest boundary owners. | None for this phase. |
| A4 quality, dedupe, and stability rules | `needs_update` | Quality anchors and real/live probe artifacts exist. | A source-layer allow/downgrade/block policy matrix still needs to be tied to concrete enforcement points. |
| A5 directed-source onboarding strategy | `not_closed` | The 45-site historical manifest exists and public-live subset evidence exists. | Full 45-site public replay plus term-fallback relevance review are still open. |
| A6 minimum source-to-ingest handoff contract | `needs_update` | Terminal output, frontdoor ingress, postprocess, and authority output are covered for source-library flow. | Provider-specific crawler and high-JS/browser handoff cases are not fully closed. |
| A7 validation pack and documentation closure | `not_closed` | This document plus the closure checker provide a repeatable baseline. | Do not archive or sync shared indexes until A4-A6 are closed. |

## Minimum Development Plan

1. Keep A1-A3 as evidence-closed and avoid rewriting the 2026-03-07 plan/tasklist beyond topic-local status notes.
2. Close A4 by pinning a source-layer allow/downgrade/block matrix to existing enforcement points in `source_library.resolver`, probe classification, and downstream frontdoor admission.
3. Close A5 only after running an opt-in 45-site public replay and recording per-target `passed`, `anti_bot_or_transport_blocked`, `policy_or_platform_required`, or `relevance_review` outcomes.
4. Close A6 by adding focused crawler/provider-specific handoff coverage that proves source identity, execution context, provenance, and quality trace survive into ingest-facing semantics.
5. Leave `CURRENT_DEV/INDEX.md`, `development-plans/INDEX.md`, `README.md`, and `MERGED_OVERVIEW.md` to a later integration lane.

## Repeatable Check

Static closure-gap mapping:

```bash
cd main/backend
python3 scripts/check_crawler_source_expansion_closure.py
```

Focused validation:

```bash
cd main/backend
python3.11 -m pytest -q \
  tests/unit/test_crawler_source_expansion_closure_check_unittest.py \
  tests/unit/test_source_library_resolver_unittest.py \
  tests/unit/test_source_library_runner_gray_rollout_unittest.py \
  tests/unit/test_collect_runtime_source_library_adapter_unittest.py \
  tests/unit/test_crawler_management_bridge_unittest.py \
  tests/unit/test_clue_chain_source_library_expansion_unittest.py
```

Expected topic state after these checks: validation passes, but overall closure remains `not_closed`.
