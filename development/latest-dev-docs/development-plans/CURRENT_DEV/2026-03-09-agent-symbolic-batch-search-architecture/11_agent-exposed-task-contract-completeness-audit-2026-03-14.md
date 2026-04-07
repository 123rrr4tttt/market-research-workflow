# Agent-Exposed Task Contract Completeness Audit (2026-03-14)

## 1. Summary

This note audits whether the current agent-facing task contract is complete enough for the LLM to invoke backend capabilities with sufficient parameters.

Conclusion:

1. the current contract is sufficient for basic task triggering,
2. after the 2026-03-14 remediation, the contract is materially closer to full-parameter invocation,
3. the remaining gap is no longer multi-file hand-written drift in core task specs; a shared task-contract module now exists, but broader runtime schema generation is still not fully centralized.

The most important issue is not missing endpoints. The issue was contract drift between planner-visible schema and execution-effective schema. A first remediation pass has now removed the highest-risk false-capability cases and added `override_params` allowlist enforcement.

## 2. Scope

This audit covers the agent-facing path around:

- `planner` task manifest,
- `agent_loop` task normalization,
- `agent_batch` dispatch payload construction,
- downstream runtime parsing for `search.market` and `source_library`.

Primary code references:

- `main/backend/app/services/agent_batch/planner.py`
- `main/backend/app/services/agent_batch/agent_loop.py`
- `main/backend/app/api/agent_batch.py`
- `main/backend/app/services/skill_runtime.py`
- `main/backend/app/services/collect_runtime/runtime.py`

## 3. Current Contract Shape

### 3.1 Planner-visible task types

The planner currently exposes two main task families to the LLM:

1. `search.market`
2. `source_library`

Planner manifest today gives the LLM a narrow task schema with required keys and optional keys.

### 3.2 Runtime-effective parameter surface

The runtime can effectively consume more parameters than the planner clearly exposes, especially for `source_library`, where much of the execution control is reconstructed from `override_params`.

This creates a split between:

- what the LLM is told it may send,
- what submit/dispatch preserves,
- what the runtime actually consumes.

## 4. Findings

### 4.0 Status Update After Remediation

The following items are now closed or partially closed in code:

1. `search.market.override_params` is now preserved through NL task submission and dispatch.
2. `source_library` now exposes more effective top-level fields to the planner-visible contract:
   - `query_terms`
   - `urls`
   - `provider`
   - `language`
   - `max_items`
   - `scope`
   - `platforms`
   - `source_mode`
3. `override_params` is no longer an open black box in `agent_batch`; channel-scoped allowlists now reject unsupported keys fail-closed.

Remaining open issue:

- planner manifest and allowlist governance now share one base task-contract source, but broader runtime request parsing is still not fully generated from that same definition.

### 4.1 Closed: `search.market.override_params` is now preserved end-to-end for supported keys

This was previously a high-risk false-capability gap.

Current supported keys:

- `enable_extraction`
- `start_offset`

These keys are now preserved through NL -> planner -> normalize -> submit -> dispatch.

### 4.2 Partially Closed: `source_library` planner schema is now wider and closer to the real runtime control surface

For `source_library`, the backend can interpret a richer set of execution controls from `override_params`, including runtime search and collection shaping fields such as:

- `query_terms`
- `urls`
- `limit`
- `provider`
- `language`
- `scope`
- `platforms`

The planner-visible schema now explicitly exposes a meaningful subset of these fields at top level, but schema ownership is still not fully centralized.

Effect:

- the runtime can do more than the agent is clearly told,
- the LLM cannot stably reason about the full valid parameter set,
- capability discovery is incomplete.

### 4.3 Medium: `source_library` still relies partly on implicit `override_params` conventions instead of a single explicit execution schema

`_submit_source_item(...)` keeps the top-level payload thin. Downstream runtime parsing then rehydrates behavior from `override_params`.

This is operationally workable, but contract quality is weak:

- parameter ownership is unclear,
- schema evolution is fragile,
- planner, dispatcher, and runtime may drift independently.

### 4.4 Reduced: manifest inconsistencies are smaller but contract ownership has not fully converged

The previous `source_library.defaults.provider` inconsistency has been addressed by explicitly exposing `provider` in the planner-visible optional keys.

This weakens the prompt contract and makes it harder for the LLM to distinguish between:

- officially supported parameters,
- implementation artifacts,
- legacy compatibility leftovers.

### 4.5 Low: normalization constraints are not fully surfaced in the agent contract

Some parameters are normalized or clamped during the agent loop, such as bounded `days_back` handling.

This is acceptable as a guardrail, but the constraint should be explicit in the agent-facing contract. Otherwise the LLM may form incorrect expectations about effective values.

## 5. Why This Matters

If the project goal is that the agent should be able to directly call all backend capabilities through skills, then the contract exposed to the LLM must satisfy all of the following:

