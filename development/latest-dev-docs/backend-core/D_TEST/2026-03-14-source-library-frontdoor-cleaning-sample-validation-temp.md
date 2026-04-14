# Source Library Frontdoor Cleaning Sample Validation (Temp)

Date: 2026-03-14

## Scope

- Sample source: `source_library` item `report1.high_value_urls`
- Project: `demo_proj`
- Sample size: 25 URLs
- Goal: use a real source-library output batch as the input set, run frontdoor cleaning, inspect residual noise, and tighten cleaner rules before scoring/extraction

## Inputs / Artifacts

- Source-library probe result:
  - `/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/tmp/source_library_high_value_probe.json`
- Baseline cleaning analysis:
  - `/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/tmp/source_library_cleaning_sample_analysis.json`
- Updated cleaning analysis after cleaner changes:
  - `/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/tmp/source_library_cleaning_sample_analysis_v2.json`

## Execution Notes

1. The source-library item `report1.high_value_urls` returned 25 `by_url` candidates.
2. Each URL was fetched with `http_utils.fetch_html(...)`.
3. Raw text was extracted with `url_pool._extract_text_from_html(...)`.
4. The extracted text was passed into `clean_frontdoor_document_candidate(...)`.
5. Cleaned text was checked with `content_quality_check(...)`.
6. Residual scanning then looked for:
   - `script_tokens`
   - `nav_home_news`
   - `cookie_banner`
   - `html_tags`
   - `privacy_terms`

## Cleaner Changes Applied

This round changed:

- [content_cleaner.py](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/backend/app/services/ingest/content_cleaner.py)
  - split out frontdoor cleaning as an explicit module
  - added frontdoor candidate cleaning metadata
  - added more line-noise markers such as share/follow/newsletter hints
  - added stronger JS/template shell markers
  - added embedded HTML fragment stripping
  - added single-line script-shell splitting on `;`, `}`, `)`
  - added CSS property-cluster rejection
  - added breadcrumb / JSON-like `name/item/position` line rejection
- [meaningful_gate.py](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/backend/app/services/ingest/meaningful_gate.py)
  - lowered `content_js_template_shell` threshold from `js_hits >= 6` to `js_hits >= 5`

## Summary

### Baseline

- `total_urls = 25`
- `fetch_ok = 24`
- `blocked = 1`
- `content_changed = 2`
- `residue_hits = 9`
- `pattern_counts`
  - `script_tokens = 9`
  - `html_tags = 1`
  - `privacy_terms = 1`

### Current

- `total_urls = 25`
- `fetch_ok = 24`
- `blocked = 1`
- `content_changed = 1`
- `residue_hits = 16`
- `pattern_counts`
  - `nav_home_news = 9`
  - `script_tokens = 12`
  - `cookie_banner = 1`
  - `privacy_terms = 1`
- `top_reasons`
  - `ok = 24`

## Interpretation

The cleaner is now better structured and frontdoor now truly runs `clean -> score`, but the real source-library sample shows that the remaining problem is no longer just HTML residue.

The dominant leftovers are:

1. Extractor-produced script/template text that already arrives as plain text instead of HTML.
2. Large site-navigation / magazine index headers that survive because they look like readable prose blocks.
3. CSS / frontend shell text that is not always isolated by line boundaries.

The headline result is:

- The architecture change is correct: cleaning is now explicit and reusable at frontdoor.
- The current heuristic cleaner is still too weak against source-library fetched web text.
- The sample should be treated as a real residue corpus for the next cleaner iteration, not as proof that cleaning is “done”.

## Residual Patterns Still Not Cleaned

### 1. JS / template shell fragments

Representative URLs:

- `https://supernote.com/pages/supernote-nomad`
- `https://support.whoop.com/s/article/Membership-Pricing`
- `https://www.androidpolice.com/oura-sells-the-benefits-of-its-subscription-as-ceramic-smart-ring-continues-to-impress/`
- `https://www.youtube.com/watch?v=GFKma0-MJpY&vl=en`
- `https://www.youtube.com/watch?v=AORC9yeoiRc`

