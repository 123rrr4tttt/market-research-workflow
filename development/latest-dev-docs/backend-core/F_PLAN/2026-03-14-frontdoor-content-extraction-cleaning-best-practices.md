# Frontdoor Content Extraction / Cleaning Best Practices

Updated: 2026-03-14 PST

## Purpose

This note translates current industry / library best practices into a concrete direction for the repository's `postprocess_frontdoor`.

The target problem is not generic HTML cleanup. The real issue is:

- source-library and URL-oriented inputs often contain boilerplate-heavy web text
- JS-heavy pages, support-center pages, navigation shells, and media shells should not all go through the same light cleaner
- frontdoor quality decisions should be based on extraction quality, not just raw text length

## External Best-Practice Signals

### 1. Main-content extraction should come before rule-heavy cleaning

Mozilla Readability is explicit about a two-step model:

- determine whether a page is likely readerable
- parse the page into article-like content

This is a better default than trying to make regex cleaning solve article extraction.

Sources:

- [mozilla/readability](https://github.com/mozilla/readability)

### 2. Boilerplate removal should be treated as a dedicated phase

Trafilatura, jusText, and Boilerpipe-style tools all frame the problem as:

- boilerplate removal
- main-text extraction
- only then light normalization / cleanup

This aligns with the repository's need to separate:

- extraction of the primary content block
- post-extraction cleanup
- quality scoring

Sources:

- [Trafilatura core functions](https://trafilatura.readthedocs.io/en/latest/corefunctions.html)
- [Trafilatura Python usage](https://trafilatura.readthedocs.io/en/latest/usage-python.html)
- [jusText](https://github.com/miso-belica/jusText)
- [BoilerPy3](https://github.com/jmriebold/BoilerPy3)

### 3. JS-heavy pages should be routed, not over-cleaned

Trafilatura's troubleshooting guidance and Google's JavaScript SEO guidance both point to the same operational reality:

- some pages are shell-first or dynamically injected
- static HTML extraction may never yield clean article text
- these pages should be rendered, cleaned elsewhere, or rejected/deferred early

Sources:

- [Trafilatura troubleshooting](https://trafilatura.readthedocs.io/en/stable/troubleshooting.html)
- [Google JavaScript SEO basics](https://developers.google.com/search/docs/crawling-indexing/javascript/javascript-seo-basics)
- [Google lazy-loaded content guidance](https://developers.google.com/search/docs/crawling-indexing/javascript/lazy-loading)

### 4. Quality gates should score extraction quality, not only text size

The common pattern across these tools is that quality is inferred from signals such as:

- readability likelihood
- content density
- stopword density
- boilerplate ratio
- shell signature prevalence
- duplication / repetition
- extracted-text-to-raw-text ratio

This is closer to the repository's needs than a pure `semantic_len` gate.

Sources:

- [mozilla/readability](https://github.com/mozilla/readability)
- [Trafilatura deduplication](https://trafilatura.readthedocs.io/en/latest/deduplication.html)
- [jusText](https://github.com/miso-belica/jusText)
- [BoilerPy3](https://github.com/jmriebold/BoilerPy3)

## Implications For Current Frontdoor

The current frontdoor already improved one important boundary:

- `clean -> score -> extract`

But the source-library validation sample shows that cleaner-side rule growth alone is not enough. Residual JS/template shells and navigation-heavy text still survive because the text extractor has already flattened the page into large plain-text blocks.

That means the next iteration should not be:

- add more and more blacklist regexes

It should be:

- make frontdoor extraction-aware before quality scoring

## Recommended Target Pipeline

The recommended frontdoor sequence is:

1. `admission`
2. `readerability / shell precheck`
3. `main-content extraction`
4. `light cleaner`
5. `extraction-quality scoring`
6. `accept | reject | return_for_cleanup`
7. `structured extraction`

This is different from the current lighter sequence because it adds an explicit content-block extraction phase before final scoring.

## Recommended Frontdoor Modules

### A. `readerability_precheck`

Responsibilities:

- quickly classify whether the page looks like an article page
- identify obvious shell-first pages
- produce early routing hints

Suggested outputs:

- `readerable: bool`
- `shell_heavy: bool`
- `js_heavy: bool`
- `page_family: article|support|video|landing|index|unknown`

### B. `main_content_extractor`

Responsibilities:

- extract the dominant article / body region
- reduce boilerplate before custom cleaning
- expose extraction confidence and size ratios

Suggested outputs:

- `raw_text_chars`
- `main_text_chars`
- `main_text_ratio`
- `extractor_name`
- `extractor_confidence`

### C. `light_cleaner`

Responsibilities:

- clean what remains after main-content extraction
- remove residual share bars, cookie snippets, shell text, CSS/JS leftovers
- avoid being responsible for finding the main article block

Boundary:

- this module should not be the primary article extractor

### D. `extraction_quality_gate`

Responsibilities:

- score the extracted main-content result
- decide `accept / reject / return_for_cleanup`
- block pages that still look shell-heavy after extraction

Suggested scoring signals:

- `readerable`
- `main_text_chars`
- `main_text_ratio`
- `shell_marker_hits`
- `js_template_hits`
- `nav_prefix_ratio`
- `cookie/privacy residue`
- `duplicate_line_ratio`

## Recommended Routing Policy

### Article-like pages

- run main-content extraction
- run light cleaner
- score normally

### JS-heavy / support-center / shell-heavy pages

- do not keep escalating regex cleaning
- route to `return_for_cleanup`
- or route to rendered extraction

### Video / social shell pages

- treat as special family
- use specialized handling or reject/defer
- do not pretend they are ordinary article pages

### Index / navigation pages

- reject or defer early
- do not let large navigation text pass quality only because it is long

## Concrete Changes Recommended For This Repository

### 1. Insert `main_content_extractor` before final quality scoring

Current issue:

- the cleaner operates on flattened extracted text
- navigation-heavy or JS-heavy shells remain long enough to look acceptable

Change:

- add a dedicated main-content extraction phase inside frontdoor
- keep `content_cleaner` as post-extraction cleanup

### 2. Change quality scoring from raw text quality to extracted content quality

Current issue:

- long shell text can still score as acceptable

Change:

- score using post-extraction text and extraction metadata
- add ratio-based features instead of length-only logic

### 3. Add a strong `return_for_cleanup` path for shell-heavy pages

Current issue:

- some sources are fundamentally bad fits for light cleaner treatment

Change:

- if residual JS/template signals remain above threshold after extraction, route out
- do not continue into structured extraction as if the page were article-clean

### 4. Add page-family classification

Current issue:

- article pages, YouTube pages, support pages, and landing pages are not separated early enough

Change:

- classify page family before extraction
- apply different gates and cleanup policies by family

### 5. Keep regex cleaners small and evidence-driven

Current issue:

- cleaner growth can easily become brittle and site-specific

Change:

- retain only rules proven by residue corpora
- prioritize structural extraction and routing over giant deny-lists

## Proposed Repository-Specific Pipeline

Recommended next-state pipeline:

```text
source_library / url inputs
  -> admission
  -> readerability_precheck
  -> page_family classification
  -> main_content_extractor
  -> light_cleaner
  -> extraction_quality_gate
  -> accept | reject | return_for_cleanup
  -> structured extraction
  -> normalizer / compat / writer
```

## Validation Guidance

The same source-library sample corpus should be kept as a fixed benchmark.

Minimum checks:

1. `main_text_ratio` becomes available for all article-like pages.
2. navigation-heavy pages are rejected or routed earlier.
3. JS-heavy pages no longer arrive at structured extraction as `ok`.
4. residue scans for `window.`, `document.`, `function(`, `prototype.`, CSS property clusters, and cookie/privacy text materially decrease.
5. article pages do not lose the first useful paragraphs due to over-cleaning.

## Bottom Line

For this repository, the best-practice shift is:

- from `clean raw text harder`
- to `extract the main content first, then clean lightly, then score extraction quality`

That is the most defensible path for the current source-library and frontdoor architecture.
