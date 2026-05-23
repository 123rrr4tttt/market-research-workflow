# Search Contract Discovery Service and Storage

Date: 2026-03-15

## Summary

The search contract probe is now promoted from a runtime-only idea into a dedicated resource-pool service.

Service name:

- `search_contract_discovery`

Primary responsibility:

- probe multiple search template variants
- probe multiple query suffix variants
- score candidate yield
- pin the best contract back into site-entry storage

## Storage Decision

No new table is introduced in this stage.

The service writes into the existing site-entry storage:

- `resource_pool_site_entries`
- `shared_resource_pool_site_entries`

Write path:

- `resource_pool.site_entries.upsert_site_entry`

Pinned fields:

- `template`
- `source_ref.service = search_contract_discovery`
- `source_ref.best_suffix`
- `extra.search_contract_profile`

## Stored Profile Shape

`extra.search_contract_profile` stores:

- `service`
- `best_template`
- `best_suffix`
- `best_score`
- `templates_tried`
- `suffixes_tried`
- `probe_rows`

This makes the probe result reusable by later runtime execution without re-running full discovery every time.

## Initial Scope

The first version only handles:

- existing `search_template` or domain-root style site entries
- controlled template variants
- controlled suffix variants

It does not yet:

- auto-run on every item execution
- add a new API endpoint
- trigger browser execution
- create a separate discovery job table

## Code Landing

- `main/backend/app/services/resource_pool/search_contract_discovery.py`
- `main/backend/app/services/resource_pool/__init__.py`

## Next Step

The next useful extension is to let `unified_search` prefer pinned `extra.search_contract_profile.best_template` and optionally append the pinned suffix for `keep` sites before falling back to broader search services.