1. complete enough for capability discovery,
2. precise enough to avoid false capability,
3. stable enough for prompt governance,
4. testable end-to-end.

The current state now satisfies item 4 materially better and partially improves items 1 to 3, but not fully.

## 6. Required Contract Model

The contract should be reorganized around one authoritative task schema per planner-visible skill.

### 6.1 Recommended rule

For every planner-visible task type, define exactly:

1. required top-level fields,
2. optional top-level fields,
3. allowed `override_params` keys,
4. normalization rules,
5. execution guarantee: whether the field is only advisory or actually behavior-affecting.

### 6.2 Recommended shape for `search.market`

Top-level should continue to own stable task-routing and common retrieval controls:

- `channel`
- `task_id`
- `query_terms`
- `max_items`
- `provider`
- `language`
- `days_back`

If `override_params` is retained, it must be narrowed and documented to only advanced controls that are truly preserved and consumed.

Example categories:

- pagination/offset controls,
- extraction toggles,
- per-keyword collector tuning.

If the chain does not preserve them, they must not be exposed.

### 6.3 Recommended shape for `source_library`

The contract should stop pretending that `source_library` is only `item_key + opaque override blob`.

Recommended top-level fields:

- `channel`
- `task_id`
- `item_key`
- `provider`
- `language`
- `max_items`
- `source_mode`
- `query_terms`
- `urls`

Recommended `override_params` reservation:

- only truly secondary knobs that are item-specific or runtime-advanced,
- not fields that are already first-class execution parameters.

### 6.4 Single-source contract ownership

The planner manifest, task normalization, submit payload builders, and runtime parsing should all derive from the same schema definition.

Target layering:

1. authoritative task schema definition,
2. planner prompt manifest generated from schema,
3. runtime validator/normalizer generated from schema,
4. dispatch payload built from validated normalized schema.

## 7. Minimal Remediation Plan

### 7.1 P0: remove false capability

Status:

- completed for `search.market` supported override keys.

### 7.2 P0: align `source_library` schema with real execution fields

Status:

- partially completed:
  - effective fields promoted to top level where appropriate,
  - remaining supported `override_params` now constrained by allowlist,
  - misleading planner inconsistency reduced.

### 7.3 P1: unify schema ownership

Introduce one shared schema source for:

- planner manifest,
- loop normalization,
- dispatch payload validation,
- skill manifest documentation.

Status:

- completed for:
  - planner manifest,
  - loop normalization,
  - dispatch skill metadata (`skill_id` / permission / consumer / trace prefix),
  - lane default policy,
  - approval argv contract,
  - skill runtime bootstrap registration metadata,
  - override allowlist governance.

- still recommended:
  - reduce `_normalize_channel` heuristic fallback for future non-search/source business channels.

### 7.4 P1: add contract tests

Add end-to-end tests for every planner-visible parameter that claims to affect behavior.

Minimum required coverage:

Status:

- completed for:
  - `search.market.override_params` survival,
  - unsupported override rejection,
  - `source_library` top-level field promotion into effective payload,
  - planner manifest field exposure checks.

- still recommended:
  - schema-source consistency tests generated from one authoritative definition.

## 8. Acceptance Standard

The agent-facing contract should be considered complete only when all of the following are true:

1. every planner-visible parameter has one authoritative definition,
2. every exposed parameter is either behavior-affecting or explicitly advisory,
3. planner-visible schema matches dispatch-effective schema,
4. runtime-only hidden parameters are minimized,
5. contract tests fail if exposed parameters stop being effective.

## 9. Decision

Current decision after audit and first remediation:

- current contract is usable for basic task planning,
- current contract now supports a materially larger and safer parameter surface for agent invocation,
- `override_params` has moved from black-box behavior to allowlist-governed behavior,
- current contract ownership now extends through planner, submit, dispatch invocation, approval binding, and skill bootstrap,
- next implementation work should target remaining heuristic channel inference and, only if needed, collect-runtime adapter auto-registration.

## 10. Current Allowed Override Keys

### 10.1 `search.market`

Allowed `override_params` keys:

- `enable_extraction`
- `start_offset`
- `require_approval`
- `approval_token`

### 10.2 `source_library`

Allowed `override_params` keys:

- `query_terms`
- `keywords`
- `search_keywords`
- `base_keywords`
- `topic_keywords`
- `urls`
- `max_items`
- `limit`
- `provider`
- `language`
- `lang`
- `scope`
- `platforms`
- `source_mode`
- `pool_scope`
- `enable_extraction`
- `keyword_batch_size`
- `per_keyword_limit`
- `_allow_internal_generic_web`
- `_handler_key`
- `_handler_site_entry_count`
- `require_approval`
- `approval_token`
- `workflow_run_id`
- `trace_id`
