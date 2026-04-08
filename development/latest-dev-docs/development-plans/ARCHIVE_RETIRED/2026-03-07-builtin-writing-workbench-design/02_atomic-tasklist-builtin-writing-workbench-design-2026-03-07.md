# Atomic Task List: Builtin Writing Workbench (2026-03-07)

## Execution Status Snapshot

- `A1`: pending, 用于冻结工作台范围、接口边界与子 Agent 包。
- `A2-A4`: pending, 前端入口、API domain、页面壳层为第一批可并行切口。
- `A5-A8`: pending, 编辑器、预览、安全、选词资料卡为核心主链。
- `A9-A11`: pending, 模板、LLM 助手、文档生命周期为功能闭环。
- `A12-A15`: pending, 后端契约、检索预览、版本/引用、模板校验与审计补齐。
- `A16`: pending, 最小回归门禁与交付收口。

## Global Serial-Parallel Rules

- L0 serial bootstrap: `A1` 必先完成，先冻结目标、依赖链、子 Agent 包边界。
- L1 parallel foundation:
  - group-1 frontend-shell: `A2`, `A3`, `A4`
  - group-2 backend-contract: `A12`
- L2 serial editor chain: `A5 -> A6 -> A7`
- L3 parallel experience layer:
  - group-1 writing-assist: `A8`, `A9`, `A10`
  - group-2 backend-interaction: `A11`, `A13`, `A14`, `A15`
- L4 serial closure: `A16` 在 `A2-A15` 全部通过最小门禁后执行。
- File-conflict rule:
  - touching `main/frontend-modern/src/app/shell/AppShell.tsx`, `main/frontend-modern/src/app/navigation/index.ts`, `main/frontend-modern/src/components/FigmaSideNav.tsx` 的任务按 task-id 串行。
  - touching `main/backend/app/api/writing.py` 的任务按 task-id 串行。
  - touching `main/frontend-modern/src/components/writing/MarkdownEditor.tsx` 的任务按 task-id 串行。

## Global Module IO Contract

Each task must declare:

- `module_input_vars`: `in_*` names + type + source + default
- `module_output_vars`: `out_*` names + type + sink
- `io_mapping`: `in_* -> out_*` and side effects
- `io_boundary`: allowed read/write scope

## Global UI Reuse Rules

- UI optimization is a first-class deliverable, not a post-polish item.
- Do not handcraft core interactions from scratch when equivalent patterns already exist in the local OSS pool.
- Before implementing any of the following, the owner must inspect at least one matching local reference and record the source in task notes:
  - sidebar/document shell
  - hover preview / tooltip / panel
  - markdown live preview
  - template picker
  - right-side ai assistant
  - search-driven related-material panel
- Preferred local references:
  - `reference-pool/oss/outline/app/components/Sidebar`
  - `reference-pool/oss/outline/app/components/HoverPreview`
  - `reference-pool/oss/outline/app/components/Template`
  - `reference-pool/oss/silverbullet/client/markdown_renderer`
  - `reference-pool/oss/silverbullet/client/codemirror`
  - `reference-pool/oss/silverbullet-ai/src/chat-panel.ts`
  - `reference-pool/oss/logseq/src/main/frontend/search`
  - `reference-pool/oss/codemirror-view/src/tooltip.ts`
  - `reference-pool/oss/codemirror-view/src/panel.ts`
- If a task intentionally diverges from a referenced implementation, it must document why reuse was rejected.

## Global Backend Reuse Rules

- Backend completion is also a reuse-first task, not a greenfield rewrite.
- Before adding a new writing-domain route or service, the owner must inspect at least one matching backend pattern already in repo and record it in task notes.
- Preferred existing backend references:
  - `main/backend/app/contracts/responses.py`
  - `main/backend/app/contracts/api.py`
  - `main/backend/app/api/__init__.py`
  - `main/backend/app/api/search.py`
  - `main/backend/app/api/llm_report.py`
  - `main/backend/app/services/search/hybrid.py`
  - `main/backend/app/services/resource_pool/unified_search.py`
  - `main/backend/app/services/source_library/resolver.py`
  - `main/backend/app/services/llm_report_source_enrichment.py`
  - `main/backend/app/services/job_logger.py`
- New writing services should wrap existing search/llm/job infrastructure behind a writing-specific facade instead of leaking raw upstream payloads to frontend.
- If a task introduces new persistence, it must explicitly justify why existing ingestion/reporting tables are insufficient and why the new table belongs in writing domain.

