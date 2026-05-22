# Wave10 Source-Library Search Governance - Adapter Capability Slice (2026-05-22)

## Scope

This Wave10 slice adds a no-network governance checker that keeps adapter capability/profile state and replay/relevance-review blockers machine-checkable.

Checker:

- `main/backend/scripts/check_source_library_search_governance.py`

Evidence:

- `development/latest-dev-docs/automation-runs/source-library-search-governance/2026-05-22/output.json`

## Adapter Capability Assertions Now Checked

| Case | Expected state |
| --- | --- |
| Known domain parser profile (`www.pymnts.com`) | `adapter_capability_status=allow`, resolved profile stays `site_adaptive.pymnts_card`. |
| Unknown requested parser profile | `adapter_capability_status=downgrade`, resolved profile becomes `site_adaptive`. |
| Anchor-only fallback profile | `adapter_capability_status=review`, `candidate_relevance_review_required=true`. |

The checker also verifies handler registration for `handler.cluster` and `generic_web.search_template`, plus capability-profile emission from the handler-cluster and generic-web adapter surfaces.

## Public Replay and Relevance Boundary

The checker reuses the deterministic A5 public replay gate and requires the following non-closure state:

- `public_network_attempted=false`
- `claims_full_45_site_public_replay=false`
- `claims_human_relevance_review_complete=false`
- term-fallback candidates remain `review_required_not_full_closure`

This preserves the Wave4/Wave8 boundary: the 45-site manifest and deterministic no-network gate are checkable, but full public replay and human relevance review are not claimed complete.

## Validation

```bash
python3.11 main/backend/scripts/check_source_library_search_governance.py --repo-root .
python3.11 -m pytest -q main/backend/tests/unit/test_source_library_search_governance_check_unittest.py
```

Result: checker passed; unit test `2 passed, 2 warnings`.
