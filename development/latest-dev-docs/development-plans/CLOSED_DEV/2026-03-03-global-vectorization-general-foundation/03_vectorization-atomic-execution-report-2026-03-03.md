# Vectorization + Legacy Merge Execution Report (2026-03-03)

## 1. Scope (Only Old Merge + Vectorization)

This report tracks only:
- vector-recall grouping
- LLM merge suggestion
- merge apply to database
- compare project verification

This report explicitly ignores A/B wording and phase semantics.

## 2. Delivered Capabilities

Implemented and usable in backend:
- node similarity recall API
- batch merge suggestion API (vector grouping + parallel LLM)
- fixed auto merge workflow
- supplemental grouping algorithm for small groups (fallback threshold)
- merge apply executor (node merge + edge remap)

Current merge eligibility rule (default):
- include: merge-eligible term-like nodes
- exclude: data-point nodes
- exclude: content-like sentence nodes

## 3. Latest Execution Snapshot (2026-03-03 PST)

### 3.1 Compare Run (latest retained run)

Path:
- `group-exports/project-compare-demo_proj_compare_0303_121137-20260303-124126/`

Summary:
- source `demo_proj`: `candidate_count=2242`, `group_count=1119`, `merge_count=36`
- compare project `demo_proj_compare_0303_121137`: `candidate_count=2240`, `group_count=1121`, `merge_count=32`
- thresholds: `similarity_threshold=0.74`, `fallback_similarity_threshold=0.72`

### 3.2 Merge Apply to Compare Project DB

Apply report:
- `project-compare-demo_proj_compare_0303_121137-20260303-124126/apply_merge_report.json`

Apply result:
- `input_merge_items=32`
- `applied_merge_items=32`
- `skipped_merge_items=0`
- `deleted_source_nodes=37`
- `inserted_edges=57`

Pool delta after apply:
- `total_nodes: -36`
- `non_data_nodes: -36`
- `data_point_nodes: 0`
- `total_edges: -62`

## 4. Duplicate Check (AI Example, Post-Apply)

Check target project:
- `demo_proj_compare_0303_121137`

Observed counts:
- exact `display_name='AI'` (case-insensitive): `11`
- exact `canonical_id='AI'` (case-insensitive): `2`

Entity-level AI nodes observed:
- IDs: `41`, `448`, `44068`

Trace outcome:
- `41` and `448` entered the same candidate group in compare run.
- LLM merge output merged `448` with another node, did not include `41`.
- `44068` was created after compare output generation timestamp, thus not included in that compare result set.

## 5. Current Constraint (Legacy Merge Path)

Why same-name nodes can remain:
- merge is constrained by same-type + group candidate set + guardrail threshold
- if a node is outside candidate set of that run, it cannot be merged in that round
- if LLM output does not include a node, it remains

## 6. Conclusion

- Vectorization + legacy merge workflow is operational end-to-end.
- Compare project write-back is confirmed working.
- Residual same-name nodes are explainable under current candidate/guardrail logic.
- Next strictness step (if needed): deterministic same-name merge fallback for selected node types.
