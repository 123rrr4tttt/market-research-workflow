# Item Field Classification Freeze

Updated: 2026-03-27 PST

## Purpose

Freeze the owner layer for fields touched by the item-layering migration so later refactors stop moving meaning between `item`, derived execution plan, and runtime diagnostics.

## Frozen Ownership

### Item Definition

- `item_key`
- `name`
- `description`
- `channel_key`
- `tags`
- `extends_item_key`
- `enabled`
- `scope`
- `schedule`
- `item_type`
- `managed_by`
- `params.query_terms`
- `params.urls`
- `params.expected_entry_type`
- `params.site_entries`
- `params.site_entry_urls`
- stable grouping metadata in `extra`

Interpretation:

- `site_entries` on the definition side means source-set membership, not route execution policy.
- Definition view may preserve the raw source-set list even when execution later derives a narrower route plan.

### Derived Execution Plan

- `execution_plan`
- `execution_plan.route_buckets.site_entries`
- `execution_plan.route_buckets.official_access_site_entries`
- `execution_plan.site_entry_urls`
- `execution_plan.route_bucket_counts`
- `execution_plan.plan_meta.search_template_source_set`
- `execution_plan.plan_meta.search_template_source_set_counts`
- `execution_plan.plan_meta.search_template_source_set_drop_reasons`

Interpretation:

- `official_access_site_entries` is not stable item meaning.
- handler-cluster source-set refinement is execution derivation, not item mutation.

### Runtime Diagnostics

- `runtime_diagnostics[*].site_policy`
- `runtime_diagnostics[*].policy_reason`
- `runtime_diagnostics[*].candidate_source_plan`
- `runtime_diagnostics[*].service_chain`
- `runtime_diagnostics[*].preferred_search_service`
- `runtime_diagnostics[*].implementation_hint`
- `runtime_diagnostics[*].parser_profile`
- `runtime_diagnostics[*].search_service`
- `runtime_diagnostics[*].search_service_fallbacks`
- `runtime_diagnostics[*].search_template_adapter`
- `runtime_diagnostics[*].search_template_adapter_reason`
- `runtime_diagnostics[*].search_template_adapter_mode`
- `runtime_diagnostics[*].browser_candidate_deferred`
- `runtime_diagnostics[*].browser_candidate_reason`
- `runtime_diagnostics[*].search_service_degraded_to`
- parser hit / rejection counters

Interpretation:

- These fields explain one run.
- They must not be emitted back into stable item views by default.

## Keep / Move / Drop

- Keep on item surface:
  - stable source-set meaning
  - user invocation contract
  - raw `site_entries`
- Move to derived plan:
  - handler-cluster source-set refinement
  - API-vs-template reroute
  - route bucket counts and drop reasons
- Move to runtime diagnostics:
  - policy branch
  - adapter branch
  - browser-deferred state
  - parser/search-service observations
- Drop from default item output:
  - `params.official_access_site_entries`
  - `extra.search_template_source_set*`

## Enforcement

- Default `list_effective_items(...)` returns definition-first items.
- Execution consumers derive their own `execution_plan`.
- Runtime traces carry execution observations in result structures only.
