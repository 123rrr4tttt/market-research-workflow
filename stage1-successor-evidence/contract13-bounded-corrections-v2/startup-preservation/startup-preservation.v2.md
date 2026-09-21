# Contract 13 requirement 4 — startup preservation

Verdict: `LOCAL_ACCEPTANCE_GAPS_REMAIN`. The eight current path hashes still match the residual-disposition receipt exactly. This package is local deterministic evidence only and does not establish live database, deployment, release, or rebind authority.

## Four preservation boundaries

1. **FastAPI startup order — PASS.** The composed app registers `_ensure_default_project_schema` first, followed by project bootstrap, all-project schemas, prompt sync, shared tables, and finally `_validate_production_composition`. The handler preserves dev/test log-and-continue and makes `prod`/`production` fail closed. No live startup was run.
2. **Celery/CLI schema initialization — LOCAL_ACCEPTANCE_GAP.** Moving DDL out of `models.base` removes the incidental schema creation formerly inherited by Celery and direct scripts. `celery_app.py` has no explicit schema initializer. `ensure_project_schema_ready` is explicit but only four scripts call it. The minimum correction is an explicit tested Celery worker-start boundary plus a shared DB-CLI preflight; import-time DDL must not be restored.
3. **First SQL operation failure/fallback/retry — PASS locally.** Both builders retain fail-closed `store_unavailable` and configured in-memory fallback. Compiler/runtime/handoff fields remain unset when construction throws, so later operations retry. A selected fallback is intentionally sticky for the service lifetime and returns to SQL only after reconstruction/restart.
4. **Concurrent first use — PASS in one instance/process; LOCAL_ACCEPTANCE_GAP across processes.** Each lazy owner uses an `RLock`; 24 calls from 12 threads built once. No cross-process lock exists. `IF NOT EXISTS` and `create_all(checkfirst=True)` are not a live proof of multi-worker PostgreSQL race/recovery behavior.

## Focused artifacts and verification

- `focused-import-time-db-boundary.patch` is a review-only extraction of the six runtime boundary hunks; unrelated shared-dirty changes are excluded.
- The repository focused selector passed: `32 passed, 13 warnings`.
- The isolated witness passed: `12 passed, 10 warnings` after final rerun.
- `ruff check` passes for the isolated witness. The virtualenv has no `ruff` binary; the available global `ruff` was used.
- `app.services.llm.cache` still performs a local SQLite cache setup during non-production Celery import. It is unchanged and outside these eight paths, so it is `OUT_OF_SCOPE`, not silently treated as preserved.

The JSON receipt contains exact hashes, per-check ceilings, and minimum follow-up actions.