## Reference Investigation Snapshot

The following local files have already been confirmed as the most relevant starting points:

- `A4` shell / left rail:
  - `reference-pool/oss/outline/app/components/Sidebar/Sidebar.tsx`
  - `reference-pool/oss/outline/app/components/Sidebar/components/DocumentLink.tsx`
  - `reference-pool/oss/outline/app/components/Sidebar/components/CollectionLink.tsx`
- `A5` editor / in-editor interaction:
  - `reference-pool/oss/codemirror-view/src/tooltip.ts`
  - `reference-pool/oss/codemirror-view/src/panel.ts`
  - `reference-pool/oss/codemirror-lang-markdown/src/markdown.ts`
  - `reference-pool/oss/codemirror-lang-markdown/src/commands.ts`
- `A6` preview chain:
  - `reference-pool/oss/silverbullet/client/markdown_renderer/markdown_render.ts`
  - `reference-pool/oss/silverbullet/client/markdown_renderer/html_render.ts`
  - `reference-pool/oss/silverbullet/client/markdown_parser/parser.ts`
- `A8` hover / related cards / citation UX:
  - `reference-pool/oss/outline/app/components/HoverPreview/HoverPreview.tsx`
  - `reference-pool/oss/logseq/src/main/frontend/search/browser.cljs`
  - `reference-pool/oss/logseq/src/main/frontend/search/protocol.cljs`
- `A9` templates:
  - `reference-pool/oss/outline/app/components/Template`
  - `reference-pool/oss/outline/app/components/TemplatizeDialog`
  - `reference-pool/oss/logseq/src/resources/templates/contents.md`
- `A10` AI assistant:
  - `reference-pool/oss/silverbullet-ai/src/chat-panel.ts`
  - `reference-pool/oss/silverbullet-ai/assets/chat-panel.html`
  - `reference-pool/oss/silverbullet-ai/src/prompts.ts`
  - `reference-pool/oss/silverbullet-ai/src/embeddings.ts`
- `A11` document behavior and link semantics:
  - `reference-pool/oss/silverbullet/client/codemirror/editor_state.ts`
  - `reference-pool/oss/silverbullet/client/codemirror/wiki_link.ts`
  - `reference-pool/oss/silverbullet/client/codemirror/top_bottom_panels.ts`

All child agents implementing `A4-A11` should read their mapped references before editing product code.

## Backend Reference Investigation Snapshot

The following repo files have already been confirmed as the most relevant backend starting points:

- `A12` contract / route registration:
  - `main/backend/app/contracts/responses.py`
  - `main/backend/app/contracts/api.py`
  - `main/backend/app/api/__init__.py`
- `A13` search aggregation / source normalization:
  - `main/backend/app/api/search.py`
  - `main/backend/app/services/search/hybrid.py`
  - `main/backend/app/services/resource_pool/unified_search.py`
  - `main/backend/app/services/llm_report_source_enrichment.py`
  - `main/backend/app/services/source_library/resolver.py`
- `A14` persistence / job-safe write pattern:
  - `main/backend/app/models/entities.py`
  - `main/backend/app/services/job_logger.py`
- `A15` llm action gateway / trace / quality gate:
  - `main/backend/app/api/llm_report.py`
  - `main/backend/app/services/llm_report_generator.py`
  - `main/backend/app/services/job_logger.py`

All child agents implementing `A12-A15` should read their mapped backend references before editing product code.

Reading the mapped references is a minimum floor, not the whole investigation.

- Child agents must not treat this task list as a substitute for repo exploration.
- Before editing code, each child agent must:
  - open the mapped backend files directly;
  - run at least one repo-wide `rg` pass for the task's key terms such as `project_key`, `trace_id`, `version`, `conflict`, `history`, `job_id`, or matching domain terms;
  - check whether the documented plan still matches current repo structure and naming.
- If repo reality differs from this document, the child agent should follow repo reality and report the drift instead of forcing the planned shape blindly.

## Backend Kickoff Checklist

The following is the implementation-prep snapshot that child agents can use directly.

It is intentionally not sufficient on its own.

- This checklist is a kickoff aid for faster alignment.
- It does not waive the requirement that child agents crawl the repo themselves.
- A child agent has not actually started implementation until it finishes both:
  - local file reading against the mapped references;
  - one fresh grep-based verification pass against the current repo.

