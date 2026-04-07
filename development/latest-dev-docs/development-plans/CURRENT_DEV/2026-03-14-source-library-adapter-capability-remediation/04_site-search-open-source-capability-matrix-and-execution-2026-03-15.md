# Site Search Open-Source Capability Matrix and Execution

Date: 2026-03-15

## Summary

This document turns the local open-source reference set under `tmp/open-source-references/` into an executable capability map for the source-library `query -> search -> candidate generation -> detail fetch` pipeline.

The immediate implementation target is not a broad crawler rewrite. The first execution step is:

- keep the current shared `search_template` service as `site_search_basic`
- route site-local search by policy to `basic`, `resilient`, `official_api`, or `skip`
- when a `keep` site returns no local candidates, try `external_search`, then degrade once to `external_search_slowlane`
- preserve `rss` / `sitemap` as candidate sources, not primary fetch targets

## Local Reference Set

- `tmp/open-source-references/google-search`
- `tmp/open-source-references/scrapy-playwright`
- `tmp/open-source-references/crawl4ai`
- `tmp/open-source-references/trafilatura`
- `tmp/open-source-references/ultimate-sitemap-parser`
- `tmp/open-source-references/feedparser`
- `tmp/open-source-references/scrawl`
- `tmp/open-source-references/elastic-crawler`

## Capability Matrix

| Internal capability | Primary reference | Why it fits | Current execution status |
| --- | --- | --- | --- |
| `site_search_basic` | current shared `search_template_service` | Existing lightweight `search -> candidate` path for sites with stable search templates | Active |
| `site_search_browser` | `scrapy-playwright` | Browser action chain for fill / click / wait / pagination on site-local search pages | Planned |
| `site_search_external_fallback` | `google-search`, current `search/web.py` | External search fallback when site-local search fails or has no query endpoint | Active |
| `site_search_external_slowlane` | DDG HTML fallback | Low-rate fallback when the provider chain returns empty or is partially rate-limited | Active |
| `resilient_fetch` | `trafilatura`, `crawl4ai` | Better retry / timeout / transport handling for 403/429/fetch-failed cases | Partially active via `basic -> resilient` |
| `candidate_scoring` | `crawl4ai` | Link and content scoring ideas fit candidate ranking before detail fetch | Planned |
| `candidate_fallback_sources` | `ultimate-sitemap-parser`, `feedparser` | Correct role is candidate seeding, not full-site fetch | Active |
| `detail_fetch` | existing frontdoor + `trafilatura` reference | Candidate URLs remain the only fetch targets after search | Existing chain active, stronger extraction planned |
| queue / crawl lifecycle reference | `elastic-crawler`, `scrawl` | Useful for later retry / queue / browser dispatch architecture | Reference only |

## Routing Decisions

The first executable routing matrix is:

| Site policy | Search service | Candidate source | Action |
| --- | --- | --- | --- |
| `keep` | `basic` | `search_template` | Run normal site-local search |
| `keep` fallback | `external_search -> external_search_slowlane` | `external_search` | Use external search when local site search is empty; degrade to slow-lane once |
| `deprioritized` | `resilient` | `search_template` | Skip by default; if override enabled, run with `resilient` |
| `api_preferred` | `official_api` | `official_api_search` | Execute official API search instead of HTML search |
| `social_skip` | `platform_api` | none | Keep interface only; do not execute |
| `rss` entries | `feed_native` | `rss_feed` | Candidate source only |
| `sitemap` entries | `sitemap_native` | `sitemap_probe` | Candidate source only |

## Code Execution Landed

This matrix is now partially executed in code:

- `site_search_policy.py`
  - adds `preferred_search_service`
  - adds `implementation_hint`
- `unified_search.py`
  - injects policy-derived `search_service` into `search_template` execution
  - auto-routes `api_preferred` sites to `official_access.api`
  - keeps `social_skip` as interface-only
  - runs `external_search` fallback for `keep` sites with zero local candidates
  - preserves structured error metadata:
    - `error_class`
    - `search_service_used`
    - `recommended_search_service`
    - `search_url`
- `search_template_service.py`
  - reuses `search/web.py` for provider-driven external search
  - degrades once to `external_search_slowlane` with low-rate DDG HTML fetch if external provider search returns empty
- `resolver.py`
  - exposes candidate-generation diagnostics:
    - `site_policy_breakdown`
    - `search_service_breakdown`
    - `error_class_breakdown`

## What We Explicitly Did Not Do Yet

- no direct `scrapy-playwright` runtime integration
- no `crawl4ai` scoring port
- no social platform API implementation
- no broad queue/retry architecture migration

These remain second-stage tasks after the current routing layer is validated on real samples.

## Next Recommended Implementation Order

1. Add `browser_candidate` search service using `scrapy-playwright` patterns for sites that need form interaction or JS rendering.
2. Add a unified slow-lane route snapshot in `candidate_pipeline` so deferred browser cases are observable.
3. Port a minimal candidate scoring layer inspired by `crawl4ai`.
4. Revisit `deprioritized` sites one by one after service routing exists.
