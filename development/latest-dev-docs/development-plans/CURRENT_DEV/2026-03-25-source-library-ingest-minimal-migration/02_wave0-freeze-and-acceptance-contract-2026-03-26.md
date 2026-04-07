# Wave 0 Freeze And Acceptance Contract

Updated: 2026-03-26 PST

## Purpose

This file closes `AT-SLIM-01` for the current source-library / ingest
minimal migration topic.

It freezes the execution scope before any structural code move and serves
as the handoff baseline for Wave 1 parallel execution.

## Frozen Outputs

### 1. Shared Acceptance Contract

- Search and Harvest remain two upstream business chains.
- The convergence target is shared called services, not semantic
  flattening of the two chains.
- `collect_urls_from_list(...)`,
  `ingest_url_via_source_library_frontdoor(...)`,
  `terminal_output`,
  `legacy_result`,
  and `job_logger` remain visible until a dedicated removal plan exists.
- `ingress_envelope` remains the pre-frontdoor unified contract.
- `document_candidate -> accept` and `records-only -> defer` remain
  individually traceable in docs, code, and tests.
- for source-library records that discover a primary-source PDF during
  URL materialization, the pre-frontdoor contract may carry the PDF as a
  local artifact payload, not just an external link.
- the expected artifact payload shape is
  `record_meta.artifact_ref` plus
  `frontdoor_ingress.collection_payload.source_artifacts`, with
  `local_path`, `sha256`, `byte_size`, `mime_type`, and
  `source_locator` preserved for downstream PDF-specific handling.

### 2. Batch Helper Input Boundary

Frozen by:

- [references/2026-03-26-batch-helper-input-boundary-and-runtime-target-contract.md](./references/2026-03-26-batch-helper-input-boundary-and-runtime-target-contract.md)

Decision:

- the future batch helper consumes `runtime_targets`
- it does not consume raw caller `urls`

### 3. Batch Switch Precedence Matrix

Frozen by:

- [references/2026-03-26-batch-switch-rollout-dispatch-precedence-matrix.md](./references/2026-03-26-batch-switch-rollout-dispatch-precedence-matrix.md)

Decision:

- async dispatch forces legacy per-URL path
- batch path selection and frontdoor rollout remain separate control
  planes
- rollback must use the batch-path knob or repo-level batch-path default

### 4. Node-Preservation Gate

Frozen by:

- [references/02_source-library-ingest-node-mapping-and-preservation-checklist-2026-03-26.md](./references/02_source-library-ingest-node-mapping-and-preservation-checklist-2026-03-26.md)

Execution rule:

- no Wave 1 or later task may replace node-level names with summary boxes
- every touched node must have an exact mapping before structural change

## Current Implementation Reality Confirmed At Freeze Time

The following current-code facts were verified before Wave 1 started:

- `run_item_with_url_routing(...)` exists as the current routed
  materialization helper
- `collect_urls_from_list(...)` exists as the current batch runtime entry
- `ingest_url_via_source_library_frontdoor(...)` exists as the current
  single-URL compatibility path
- `build_source_library_ingress_envelope(...)`,
  `build_frontdoor_ingress_envelope(...)`,
  and `run_postprocess_frontdoor(...)` exist as the current frontdoor
  convergence path
- the current async URL path still queues single-URL shaped tasks

## Wave 1 Entry Rule

Wave 1 may start only after reading this file together with:

- [03_atomic-tasklist-source-library-ingest-minimal-migration-2026-03-26.md](./03_atomic-tasklist-source-library-ingest-minimal-migration-2026-03-26.md)
- [04_parallel-wave-plan-source-library-ingest-minimal-migration-2026-03-26.md](./04_parallel-wave-plan-source-library-ingest-minimal-migration-2026-03-26.md)

## Recommended Validation

- `rg -n "Search|Harvest|runtime_targets|url_batch_path_mode|records-only|document_candidate" development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-25-source-library-ingest-minimal-migration -S`