- `A12` contract kickoff:
  - define `KeywordCardRequest`, `KeywordCardItem`, `KeywordCardListResponse`
  - define `KeywordCardPreviewRequest/Response`
  - define `KeywordCardDetailResponse`
  - define `SuggestRequest`, `SuggestItem`, `SuggestResponse`
  - reserve `TemplateValidateRequest/Response`
  - reserve `LlmActionRequest/Response`, `LlmActionHistoryItem`
  - enforce `status/data/error/meta` with `trace_id/project_key/request_id`
- `A13` service kickoff:
  - implement `normalize_and_rewrite_query`
  - implement `aggregate_cards`
  - implement `get_card_preview`
  - implement `get_card_detail`
  - implement `suggest`
  - wrap existing `search/resource_pool/source_enrichment` instead of duplicating source fetch logic
- `A14` persistence kickoff:
  - add writing-domain document head model
  - add draft checkpoint model
  - add citation persistence model
  - define `409 + details.conflict_code` protocol
  - support `autosave_token/request_id` idempotency
- `A15` llm/audit kickoff:
  - add template validate contract
  - add sync-first `llm-actions` gateway
  - map `EtlJobRun` into writing history read model
  - gate all read/write paths by `project_key`
  - constrain `job_type` naming to fit current 16-char storage behavior

## Sub-Agent Packaging

- Agent-UI:
  - owns `A2`, `A3`, `A4`
  - focus: navigation, writing domain, page shell
- Agent-Editor:
  - owns `A5`, `A6`, `A7`
  - focus: CodeMirror, preview, selection/tooltip chain
- Agent-Sidebar:
  - owns `A8`, `A9`, `A10`
  - focus: keyword cards, templates, llm assistant
- Agent-Backend:
  - owns `A11`, `A12`, `A13`, `A14`, `A15`
  - focus: document lifecycle, backend APIs, preview/search, versioning/citations, template validation/audit
- Agent-QA:
  - owns `A16`
  - focus: smoke/e2e/regression closure

## Task A1: Scope Freeze and Work Package Split

- 目标: Freeze the builtin writing workbench scope, module ownership, and serial-parallel execution order before implementation.
- status: pending
- depends_on: `[]`
- blocks: `["A2","A3","A4","A12"]`
- 输入: `01_builtin-writing-workbench-design-2026-03-07.md`, local OSS reuse map, current frontend/backend boundaries
- 输出:
  - one frozen implementation boundary for MVP
  - one sub-agent package split (`UI/Editor/Sidebar/Backend/QA`)
  - one explicit non-goals list
- 验收:
  - MVP scope is limited to markdown edit/preview, keyword cards, 3 templates, 4 llm actions, document save/export.
  - `Tiptap` remains phase-2 fallback, not MVP primary path.
  - child-agent ownership is non-overlapping by file boundary.
- 最小门禁:
  - review main plan doc and atomic task doc consistency
- 模块 IO:
  - module_input_vars: `in_plan_doc(file)`, `in_oss_map(doc)`, `in_repo_boundaries(obj)`
  - module_output_vars: `out_scope(doc)`, `out_agent_packages(list)`, `out_non_goals(list)`
  - io_mapping: `in_*` -> frozen scope + package split + non-goals
  - io_boundary: development docs only

## Task A2: Navigation Entry and Route Contract

- 目标: Add the writing workbench entry to modern frontend navigation and hash routing.
- status: pending
- depends_on: `["A1"]`
- blocks: `["A3","A14"]`
- 输入: `main/frontend-modern/src/components/FigmaSideNav.tsx`, `main/frontend-modern/src/app/navigation/index.ts`, `main/frontend-modern/src/app/shell/AppShell.tsx`
- 输出: one reachable `写作工作台` route with stable `NavMode/hash` semantics.
- 验收:
  - sidebar shows `写作工作台`
  - clicking entry reaches writing page
  - page refresh preserves hash and active nav state
- 最小门禁:
  - `cd main/frontend-modern && npm run -s lint`
- 模块 IO:
  - module_input_vars: `in_mode(str)`, `in_hash(str)`, `in_nav_click(event)`
  - module_output_vars: `out_route(str)`, `out_active_mode(str)`, `out_hash_synced(bool)`
  - io_mapping: `in_nav_click` -> `out_route/out_active_mode`; refresh hash -> `out_hash_synced=true`
  - io_boundary: nav shell files only

## Task A3: Writing Domain API and Query Key Model

