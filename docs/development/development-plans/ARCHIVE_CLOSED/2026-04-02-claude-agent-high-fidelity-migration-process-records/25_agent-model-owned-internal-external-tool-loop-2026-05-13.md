<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration-process-records/25_agent-model-owned-internal-external-tool-loop-2026-05-13.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration-process-records/25_agent-model-owned-internal-external-tool-loop-2026-05-13.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# Agent Model-Owned Internal External Tool Loop - 2026-05-13

## Scope

This note closes a backend regression slice for `21_agent-goal-gap-and-optimization-direction-2026-05-13.md` O3 and part of O5. It verifies that AgentCore can run a repeated model-owned tool loop across internal project evidence, long-task stage state, external discovery planning, governed source intake dispatch, investigation leads, writing output, and resume state.

This is not a full product closure claim. Browser coverage for a real backend source intake chain remains separate.

## Implemented / Verified Behavior

The new regression `test_model_owned_loop_internal_first_external_discovery_stage_and_resume` covers this sequence:

1. `agent_task.plan.append` creates durable split tasks.
2. `project.context.bundle` reads internal project material first.
3. `agent_long_task.stage.update(stage=internal_evidence)` records evidence refs, gap list, and next actions.
4. `source.discovery.plan` plans external candidates without network fetch or ingest.
5. `agent_long_task.stage.update(stage=external_discovery)` records the external discovery plan.
6. `ingest.source_library.run` dispatches a governed source-library collection item.
7. `agent_long_task.stage.update(stage=source_intake)` records the source intake task id.
8. `agent_investigation.leads.append` persists followed leads, pending questions, clue nodes/edges, and citations.
9. `writing.document.insert_paragraph` writes the draft through the versioned writing tool boundary.
10. `agent_long_task.stage.update(stage=draft_output)` records draft refs and moves the durable state to verification.
11. `agent_session.resume_bundle` returns compact resumable long-task state and artifacts.

## Contract Checks

- The tool-result order proves the model loop observes one tool result before selecting the next tool.
- Internal project material is inspected before external discovery.
- `source.discovery.plan` remains no-fetch/no-write and returns review-before-ingest gates.
- `ingest.source_library.run` is only used after discovery and returns the governed dispatch task id.
- `source_intake` stage records intake refs before clue persistence and draft output.
- Source-library entries remain labeled as catalog/data-source entrypoints, not already ingested project material.
- Long-task state survives into `agent_session.resume_bundle` with `current_stage=verification`.
- Investigation lead artifacts and writing draft output are both present before final answer.

## Verification

- `PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/unit/test_agent_core_unittest.py -q -k "model_owned_loop_internal_first or source_discovery_to_investigation_to_writing_resume_chain or long_task_stage_state"` -> `3 passed, 3 warnings`
- `PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/unit/test_material_ontology_unittest.py main/backend/tests/unit/test_interactive_agent_runtime_unittest.py main/backend/tests/unit/test_agent_run_loop_unittest.py main/backend/tests/unit/test_agent_core_unittest.py main/backend/tests/integration/test_agent_chat_api_unittest.py -q` -> `102 passed, 11 warnings`

## Remaining Gaps From 21

- Browser coverage still uses mocked AgentChat streams for the long-task UI; real-backend browser coverage is still needed where feasible.
- Source intake has backend coverage, but still needs a browser scenario that surfaces actual intake results after discovery review.
- Final closure still requires auditing every acceptance-matrix row in `21_agent-goal-gap-and-optimization-direction-2026-05-13.md`.
