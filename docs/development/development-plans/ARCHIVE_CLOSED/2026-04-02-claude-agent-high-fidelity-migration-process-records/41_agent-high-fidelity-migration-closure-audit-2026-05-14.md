<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration-process-records/41_agent-high-fidelity-migration-closure-audit-2026-05-14.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration-process-records/41_agent-high-fidelity-migration-closure-audit-2026-05-14.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# Agent High-Fidelity Migration Closure Audit

Date: 2026-05-14
Status: closure audit; R1 closed by 43; R2 closed by 42; R3 closed by 44
Mainline: Claude Code level AgentCore reconstruction

## Purpose

This audit reconciles the active requirements in `02_claude-code-level-agent-interaction-todo-2026-05-10.md`, `17_claude-code-core-reconstruction-spec-2026-05-11.md`, `18_agent-architecture-deepening-writing-investigation-spec-2026-05-11.md`, and `21_agent-goal-gap-and-optimization-direction-2026-05-13.md`.

Older documents in this folder contain historical `Remaining Gap` sections. Those gaps are not current by themselves. A gap remains current only if it is still not covered by later code, tests, browser scenarios, or this audit.

This document also records the standing requirement for Agent system-capability invocation: when the user asks for research, source discovery, material supplementation, verification, comparison, or any multi-source evidence task, the Agent must not reduce system capability use to one serial tool call or one keyword. It must construct and execute a matrix of retrieval/search routes, keyword variants, provider/tool candidates, evidence classes, and verification passes, then merge and rank the results before answering or writing. That R3 requirement is now implemented and validated by `44_agent-matrix-capability-execution-r3-2026-05-14.md`.

## Current Closure Position

The AgentCore mainline is now materially different from the early `agent_batch`-first implementation:

- free dialogue and ordinary factual turns are handled by AgentCore/model output without submitting `agent_batch`;
- project data, graph, artifacts, source catalog, source history, writing documents, long-task stages, candidate review, URL-pool submission/status, and writing edits are exposed as AgentCore tools;
- material semantics now distinguish internal existing material, generated project artifacts, source catalog entries, external discovery, and external ingest;
- AgentChat has bounded session scrolling, stream-first turn handling, workbench tabs, progressive tool cards, source candidate review, long-task stage recovery, and reload-safe source history;
- the writing workbench routes the agent panel through AgentCore, passes selection/range/cursor context, writes through versioned tools, and supports locate/accept/reject/rollback.

The previous non-code blocker was stable live external search provider configuration. That is now validated in this runtime by `43_agent-live-provider-r1-validation-2026-05-14.md`: AgentCore selected configured Serper through `source.web.search`, returned live candidates, and passed a candidate through `source.candidate.review` into a `url_pool` ingest payload.

## New Requirement: Matrix Capability Invocation

Agent system capabilities must be treated as a search and verification matrix, not as a single serial lane.

### Required Matrix Shape

| Dimension | Requirement | Examples |
| --- | --- | --- |
| Intent decomposition | Split a broad request into independent investigation facets before tool calls. | concept definition, implementation evidence, source freshness, local project evidence, contrary evidence, user-facing impact. |
| Keyword matrix | Generate multiple keyword groups instead of one query string. | exact terms, synonyms, Chinese/English variants, domain terms, entity names, failure symptoms, implementation identifiers. |
| Tool/provider matrix | Route across available internal and external tools when appropriate. | `project.context.bundle`, structured data search, graph query, source catalog/history, `source.web.search`, URL-pool candidate review, browser/manual probes. |
| Scope matrix | Separate internal existing evidence, generated artifacts, source-library records, external candidates, and fresh live search results. | internal docs first for project facts; external search only when new/outside/current sources are requested or internal evidence is insufficient. |
| Evidence matrix | Collect several evidence types before concluding. | source title/snippet/url, stored item metadata, document path, code/test evidence, runtime probe output, failure diagnostics. |
| Verification matrix | Validate important claims with at least one independent check when feasible. | provider diagnostics, local readback, targeted test, smoke command, status file, artifact existence, source-history recovery. |
| Merge/rank step | Deduplicate and rank matrix results before producing final output. | prefer verified internal evidence for project facts; prefer configured provider results over DDG fallback; preserve uncertainty labels. |