- 目标: Create a dedicated frontend writing domain instead of coupling the page to scattered `admin` or `llm-report` calls.
- status: pending
- depends_on: `["A1"]`
- blocks: `["A4","A8","A9","A10","A11","A14"]`
- 输入: `main/frontend-modern/src/lib/api/endpoints.ts`, `main/frontend-modern/src/lib/queryKeys.ts`, writing API contract
- 输出:
  - `src/lib/api/domains/writing.ts`
  - writing query key family
  - minimal frontend writing types
- 验收:
  - writing page only consumes the writing domain
  - no component hardcodes `/api/v1/writing/*`
  - query keys are project-aware
- 最小门禁:
  - `cd main/frontend-modern && npm run -s lint`
- 模块 IO:
  - module_input_vars: `in_project_key(str)`, `in_endpoint_contract(obj)`, `in_query_params(obj)`
  - module_output_vars: `out_api_methods(list)`, `out_query_keys(list)`, `out_domain_types(list)`
  - io_mapping: contract + params -> typed domain methods and cache keys
  - io_boundary: frontend api layer only

## Task A4: Writing Workbench Shell

- 目标: Build the three-column page shell with `Write / Preview / Split` modes and isolated writing state.
- status: pending
- depends_on: `["A2","A3"]`
- blocks: `["A5","A8","A9","A10","A11","A14"]`
- 输入: route contract, writing domain, page layout conventions
- 输出:
  - `src/pages/WritingWorkbenchPage.tsx`
  - `src/components/writing/WritingShell.tsx`
  - base workbench state model
- 验收:
  - left / center / right columns render stably
  - mode switch does not drop content
  - loading/error/dirty states are visible
  - shell interaction and panel hierarchy are benchmarked against `outline` sidebar layout and `silverbullet` editor-preview organization instead of bespoke layout invention
- 最小门禁:
  - `cd main/frontend-modern && npm run -s lint`
- 模块 IO:
  - module_input_vars: `in_doc_state(obj)`, `in_view_mode(str)`, `in_layout_event(event)`
  - module_output_vars: `out_shell_rendered(bool)`, `out_view_mode(str)`, `out_state_visible(obj)`
  - io_mapping: shell state + mode -> stable layout render + visible state feedback
  - io_boundary: writing page/shell only

## Task A5: CodeMirror Markdown Editor Integration

- 目标: Integrate a Markdown-first editor using `CodeMirror 6` with stable selection and change events.
- status: pending
- depends_on: `["A4"]`
- blocks: `["A6","A7","A8","A10","A11","A14"]`
- 输入: local OSS refs `reference-pool/oss/codemirror-view`, `reference-pool/oss/codemirror-lang-markdown`, writing shell
- 输出: `src/components/writing/MarkdownEditor.tsx` with `value/onChange/selection` contract.
- 验收:
  - headings/lists/quotes/code blocks edit correctly
  - selection and cursor info are externally consumable
  - undo/redo and focus behavior are stable
  - tooltip/panel/selection behavior references `codemirror-view` primitives rather than custom DOM overlays
- 最小门禁:
  - `cd main/frontend-modern && npm run -s lint`
- 模块 IO:
  - module_input_vars: `in_markdown(str)`, `in_editor_config(obj)`, `in_selection_event(event)`
  - module_output_vars: `out_markdown(str)`, `out_selection(obj)`, `out_editor_ready(bool)`
  - io_mapping: editor input + user actions -> updated markdown + selection payload
  - io_boundary: editor component and writing-specific editor helpers only

## Task A6: Markdown Preview and Sanitization Chain

- 目标: Add secure Markdown preview with `react-markdown + remark-gfm + rehype-sanitize`.
- status: pending
- depends_on: `["A5"]`
- blocks: `["A10","A14"]`
- 输入: editor content, preview security policy, existing UI tokens
- 输出: `src/components/writing/MarkdownPreview.tsx`
- 验收:
  - GFM content renders correctly
  - dangerous HTML, inline events, and suspicious links do not execute
  - write/preview/split all read from the same canonical markdown state
- 最小门禁:
  - `cd main/frontend-modern && npm run -s lint`
- 模块 IO:
  - module_input_vars: `in_markdown(str)`, `in_sanitize_policy(obj)`, `in_render_mode(str)`
  - module_output_vars: `out_preview_html(node)`, `out_sanitized(bool)`, `out_blocked_items(list)`
  - io_mapping: markdown + policy -> sanitized preview render + blocked item trace
  - io_boundary: preview component only

## Task A7: Selection Event, Throttle, and Abort Semantics

