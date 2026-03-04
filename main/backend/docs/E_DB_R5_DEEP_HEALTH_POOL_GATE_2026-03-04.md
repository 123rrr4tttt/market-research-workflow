# E-DB R5: Deep Health Pool Gate (2026-03-04)

## Scope

- Line: E-db (R5)
- Goal: introduce a minimal and rollback-safe DB observability gate.
- Touchpoint: `/api/v1/health/deep` only.

## Change

- Add pool exhaustion gate in deep health endpoint:
  - Keep DB ping (`SELECT 1`) unchanged.
  - Keep pool detail output unchanged.
  - Add `database_pool` check result:
    - `ok` when pool usage is below limit.
    - `error: pool_exhausted` when `checkedout >= size + db_pool_max_overflow`.
  - Add `details.database_pool_gate` when exhausted.

## Why this is low-risk

- Read-only runtime check, no data schema or write-path change.
- No migration needed.
- Single endpoint behavior update, easy rollback.

## Rollback

- Revert commit for this task, or remove the `database_pool` exhaustion branch from `app/main.py`.

