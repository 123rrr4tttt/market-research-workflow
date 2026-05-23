# Wave8-3 Adapter Capability Parser Profile Gate

Date: 2026-05-22
Scope: source-library `site_search` lane / `search_template` adapter capability

## Closed Partial Gap

The `search_template` adapter no longer treats every requested `parser_profile` as implicitly validated.

This closes the narrow parser/profile capability gap where an entry-level remediation could pass an unknown profile key through the source-library adapter path and still look like an executable parser contract. The adapter plan now emits a capability status before execution:

| Case | Status | Runtime action |
|---|---|---|
| Known validated profile, e.g. `site_adaptive.pymnts_card` | `allow` | Keep the resolved parser profile. |
| Unknown requested profile | `downgrade` | Replace it with the adapter default profile and record the downgrade reason. |
| Anchor-only fallback profile | `review` | Keep the profile but mark candidates as requiring relevance review. |

## Code Contract

- `search_result_parser_profiles.resolve_parser_profile_capability(...)` is the status contract.
- `search_template_adapters.apply_search_template_adapter_plan(...)` applies the contract to adapter params.
- `unified_search_by_item_payload(...)` records `adapter_capability_status`, `parser_profile_resolved`, and `relevance_review_required` in site-search runtime diagnostics.

## Three-Lane Boundary

This change is deliberately limited to the `site_search` lane. It does not modify `protocol_search`, `provider_harvest`, `url_execution`, ingest frontdoor routing, or shared development indexes.

## Evidence Gate

Checker:

```bash
cd main/backend
python3.11 scripts/check_source_library_adapter_capability.py
```

Focused tests:

```bash
cd main/backend
python3.11 -m pytest -q \
  tests/unit/test_resource_pool_search_template_adapters_unittest.py \
  tests/unit/test_resource_pool_unified_search_unittest.py
```

## Remaining Gaps

- Public 45-site replay and term-fallback relevance review remain open and should not be counted as closed by this local parser-profile gate.
- Site-specific parser expansion remains incremental; this gate only prevents unknown/low-confidence parser profiles from masquerading as validated capability.
- Relevance-review is now routed as metadata, not a human-review workflow UI.
