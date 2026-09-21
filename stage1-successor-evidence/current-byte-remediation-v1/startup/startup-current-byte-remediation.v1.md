# Contract 13 startup current-byte remediation

Verdict: `LOCAL_IMPLEMENTATION_COMPLETE_LIVE_POSTGRES_VALIDATION_PENDING`.

The current-byte implementation now has one explicit schema-DDL effect boundary. On PostgreSQL it begins a transaction, applies the configured lock timeout, acquires a stable schema-scoped `pg_advisory_xact_lock`, performs DDL, and commits or rolls back. All public workflow-graph DDL shares the `public` lock; per-project initialization shares the corresponding project-schema lock. A failed transaction leaves no committed partial DDL and releases the transaction lock, so a later invocation can retry.

Celery registers a strong `worker_process_init` receiver. Importing the Celery module still performs no schema DDL. Development preserves log-and-continue; a production initializer exception is converted to `WorkerTerminate(1)`, which is not swallowed by Celery's `Signal.send` exception handler and terminates the worker child before task consumption.

Database CLI callers now have a general fail-closed `initialize_database_cli` / `run_database_cli` boundary backed by the full `ensure_project_schema_ready` preflight. The negative test proves that command execution cannot follow a failed preflight. This does not silently certify historical standalone scripts that bypass both the wrapper and the existing explicit preflight.

Offline verification passed: `52 passed, 1 skipped, 28 warnings`; the skip is the opt-in live PostgreSQL multi-process fixture. The fixture accepts only `MRW_TEST_POSTGRES_URL` pointing at localhost with a database name beginning `mrw_test_`. No such URL was present, so no database connection was attempted and live PostgreSQL race/recovery remains unverified rather than reported as PASS.

No service, container, provider, network, configured business database, deployment, release, rebind, or authority operation ran. Contracts, prior evidence, candidates, current binding artifacts, registries, `process.py`, and vector/search scripts were not changed.
