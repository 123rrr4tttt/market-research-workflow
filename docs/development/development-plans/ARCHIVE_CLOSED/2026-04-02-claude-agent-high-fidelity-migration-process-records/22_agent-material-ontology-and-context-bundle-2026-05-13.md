<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration-process-records/22_agent-material-ontology-and-context-bundle-2026-05-13.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration-process-records/22_agent-material-ontology-and-context-bundle-2026-05-13.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# Agent Material Ontology And Context Bundle

Date: 2026-05-13
Status: active implementation evidence, not final closure
Mainline: Claude Code level AgentCore reconstruction

## Purpose

This pass closes the first P0 slice from `21_agent-goal-gap-and-optimization-direction-2026-05-13.md`: the agent must distinguish project-local materials from source-library/data-source entrypoints, and must treat generic material supplementation differently from writing-context material supplementation.

## Implemented

- Added shared backend ontology contract in `main/backend/app/services/agent_runtime/material_ontology.py`.
- Added `project.context.bundle` as a read-only runtime capability.
- The bundle combines:
  - internal existing structured data inventory and records;
  - writing documents;
  - generated session artifacts;
  - source-library catalog entries labelled as collection entrypoints;
  - missing-evidence hints.
- Turn decision and capability selection now consume the shared ontology instead of duplicating only ad hoc phrase checks.
- AgentChat tool calls now carry `material_category` metadata and show material labels in tool rows.

## Behavior Matrix

| Prompt | Expected Boundary | Evidence |
| --- | --- | --- |
| `项目库里已有资料有哪些` | internal existing project materials | `project.context.bundle`, `project.summary.read`, `project.structured_data.search`, `agent_artifact.search`; no `source_library.item.list` |
| `帮我补充资料` | internal-first plus governed collection preparation | `project.context.bundle` and internal read tools, then `source_library.item.list` and `agent_batch.nl_command.submit` approval path |
| `写作时帮我补充资料` | writing context prefers internal material first | read-only `project.context.bundle` plus internal project/artifact tools; no `agent_batch` |
| `写作时帮我补充外部资料` | writing context plus external collection boundary | internal context bundle plus source catalog list and governed `agent_batch` path |
| `当前有哪些来源库 item` | source catalog only | source-library read tools; labelled as collection/data-source entries, not existing evidence |

## Verification

- `PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/unit/test_material_ontology_unittest.py main/backend/tests/unit/test_interactive_agent_runtime_unittest.py main/backend/tests/unit/test_agent_run_loop_unittest.py main/backend/tests/unit/test_agent_core_unittest.py main/backend/tests/integration/test_agent_chat_api_unittest.py -q`
  - Result: `96 passed, 11 warnings`.
- `npm run lint -- src/pages/AgentChatPage.tsx src/pages/agent-chat.css src/lib/types.ts`
  - Result: passed with existing CSS ignored warning.
- `npm run build`
  - Result: passed.

## Remaining Gap

This pass does not close the whole 21号 goal document. Remaining high-value gaps:

- Browser-level scenario verification for the full acceptance matrix.
- Writing selection/cursor/range tools and AgentCore-backed replacement flows.
- Long investigation/writing durable stage machines across hard refresh.
- Stronger model-owned repeated tool loop beyond selected read-only capability execution.
