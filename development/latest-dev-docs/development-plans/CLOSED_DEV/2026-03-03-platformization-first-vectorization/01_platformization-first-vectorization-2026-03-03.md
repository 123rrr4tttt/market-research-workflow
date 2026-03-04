# Platformization-First Refactor GM (2026-03-03)

## 1. Decision

Refactor order is fixed as:

1. Platformization first (stabilize single write workflow and ingest contracts)
2. Vectorization second (build on stable upstream semantics)

Rationale:
- Current docs already define `single_url` as the only final write workflow.
- If vectorization is done before platformization, ingest refactors will change upstream payload semantics and force re-embedding/revalidation.

## 2. Scope

In scope:
- Backend ingest workflow standardization around `single_url`
- Task orchestration and runtime observability standardization
- Contract freeze for vectorization upstream fields
- Vectorization Phase M1/M2 after platform contract freeze

Out of scope (this GM):
- Frontend visual redesign
- Full graph engine migration
- Non-core domain feature expansions

## 3. Target Architecture Baseline

Single write rule:
- Only `app/services/ingest/single_url.py` (or its refactored pipeline successor) can persist final `Document` records.
- `url_pool`, `source_library`, `discovery`, `raw_import` are candidate production / orchestration layers only.

Contract rule:
- All ingest entries must emit stable business result fields:
  - `status`
  - `inserted_valid`
  - `rejected_count`
  - `rejection_breakdown`
  - `degradation_flags`

Vectorization upstream contract freeze (before M1):
- `project_key`
- `object_type`
- `object_id`
- `vector_version`
- `clean_text`
- `language`
- `source_domain`
- `effective_time`
- `keep_for_vectorization`

## 4. Execution Plan

### P0 (Platformization Core)

P0-1: GateService consolidation
- Create shared gate module (URL policy + content quality + provenance reason codes).
- Ensure all write paths reuse one gate implementation.

P0-2: `single_url` pipeline split
- Refactor into staged pipeline:
  - `classify`
  - `fetch`
  - `parse`
  - `gate`
  - `persist`
- Keep output payload backward-compatible.

P0-3: Task orchestration normalization
- Remove direct `.run(...)` style task chaining where broker path is expected.
- Use explicit async orchestration semantics and preserve job status visibility.

P0-4: API/router startup hardening
- Remove broad silent router-load fallback behavior.
- Fail fast when API module loading is broken.

### P1 (Platform Productization)

P1-1: Runtime observability standard fields
- Add/normalize:
  - `error_code`
  - `quality_score`
  - `handler_used`
  - `skip_reason`

P1-2: Replay support baseline
- Provide replay entry based on historical job parameters.

P1-3: Contract hardening
- Explicitly return effective defaults in API responses for ingest options.

### M1 (Vectorization Foundation, after P0 freeze)

M1-1: Data model and storage baseline
- Keep compatibility with current `Embedding` table while introducing general object-level vector contract.
- Ensure migration safety and rollback path.

M1-2: Embedding pipeline baseline
- Document/chunk pipeline with versioned embeddings.
- Enforce frozen upstream fields from Section 3.

M1-3: Retrieval API baseline
- Introduce/align a unified vector retrieval endpoint for internal reuse.

### M2 (Business Integration)

M2-1: Hybrid search integration hardening
- Keep current hybrid path stable, then extend object types gradually.

M2-2: Graph/report adapters
- Add adapters for graph dedupe and report evidence retrieval on shared vector plane.

## 5. Milestones and Exit Criteria

Milestone A (P0 done):
- All major ingest write paths converge to single write workflow.
- Gate reason codes are unified and observable.
- Existing ingest contract tests pass.

Milestone B (P1 done):
- Process metrics expose core quality/error dimensions.
- Replay baseline available.

Milestone C (M1 done):
- Vectorization pipeline runs on stable ingest outputs.
- Vector contract test passes.

Milestone D (M2 done):
- Search/graph/report consume same vector foundation without contract drift.

## 6. Test and Guardrails

Required checks per phase:

P0/P1:
- `pytest -m "unit and not external" -q`
- `pytest -m "integration and not external" -q`
- `pytest tests/core_business/test_ingest_core_contract.py -q`

M1/M2:
- `pytest -m "contract and not external" -q`
- vector contract tests (new)
- hybrid search regression tests

## 7. Risks and Controls

Risk 1: over-blocking after gate unification
- Control: feature flag + canary on `demo_proj` + rejection telemetry review.

Risk 2: pipeline refactor breaks legacy task assumptions
- Control: staged rollout, keep payload compatibility, add regression matrix.

Risk 3: vector coverage drop after stricter ingest gates
- Control: track coverage KPI separately from quality KPI; tune thresholds with sample review.

## 8. Working Rules

- Do not start vector M1 before P0 contract freeze sign-off.
- Any change touching ingest output fields must update contract tests first.
- Avoid introducing a second write workflow.

## 9. Suggested File-Level Taskboard

Platformization first:
- `main/backend/app/services/ingest/single_url.py`
- `main/backend/app/services/ingest/meaningful_gate.py`
- `main/backend/app/services/tasks.py`
- `main/backend/app/main.py`
- `main/backend/app/api/ingest.py`

Vectorization second:
- `main/backend/app/models/entities.py`
- `main/backend/app/services/indexer/policy.py`
- `main/backend/app/services/search/hybrid.py`
- `main/backend/tests/contract/` (new vector contract test)

## 10. Current Status

- Decision confirmed: platformization first, vectorization second.
- This GM is the execution baseline for 2026-03-03 onward.
