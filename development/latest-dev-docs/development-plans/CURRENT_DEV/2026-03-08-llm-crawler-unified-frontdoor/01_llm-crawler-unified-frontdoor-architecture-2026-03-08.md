# LLM + Crawler Unified FrontDoor Architecture (Draft)

Date: 2026-03-08 (PST)
Owner: backend ingest / crawler pipeline
Scope: `main/backend/app/services/ingest/*`

## 1. Background and Goal

Current direction is correct: `mechanical flow + adapter + crawler`.
Main gap is not crawler capacity itself, but inconsistent front-door handling and uneven adapter coverage.

Target state:
- Any URL enters one unified front door.
- Output is always either:
  - high-quality body content written to `documents`, or
  - a machine-readable failure reason with stable reason code.
- URL-only payload must never land in `documents`.

Non-goal:
- Not aiming for 100 percent successful body extraction for all URLs.

## 2. Architecture Overview

Unified chain:
1. `FrontDoorIngestOrchestrator`
2. `URL Normalize + Unwrap Adapter Pool`
3. `Policy/Safety Gate`
4. `Fetch Router` (`http_fetch | browser_fetch | crawler_pool`)
5. `Extraction Pipeline` (`rule -> readability -> llm(schema)`)
6. `Quality Gate`
7. `Persist` (body-only)
8. `Observability + reason code metrics`

## 3. Stage Contracts (must be stable)

Each stage returns a consistent envelope:
- `status`: `success | degraded_success | failed`
- `reason_code`: stable internal code
- `reason_category`: `policy | fetch | extract | quality | system`
- `stage`: `unwrap | gate | fetch | extract | quality | persist`
- `retryable`: boolean
- `trace_id`: string
- `request_key`: string
- `degradation_flags`: list[string]
- `diagnostics`: object

Contract rule:
- `documents` write is allowed only when `status=success` and `quality_gate_passed=true`.

## 4. URL Unwrap Adapter Pool Plan

Current adapters:
- `query_wrapped_url`
- `google_news_token`

Pool rules:
- ordered execution, bounded by `max_steps`
- each adapter emits `step_name`
- final URL must pass safety checks before network redirect

Next adapters (priority):
1. social redirect wrappers (`l.php`, `t.co`, `lnkd.in` style)
2. aggregator/news wrappers with tokenized path variants
3. file-host wrappers (only if target type is body-extractable)

## 5. Safety Baseline (mandatory)

Before any redirect-follow or fetch:
- deny localhost and private CIDR targets
- deny non-http(s) protocols
- optional domain allow/deny policy by project
- keep robots policy decision explicit in result

If blocked:
- no `documents` write
- return `failed/degraded_success` with reason code, e.g.:
  - `ssrf_target_blocked`
  - `robots_forbidden`
  - `url_policy_blocked`

## 6. Fetch Router Strategy

Routing heuristics:
- static/detail page: direct HTTP fetch first
- high-js or known anti-bot domains: browser/crawler pool first
- search/list shell pages: extract candidate links then recurse via same front door

Retry policy (borrowed from mature crawler practice):
- retry only transient failures (`429`, `5xx`, timeout, connection reset)
- cap retries with per-request counter
- emit reason counters by class

## 7. Extraction Pipeline Strategy

Extraction order:
1. rule-based extraction (cheap)
2. readability/general text extraction
3. llm structured extraction with schema (optional enhancement)

LLM usage policy:
- LLM is not a replacement for fetch/parse stage
- LLM is an enhancement for structure and normalization
- always attach extraction provenance in diagnostics

## 8. Quality Gate and Persistence Policy

Minimum gate examples:
- body length threshold
- noise ratio threshold
- no script-shell / nav-shell dominant content

Persistence rules:
- pass: write `documents` with body
- fail: do not write `documents`; write task result + reason only

This preserves strict invariant:
- `documents` final artifact must be body content, source-independent.

## 9. Metrics and SLO

Required metrics:
- `url_only_document_rate` (target 0)
- `empty_body_rate`
- `reason_code_top_n`
- `retry_count_by_reason`
- `adapter_hit_rate`
- `extract_success_rate_by_channel`

Operational SLO proposal:
- `url_only_document_rate == 0` for all projects
- top 10 failures all map to stable reason code

## 10. Integration Plan (phased)

Phase 1: front door and contract hardening
- add `FrontDoorIngestOrchestrator`
- force body-only documents policy
- unify status/reason envelope

Phase 2: unwrap + safety + routing hardening
- expand adapter pool and telemetry
- add SSRF-safe redirect checks
- route strategy split for js-heavy domains

Phase 3: extraction quality uplift
- schema-based LLM extraction as stage 3 enhancement
- reason-aware fallback and retry tuning

Phase 4: observability and rollout
- project-level dashboard
- gray rollout with per-project toggle
- strict regression gates in tests

## 11. File-level Landing Map (backend)

Primary files:
- `main/backend/app/services/ingest/url_unwrap.py`
- `main/backend/app/services/ingest/single_url.py`
- `main/backend/app/services/ingest/url_pool.py`
- `main/backend/app/services/ingest/news.py`
- `main/backend/app/services/ingest/market_web.py`

New recommended module:
- `main/backend/app/services/ingest/frontdoor_orchestrator.py`

## 12. Acceptance Criteria

Must pass:
1. no URL-only insert into `documents`
2. all front-door runs produce stable envelope fields
3. adapter steps are observable in result diagnostics
4. failure reasons are explainable and aggregatable
5. existing core ingest contract tests remain green

