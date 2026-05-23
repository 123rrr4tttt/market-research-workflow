# Parallel Execution Playbook (Spark/Codex)

Date: 2026-03-10 (PST)
Topic: Agent + Symbolic + Batch Search
Mode: high-parallel delivery with model routing

## 1. Execution Policy (frozen)

1. Massive parallelism by atomic tasks and low coupling boundaries.
2. Simple tasks -> Spark lane.
3. Complex tasks -> Codex lane.
4. Compatibility-first with project-native contracts.
5. New path converges to `status/data/error/meta` and keeps legacy adapters during migration.

## 2. Model Routing Standard

Spark lane (simple):
- doc/schema freeze,
- reason-code dictionary,
- compatibility mapping tables,
- lightweight tests (single-module assertions),
- UI copy/interaction composition.

Codex lane (complex):
- cross-module runtime orchestration,
- service adapters and registry integration,
- persistence/replay logic and migrations,
- API and contract convergence,
- integration/regression and release gates.

Escalation rule:
- if one task touches >=3 modules or changes behavior/state machine, force Codex lane.

## 3. Parallel Sequence (Dependency-aware)

Wave P0-A (parallel, must finish before P0-B):
- AT-00 orchestrator baseline (Codex)
- AT-00.1 skill registry baseline (Codex)
- AT-00.5 stage IO freeze artifacts (Spark)

Wave P0-B (parallel after P0-A schema freeze):
- AT-00.2 handoff persistence/replay (Codex)
- AT-00.3 rule engine baseline (Codex)
- AT-00.4 batch queue baseline (Codex)

Wave P1-A (parallel):
- AT-01 collection contract freeze + compatibility map (Spark)
- AT-02 collection adapters registry-only migration (Codex)

Wave P1-B (parallel):
- AT-03 symbolic guardrails on collection path (Codex)
- AT-04 scheduler baseline with strategy knobs (Codex)

Wave P1-C (parallel):
- AT-05 batch APIs (Codex)
- AT-06 existing UI operations (Spark first + Codex final contract lock)

Wave P2-A (parallel):
- AT-07 workflow/llm skill adapters (Codex)
- AT-08 handoff hardening and completion (Codex)

Wave P2-B (finalize):
- AT-09 observability + release/rollback gates (Codex)

## 4. Atomic Task Packets

### AT-00 + AT-00.1
- Owner lane: Codex
- Parallel subtasks:
  - orchestrator contract freeze,
  - runtime loop + handoff hook,
  - trace/idempotency baseline,
  - registry model + dispatcher,
  - unknown-skill fail-closed tests.
- Candidate files:
  - `main/backend/app/services/agent_runtime/*` (new),
  - `main/backend/app/api/agent_batch.py` (new),
  - `main/backend/app/api/__init__.py`,
  - `main/backend/tests/unit/test_agent_runtime_orchestrator_unittest.py` (new),
  - `main/backend/tests/unit/test_skill_registry_unittest.py` (new).

### AT-00.2 + AT-00.3
- Owner lane: Codex (Spark assists DSL taxonomy)
- Parallel subtasks:
  - handoff/replay data model,
  - replay service with `events_only` default,
  - rule-set immutable versions,
  - compiler/evaluator with checksum and decision logs.
- Candidate files:
  - `main/backend/app/models/entities.py`,
  - `main/backend/migrations/versions/*`,
  - `main/backend/app/services/agent_runtime/handoff_store.py` (new),
  - `main/backend/app/services/rule_engine/*` (new),
  - `main/backend/tests/unit/test_rule_engine_*` (new).

### AT-00.4 + AT-00.5
- Owner lane: Codex (Spark produces IO freeze spec)
- Parallel subtasks:
  - queue job/item lifecycle and retry budget,
  - scheduler runtime hooks,
  - stage schema whitelist gates,
  - disable silent DB->memory fallback for production path.
