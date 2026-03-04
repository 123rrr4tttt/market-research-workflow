# Meaningful Ingest Guardrails Plan (2026-03-02)

## 1. Goal

Build a strict ingestion guardrail so workflow outputs are meaningful by default, and shell/noise pages are rejected before document write.

Primary outcome:
- Stop producing low-value records such as navigation/login/search shell pages, JS hydration payloads, and binary PDF raw bytes.
- Treat `single_url` as the only ingestion workflow, and enforce one shared acceptance gate there.
- Other flows (`url_pool`, `source_library`) only produce candidates and must route final writes to `single_url`.

## 2. Problem Patterns Observed

Based on recent runtime cleanup in `project_demo_proj`, meaningless outputs fall into these stable patterns:

1. URL-level low-value endpoints:
- `/search`, `/login`, `/home`, `/showcase`, `/topics/*`, `/stargazers`, `/sitemap`

2. Shell-like content signatures:
- Google shell: `window.wiz_progre`
- Wix shell: `var bodyCacheable = true`
- Frontend hydration shell: `self.__next_f`
- Error wrapper shell: `errorContainer`

3. Binary payload leakage:
- content starts with `%PDF-1.x` and has no parsed article text.

4. Empty payload:
- `content IS NULL` or whitespace-only content.

## 3. Design Principle

One write rule for all ingest entries:
- No direct `Document` write without passing the same `meaningful_document_gate`.

Two-step safety for operations:
- Dry-run first, then apply by explicit IDs only.

## 4. Workflow Changes

### 4.1 WF-1 `single_url` (mandatory gate)

Add two gates:

1) `pre_fetch_url_gate`
- Input: URL only.
- Reject low-value domain/path by policy.
- Output: `blocked=true` + `skip_reason=url_policy_low_value_endpoint`.

2) `pre_write_content_gate`
- Input: fetched content + metadata.
- Reject if:
  - empty content
  - shell signature hit
  - raw PDF binary without successful text extraction
  - semantic text length below threshold (`min_semantic_len`)
- Output: `accepted/rejected`, `rejection_reason`, `quality_score`.

Search-template alignment (new):
- `single_url` supports configurable search fan-out and fallback inside the same workflow:
  - `search_expand`, `search_expand_limit`
  - `search_provider`, `search_fallback_provider`, `fallback_on_insufficient`
  - `target_candidates`, `min_results_required`
  - `decode_redirect_wrappers`, `filter_low_value_candidates`
- For `/search` style URLs, pipeline can:
  1) parse search results
  2) optionally fallback to `ddg_html` when insufficient
  3) fan-out top-N result URLs and run WF-1 gate per child URL

### 4.2 WF-2 `url_pool` (candidate-only, no bypass)

- Every target URL must call WF-1 (`single_url`) core path and inherit both gates.
- Remove any shortcut direct write branch.
- Aggregate rejection counters in result payload.

### 4.3 WF-3 `source_library` (candidate-only, no bypass)

- Auto-ingest branch must route to WF-1 (`single_url`) per URL.
- Keep candidate parse/write-to-pool behavior, but final `Document` insertion requires gate pass.

### 4.4 WF-4 post-ingest sanitation (already introduced)

- Keep cleanup script as fallback safety net.
- Not primary quality control path; primary is pre-write gate.

## 5. File-Level Implementation Plan

## 5.1 New module

- Add: `app/services/ingest/meaningful_gate.py`
- Responsibilities:
  - `url_policy_check(uri, config) -> GateDecision`
  - `content_quality_check(uri, content, doc_type, extraction_status, config) -> GateDecision`
  - shared shell/binary patterns

### 5.2 Integrate WF-1

- Modify: `app/services/ingest/single_url.py`
- Changes:
  - call `url_policy_check` before handler allocation/fetch
  - call `content_quality_check` before `Document` write
  - include `rejection_reason` and gate diagnostics in output contract
  - map status:
    - `success`: inserted valid doc
    - `degraded_success`: completed but rejected/duplicate/fallback only
    - `failed`: execution error and no usable output