### Operational Rule

For research, material collection, source discovery, comparison, verification, and long-investigation turns, the Agent should plan system capability use as batches:

```text
intent facets
  x keyword/query variants
  x source/tool/provider routes
  x evidence/verification gates
  -> merged candidate set
  -> ranked answer / governed ingest / writing update
```

Single-call use is acceptable only for narrow deterministic actions, such as reading a named file, opening a known document, checking one explicit status, or applying one already-selected edit.

### Anti-Pattern

The following behavior is explicitly not acceptable for agentic research/source workflows:

- one broad user request -> one `source.web.search` query -> final answer;
- one keyword -> one provider -> source absence conclusion;
- internal project question -> external web search before checking project context;
- writing/source supplementation -> direct ingest without candidate review;
- stale or unconfigured provider -> "no sources found" without provider diagnostics;
- long investigation -> single sequential chain that cannot branch, compare, or recover.

### Expected Behavior

The Agent should surface or internally preserve the matrix:

- query groups tried;
- tools/providers considered and selected;
- provider readiness or missing-provider diagnostics;
- candidate counts and failure classes;
- which evidence became answer-grade, ingest-grade, or follow-up-only;
- unresolved gaps that need user choice or environment configuration.

This requirement upgrades the closure bar: having a live provider and AgentCore tools is not enough. The Agent must use them in matrix form when the task naturally requires breadth, comparison, or evidence quality. Current implementation evidence is recorded in `44`.

## Requirement Matrix