- 目标: Stabilize selection-driven keyword lookup with debounce, dedupe, and abort behavior.
- status: pending
- depends_on: `["A5"]`
- blocks: `["A8","A10","A14"]`
- 输入: selection events, keyword-card trigger rules, request lifecycle policy
- 输出:
  - selection trigger hook/service
  - 10-second dedupe window
  - abort-on-stale-request behavior
- 验收:
  - selections under 2 chars do not trigger
  - repeated same selection within 10s does not re-request
  - stale requests are canceled when selection changes
- 最小门禁:
  - `cd main/frontend-modern && npm run -s lint`
- 模块 IO:
  - module_input_vars: `in_selection(str)`, `in_now(ts)`, `in_request_state(obj)`
  - module_output_vars: `out_query(str?)`, `out_aborted(bool)`, `out_deduped(bool)`
  - io_mapping: valid selection -> one query; stale/duplicate selection -> abort or dedupe signal
  - io_boundary: editor hook/service and writing request control helpers only

## Task A8: Keyword Insight Sidebar and Citation Basket

- 目标: Build the right sidebar for `相关资料 / 已加入引用 / 同义词 / LLM 建议问题` and support citation insertion.
- status: pending
- depends_on: `["A3","A4","A7"]`
- blocks: `["A10","A11","A14"]`
- 输入: keyword-card API contract, selection trigger output, editor insertion hooks
- 输出:
  - `src/components/writing/KeywordInsightSidebar.tsx`
  - `src/components/writing/CitationBasket.tsx`
- 验收:
  - keyword cards appear within expected interaction window
  - insert citation preserves source link and metadata
  - basket reflects inserted sources and supports jump-back
  - sidebar/panel/card interaction is benchmarked against `outline` hover preview and `logseq` search-driven related-material experience
- 最小门禁:
  - `cd main/frontend-modern && npm run -s lint`
- 模块 IO:
  - module_input_vars: `in_keyword_cards(list)`, `in_insert_action(obj)`, `in_citation_state(obj)`
  - module_output_vars: `out_sidebar_render(bool)`, `out_inserted_citation(obj)`, `out_basket_state(obj)`
  - io_mapping: card action -> inserted citation + basket update + source retention
  - io_boundary: sidebar and citation basket components only

## Task A9: Template Library and Variable Injection

- 目标: Implement the first three report templates and variable-aware template loading.
- status: pending
- depends_on: `["A3","A4"]`
- blocks: `["A10","A11","A14"]`
- 输入: template manifest/body contract, three MVP template categories, writing state
- 输出:
  - `src/components/writing/TemplateLibraryPanel.tsx`
  - writing-side template loader/validator
- 验收:
  - three template types are selectable
  - switching templates does not overwrite existing body content
  - missing required variables are explicitly surfaced
  - template picker interaction references `outline` template flow and avoids custom multi-step dialog unless strictly needed
- 最小门禁:
  - `cd main/frontend-modern && npm run -s lint`
- 模块 IO:
  - module_input_vars: `in_template_key(str)`, `in_template_manifest(obj)`, `in_doc_state(obj)`
  - module_output_vars: `out_template_ctx(obj)`, `out_missing_vars(list)`, `out_body_unchanged(bool)`
  - io_mapping: template selection -> validated context + missing vars + body preservation signal
  - io_boundary: template panel and writing template helpers only

## Task A10: LLM Assistant Panel and Action Orchestration

- 目标: Add the right-side LLM assistant with `outline_generate / section_expand / selection_rewrite / evidence_summary`.
- status: pending
- depends_on: `["A3","A6","A8","A9"]`
- blocks: `["A14"]`
- 输入: llm-action API contract, editor selection/content, sidebar citations, template context
- 输出:
  - `src/components/writing/LlmAssistantPanel.tsx`
  - writing llm action orchestrator
- 验收:
  - failed llm action does not overwrite original content
  - every action shows `trace_id` and source list
  - action scope can target selection/section/document explicitly
  - right-side ai panel interaction references `silverbullet-ai` chat panel structure before any custom redesign
- 最小门禁:
  - `cd main/frontend-modern && npm run -s lint`
- 模块 IO:
  - module_input_vars: `in_action_mode(str)`, `in_selection(str?)`, `in_doc_ctx(obj)`, `in_template_ctx(obj)`
  - module_output_vars: `out_llm_payload(obj)`, `out_trace_id(str?)`, `out_content_patch(obj?)`
  - io_mapping: action + context -> one llm payload -> traced patch or visible failure
  - io_boundary: llm panel and writing llm helper layer only

## Task A11: Document Lifecycle, Auto-Save, and Export