Observed residue forms:

- `prototype.`
- `Symbol.iterator`
- `window.*`
- `document.*`
- `function(...)`
- `pf_page_*`
- `analytics / tracking / onload / onerror`
- inline `name/item/position` breadcrumb fragments

Assessment:

- These are not “small leftovers”.
- They indicate some pages are fundamentally shell-heavy and should probably be downgraded to `return_for_cleanup` or blocked earlier, not just lightly cleaned.

### 2. Navigation-heavy article headers

Representative URLs:

- `https://www.thequalityedit.com/articles/remarkable-tablet-review`
- `https://www.dcrainmaker.com/2021/11/oura-depth-review.html`
- `https://www.theverge.com/news/671955/jony-ive-rabbit-r1-humane-ai-pin`
- `https://www.whoop.com/us/en/thelocker/whoop-year-in-review-2025/`
- `https://pylessons.com/news/humane-ai-pin-shutdown-refund-policy-tech-discontinuation`

Observed residue forms:

- category stacks
- “Home / News / Gadgets / See All / Follow / Share” shells
- table-of-contents blocks
- section menu headers
- CSS-like page shell text

Assessment:

- These pages often still contain usable article text, but the prefix shell is too large.
- This needs prefix-trimming or shell-window detection, not only token blacklists.

### 3. Privacy / cookie / consent leftovers

Representative URLs:

- `https://support.whoop.com/s/article/Membership-Pricing`
- `https://eu.36kr.com/en/p/3380081710655237`

Observed residue forms:

- `cookie`
- `privacy policy`
- consent wording mixed into otherwise valid article text

Assessment:

- This is lower-volume than script-shell residue.
- It is still worth handling at cleaner stage so quality scoring does not need to carry all of it.

## What Improved

- Frontdoor sequencing is now explicit: clean first, then score.
- Cleaner logic is no longer buried inside the quality gate.
- Script-shell blocking in `meaningful_gate` is slightly more tolerant of cleaner-side normalization.
- CSS and embedded HTML shell text now have dedicated cleaner rules.

## What Did Not Improve Enough

- Sample-level `content_changed` remained very low.
- `script_tokens` remain the dominant residue type.
- Navigation-heavy shells still pass through as readable text.
- Some sources are likely better handled by upstream extraction-quality routing than by incremental regex growth alone.

## Next Optimization Directions

1. Add prefix-shell trimming:
   - detect large nav/header blocks before the first article-like paragraph
   - trim the prefix instead of only dropping per-line noise
2. Add shell-heavy page fallback:
   - if JS/template residue remains above threshold, mark `return_for_cleanup`
   - do not allow those pages to look “ok” only because semantic length is high
3. Add richer CSS / frontend bundle detection:
   - more bundle-specific signals for `prototype`, `iterator`, tracking loaders, minified frontend scaffolding
4. Consider source-type routing:
   - YouTube / support-center / JS-heavy marketing landing pages may need different cleaning/extraction admission rules

## Validation Performed

Commands run:

```bash
python3.11 -m pytest -q main/backend/tests/unit/test_meaningful_gate_unittest.py main/backend/tests/unit/test_postprocess_frontdoor_unittest.py
python3.11 -m pytest -q main/backend/tests/unit/test_postprocess_frontdoor_unittest.py main/backend/tests/unit/test_ingest_frontdoor_context_unittest.py main/backend/tests/unit/test_discovery_store_guardrails_unittest.py main/backend/tests/unit/test_raw_import_structuring_unittest.py main/backend/tests/unit/test_admin_reextract_unittest.py main/backend/tests/unit/test_topic_workflow_unittest.py
```

Results:

- targeted tests: `23 passed`
- wider frontdoor-related suite: `11 passed, 5 skipped`

## Temporary Status

This file is intentionally temporary and is not yet promoted into the indexed merged docs.
