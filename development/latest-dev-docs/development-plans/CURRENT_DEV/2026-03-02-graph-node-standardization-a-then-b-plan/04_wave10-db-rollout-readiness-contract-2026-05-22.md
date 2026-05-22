# Wave10 DB Rollout Readiness Contract (2026-05-22)

## Scope

Worker branch:

- `codex/devdocs-wave10-graph-node-db-rollout`

Target topic:

- `2026-03-02-graph-node-standardization-a-then-b-plan`

This lane adds a repeatable pre-live DB dry-run readiness contract. It does not edit shared navigation indexes.

## Result

Status: `pre-live readiness slice landed`.

Implemented contract:

- `main/backend/scripts/check_graph_projection_contract.py` now emits both:
  - the existing deterministic no-DB projection dry-run report;
  - a new `pre_live_db_dry_run_readiness` report.
- The readiness report checks:
  - read mode is one of `a_only` / `b_canary` / `b_primary`;
  - pre-live read mode remains `a_only` or explicitly scoped `b_canary`;
  - write mode remains `off` or `shadow` before a bounded dry-run passes;
  - backfill is dry-run and bounded by `--backfill-limit`;
  - graph node/alias/edge migration files and ordering are present;
  - admin projection write failure, projection read failure, and backfill apply failure are isolated by rollback/fallback guards.

The checker keeps:

- `live_db_validated=false`
- `closure_claim=false`

## Code Changes

- `main/backend/app/api/admin.py`
  - rolls back projection write/read failures before continuing with the A-path response.
- `main/backend/app/services/graph/backfill_graph_nodes.py`
  - rolls back failed apply-mode backfill attempts and re-raises the original failure.
- `main/backend/app/services/graph/persistence/graph_projection_contract.py`
  - adds the pure readiness contract model and static readiness checks.
- `main/backend/scripts/check_graph_projection_contract.py`
  - adds CLI flags for planned read/write mode, canary projects, bounded dry-run limit, apply-mode negative checks, and migration root.
- `main/backend/tests/unit/test_graph_backfill_readiness_unittest.py`
  - proves dry-run avoids writer/commit and apply failures roll back.
- `main/backend/tests/unit/test_graph_persistence_writer_unittest.py`
  - proves pre-live readiness passes for bounded dry-run and blocks `b_primary` + apply before live DB evidence.
- `main/backend/tests/integration/test_admin_graph_standardization_unittest.py`
  - proves shadow write failure and b-canary read failure both return the A-path graph response.

## Verification

Commands were run with `/Users/wangyiliang/.local/bin/python3.11` because this worktree does not contain `main/backend/.venv311`.

```bash
cd /Users/wangyiliang/market-research-workflow.worktrees/devdocs-wave10-graph-node-db-rollout/main/backend
/Users/wangyiliang/.local/bin/python3.11 -m pytest -q \
  tests/unit/test_graph_persistence_writer_unittest.py \
  tests/unit/test_graph_backfill_readiness_unittest.py \
  tests/integration/test_admin_graph_standardization_unittest.py
```

Result:

- `22 passed, 11 warnings`

```bash
cd /Users/wangyiliang/market-research-workflow.worktrees/devdocs-wave10-graph-node-db-rollout/main/backend
/Users/wangyiliang/.local/bin/python3.11 scripts/check_graph_projection_contract.py --format json
```

Result:

- `status=ok`
- `readiness.ready_for_live_db_dry_run=true`
- `readiness.live_db_validated=false`
- `readiness.closure_claim=false`

```bash
cd /Users/wangyiliang/market-research-workflow.worktrees/devdocs-wave10-graph-node-db-rollout/main/backend
/Users/wangyiliang/.local/bin/python3.11 -m pytest -q \
  tests/unit/test_graph_projection_unittest.py \
  tests/unit/test_graph_persistence_writer_unittest.py \
  tests/unit/test_graph_backfill_readiness_unittest.py
```

Result:

- `12 passed, 2 warnings`

```bash
cd /Users/wangyiliang/market-research-workflow.worktrees/devdocs-wave10-graph-node-db-rollout
git diff --check
/Users/wangyiliang/.local/bin/python3.11 scripts/check_current_dev_wave10_plan.py
```

Results:

- `git diff --check` passed.
- `OK wave10_current_dev_plan=passed mode=codex/devdocs-wave10-graph-node-db-rollout branches=9 changed_files=8 worker_boundary_enforced=true`

## Boundary

This lane does not claim full DB rollout closure.

Still required before archiving this topic:

- run Alembic `current` / `upgrade head` against a configured tenant schema;
- run `scripts/backfill_graph_nodes.py --dry-run --limit 10` against a live tenant DB;
- compare `b_canary` or `b_primary` read-mode parity against seeded tenant projection data;
- let the integration lane update shared indexes after worker branches merge.
