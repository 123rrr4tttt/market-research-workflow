# Reinvestigation Focused on Single-URL First Ingest Allocation Plan (2026-03-02)

Reference plan:
- `01_single-url-first-ingest-allocation-plan-2026-03-02.md`

This review only re-audits the plan scope and marks each planned capability as:
- `Implemented`
- `Partially Implemented`
- `Not Implemented`

---

## A. Phase-1 Core (Single URL First)

### A1) Entry Capability Profiling
- Plan target: `entry_type/render_mode/anti_bot_risk/auth_required`
- Status: `Implemented`
- Evidence:
  - `main/backend/app/services/ingest/single_url.py:120-151`
  - Capability profile is propagated in result payloads and doc metadata:
    - `main/backend/app/services/ingest/single_url.py:682-683,766-767,799-800,949-951,981-982`

### A2) Handler Allocation Rules (A/B/C/D)

1. Rule A (`official_api` URL -> `official_api` handler)
- Status: `Partially Implemented`
- Evidence:
  - Planned handler/fetch tier exists: `main/backend/app/services/ingest/single_url.py:164-167`
  - But actual `handler_used` defaults to `native_http`: `main/backend/app/services/ingest/single_url.py:178-180`
  - Official API adapter is placeholder-level: `main/backend/app/services/source_library/adapters/official_access.py:8-19`

2. Rule B (high JS/anti-bot -> `browser_render` or `crawler_provider`)
- Status: `Partially Implemented`
- Evidence:
  - JS/high risk detection and planned tier: `main/backend/app/services/ingest/single_url.py:42-50,143-150,170-174`
  - Real browser-render execution path is not fully wired; practical fallback is crawler on specific conditions:
    - `main/backend/app/services/ingest/single_url.py:627-631,645-655`
  - Resolver contains `special_web.*` route placeholders: `main/backend/app/services/source_library/resolver.py:362-389,398-406`

3. Rule C (static detail -> `native_http`)
- Status: `Implemented`
- Evidence:
  - Detail inference and default tier: `main/backend/app/services/ingest/single_url.py:133-134,160-161`
  - Main fetch path: `main/backend/app/services/ingest/single_url.py:708-710`

4. Rule D (single controlled fallback then stop/degrade)
- Status: `Partially Implemented`
- Evidence:
  - Native fetch failure -> one crawler fallback attempt: `main/backend/app/services/ingest/single_url.py:707-713`
  - Search-template insufficient results -> one crawler fallback attempt: `main/backend/app/services/ingest/single_url.py:751-754`
  - Not uniform for all failure types (many gates return directly without fallback):
    - `main/backend/app/services/ingest/single_url.py:787-812,868-902`

### A3) Parse + Relevance Gate
- Plan target: reject low-value pages before final write
- Status: `Implemented`
- Evidence:
  - Candidate-level low-value URL filtering:
    - `main/backend/app/services/resource_pool/unified_search.py:249-268,512`
  - URL/content quality gate:
    - `main/backend/app/services/ingest/meaningful_gate.py:121-161,164-255`
  - Discovery store gate bridge:
    - `main/backend/app/services/ingest/discovery/store.py:95-116`
  - Single-url page-type low-value classification:
    - `main/backend/app/services/ingest/single_url.py:439-460`

### A4) Extraction Status + Canonical Metadata
- Plan target: explicit extraction status + stable metadata keys
- Status: `Partially Implemented`
- Evidence:
  - Stable keys present in output path: `quality_score/degradation_flags/structured_extraction_status`
    - `main/backend/app/services/ingest/single_url.py:936-973`
  - URL-pool aggregation preserves degradation/status context:
    - `main/backend/app/services/ingest/url_pool.py:278-413,440-590`
- Gap:
  - Plan wording uses `extraction_status`; code commonly exposes `structured_extraction_status`.
  - Consumer-side naming consistency is not guaranteed unless mapped.

### A5) Quality Decision (`success/degraded_success/failed`)
- Status: `Implemented` (result-level), `Partially Implemented` (observability-level)
- Evidence:
  - Result-level tri-state exists in single-url flow:
    - `main/backend/app/services/ingest/single_url.py:714-732,757-783,868-902,906-931,936-973`
- Gap:
  - Job/task outer status is separate (`completed/failed`) and can hide result-level degraded semantics if dashboards only read outer status:
    - `main/backend/app/services/job_logger.py:49-74,77-99`
    - `main/backend/app/services/tasks.py:43-62`

---

