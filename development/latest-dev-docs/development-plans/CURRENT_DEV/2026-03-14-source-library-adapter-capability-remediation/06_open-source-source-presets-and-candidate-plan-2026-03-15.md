# Open-Source Source Presets and Candidate Plan

Date: 2026-03-15

## Summary

Two concrete outputs were landed from local open-source project inspection:

1. An importable open-source preset layer for media/source seeds.
2. A modular candidate-source execution plan for `unified_search`.

This turns the local OSS references into reusable project assets instead of one-off notes.

## Local OSS Inputs

- `tmp/open-source-references/fundus`
  - strongest reusable source inventory
  - publisher model exposes `sources=[RSSFeed|Sitemap|NewsMap(...)]`
- `tmp/open-source-references/news-crawl`
  - small but useful news seed sample in `seeds/feeds.txt`
- `tmp/open-source-references/RSSHub`
  - route/registry model useful for adapter registration and source routing

## Code Outputs

### 1. Open-source source presets

Files:

- `main/backend/app/services/resource_pool/open_source_source_presets.py`
- `main/backend/app/services/resource_pool/open_source_source_importer.py`

What was added:

- `business_media_foundation`
  - Reuters news sitemap
  - CNBC news sitemap / sitemapAll
  - Business Insider news sitemap
  - TechCrunch news sitemap
  - Wired RSS
  - AP News content sitemap
  - Guardian RSS / news sitemap
  - BBC news sitemap
- `tech_business_search_media`
  - validated search-template media entries already proven in the current stack

Import behavior:

- writes into existing `resource_pool_site_entries`
- preserves provenance in `source_ref` / `extra`
- adds `open_source_preset` tagging for future filtering

### 2. Candidate-source plan

File:

- `main/backend/app/services/resource_pool/candidate_source_plan.py`

What was added:

- `CandidateSourceStep`
- `CandidateSourcePlan`
- `build_candidate_source_plan(...)`
- `plan_to_metadata(...)`

Purpose:

- make the per-entry execution path explicit
- separate policy-driven routing from entry-type execution
- move current code closer to `publisher sources -> execution plan -> candidate generation`

## API Outputs

File:

- `main/backend/app/api/resource_pool.py`

New endpoints:

- `GET /api/v1/resource_pool/open-source-presets`
- `POST /api/v1/resource_pool/import/open-source-presets`

## Runtime Integration

File:

- `main/backend/app/services/resource_pool/unified_search.py`

Current integration:

- `site_entries_used[*].candidate_source_plan` now carries structured plan metadata
- `service_chain` is now derived from the candidate-source plan

## Live Result

Project:

- `demo_proj`

Imported:

- `business_media_foundation`: 10 sitemap + 2 rss seeds
- `tech_business_search_media`: 5 search-template media entries

Handler sync:

- `handler.cluster.rss`
- `handler.cluster.search_template`
- `handler.cluster.sitemap`

Real validation:

- RSS foundation sample produced candidates successfully
- sitemap foundation sample produced candidates after fixing a stale argument mismatch in `unified_search -> execute_sitemap_probe`

## Validation

- `python3.11 -m pytest -q tests/unit/test_resource_pool_unified_search_unittest.py tests/unit/test_resource_pool_open_source_source_importer_unittest.py tests/unit/test_resource_pool_api_unittest.py`
- result: `21 passed`

## Next Step

Best next move:

1. add more preset packs from `fundus` by region/topic
2. rank imported sources by live candidate quality
3. continue splitting `unified_search` execution into plan-driven source modules
