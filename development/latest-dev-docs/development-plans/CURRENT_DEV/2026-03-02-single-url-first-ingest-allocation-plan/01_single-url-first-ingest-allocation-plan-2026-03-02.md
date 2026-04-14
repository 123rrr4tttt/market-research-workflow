# Single-URL First Ingestion Allocation Plan (2026-03-02)

## 1. Goal

Build a stable ingestion path where users input general task params from frontend, and backend consistently outputs meaningful, schema-consistent documents.

Execution strategy:
- Phase 1: make single URL pipeline deterministic and high quality.
- Phase 2+: add aggregation strategies on top of validated single URL primitives.
- Platformization rule: `single_url` is the only ingestion workflow for document writes.

## 2. End-to-End Layers (Frontend -> Document)

1. Frontend Task Input Layer
- Unified fields: `topic`, `query_terms`, `region`, `language`, `time_range`, `strict_mode`, `max_docs`.
- Frontend does not choose low-level handler types.
- Single-URL advanced fields are now externally configurable from frontend request payload:
  - `search_expand`, `search_expand_limit`
  - `search_provider`, `search_fallback_provider`, `fallback_on_insufficient`
  - `target_candidates`, `min_results_required`
  - `decode_redirect_wrappers`, `filter_low_value_candidates`

2. Task Planning Layer
- Build `ExecutionPlan` from user intent.
- Split into URL candidates + execution budget + quality thresholds.
- All candidates must be routed to `single_url` for final write decision.

3. Entry Capability Profiling Layer
- For each URL, compute:
  - `entry_type` (rss/sitemap/search_template/domain_root/api)
  - `render_mode` (static/js)
  - `anti_bot_risk` (low/medium/high)
  - `auth_required` (yes/no)

4. Handler Allocation Layer
- Select fetch strategy by capability score, not by `entry_type` only.
- Candidate strategy set:
  - `native_http`
  - `browser_render`
  - `crawler_provider`
  - `official_api`
- Note: handler choice is internal to `single_url`, not a separate ingest workflow.

5. Fetch + Anti-Bot Execution Layer
- Execute with retries, rate limit, user-agent and timeout policy.
- Persist fetch diagnostics (`status_code`, `redirects`, `blocked_signal`, `render_used`).

6. Parse + Relevance Gate Layer
- Classify fetched page: `detail/list/nav/login/search-shell`.
- Reject low-value pages before extraction (home/login/about/topics/search shell).

7. Extraction Layer
- Run structured extraction with explicit status:
  - `ok`
  - `empty_structured_output`
  - `extractor_exception`
- No pseudo-structured fallback fields for failed extraction.

8. Canonical Document Builder Layer
- Build consistent document envelope:
  - core: `doc_type/title/uri/content/summary/publish_date`
  - structured: `entities_relations/market/policy/sentiment`
  - quality/provenance: `quality_score/degradation_flags/handler_used/fetch_tier/source_ref`

9. Quality Decision Layer
- Final task status:
  - `success`: enough high-quality docs
  - `degraded_success`: docs exist but below quality threshold
  - `failed`: no usable docs

## 3. Phase 1 Scope (Single URL First)

### 3.1 Functional Scope
- New pipeline focus endpoint: single URL ingest path.
- Input: one URL + optional query context.
- Output: one canonical document + diagnostics.
- For `search_template` URLs, support optional search fan-out (`top-N` result URL expansion) and provider fallback, fully controlled by request options.

### 3.2 Allocation Rules (v1)
- Rule A: official API URL patterns -> `official_api`.
- Rule B: high JS/anti-bot domain list -> `browser_render` or `crawler_provider`.
- Rule C: static article/detail pages -> `native_http`.
- Rule D: if route fails, one controlled fallback only, then stop and mark degraded.

### 3.3 Anti-Bot Baseline
- Add per-domain policy table:
  - allowed strategy
  - retry budget
  - cooldown
  - ban indicators
- Store block signals in job params and document provenance.

### 3.4 Parse + Quality Baseline
- Add page-type classifier.
- Hard reject low-value types for final document ingestion:
  - login/register/account
  - homepage/navigation/topic hub
  - empty search shell without result entries

### 3.5 Canonical Schema Baseline
- Enforce consistent extracted keys and status fields.
- Required per-doc metadata:
  - `extraction_status`
  - `quality_score`
  - `degradation_flags`

## 4. Phase 2 Scope (Aggregation Strategies)

After single URL quality is stable, add aggregation strategies:
- Strategy S1: search-template expansion (strict relevance threshold).
- Strategy S2: sitemap/rss expansion (detail-page prioritization).
- Strategy S3: mixed-source hybrid (API + crawler + web fallback).

Aggregation uses single URL pipeline as the only ingestion primitive.
No new workflow is allowed to bypass `single_url` for direct `Document` insertion.

## 5. Milestones

M1 (Single URL MVP)
- Implement URL capability profiling + handler allocation v1.
- Implement parse relevance gate + extraction status normalization.
- Deliver consistent single-doc output contract.

M2 (Single URL Hardening)
- Domain anti-bot policy table + telemetry.
- Quality scoring and degraded_success semantics.
- Backfill script to normalize recent inconsistent docs.

M3 (Aggregation Enablement)
- Add S1 strategy with strict gate.
- Add per-strategy regression tests and quality KPIs.

## 6. Acceptance Criteria

For single URL mode:
- Same URL repeatedly ingested yields stable structured keys and status.
- Low-value pages are rejected before final document write.
- Blocked/JS pages are routed to stronger handler tier, not silently treated as success.
- Frontend receives explicit `success/degraded_success/failed`.

For system-level consistency:
- Document schema is stable across handler types.
- No pseudo-structured payload for extraction failures.

## 7. Minimal Test Plan

1. Unit tests
- URL capability profiling and allocation decision.
- Low-value page classifier.
- Canonical document builder field contract.

2. Integration tests
- Single URL static page -> success.
- Single URL JS/anti-bot page -> routed handler + meaningful result/degraded.
- Single URL low-value page -> rejected/degraded.

3. Contract tests
- Frontend response shape for `success/degraded_success/failed`.

## 8. Risks and Controls

Risk:
- Over-strict gating may reduce insert counts.

Control:
- Use degraded_success tier and tune thresholds by domain cohorts.

Risk:
- Domain anti-bot behavior changes quickly.

Control:
- Keep policy table configurable and versioned; monitor fallback rates.

## 9. Deliverables

- Single URL ingestion plan and execution checklist (this doc).
- Implementation tasks (next document in CURRENT_DEV).
- Test matrix and rollout checklist.