- 目标: Close the user flow for new/open/save/reopen/export with project-aware document persistence.
- status: pending
- depends_on: `["A3","A4","A8","A9"]`
- blocks: `["A14"]`
- 输入: writing documents API, template context, citation basket state
- 输出:
  - new/open/save/reopen workflow
  - markdown export path
  - optional auto-save hook
- 验收:
  - save + reopen yields identical content
  - export produces standard markdown with retained citations
  - project isolation is preserved on all actions
- 最小门禁:
  - `cd main/frontend-modern && npm run -s lint`
- 模块 IO:
  - module_input_vars: `in_doc_id(str?)`, `in_project_key(str)`, `in_markdown(str)`, `in_export_mode(str)`
  - module_output_vars: `out_saved_doc(obj)`, `out_reopened_doc(obj)`, `out_export_blob(file)`
  - io_mapping: markdown + project context -> persisted doc and export artifact
  - io_boundary: writing lifecycle frontend + writing domain calls only

## Task A12: Backend Writing Contracts and Route Group

- 目标: Create the dedicated backend contract layer and register `/api/v1/writing/*`.
- status: pending
- depends_on: `["A1"]`
- blocks: `["A13","A14"]`
- 输入: current backend envelope contract, writing doc/template/keyword/llm requirements
- 输出:
  - `main/backend/app/api/writing.py`
  - writing schemas for document/template/keyword-card/hover-preview/citation/llm-action/audit-history
  - `main/backend/app/services/writing/` service package skeleton
  - registered router in `api/__init__.py`
  - explicit request/response envelopes for `draft`, `preview`, `detail`, `suggest`, `history`, `validate`
  - concrete schema set for:
    - `KeywordCardRequest`
    - `KeywordCardItem`
    - `KeywordCardListResponse`
    - `KeywordCardPreviewRequest/Response`
    - `KeywordCardDetailResponse`
    - `SuggestRequest/Response`
    - `TemplateValidateRequest/Response`
    - `LlmActionRequest/Response`
- 验收:
  - all writing APIs use unified `status/data/error/meta`
  - contract types are explicit and project-aware
  - no writing page behavior depends on raw `admin` or `llm-report` routes
  - route group explicitly reserves paths for `draft`, `citations`, `templates/validate`, `keyword-cards/preview`, `cards/{card_id}`, `suggest`, `llm-actions/history`
  - `meta` consistently carries at least `trace_id/project_key`
  - route design distinguishes lightweight `preview` payloads from full `detail` payloads
  - schema names and route names stay under one naming system: `writing`, not mixed `writing`/`writing-workbench`
- 最小门禁:
  - `python3 -m compileall main/backend/app/api/writing.py main/backend/app/api/__init__.py main/backend/app`
- 模块 IO:
  - module_input_vars: `in_project_key(str)`, `in_api_payload(obj)`, `in_schema_defs(list)`
  - module_output_vars: `out_routes(list)`, `out_contracts(list)`, `out_envelope_ok(bool)`
  - io_mapping: payload/schema defs -> registered routes + envelope-safe contracts
  - io_boundary: backend writing api + schema layer only
- 实现前清单:
  - request validation should cap `query` length and `limit`
  - `meta` should reserve `request_id/search_backends_used/source_count/dedupe_count/cache_hit`
  - `ErrorCode` should stay on existing enum set; writing-specific distinctions go into `error.details`
  - `HTTPException` can still be raised internally, but route output should be normalized before returning to frontend

## Task A13: Backend Keyword Aggregation, Hover Preview, and Suggest

- 目标: Implement the interaction-facing backend for keyword-card aggregation, hover preview/detail, suggest/typeahead, and source-scoring snapshots.
- status: pending
- depends_on: `["A12"]`
- blocks: `["A15","A16"]`
- 输入:
  - `admin documents`
  - `resource_pool`
  - graph/extracted summaries
  - selection-triggered frontend query patterns
- 输出:
  - keyword-card aggregation service
  - hover-preview/card-detail service
  - suggest/typeahead service
  - source-score/dedupe snapshot in response meta
  - selection fingerprint / short-term cache strategy
  - recommended file targets:
    - `main/backend/app/services/writing/keyword_card_service.py`
    - `main/backend/app/services/writing/search_suggest_service.py`
    - `main/backend/app/services/writing/keyword_cache.py` or equivalent cache helper
