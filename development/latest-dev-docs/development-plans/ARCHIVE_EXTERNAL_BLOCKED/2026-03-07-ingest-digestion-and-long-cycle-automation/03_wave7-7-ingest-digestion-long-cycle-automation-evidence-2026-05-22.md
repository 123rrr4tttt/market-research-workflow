# Wave7-7 Ingest Digestion Long-Cycle Automation Evidence

Date: 2026-05-22 PST
Branch: `codex/devdocs-wave7-ingest-digestion-automation`
Status: `partial implementation evidence / not closed`

## Status Check

The shared audit still records this topic as `no_closure_claim / doc_aligned`:

- [CURRENT_DEV status audit](../STATUS_AUDIT_2026-04-07.md)
- [Main plan](./01_ingest-digestion-and-long-cycle-automation-plan-2026-03-07.md)
- [Atomic task list](./02_atomic-tasklist-ingest-digestion-and-long-cycle-automation-2026-03-07.md)

That status was accurate for the March document set: the 01 plan explicitly says it is a planning document and the 02 task list keeps A1-A8 pending. After this Wave7-7 lane, the topic-local state is more precise as:

```text
partial implementation evidence / shared index not touched / do not archive
```

This is still not a closure claim. The repo now has a test-backed minimum contract for digestion and long-cycle status checking, but it does not yet have a full recurring scheduler, persistent long-cycle task table, or end-to-end downstream automation run.

## Code Facts

| Surface | Current repo fact | Evidence |
| --- | --- | --- |
| Digestion taxonomy | Input kind, content format, digestion stage, normalized envelope, time semantics, and digestion decision contracts exist. | [ingest_digestion.py](../../../../../main/backend/app/contracts/ingest_digestion.py) |
| Long-cycle status contract | This lane adds `LongCycleTaskStatus`, `LongCycleTaskObject`, `LongCycleTaskSnapshot`, and `LongCycleAutomationStatus`. | [ingest_digestion.py](../../../../../main/backend/app/contracts/ingest_digestion.py) |
| Digestion scaffold | Existing scaffold classifies inputs, infers content formats, derives task-window bounds, and chooses pass-through / chunk-first / summarize-first / extract-first decisions. | [digestion_scaffold.py](../../../../../main/backend/app/services/ingest/digestion_scaffold.py) |
| Long-cycle checker | This lane adds `build_long_cycle_task_object()` and `check_long_cycle_automation_status()` so future automation can distinguish `ready` from `blocked` before dispatch. | [digestion_scaffold.py](../../../../../main/backend/app/services/ingest/digestion_scaffold.py) |
| Time-window reuse | Long-cycle checker reuses `Nd` candidate windows and the existing prompt-time-density task/API remains the repo-owned selection surface. | [tasks.py](../../../../../main/backend/app/services/tasks.py), [stats.py](../../../../../main/backend/app/api/stats.py) |
| Frontdoor status projection | Existing Wave4 evidence proves backend frontdoor route intent and status projection, including `frontdoor_status_summary`. | [frontdoor-router-hardening evidence](../../../automation-runs/frontdoor-router-hardening/2026-05-22/README.md) |
| Current ingest write path | Existing Wave3 evidence pins `/api/v1/ingest/url/single` to source-library/frontdoor/terminal writer, not a stale `single_url.py` target. | [ingest-frontdoor closure evidence](../../../automation-runs/ingest-frontdoor-closure/2026-05-22/README.md) |

## Checker Semantics

`check_long_cycle_automation_status()` returns contract version `ingest.long_cycle_automation_status.v1` and includes:

- `status`: `ready` when the task goal, input scope, candidate windows, selected window, and output target are internally consistent.
- `blockers`: stable reason strings such as `invalid_candidate_windows`, `selected_window_not_in_candidate_windows`, `missing_task_goal`, `missing_output_target`, `missing_candidate_windows`, and `missing_input_scope`.
- `task`: a normalized long-cycle task object with template-level fields and a last-run status snapshot.
- `normalized_input`: the existing digestion envelope.
- `digestion_decision`: the existing pass-through / chunk-first / summarize-first / extract-first decision.

This deliberately remains a pre-dispatch status checker. It does not enqueue Celery tasks, mutate source-library data, or claim scheduler persistence.

## Minimal Plan From Here

1. Keep this topic in `CURRENT_DEV`; do not archive from this lane.
2. Use `check_long_cycle_automation_status()` as the guard before any future recurring ingest automation dispatch.
3. Route future URL/source-library work through the existing frontdoor contracts and status projection instead of inventing a parallel quality gate.
4. Add the next implementation slice only when it can prove an actual run path: selected window -> task dispatch -> digestion output -> downstream handoff.
5. Leave shared indexes unchanged in this branch; a later integration lane can reconcile topic-local status with `README.md`, `MERGED_OVERVIEW.md`, `development-plans/INDEX.md`, and `CURRENT_DEV/INDEX.md`.

## Validation

Commands run from this worktree:

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_ingest_digestion_scaffold_unittest.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_ingest_digestion_scaffold_unittest.py main/backend/tests/unit/test_ingest_frontdoor_context_unittest.py main/backend/tests/unit/test_frontdoor_orchestrator_unittest.py main/backend/tests/unit/test_postprocess_frontdoor_unittest.py main/backend/tests/unit/test_ingest_metrics_payload_unittest.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/core_business/test_ingest_core_contract.py main/backend/tests/unit/test_source_library_handler_cluster_frontdoor_unittest.py main/backend/tests/unit/test_collect_runtime_source_library_adapter_unittest.py main/backend/tests/unit/test_collect_runtime_auto_batch_unittest.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m py_compile main/backend/app/contracts/ingest_digestion.py main/backend/app/services/ingest/digestion_scaffold.py
git diff --check
```

Observed result:

- `8 passed`
- `38 passed, 2 warnings`
- `34 passed, 11 warnings`
- `py_compile` passed
- new-document Markdown link check passed: `files=1 links=11`
- `git diff --check` passed
