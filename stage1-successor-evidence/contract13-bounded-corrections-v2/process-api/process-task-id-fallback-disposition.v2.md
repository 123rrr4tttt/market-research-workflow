# Contract 13 process API bounded correction v2

Status: `BOUNDED_CORRECTION_COMPLETE_PROPOSED_REPAIR_UNINTEGRATED`

Authority: `false`

Contract item: `13_contract12-supervisor-review-and-return.v1.md` item 1

Contract SHA-256: `ac1629315b3ae91aa9de59b7ae87da04a5f10c54d643e406d8785a0783071717`

## Corrected `query_default` analysis

`get_task_info` declares:

```python
project_key: Optional[str] = Query(
    None,
    description="项目标识（用于查询对应项目 schema 的 DB job）",
)
```

With FastAPI 0.120.4, the declared Python default is an object of exact type `fastapi.params.Query`. Its exact `repr` is `Query(None)`; it is not `None`, it is truthy, and its `.default` field is the `builtins.NoneType` value `None`.

These invocation modes are distinct:

1. A direct Python call `get_task_info("db-job-7")` receives the declared `fastapi.params.Query` object. Because the object is truthy, the endpoint selects `bind_project(project_key)` and forwards that same descriptor object to `_db_job_to_runtime_task_info`.
2. A correct direct-call fixture uses `get_task_info("db-job-7", project_key=None)`. The endpoint selects `nullcontext()` and forwards `None`.
3. An in-process FastAPI request `GET /process/db-job-7` with the query parameter omitted is parsed by FastAPI, which applies the descriptor's inner default and invokes the endpoint with `project_key=None`.

Thus the v1 sentence claiming that a direct omitted call receives `None` is superseded. The descriptor object and the value resolved by FastAPI request parsing are not interchangeable.

## Isolated identity evidence

The executable witness imports the actual current endpoint and projection functions, replaces only DB/network boundaries with in-process fakes, and checks the exact current source hash. No database or network is contacted.

Current before-state with a DB job lacking payload `task_id`:

```text
runtime projection task_id = null
info overlay task_id       = null
logs task_id               = db-job-7
```

`_db_job_to_runtime_task_info` forms `{**task_info, **runtime_projection}`. The later projection value therefore overwrites the endpoint identity `db-job-7` with `null`. The logs path independently retains the requested endpoint identity.

The proposed in-memory after-state uses this ordered choice inside `_db_job_projection`:

```text
first_non_empty(payload task_id, db-job-{job.id})
```

It yields:

```text
missing payload: projection = info = logs = db-job-7
explicit payload: info = provider-task-9
```

The provider/runtime payload identity remains first. `db-job-{job.id}` is only the missing-payload fallback.

## Fixture boundary versus production defect

Changing the direct unit fixture to pass `project_key=None` is necessary to model an HTTP request's resolved default. It only corrects the invocation boundary. The witness then calls the current endpoint with explicit `None` and still observes `info.task_id=null` against `logs.task_id=db-job-7`. Therefore a fixture-only change cannot eliminate the production projection defect.

The existing proposal remains unintegrated:

```text
main/backend/app/api/process.py
790b6cb90086d6ba1171309e572b7e7be4c906db3705170dbd4a12ca7ea16c63
  ->
5687389bdad57881a0f96543ba32ac4eaaaeef0f7939f8f7e36e16316ed7ee61
```

Its v1 patch artifact is unchanged at SHA-256 `5ea2bc4389717be260bfb25588776a728e89157166c32e767f92fc612aacdf78`. Applying it still requires additive rebind authorization.

## Reproduction

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:main/backend \
  main/backend/.venv311/bin/python \
  stage1-successor-evidence/contract13-bounded-corrections-v2/process-api/process-task-id-overlay-witness.v2.py
```

The captured JSON is `process-task-id-overlay-witness-results.v2.json`. All six assertions pass. The witness also verifies the current and proposed source hashes and the replacement's unique occurrence.

## Ceiling

No source, B23 record, historical artifact, test, live database, provider, network, registry, or signing state was changed. This package is create-only bounded evidence. Stage 1 remains unaccepted; Phase B/C/v5 remains gated; production release is not authorized.
