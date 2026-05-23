<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration-process-records/44_agent-matrix-capability-execution-r3-2026-05-14.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration-process-records/44_agent-matrix-capability-execution-r3-2026-05-14.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# Agent Matrix Capability Execution R3

Date: 2026-05-14
Status: R3 implementation evidence
Mainline: Claude Code level AgentCore reconstruction

## Purpose

This document closes the R3 matrix-capability requirement introduced by `41_agent-high-fidelity-migration-closure-audit-2026-05-14.md`.

Research, source discovery, material supplementation, verification, comparison, and multi-source evidence tasks must not collapse into one broad query or one serial tool lane. AgentCore must expose and preserve a matrix of intent facets, keyword variants, tool/provider routes, evidence classes, verification gates, and merge/rank output.

## Implemented Coverage

Updated files:

- `main/backend/app/services/agent_core/project_tools.py`
- `main/backend/app/services/agent_core/json_provider.py`
- `main/backend/app/services/agent_core/native_provider.py`
- `main/backend/app/api/agent_chat.py`
- `main/backend/tests/unit/test_agent_core_unittest.py`
- `main/frontend-modern/tests/e2e/agent-chat-real-backend-long-task.spec.ts`

### Source Discovery Matrix

`source.discovery.plan` now returns `capability_matrix` when `matrix_mode=true`:

- intent facets for internal project evidence, source catalog entrypoints, external live candidates, quality/trust review, and writing/answer integration;
- keyword variants for base semantic, official/report, policy/regulatory, market/statistics/dataset, and optional domain-constrained branches;
- tool/provider routes across internal project tools, source discovery/search/review/ingest boundaries, and provider readiness routes;
- evidence and verification gates for provider diagnostics, URL trust, source-history state, URL-pool status/readback, and zero-result uncertainty.

### Source Web Search Matrix

`source.web.search` now supports:

- `matrix_mode`;
- `query_variants`;
- `providers`;
- bounded branch fanout;
- per-branch provider diagnostics;
- per-branch failure isolation;
- candidate dedupe by normalized URL/checksum;
- merge/rank output with `matrix_rank`, `branch_count`, and `matrix_branches`;
- `matrix_summary` with branch counts, provider counts, merged candidate count, accepted candidate count, dedupe policy, and absence-claim rule.

Zero-result branches remain uncertainty, not evidence absence. The result explicitly keeps `absence_claim_allowed=false` when no candidates are found.

### Provider And Browser Guidance

Both JSON and native providers now instruct the model to use capability matrices for broad research/source/material/verification tasks, while preserving narrow single-call behavior for deterministic actions.

The real-backend AgentChat E2E now expects `capability_matrix` and `matrix_summary` in broad material and long-task source flows.

## Verification

Focused R3 gate:

```bash
/opt/homebrew/bin/python3.11 -m py_compile main/backend/app/services/agent_core/project_tools.py main/backend/app/services/agent_core/json_provider.py main/backend/app/services/agent_core/native_provider.py main/backend/app/api/agent_chat.py main/backend/tests/unit/test_agent_core_unittest.py
PYTHONPATH=main/backend /opt/homebrew/bin/python3.11 -m pytest -q main/backend/tests/unit/test_agent_core_unittest.py -k "source_discovery_plan_returns_capability_matrix or source_web_search_matrix_merges_ranks or source_web_search_returns_trusted_candidates_without_ingest or source_web_search_empty_result_reports_provider_uncertainty or diagnostics_use_google"
```

Result:

```text
5 passed, 55 deselected, 3 warnings
```

Broader AgentCore gate:

```bash
PYTHONPATH=main/backend /opt/homebrew/bin/python3.11 -m pytest -q main/backend/tests/unit/test_agent_core_unittest.py main/backend/tests/unit/test_material_ontology_unittest.py main/backend/tests/unit/test_agent_control_tools_unittest.py
```

Result:

```text
69 passed, 3 warnings
```

Frontend E2E lint gate:

```bash
npm exec eslint -- tests/e2e/agent-chat-real-backend-long-task.spec.ts
```

Result:

```text
passed
```

Real-backend AgentChat E2E gate:

```bash
AGENT_CORE_E2E_SCRIPTED_PROVIDER_ENABLED=true PYTHONPATH=main/backend /opt/homebrew/bin/python3.11 -m uvicorn app.main:app --host 127.0.0.1 --port 8021
AGENT_CORE_REAL_BACKEND_E2E=1 VITE_API_PROXY_TARGET=http://127.0.0.1:8021 npm run test:e2e -- tests/e2e/agent-chat-real-backend-long-task.spec.ts --reporter=line
```

Result:

```text
2 passed
```

## Live Matrix Probe

A live AgentCore probe used the actual tool registry and configured Serper provider:

```text
status=completed
candidate_count=4
accepted_candidate_count=4
matrix_mode=true
query_variant_count=2
provider_count=1
branch_count=2
completed_branch_count=2
failed_branch_count=0
zero_result_branch_count=0
merged_candidate_count=4
merge_rank_applied=true
providers_considered=["serper"]
```

Observed candidate examples:

- ITIF: `A Time to Act: Policies to Strengthen the US Robotics Industry`
- IDC: `Humanoid Robotics Commercialization Trends 2026`
- McKinsey: `The robotics revolution: Scaling beyond the pilot phase`
- Mordor Intelligence: `Commercial Robotics Market Size, Share & Growth Trends 2031`

The probe intentionally did not ingest live URLs into the project library. It validated retrieval, branch diagnostics, merge/rank, and candidate handoff readiness; governed ingest remains covered by deterministic URL-pool tests and browser E2E.

## R3 Closure Decision

R3 is closed for the current high-fidelity migration scope:

- the capability matrix exists as structured tool output;
- the live search tool executes matrix branches rather than one serial query when requested;
- branch diagnostics, merge/rank, and zero-result uncertainty are preserved;
- tests cover matrix generation and merge/rank behavior;
- real-backend browser expectations now require matrix evidence for broad material/source scenarios.

Future improvements can add more external providers or MCP search routes, but those are capacity expansion items, not blockers for this R3 closure.
