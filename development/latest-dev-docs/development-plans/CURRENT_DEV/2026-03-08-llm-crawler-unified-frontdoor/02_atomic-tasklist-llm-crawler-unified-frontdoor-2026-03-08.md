# Atomic Tasklist: LLM + Crawler Unified FrontDoor

Date: 2026-03-08 (PST)
Owner: backend ingest / crawler pipeline
Parent: `01_llm-crawler-unified-frontdoor-architecture-2026-03-08.md`

## 0. 2026-05-22 Current Code Mapping

Status: `需更新 -> 已完成当前入口重映射` for this lane.

Implementation note:
- `single_url` in this tasklist is a legacy contract name. Current code uses `url_pool.single_url_compat` plus source-library URL routing and `postprocess_frontdoor`.
- `frontdoor_orchestrator.py` exists as `FrontDoorOrchestrator`; the URL-execution writer path is currently exercised through `ingest_url_via_source_library_frontdoor -> frontdoor_ingress -> run_postprocess_frontdoor(run_writer=True)`.
- The focused compatibility contract is now pinned by `main/backend/tests/unit/test_ingest_frontdoor_context_unittest.py`.

## 1. Scope and Deliverable

Goal:
- Implement a unified ingest front door with strict body-only persistence and stable stage contract.

Out of scope:
- Full guarantee of successful extraction for all URLs.

Final deliverable:
- All URL-based ingest paths route through one orchestrator and return a stable envelope.

## 2. Atomic Tasks

### AT-01 FrontDoor orchestrator skeleton
- Target: create orchestration entrypoint and stage flow scaffold.
- Input: existing URL-execution compatibility path, `url_pool`, `news`, `market_web`, and source-library terminal output flows.
- Output: `frontdoor_orchestrator.py` / frontdoor ingress-postprocess chain with deterministic stage sequence.
- Acceptance:
  - entrypoint callable from existing ingest services
  - stage order fixed and traceable
  - minimum contract fields always present
- Minimal gate:
  - unit test for stage sequence and envelope defaults

### AT-02 Unified stage envelope contract
- Target: normalize all stage outputs to one schema.
- Input: current mixed result payloads.
- Output: shared contract helper and reason-code normalization map.
- Acceptance:
  - fields: `status/reason_code/reason_category/stage/retryable/trace_id/request_key`
  - no stage returns ad-hoc-only status fields
- Minimal gate:
  - contract unit tests and existing core contract tests pass

### AT-03 URL unwrap adapter pool hardening
- Target: expand and standardize adapter-pool behavior.
- Input: current `query_wrapped_url` and `google_news_token` adapters.
- Output: ordered adapters with step audit and bounded execution.
- Acceptance:
  - adapter steps emitted in diagnostics
  - max steps enforced
  - duplicate final URL dedupe stable
- Minimal gate:
  - `test_url_unwrap_unittest.py` plus added adapter regression cases

### AT-04 Redirect safety baseline (SSRF-safe)
- Target: block unsafe redirect targets before follow.
- Input: current redirect-follow behavior in unwrap layer.
- Output: target validation for localhost/private/reserved ranges.
- Acceptance:
  - unsafe targets rejected with stable reason code (`ssrf_target_blocked`)
  - no unsafe follow is executed
- Minimal gate:
  - unit tests with mocked redirect targets

### AT-05 Router split by page/channel characteristics
- Target: route fetch strategy by URL/page characteristics.
- Input: existing direct-fetch and crawler fallback logic.
- Output: strategy router (`http_fetch | browser_fetch | crawler_pool`).
- Acceptance:
  - high-js/high-risk domains route to browser/crawler path
  - static detail pages keep light fetch first
- Minimal gate:
  - routing unit tests for representative domains

### AT-06 Retry policy standardization
- Target: reason-aware retry and max-attempt control.
- Input: current ad-hoc retries across flows.
- Output: retry class map (`transient/permanent`) and counters.
- Acceptance:
  - transient failures retried with cap
  - permanent failures no blind retry
  - retry counters emitted by reason
- Minimal gate:
  - unit tests for retry classification

### AT-07 Body-only persistence invariant
- Target: enforce strict persistence gate before `documents` write.
- Input: current persistence paths.
- Output: single persistence guard used by all URL ingest entrypoints.
- Acceptance:
  - URL-only and empty-body never written into `documents`
  - failure path records reason and diagnostics only
- Minimal gate:
  - integration test: URL-only payload should not create document row

### AT-08 Extraction pipeline tiering
- Target: stage extraction as `rule -> readability -> llm(schema)`.
- Input: current extraction utilities.
- Output: tiered extraction orchestrated in one place.
- Acceptance:
  - LLM extraction is enhancement layer, not fetch replacement
  - extraction provenance attached in diagnostics
- Minimal gate:
  - unit tests for tier fallback behavior

### AT-09 Observability and reason-code dashboard payload
- Target: emit stable operational metrics for failure analysis.
- Input: current job logs.
- Output: metric payload fields for monitoring/BI.
- Acceptance:
  - metrics include: `url_only_document_rate`, `empty_body_rate`, `reason_code_top_n`, `adapter_hit_rate`
  - all failures map to stable reason code
- Minimal gate:
  - contract test for metrics payload schema

### AT-10 Gray rollout and rollback controls
- Target: safe release via project-level toggle.
- Input: current runtime config model.
- Output: toggles for orchestrator/adapter/routing strictness.
- Acceptance:
  - can enable per project and rollback quickly
  - fallback path remains available during rollout
- Minimal gate:
  - config and integration tests for toggle behavior

## 3. Execution Order

1. AT-01
2. AT-02
3. AT-03 + AT-04
4. AT-05 + AT-06
5. AT-07
6. AT-08
7. AT-09
8. AT-10

## 4. Global Acceptance Criteria

- `url_only_document_rate == 0`
- all URL ingest entrypoints pass through front door
- all outputs expose stable envelope fields
- core ingest contract tests remain green

## 5. Minimal Verification Commands

```bash
cd main/backend
.venv311/bin/pytest -q tests/core_business/test_ingest_core_contract.py tests/core_business/test_api_group_b_core_contract.py
.venv311/bin/pytest -q tests/unit/test_url_unwrap_unittest.py
```