- 验收:
  - keyword-card route aggregates three source classes with stable mapping
  - hover preview can return lightweight payload without forcing full-card load
  - card detail can expose source credibility, dedupe trace, and normalized provenance
  - suggest route can serve template search, keyword suggestions, and related-material typeahead
  - duplicate selection requests can be recognized through `selection_hash/request_id`
  - response payload explicitly separates `snippet` from heavier provenance/debug blocks
  - service implementation reuses existing `search/resource_pool/source_enrichment` capabilities rather than cloning search logic
  - query normalization and `selection_hash` canonicalization are documented and shared with frontend
- 最小门禁:
  - `python3 -m compileall main/backend/app/services`
  - `cd main/backend && .venv311/bin/python -m pytest -q tests/unit tests/core_business || true`
- 模块 IO:
  - module_input_vars: `in_keyword(str)`, `in_project_key(str)`, `in_hover_card_id(str?)`, `in_suggest_query(str?)`
  - module_output_vars: `out_keyword_cards(list)`, `out_hover_preview(obj?)`, `out_suggest_items(list)`, `out_score_snapshot(obj?)`
  - io_mapping: validated project context + interaction query -> cards/preview/suggest + source snapshot meta
  - io_boundary: backend writing service layer + relevant tests only
- 实现前清单:
  - `aggregate_cards` should call `search/hybrid`, `resource_pool/unified_search`, and `llm_report_source_enrichment` in a bounded, timeout-aware way
  - `card_id` should be stable enough for preview/detail round-trip within one query session
  - `preview` and `detail` payload builders should be separate functions
  - `suggest` should support at least `keyword/template/material/command` four modes
  - cache scope should be `project_key + selection_hash + mode`

## Task A14: Draft Autosave, Citation Persistence, and Version Conflict

- 目标: Implement the persistence features required by interaction design: autosave draft, citation persistence/recovery, and optimistic version conflict handling.
- status: pending
- depends_on: `["A12"]`
- blocks: `["A16"]`
- 输入:
  - document edit/save/autosave interactions
  - citation insert/recover/export interactions
  - project isolation requirement
- 输出:
  - draft autosave route/service
  - citation entity persistence and restore route/service
  - document version/etag conflict contract
  - writing-domain persistence shape for document head, draft checkpoint, and citation rows
  - recommended file targets:
    - `main/backend/app/services/writing/document_service.py`
    - `main/backend/app/services/writing/citation_service.py`
    - `main/backend/app/models/entities.py` plus migration when persistence tables are needed
    - optional: `main/backend/app/models/writing_entities.py` if writing tables are separated from shared entities
- 验收:
  - autosave can write draft state without overwriting confirmed content blindly
  - stale version update returns explicit conflict code and current head version
  - citations can be restored by `doc_id`
  - export path can rebuild normalized citations from stored entities
  - autosave supports `autosave_token` or equivalent idempotency semantic
  - writing persistence does not overload ingestion `Document` semantics without an explicit compatibility decision
  - conflict response includes enough info for frontend to show "who/when/which version" without extra round-trip
  - persistence design explicitly chooses between extending `entities.py` and adding dedicated writing model file
- 最小门禁:
  - `python3 -m compileall main/backend/app/services`
  - `cd main/backend && .venv311/bin/python -m pytest -q tests/unit tests/core_business || true`
- 模块 IO:
  - module_input_vars: `in_doc_id(str)`, `in_version(str?)`, `in_doc_patch(obj)`, `in_citations(list)`
  - module_output_vars: `out_draft_state(obj)`, `out_saved_version(str?)`, `out_conflict(obj?)`, `out_citation_rows(list)`
  - io_mapping: doc patch + citations + version -> saved draft/version or explicit conflict + restored citations
  - io_boundary: backend writing document/citation/export services only
- 实现前清单:
  - minimum new tables: `writing_documents`, `writing_document_drafts`, `writing_document_citations`
  - optional audit table: `writing_document_events`
  - conflict payload should include `conflict_code/expected_version/current_version/server_snapshot/updated_at`
  - optimistic write path should use atomic update or row lock to avoid ABA race
  - cross-project writes must be blocked before touching document rows

## Task A15: Template Validation, LLM Action Gateway, Audit Read Path, and Authz

- 目标: Implement server-side template validation, llm action execution/audit, and the read APIs needed for trace/history/replay.
- status: pending
- depends_on: `["A12","A13","A14"]`
- blocks: `["A16"]`
- 输入:
  - template manifest/body
  - existing `llm_report_*` services
  - user-triggered llm actions
  - project-level authz requirements