### 5.3 Integrate WF-2 (candidate router)

- Modify: `app/services/ingest/url_pool.py`
- Changes:
  - force reuse of WF-1 for each candidate URL
  - return counters:
    - `rejected_url_policy`
    - `rejected_content_gate`
    - `inserted_valid`

### 5.4 Integrate WF-3 (candidate router)

- Modify: `app/services/collect_runtime/adapters/source_library.py`
- Changes:
  - when auto-ingest is enabled, route each URL to WF-1 path
  - merge gate metrics into adapter output

### 5.5 Runtime contract and API visibility

- Modify: `app/services/tasks.py`, `app/api/ingest.py` (if response shape used there)
- Changes:
  - expose:
    - `inserted_valid`
    - `rejected_count`
    - `rejection_breakdown`
    - `status` (`success|degraded_success|failed`)
  - for search-template path also expose:
    - `search_results.result_count`
    - `search_results.fallback_used`
    - `search_expand.enabled/expanded_count`

### 5.6 Configurable policy

- Add settings in `app/settings/config.py`:
  - `ingest_low_value_domains` (csv/json)
  - `ingest_low_value_path_keywords`
  - `ingest_shell_signatures`
  - `ingest_min_semantic_len` (default conservative)
  - `ingest_enable_strict_gate` (feature flag)

## 6. Rule Set v1 (Conservative)

URL policy reject:
- domain in:
  - `news.google.com`
  - `x.com`
  - `actiontoaction.ai`
- OR path includes:
  - `/search`, `/login`, `/home`, `/showcase`, `/topics/`, `/stargazers`, `/sitemap`

Content policy reject:
- empty content
- contains signature:
  - `window.wiz_progre`
  - `var bodyCacheable = true`
  - `self.__next_f`
  - `errorContainer`
- binary PDF raw marker `%PDF-1.` without extracted plain text
- normalized semantic text length < threshold

## 7. Milestones

M1 (1 day) - Gate foundation
- Add `meaningful_gate.py`
- Integrate into WF-1
- Add unit tests for rule hits and misses

M2 (1 day) - Multi-entry enforcement
- Integrate WF-2/WF-3 to reuse WF-1 write path
- Return rejection counters in business payload

M3 (0.5 day) - Observability and rollout
- expose response metrics
- enable feature flag by environment
- run canary on `demo_proj`

## 8. Acceptance Criteria

Functional:
- No new records with known shell signatures are inserted.
- No new records with raw PDF binary payload are inserted.
- No `url_fetch` low-value endpoint is inserted as final document.

Contract:
- API/task outputs include `inserted_valid`, `rejected_count`, `rejection_breakdown`.
- Status semantics distinguish `degraded_success` from real `success`.
- Frontend/API can externally pass search-template options listed in WF-1 and keep request contract stable in sync/async modes.

Regression safety:
- Existing meaningful article pages still pass and insert.
- Duplicate handling unchanged for valid docs.

## 9. Minimal Test Plan

Unit:
- `meaningful_gate.url_policy_check`
- `meaningful_gate.content_quality_check`
- status mapping function

Integration:
- single URL low-value endpoint -> rejected
- single URL valid article -> inserted
- url_pool batch with mixed candidates -> partial insert + rejection breakdown
- source_library auto-ingest -> no direct bypass write
- single URL search-template with `search_expand=true` -> fan-out child URLs and enforce WF-1 gate per child.
- single URL search-template with insufficient results + fallback enabled -> `fallback_used=true` and result count updated.

Contract:
- ingest API response fields stable for success/degraded/failed

## 10. Rollout and Risk Control

Rollout steps:
1. Enable strict gate in `demo_proj`.
2. Observe 24h rejection metrics and inserted_valid ratio.
3. Tune domain/path policy and length threshold.
4. Roll out to other project schemas.

Rollback:
- Feature flag `ingest_enable_strict_gate=false` to disable new gate quickly.

Risk:
- Over-blocking can reduce insert volume.
Control:
- Conservative v1 rules + explicit rejection telemetry + fast config tuning.

