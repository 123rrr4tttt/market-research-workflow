# Agent Dispatch Lane Alignment and Contract Closure (2026-03-14)

## Summary

This closure note records the follow-up alignment work required after the source-library service architecture was split into item resolver, orchestrator, and clean terminal output layers.

Two gaps were identified in the agent-facing runtime:

1. `ingest.dispatch.*` still used direct `.delay(...)`, which bypassed lane-aware queue routing already implemented by `agent_batch.dispatch.*`.
2. Frontdoor tests still assumed `generic_web.*` could be executed directly, while the resolver now treats that path as an internal-only capability.

## Decisions

1. `ingest.dispatch.market_collect` and `ingest.dispatch.source_library_item` must use the same lane routing helper as `agent_batch.dispatch.*`.
2. Lane validation is strict: accepted values are `main`, `subagent`, `system`.
3. `agent_batch` manifest payloads must explicitly include `channel` so manifest and runtime payload shape stay aligned.
4. `generic_web.*` direct execution remains blocked unless `_allow_internal_generic_web=true` is supplied by an internal caller.

## Runtime Contract

### Lane routing

- Shared helper:
  - validates lane
  - resolves queue by lane
  - uses `apply_async(queue=..., routing_key=...)` when available
  - falls back to `.delay(...)` only when the task stub does not expose `apply_async`

### Source-library async dispatch

- Ingest path:
  - `POST /api/v1/ingest/source-library/run`
  - async branch -> `ingest.dispatch.source_library_item`
  - lane fixed to `subagent`
- Agent path:
  - `POST /api/v1/agent-batch/jobs`
  - `channel=source_library`
  - dispatches via `agent_batch.dispatch.source_library_item`

Both paths now share the same lane semantics and queue routing rules.

## API / Output Notes

1. `POST /api/v1/ingest/source-library/run` sync path is no longer documented as a legacy bare-json style response.
2. The authoritative output contract is `source_library.terminal_output.v1`.
3. Legacy counters may still appear inside compatibility snapshots, but terminal output is the primary contract.

## Validation

Run:

```bash
cd main/backend
.venv311/bin/python -m pytest -q \
  tests/core_business/test_ingest_core_contract.py \
  tests/unit/test_agent_batch_api_unittest.py \
  tests/unit/test_frontdoor_orchestrator_unittest.py
```

Expected:

1. ingest async tests assert lane-aware `apply_async(queue=..., routing_key=...)`
2. agent-batch tests remain green with explicit `channel` payload alignment
3. frontdoor tests assert both:
   - internal generic_web path works when explicitly enabled
   - direct generic_web execution is rejected by default