- 输出:
  - template validation service/route
  - llm action gateway
  - llm action history/read route
  - authz/project-key enforcement
  - sync/async action mode contract with reusable trace/job model
  - recommended file targets:
    - `main/backend/app/services/writing/template_service.py`
    - `main/backend/app/services/writing/llm_action_service.py`
    - optional history mapper inside `main/backend/app/services/writing/history_service.py`
- 验收:
  - template validation can return missing vars/defaults/type errors before run
  - llm action route returns `content/sources/mode/warnings/trace_id`
  - llm action history can query action logs, failure reasons, and source/version replay metadata
  - cross-project access is blocked consistently
  - long-running actions reserve async mode with `job_id/status/trace_id` compatibility
  - llm audit read path is backed by existing job logging or equivalent durable trace store
  - template snapshot version is included wherever action execution depends on template content
  - job naming strategy is constrained to current `EtlJobRun.job_type` storage limit
- 最小门禁:
  - `python3 -m compileall main/backend/app/services`
  - `cd main/backend && .venv311/bin/python -m pytest -q tests/unit tests/core_business || true`
- 模块 IO:
  - module_input_vars: `in_template(obj)`, `in_llm_action(obj)`, `in_project_key(str)`, `in_history_query(obj?)`
  - module_output_vars: `out_template_validation(obj)`, `out_llm_result(obj)`, `out_action_history(list)`, `out_authz_pass(bool)`
  - io_mapping: validated template + action + project context -> llm result/history/authz decision
  - io_boundary: backend writing template/llm/authz services only
- 实现前清单:
  - `validate_template_payload` should check structure, required variables, type mismatches, and template version presence
  - `dispatch_action` should be sync-first and reuse `job_logger.start_job/complete_job/fail_job`
  - `history` should map `EtlJobRun` to a writing-specific read model instead of exposing raw params blob
  - authz should run in both API layer and service layer for document/template/history access
  - `async=true` should be treated as protocol reservation unless a real worker execution path is introduced

## Task A16: Minimum Regression Gate and Delivery Closure

- 目标: Establish the minimum regression suite and final closure bundle for the builtin writing workbench.
- status: pending
- depends_on: `["A2","A3","A4","A5","A6","A7","A8","A9","A10","A11","A12","A13","A14","A15"]`
- blocks: `[]`
- 输入: all frontend/backend writing outputs, minimum validation checklist from main plan doc
- 输出:
  - smoke/e2e test set
  - contract/security test set
  - one closure note with pass/fail and known residual risks
  - recommended backend tests:
    - `main/backend/tests/core_business/test_writing_api_contract.py`
    - `main/backend/tests/core_business/test_writing_document_service.py`
    - `main/backend/tests/integration/test_writing_documents_api.py`
    - `main/backend/tests/integration/test_writing_keyword_cards_api.py`
    - `main/backend/tests/integration/test_writing_llm_actions_api.py`
    - `main/backend/tests/security/test_writing_authz.py`
- 验收:
  - route reachability verified
  - save/reopen/export verified
  - keyword-card selection flow verified
  - citation insertion verified
  - hover preview/detail flow verified
  - suggest/typeahead flow verified
  - autosave/version-conflict flow verified
  - template switching body-preservation verified
  - template validation error flow verified
  - llm failure no-overwrite verified
  - llm action history/trace read flow verified
  - duplicate selection request + preview/detail downgrade flow verified
  - markdown preview sanitization verified
  - closure note explicitly records which local OSS interactions were reused and where custom interaction was still necessary
- 最小门禁:
  - `cd main/frontend-modern && npm run -s lint`
  - `cd main/backend && .venv311/bin/python -m pytest -q tests/unit tests/core_business || true`
  - `cd main/frontend-modern && npm run -s test:e2e || true`
- 模块 IO:
  - module_input_vars: `in_test_cases(list)`, `in_smoke_routes(list)`, `in_security_payloads(list)`
  - module_output_vars: `out_passed(int)`, `out_failed(int)`, `out_closure_note(file)`
  - io_mapping: case execution -> pass/fail counts + closure note + residual risk list
  - io_boundary: writing tests, closure doc, and no broader repo refactor

## Verification Snapshot

- Current turn only produced plan-level decomposition.
- No business code has been changed yet.
- The task list is ready for child-agent assignment by package:
  - Agent-UI: `A2-A4`
  - Agent-Editor: `A5-A7`
  - Agent-Sidebar: `A8-A10`
  - Agent-Backend: `A11-A13`
  - Agent-QA: `A14`
