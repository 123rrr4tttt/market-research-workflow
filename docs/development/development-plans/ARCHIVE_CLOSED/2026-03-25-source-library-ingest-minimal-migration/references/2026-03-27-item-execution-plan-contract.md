# Item Execution Plan Contract

Updated: 2026-03-27 PST

## Contract

Current contract version:

- `source_library.item_execution_plan.v1`

## Required Fields

```json
{
  "contract_version": "source_library.item_execution_plan.v1",
  "item_key": "handler.cluster.search_template",
  "expected_entry_type": "search_template",
  "route_buckets": {
    "site_entries": ["..."],
    "official_access_site_entries": ["..."]
  },
  "site_entry_urls": ["..."],
  "route_bucket_counts": {
    "site_entries": 0,
    "official_access_site_entries": 0,
    "total": 0
  },
  "plan_meta": {}
}
```

## Semantics

- `route_buckets.site_entries`
  - executable site-search routes that still use normal site-entry search handling
- `route_buckets.official_access_site_entries`
  - executable routes that must bypass normal template execution and go through API-preferred handling
- `site_entry_urls`
  - deduped merged execution order input for unified search
- `route_bucket_counts`
  - plan-local observability for route sizing
- `plan_meta`
  - derivation-local metadata; valid for planning/debug, not stable item meaning

## Handler-Cluster Specialization

For `handler.cluster.search_template`:

- raw definition `params.site_entries` remains the source-set abstraction
- execution plan narrows that raw set into:
  - validated template routes
  - official-access reroutes
  - drop reasons for bad/deprioritized entries

## Consumer Rules

- unified search must consume `execution_plan.site_entry_urls` instead of reading mixed execution fields from item definition
- API grouped views may use execution plan internally for handler derivation
- item listing must not expose route buckets unless explicitly opted in

## Compatibility Rule

- During migration, consumers may still accept an item without an attached `execution_plan`
- In that case, they must derive the plan locally via `build_item_execution_plan(...)`
