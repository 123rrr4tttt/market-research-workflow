# Process API task-id fallback residual disposition

Status: `PROPOSED_ADDITIVE_REBIND_NOT_AUTHORITY`  
Node: `main/backend/tests/unit/test_collect_runtime_process_fallback_unittest.py::CollectRuntimeProcessFallbackUnitTestCase::test_process_db_job_provider_fallback_consistent_for_info_and_logs`  
Successor cell: `C5.4` (`legacy.process_readback.v1`)

## Finding

The current DB projection extracts `task_id` only from persisted runtime payloads. For a legacy `EtlJobRun` with no payload task id, it produces `None`. `_db_job_to_runtime_task_info` then evaluates:

```python
{**task_info, **runtime_projection}
```

The later `runtime_projection` value wins, so its `task_id=None` overwrites the canonical `task_info["task_id"] == "db-job-7"`. The DB logs endpoint uses the requested path parameter directly and still reports `db-job-7`. This is an observable production readback mismatch, not an isolated test-only defect.

The direct call in the unit test is `get_task_info("db-job-7")`. FastAPI's `Query(None, ...)` default is applied by HTTP dependency handling; a direct Python invocation simply uses the declared default `None` for `project_key`. That default is unrelated to the task-id overwrite.

## Proposed patch (not applied)

The create-only review artifact is [process-task-id-fallback.patch](./process-task-id-fallback.patch):

```diff
--- a/main/backend/app/api/process.py
+++ b/main/backend/app/api/process.py
@@
-    task_id = _first_runtime_value(_runtime_task_id_from_payload(params, result_payload, progress_payload))
+    task_id = _first_runtime_value(
+        _runtime_task_id_from_payload(params, result_payload, progress_payload),
+        f"{_DB_JOB_PREFIX}{job.id}" if job.id is not None else None,
+    )
```

The proposed source transition is SHA-256 `790b6cb90086d6ba1171309e572b7e7be4c906db3705170dbd4a12ca7ea16c63` -> `5687389bdad57881a0f96543ba32ac4eaaaeef0f7939f8f7e36e16316ed7ee61` (56,769 -> 56,853 bytes; 1,506 -> 1,509 lines). An explicit provider/runtime task id remains authoritative; the DB pseudo-id is only a missing-metadata fallback.

## Binding impact

The current B23 C5 source binding is `fragments/C5.json#/source_bindings/10`, role `legacy_donor_c5_4_supplementary`. It is repeated by `manifests/C5.json#/sources/6` and `candidates/C5/candidate.v2.json#/sources/6` with the immutable `790b6c...` snapshot. The linked B23 I1 exact-binding record is `fragments/I1.json#/bindings/63`; its `successor_sha256` is also `790b6c...`, and the I1 manifest/candidate repeat that source hash. The current production declaration is `stage1-evidence/production-contract-implementation.v1.json#/bindings/required_files/source/80`; the all-lines donor closure is `AllLinesDonorByteClosure.v1.json#/entries/20`, and the movement inventory references it from movements `ALL-SM-005` and `ALL-SM-008`.

The target unit test is not listed in B23's C5/I1 test bindings (`UNBOUND_IN_B23_DECLARATIONS`). Its missing-payload fixture is nevertheless the regression witness for this production projection path; adding `task_id` to that fixture would hide the defect and is not proposed.

## Evidence and ceiling

An offline pure projection simulation yielded:

```text
before: projection_task_id=None, info_task_id=None, logs_task_id=db-job-7
after:  projection_task_id=db-job-7, info_task_id=db-job-7, logs_task_id=db-job-7
explicit provider task id preserved: provider-task-9
```

The focused pytest module is skipped in this environment because import-time workflow-graph DB bootstrap is fail-closed; no database or network was contacted. Relevant `compileall` and `git diff --check` checks pass.

The smallest safe next operation is a create-only exact-byte rebind candidate for the C5.4 supplementary donor and linked I1 source declaration, followed by explicit additive authorization. B23 fragments, manifests, candidate snapshots, and prior hashes remain immutable. The proposed hash is not authority, and production release remains `PRODUCTION_RELEASE_NOT_AUTHORIZED`.