| Requirement | Current Status | Evidence |
| --- | --- | --- |
| Free dialogue must not enter batch execution for greetings, facts, capability, or project status. | Covered. | `main/backend/tests/unit/test_interactive_agent_runtime_unittest.py`; `main/frontend-modern/tests/e2e/agent-chat.spec.ts`; `main/frontend-modern/tests/e2e/agent-chat-real-backend-long-task.spec.ts` normal fact scenario. |
| Tool choice must be model/core owned, with keyword logic reduced to hints and guardrails. | Covered for the AgentCore mainline. | `main/backend/app/services/agent_core/core.py`; `native_provider.py`; `json_provider.py`; `tool_window.py`; backend loop tests in `test_agent_core_unittest.py`. |
| One turn can run repeated tool loops and feed results back to the model. | Covered. | `test_model_owned_loop_internal_first_external_discovery_stage_and_resume` covers plan -> internal context -> stage -> discovery -> ingest -> trace -> writing -> resume. |
| System capability use for research/source tasks must be matrix-based, not a single serial query/tool lane. | Covered. | `source.discovery.plan` capability matrix; `source.web.search` `matrix_mode`, `query_variants`, provider branches, branch diagnostics, merge/rank; focused R3 tests and live matrix probe in `44`. |
| Dynamic project-aware tool pool and tool contracts. | Covered. | `registry.py`, `project_tools.py`, `tool_pool.py`, `tool_window.py`, `contracts.py`; tests for project context, source tools, writing tools, control tools, URL-pool status/history. |
| `agent_batch` becomes governed compatibility tooling, not default routing. | Covered for ordinary and covered project-agent scenarios. | Interactive runtime tests assert ordinary chat/project/writing material turns do not call `agent_batch`; AgentChat E2E asserts no `agent_batch.nl_command.submit` in normal/project/control turns. |
| Internal existing materials must not be confused with source-library/source catalog entries. | Covered. | `material_ontology.py`; `project.context.bundle`; `test_material_ontology_unittest.py`; real-backend E2E material/source catalog checks; docs `22`, `27`, `40`. |
| General material supplementation should inspect internal context first, then plan discovery/collection when needed. | Covered for scripted/model-owned matrix. | `agent-chat-real-backend-long-task.spec.ts`; `tool_window.py`; `json_provider.py` and `native_provider.py` prompts; `test_agent_core_unittest.py` material collection tool-window assertions. |
| Writing-context material supplementation should prefer project/internal material unless external/new material is explicit or an internal gap is stated. | Covered. | `test_material_ontology_unittest.py`; real-backend E2E for writing internal, already-ingested, external-gap, and outside-public-source phrasing; doc `40`. |
| Writing workbench must be AgentCore-backed and selection/range/cursor aware. | Covered. | `WritingWorkbenchPage.tsx`; `AgentWritingAssistantPanel.tsx`; `writing.document.read/create/insert_paragraph` tools; `writing-workbench.spec.ts`; doc `23` and `29`. |
| Workbench edits must be diffed, versioned, reviewable, and rollback-capable. | Covered. | `writing.document.insert_paragraph` version/etag behavior; replacement metadata stores rollback source; E2E covers locate, diff, accept, reject, and original-text restore. |
| Long investigation/writing must split stages, persist state, recover after refresh, and surface progress. | Covered. | `agent_long_task.stage.update`, `agent_task.plan.append`, `agent_session.resume_bundle`; AgentChat long-task E2E reload checks; docs `24`, `25`, `26`, `39`. |
| Source discovery must separate planning/search from ingest. | Covered. | `source.discovery.plan` is no-fetch/no-write; `source.web.search` returns candidates only; `source.candidate.review` gates user/model decision; `ingest.url_pool.submit` and `ingest.source_library.run` perform governed intake. |
| URL-pool candidate review must survive reload and feed follow-up writing. | Covered in deterministic real-backend E2E. | `source.history.read`, `ingest.url_pool.status`, task event writeback; AgentChat E2E approve -> reload -> completed status -> write to workbench. |
| Frontend session UI should be bounded and page-switch/reload tolerant. | Covered for current AgentChat/workbench flows. | `agent-chat.css` bounded layout and scroll containers; AgentChat reload checks; writing workbench real backend readback; docs `20`, `24`, `38`, `39`. |
| Cancel, retry, continue should be user-visible tools, not only global buttons. | Covered. Natural-language control tools exist, and source-library, workflow, direct skill, URL-pool submit/background, and report generation all have cooperative-abort evidence. | `test_agent_control_tools_unittest.py`; `agent-chat.spec.ts`; `test_source_library_run_stops_dispatching_after_session_cancel`; `test_workflow_graph_run_does_not_invoke_skill_after_session_cancel`; `test_direct_skill_invocation_does_not_run_after_session_cancel`; `test_ingest_url_pool_submit_does_not_queue_after_session_cancel`; `test_url_pool_background_task_stops_when_agent_session_is_canceled`; `test_report_generate_does_not_write_artifact_after_session_cancel`. |
| Performance baseline must avoid slow per-turn CLI spawn and reduce tool/context bloat. | Covered at architecture level, with benchmark evidence in prior docs. | Codex core persistent mount and idle TTL implementation docs; `17` performance notes; `20` stream hang RCA; compact result handling in `core.py` and tool summaries. |
| Live external search should use real configured providers when available and avoid false absence claims when unavailable. | Covered in this runtime; diagnostics remain required for deployments without a provider. | `source.web.search` provider readiness diagnostics; tests for Google env names and empty-result uncertainty; docs `34`, `37`; live AgentCore provider validation in `43`. |

## Historical Gap Reconciliation

| Historical Gap | Reconciled State |
| --- | --- |
| Mechanical routing and `你好` entering `agent_batch`. | Closed by AgentCore model-first routing, ordinary chat tests, and UI assertions that hide execution chrome for no-tool turns. |
| Final answers were templated/status-like. | Closed by model final-answer providers and contentfulness guidance/tests requiring concrete tool result synthesis. |
| Project data questions lacked structured/graph/data tools. | Closed by `project.context.bundle`, `project.structured_data.search`, `project.structured_graph.query`, graph search, and real-backend project data scenarios. |
| Source-library and project materials were conflated. | Closed by shared material ontology and context bundle source-catalog note. |
| Writing AI was separate from AgentCore. | Closed by AgentCore-backed writing assistant panel and writing document tools. |
| Selection/cursor edits were not tool-callable. | Closed by `replace_range`, `insert_at_offset`, selection snapshots, and E2E rollback. |
| Long tasks were one-shot messages. | Closed by stage state, task plan, resume bundle, session artifacts, and reload recovery. |
| Source candidates were frontend-only cards. | Closed by `source.candidate.review`, session artifacts, source history, URL-pool submit/status, and writeback events. |
| Artifact/task details were full-page or stale. | Closed by bounded AgentChat thread, runtime details tabs, folded tool details, and session-scoped reload recovery. |
| Zero-result external search looked like evidence absence. | Closed by provider diagnostics and explicit uncertainty next gates. Live provider proof is recorded in `43`; deployments without a stable provider must still report provider limitation. |

