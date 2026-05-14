# Completion Audit

Objective: complete the next-round development task prescribed under `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-05-14-local-open-search-provider-isolation`.

## Checklist

| Requirement | Evidence | Status |
|---|---|---|
| WritingWorkbench frontend e2e works for the new search/material path | `writing_workbench_material_search.summary.json`: `frontend_status=passed`, `tests_passed=6`; e2e includes `searches selected material through the writing agent without writing back` | passed |
| WritingWorkbench can trigger material search from selected text | e2e verifies selected-text action calls `project.context.bundle` and `writing.document.list` | passed |
| Material search does not write back unless explicitly requested | e2e verifies no actual `writing.document.insert_paragraph` tool call for material search | passed |
| Agent / WritingWorkbench contract is aligned | `frontend_contract_diff.json`: `status=aligned`, `diffs=[]`; `agent_vs_workbench_contract_alignment.md` | passed |
| Backend material retrieval replay still works | `writing_workbench_material_retrieval.json`: `backend_replay_status=passed`, `result_count=10` | passed |
| SearXNG result enters candidate approval gate | `searxng_candidate_approval_gate.json`: provider `searxng`, 14 candidates, statuses include approved / rejected / pending_approval | passed |
| Approval / rejection state is auditable | `searxng_candidate_approval_gate.json`: 1 approved, 1 rejected, 12 pending_approval; `searxng_candidate_approval_gate.summary.md` | passed |
| Only approved candidates can enter governed ingest | `searxng_candidate_approval_gate.json`: `url_pool_submit_performed_for_approved_only=true`, rejected candidate has no ingest payload | passed |
| Raw SearXNG search results do not write source_library | `source_library_write_boundary_audit.md`: `bare_search_results_written_to_source_library=false`, `source_library_write_performed=false` | passed |
| `provider="auto"` still excludes SearXNG | `agent_searxng_search.summary.json` diagnostics and `searxng_candidate_approval_gate.json`: `recommended_provider_order` does not include `searxng` | passed |
| Named automation artifacts exist | Required files in `frontend-coherence-and-searxng-gate/2026-05-14/` are present, including screenshot and JSON/MD summaries | passed |
| Backend Python gates pass | `pytest main/backend/tests/unit/test_search_web_provider_adapters_unittest.py main/backend/tests/unit/test_agent_core_unittest.py main/backend/tests/unit/test_source_candidate_trust_unittest.py -q`: 70 passed | passed |
| Frontend TypeScript gate passes | `npx tsc --noEmit`: passed | passed |
| Temporary services cleaned up | `docker compose -f ops/search-lab/docker-compose.yml ps -a`: empty; no listeners on 8001 or 4173 | passed |

## Notes

- `npm run test -- --run` is not available because `main/frontend-modern/package.json` has no `test` script. The current frontend gate for this scope is Playwright e2e.
- LanceDB vector / hybrid retrieval is explicitly excluded from this iteration and routed to the global vectorization directory.