## B. Search-Template Batch Domain (within this plan’s aggregation prerequisite)

### B1) Is chain integrated?
- Status: `Implemented`
- Evidence:
  - Handler-cluster route in collect runtime:
    - `main/backend/app/services/collect_runtime/adapters/source_library.py:44-95`
  - Unified search executes per batch:
    - `main/backend/app/services/resource_pool/unified_search.py:341-355`

### B2) Why `candidates=0` happens frequently?
- Status: Known behavior, currently strict by default in handler-cluster path
- Evidence:
  - `allow_term_fallback` default differs by path:
    - Unified-search function default: true (`.../resource_pool/unified_search.py:307,354-355`)
    - Handler-cluster call default: false (`.../collect_runtime/adapters/source_library.py:94`)
  - Strict URL-term filtering and domain filtering can empty candidates:
    - `.../resource_pool/unified_search.py:216-247,458-461,486-487,512`

### B3) write_to_pool/auto_ingest defaults
- Status: `Implemented` with path-dependent defaults
- Evidence:
  - Unified-search API defaults false: `main/backend/app/api/resource_pool.py:618,620`
  - Handler-cluster path defaults true: `main/backend/app/services/collect_runtime/adapters/source_library.py:88-92`

---

## C. Anti-Bot Baseline and Block Diagnostics

- Plan target: persist block signals in task/document provenance
- Status: `Partially Implemented`
- Evidence:
  - There is gate-level rejection and degradation signaling:
    - `main/backend/app/services/ingest/single_url.py:603-623,874-902`
  - But no dedicated blocked-signal canonical field is consistently persisted in job params/doc metadata as a first-class contract key.

---

## D. Acceptance Criteria Re-check

1. Same URL repeatedly yields stable structured keys/status
- Status: `Partially Implemented`
- Notes: core keys are stable, but naming mismatch risk (`extraction_status` vs `structured_extraction_status`).

2. Low-value pages rejected before final write
- Status: `Implemented`

3. Blocked/JS pages routed to stronger handler, not silently success
- Status: `Partially Implemented`
- Notes: stronger planned tiers exist; actual execution still often native-first with conditional crawler fallback.

4. Frontend receives explicit `success/degraded_success/failed`
- Status: Backend `Implemented`; Frontend consumption `Not Implemented`
- Evidence:
  - FE action layer does not explicitly branch/render tri-state semantics:
    - `main/frontend-modern/src/hooks/useIngestActions.ts:53-63`
    - `main/frontend-modern/src/pages/IngestPage.tsx:80-85`
    - `main/frontend-modern/src/pages/ProcessPage.tsx:18-23`

5. No pseudo-structured payload for extraction failures
- Status: `Partially Implemented`
- Notes: graceful degraded path exists; no explicit “pseudo-structured” contract type, and no system-level contract test asserting this invariant end-to-end.

---

## E. Test Coverage Audit (plan’s minimal test plan mapping)

### E1) Unit tests
- Status: `Mostly Implemented`
- Evidence:
  - Single-url tri-state and degradation cases covered:
    - `main/backend/tests/unit/test_single_url_ingest_unittest.py:32-70,102-134,208-246,274-340`

### E2) Integration tests
- Status: `Partially Implemented`
- Gap:
  - Route/infrastructure checks exist, but explicit assertions for tri-state semantics and JS/blocked routing branches are limited:
    - `main/backend/tests/integration/test_ingest_baseline_matrix_unittest.py:50-132`

### E3) Contract tests
- Status: `Partially Implemented`
- Evidence:
  - Process consistency contracts are strong:
    - `main/backend/tests/core_business/test_process_consistency_core_contract.py:62-107,173-205`
- Gap:
  - Single-url result tri-state and extraction-failure no-pseudo-structured are not strongly asserted as contracts:
    - `main/backend/tests/core_business/test_ingest_core_contract.py:175-214`

---

## F. Final Verdict (focused on this plan domain)

Overall implementation state vs this plan:
- `Implemented`: capability profiling, static detail native path, low-value gating baseline, result-level tri-state semantics
- `Partially Implemented`: official_api allocation execution, JS/anti-bot stronger handler realization, single-fallback policy uniformity, blocked diagnostics persistence, canonical extraction status naming consistency, system-level test closure
- `Not Implemented` (from plan acceptance perspective): frontend explicit tri-state consumption

Short judgment:
- The plan is not stale; it is still the right domain model.
- Current system is in a “Phase-1 partially completed, with key semantics in place but strategy/contract closure not complete” state.