## True Remaining Items

### R3 Matrix Capability Execution

Status: closed by [`44_agent-matrix-capability-execution-r3-2026-05-14.md`](./44_agent-matrix-capability-execution-r3-2026-05-14.md).

Current validation:

- `source.discovery.plan` returns `capability_matrix`;
- `source.web.search` supports `matrix_mode`, `query_variants`, provider branches, branch diagnostics, dedupe, and merge/rank output;
- focused R3 gate -> `5 passed, 55 deselected, 3 warnings`;
- broader AgentCore gate -> `69 passed, 3 warnings`;
- live Serper matrix probe -> 2 completed branches, 4 merged candidates, `merge_rank_applied=true`;
- real-backend AgentChat E2E expectations require `capability_matrix` and `matrix_summary` in broad material/source flows.

### R1 Stable Live Search Provider

Status: closed by [`43_agent-live-provider-r1-validation-2026-05-14.md`](./43_agent-live-provider-r1-validation-2026-05-14.md).

The live validation used the actual AgentCore tool registry:

- `source.web.search` returned 3 live candidates through `provider=auto`;
- provider diagnostics reported `configured_paid_providers=["serper"]` and `selected_provider_configured=true`;
- `source.candidate.review` approved a returned live candidate and produced `next_gate=run_ingest.url_pool.submit_with_payload`;
- the review generated a session artifact and a concrete `url_pool` ingest payload.

The validation intentionally did not dispatch a real external URL into URL-pool ingest because that would mutate project/source-library state without a user-selected target source. The mutating URL-pool/status/writeback path remains covered by deterministic tests and browser E2E.

### R2 Cooperative Abort Breadth

Status: closed by [`42_agent-cooperative-abort-coverage-2026-05-14.md`](./42_agent-cooperative-abort-coverage-2026-05-14.md).

Natural-language `task.cancel` exists and session state cancels correctly. The current AgentCore execution surfaces now check cancellation before continuing:

- `ingest.source_library.run`;
- `workflow_graph.run`;
- direct projected skill invocation;
- `ingest.url_pool.submit`;
- `task_ingest_url_via_source_library`;
- `report.generate`.

Current validation:

- focused abort/status gate -> `8 passed, 50 deselected, 3 warnings`;
- broader AgentCore gate -> `67 passed, 3 warnings`.

## Acceptance Matrix From 21

| Scenario | Status | Browser/Unit Gate |
| --- | --- | --- |
| Normal fact question | Covered. | AgentChat E2E: CAPM factual answer, no tools, no `agent_batch`, no debug metadata. |
| Project material inventory | Covered. | Real-backend AgentChat E2E: project material inventory labels internal existing material. |
| Source-library question | Covered. | Real-backend AgentChat E2E: source catalog path exposes `source_library.item.list` and does not label it as existing material. |
| General supplement request | Covered. | Real-backend AgentChat E2E: internal context plus discovery/search/ingest boundary. |
| Writing supplement request | Covered. | Real-backend AgentChat E2E: writing internal material uses `project.context.bundle` and `writing.document.list`, not ingest. |
| Writing external supplement | Covered except live provider environment. | Real-backend scripted E2E reaches `source.discovery.plan`, `source.web.search`, and governed intake; live non-scripted provider remains R1. |
| Long investigation | Covered. | Real-backend AgentChat E2E: stage cards, source intake, task-event writeback, refresh recovery. |
| Workbench edit | Covered. | Writing workbench E2E: selection -> AgentCore stream -> replace_range -> diff -> locate -> reject rollback. |

## Closure Decision

The documented AgentCore architecture and covered user scenarios are closed for the current high-fidelity migration scope. The folder should no longer be read as a set of open implementation gaps merely because older documents contain `Remaining Gap` sections.

R1 is closed by the 43号 live-provider evidence note. R2 is closed by the 42号 cooperative-abort evidence note. R3 is closed by the 44号 matrix-capability evidence note. Future deployments still need provider diagnostics enabled so a missing external provider is reported as a provider limitation rather than as absence of evidence.
