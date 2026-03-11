# P1 Delivery Checklist and Parallel Status

Date: 2026-03-10 (PST)  
Topic: Agent + Symbolic + Batch Search  
Phase: P1 (Collection-chain enablement)

## 1. Scope (P1)

Included atomic tasks:
- AT-01 collection contract freeze + compatibility map.
- AT-02 collection adapters registry-only migration.
- AT-03 symbolic guardrails on collection path.
- AT-04 scheduler baseline with strategy knobs.
- AT-05 batch APIs (P1 delivery dependency for execution surface).
- AT-06 existing UI operations (Spark composition + Codex contract lock).

Out of P1 scope:
- AT-07/08/09 (workflow/llm full skillization, handoff hardening finalization, release/rollback full gate).

## 2. Parallel Execution Status (Spark/Codex)

### Spark lane (doc/contracts/UI composition)

- AT-01 contract artifacts: Done.
- AT-01 compatibility mapping table: Done.
- AT-06 UI operation flow/copy draft: Done.
- P1 documentation sync (`02/03/04/05` consistency): In progress.

### Codex lane (runtime/integration/contract lock)

- AT-02 adapter runtime migration: Done.
- AT-03 guardrail matrix + reason taxonomy + fail-closed routing: Done.
- AT-04 scheduler baseline + strategy knobs: Done.
- AT-05 batch API family baseline: Done.
- AT-06 final API contract lock + regression verification: Done (local implementation + build/contract verification complete).

## 3. P1 Gate Commands (must pass)

Primary gate for P1 wave:
```bash
bash scripts/test-standardize.sh contract
bash scripts/test-standardize.sh integration
```

Recommended targeted checks before merge:
```bash
bash scripts/test-standardize.sh unit
bash scripts/test-standardize.sh core
pytest main/backend/tests/integration/test_t22_source_library_scrapy_collect_runtime_integration_unittest.py -q
pytest main/backend/tests/core_business/test_process_consistency_core_contract.py -q
```

## 4. P1 Done Criteria (验收标准)

P1 is accepted only when all criteria below are true:

1. Collection chain is agent-triggerable end-to-end and can persist outputs through project-native contracts.
2. Collection adapters run through registry-only dispatch; compatibility bridge remains available for legacy callers.
3. Guardrail decisions are deterministic and fail-closed, with stable `reason_code` emitted for every blocked path.
4. Scheduler state projection includes `schedule_id/batch_id/state/attempt_count` and is query-consistent via `/process/*` endpoints.
5. Batch execution surface for collection path is reachable from API and observable in process timeline.
6. P1 gate commands pass (`contract` + `integration`) with no new P1-scope regression.
7. Spark/Codex split responsibilities are both completed, and AT-06 final contract lock is merged.

## 5. Delivery Sign-off Checklist

- [ ] AT-01/02/03/04/05 implementation merged.
- [ ] AT-06 UI + API contract lock merged.
- [ ] P1 gate commands executed and archived in CI artifacts.
- [ ] No silent production fallback from durable store to memory on collection path.
- [ ] Docs index updated (`README.md` in this topic) and read order includes this checklist.

## 6. Ownership Snapshot (for handoff)

- Spark: contract documentation, compatibility map, UI operation composition.
- Codex: runtime orchestration changes, adapter/guardrail/scheduler/batch API implementation, final contract lock and regression gate.
- Joint: P1 done-criteria confirmation and merge gate sign-off.

## 7. Execution Update (2026-03-10, Codex)

- `agent-batch` submit path now enforces fail-closed guardrail pre-dispatch:
  - unsupported channels are rejected with stable `reason_code`,
  - missing `contract_version` is rejected pre-dispatch.
- `rule_set` pre-dispatch controls are wired for P1 collection path:
  - `blocked_channels`,
  - `max_items_cap`,
  - `provider_allowlist`,
  - `require_project_key`.
- `rule-sets/validate` now emits unsupported-field warnings for non-P1 keys.
- Unit and contract/integration gates were rerun after change; the previously observed local integration smoke failure (`test_frontend_ingest_flow_smoke_unittest.py`) has now been fixed in follow-up validation.

## 8. Execution Update (2026-03-10, Codex, AT-06 UI Contract Lock)

- Frontend existing page operation now wires full P1 batch-execution surface without adding a standalone UI page:
  - submit batch (`/agent-batch/jobs`),
  - query queue/progress (`/agent-batch/jobs/{job_id}` + `/items`),
  - timeline (`/events`),
  - failed-item one-click replay (`/retry`),
  - optional NL command entry (`/nl-command`).
- API endpoint map and typed wrappers were added in `frontend-modern` for all P1 `agent-batch` routes, including rule-set validation endpoint exposure.
- Ingest page now includes:
  - queue view,
  - timeline table,
  - failure error display and rejected `reason_code` summary,
  - per-item retry action.
- Local verification after AT-06 wiring:
  - `npm run build` (frontend-modern): pass.
  - `bash scripts/test-standardize.sh contract`: pass.
  - `bash scripts/test-standardize.sh integration`: pass.
- Integration smoke fix summary:
  - `tests/integration/test_frontend_ingest_flow_smoke_unittest.py` task stubs now mock Celery-style `.delay(...)` calls correctly.
  - Sync assertion now matches current ingest source-library sync payload shape (`mode: sync`, top-level counters).