- Candidate files:
  - `main/backend/app/services/tasks.py`,
  - `main/backend/app/services/workflow_graph/store.py`,
  - `main/backend/app/api/process.py`,
  - `main/backend/tests/contract/*`,
  - `development/.../03_atomic-task-library-investigation-map-2026-03-10.md`.

### AT-01 + AT-02
- Owner lane: Spark(contracts) + Codex(implementation)
- Parallel subtasks:
  - collection skill contract + versioning,
  - legacy compatibility bridge,
  - registry-only adapter dispatch,
  - normalized adapter output with `meta.raw` retained.
- Candidate files:
  - `main/backend/app/services/collect_runtime/contracts.py`,
  - `main/backend/app/services/collect_runtime/runtime.py`,
  - `main/backend/app/services/collect_runtime/adapters/*.py`,
  - `main/backend/app/api/ingest.py`,
  - `main/backend/tests/integration/test_t22_source_library_scrapy_collect_runtime_integration_unittest.py`.

### AT-03 + AT-04
- Owner lane: Codex
- Parallel subtasks:
  - pre-dispatch guardrail matrix and reason taxonomy,
  - deterministic routing with fail-closed,
  - scheduler contract (`schedule_id/batch_id/state/attempt_count`),
  - `/process/*` status projection consistency.
- Candidate files:
  - `main/backend/app/services/source_library/runner.py`,
  - `main/backend/app/services/collect_runtime/runtime.py`,
  - `main/backend/app/services/tasks.py`,
  - `main/backend/app/api/process.py`,
  - `main/backend/tests/core_business/test_process_consistency_core_contract.py`.

### AT-05 + AT-06 + AT-07 + AT-08 + AT-09
- Owner lane:
  - Codex: AT-05/07/08/09,
  - Spark: AT-06 UI composition,
  - Codex final: AT-06 API contract lock and regression.
- Parallel subtasks:
  - batch API family,
  - process UI retry/timeline/reason display,
  - workflow/llm skill adapters,
  - handoff persistence hardening,
  - observability schema + release/rollback gates.
- Candidate files:
  - `main/backend/app/api/process.py`,
  - `main/backend/app/services/workflow_graph/*`,
  - `main/backend/app/services/llm/platformization.py`,
  - `main/frontend-modern/src/pages/ProcessPage.tsx`,
  - `scripts/pre_release_min_gate.sh`,
  - `main/ops/rollback.sh`.

## 5. Concurrency and Agent Topology

Recommended active agents per wave:
- Spark lane: 2-3 agents.
- Codex lane: 4-6 agents.
- Total concurrent agents: 6-9.

Ownership rule:
- each agent owns a file subset,
- same-file collisions are merged by primary Codex integrator,
- failed tasks retry in isolation only.

## 6. Gate Matrix (must pass per wave)

Per atomic task minimum gate:
- at least one of `contract` / `unit` / `integration`.

Wave gates:
1. P0-A
```bash
bash scripts/test-standardize.sh contract
bash scripts/test-standardize.sh unit
```
2. P0-B
```bash
bash scripts/test-standardize.sh unit
bash scripts/test-standardize.sh integration
```
3. P1
```bash
bash scripts/test-standardize.sh contract
bash scripts/test-standardize.sh integration
```
4. P2
```bash
bash scripts/test-standardize.sh contract
bash scripts/test-standardize.sh unit
bash scripts/test-standardize.sh integration
bash scripts/pre_release_min_gate.sh
```

## 7. Anti-Drift Controls

1. Every AT starts from frozen docs: `02` + `03` + this file.
2. Every new skill invocation must carry `contract_version`.
3. Every replay path logs `trace_id + run_id/job_id + replay_mode`.
4. Every guardrail block emits stable `reason_code`.
5. No production silent fallback from durable store to memory.
6. Legacy compatibility adapters remain until designated cutover milestone.

## 8. Definition of Fully Landed

- full collection chain can be triggered by agent to ingest and persistence,
- strategy knobs are runtime-adjustable,
- workflow/llm path is skill-first,
- handoff chain is replayable and auditable,
- release/rollback gates pass and are drill-validated.
