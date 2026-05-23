<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration/46_agent-context-manifest-and-demand-read-synthesis-2026-05-14.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration/46_agent-context-manifest-and-demand-read-synthesis-2026-05-14.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# Agent Context Manifest And Demand-Read Synthesis

Date: 2026-05-14
Status: implemented and regression-covered
Mainline: Claude Code level AgentCore reconstruction

## Why This Reopens The Quality Bar

The previous closure audit proved that AgentCore can route free chat, call project tools, handle writing/workbench actions, and run source discovery. The latest user-facing failure is narrower but important: after local data tools run, the final answer can still look like a structured inventory instead of a concrete summary or analysis.

The root cause is architectural, not only prompt wording:

- tool results are compacted by object order before they are sent back to the model;
- `project.context.bundle` can lose `evidence` and `components` in the second model step;
- `project.structured_data.search` can lose concrete `items` after inventory/count fields occupy the first compacted slots;
- the `project-context` auto-answer path can return a template summary before the model has a chance to inspect specific records;
- final answer instructions currently say to include counts/snippets/result IDs, but do not enforce evidence-based synthesis after local data access.

This means the agent may successfully call local data tools while the model only sees counts, categories, and status text.

## External Reference Positioning

The target design follows three public patterns:

- Claude Code style project agents keep a model-owned loop and manage context through compaction plus tool access, instead of forcing every possible file/tool result into one prompt.
- MCP separates model-controlled tools from contextual resources; project data should expose stable read handles and resource-like entries, not only opaque summaries.
- SWE-agent's ACI framing treats the agent interface as a core performance surface: the tool/observation format should let the model navigate, inspect, verify, and synthesize.

Reference links:

- Claude Code: `https://code.claude.com/docs/en/how-claude-code-works`
- Claude Code memory: `https://code.claude.com/docs/en/memory`
- MCP server concepts: `https://modelcontextprotocol.io/docs/learn/server-concepts`
- MCP resources: `https://modelcontextprotocol.io/docs/concepts/resources`
- MCP tools: `https://modelcontextprotocol.io/specification/2025-06-18/server/tools`
- SWE-agent paper: `https://arxiv.org/abs/2405.15793`

## Target Architecture

The agent should use a `manifest-first -> demand-read -> model-owned synthesis` flow.

### 1. Manifest-First Search And Bundle Tools

Search/list/context tools should return an analysis-ready manifest, not a final answer substitute.

Required manifest fields:

- `item_id` or `resource_uri`;
- `dataset` / `kind` / `category`;
- `title`;
- `why_matched`;
- `short_snippet`;
- `source_ref` when available;
- `quality_flags` when available;
- `read_tool` and `read_arguments`;
- `is_source_catalog_entry` to avoid confusing source-library entrypoints with already-ingested project materials.

Affected tools:

- `project.structured_data.search`;
- `project.context.bundle`;
- `project.structured_graph.query`;
- `project.graph.search`;
- `source.web.search` candidate manifests;
- writing workbench document list/read summaries.

### 2. Demand-Read Tools

The model must be able to open concrete records after seeing a manifest.

New or normalized tool contracts:

- `project.structured_data.item.read`
  - input: `project_key`, `dataset`, `record_id` or `item_id`;
  - output: complete record payload, cleaned text, source refs, quality flags, and compact provenance.
- `project.structured_data.items.read`
  - input: a bounded list of item handles;
  - output: ordered records plus per-item errors.
- `project.context.resource.read`
  - input: `resource_uri` from manifest;
  - output: resolved project material regardless of backing dataset.
- `writing.document.section.read`
  - input: `doc_id`, optional range/heading/cursor context;
  - output: bounded writing text with version and selection anchors.

The tools must be read-only, model-callable, and visible in project-context/writing/investigation tool windows.

### 3. Model-Owned Synthesis

The normal path after a project data tool result must return to the model.

Rules:

- remove `project-context` auto-template finalization from the main path;
- keep template summaries only as failure fallback for model timeout, invalid protocol repair exhaustion, or no final answer;
- after local data manifests are present, the model may call demand-read tools before finalizing;
- final answers after local data access must include an evidence-based synthesis, not only a dataset/count list.

Minimum answer standard:

- name at least two concrete pieces of evidence when available;
- explain the pattern or implication across records;
- distinguish stored project materials from source catalog/external candidates;
- state limits of the local data when relevant;
- offer a next useful action based on the actual findings.

### 4. Context Compaction Rules

Replace field-order truncation with tool-aware compaction.

Required behavior:

- always preserve `model_evidence_manifest`;
- always preserve read handles and `read_tool` arguments;
- preserve top concrete `items` or `evidence` before inventory/count metadata;
- preserve `source_catalog_note` and material category boundary fields;
- when content is omitted, include a machine-actionable `omitted_read_handles` list;
- transcript compaction must summarize old tool results by manifest and handles, not only `model_summary`.

Tool-specific priorities:

| Tool | Must Preserve For Model | May Compress First |
| --- | --- | --- |
| `project.context.bundle` | `model_evidence_manifest`, `evidence`, `missing_evidence`, `source_catalog_note` | deep `components` details |
| `project.structured_data.search` | top `items`, `dataset_counts`, `total_matches`, read handles | full inventory, `dataset_results` |
| `source.web.search` | candidate title/url/snippet/provider diagnostics | raw branch details |
| `project.structured_data.quality_audit` | noisy examples, reasons, recommended actions | full scanned table |

## Implementation Tasks

| ID | Task | Code Area | Acceptance |
| --- | --- | --- | --- |
| C46-T01 | Add `model_evidence_manifest` builder for local project records. | `structured_data_search.py`, `read_only_tools.py`, `project_tools.py` | Search/context tool results expose manifest entries with read handles. |
| C46-T02 | Add item/resource demand-read tools. | `read_only_tools.py`, `project_tools.py`, capability registry/tool window | Model can call item read after search without write permission. |
| C46-T03 | Replace generic field-order transcript compaction with tool-aware compaction. | `agent_core/core.py` | Second provider call receives concrete item titles/snippets/handles. |
| C46-T04 | Remove normal-path `project-context` auto-template summary. | `agent_chat.py`, `core.py` | Project-context runs return to provider after tool results unless fallback is explicitly activated. |
| C46-T05 | Tighten final-answer synthesis instructions. | `json_provider.py`, `native_provider.py` | Prompt requires synthesis/patterns/limits after local data access. |
| C46-T06 | Add backend regression tests for manifest and demand-read. | `test_agent_core_unittest.py`, `test_agent_chat_api_unittest.py` | Tests fail if `items/evidence` disappear from model transcript. |
| C46-T07 | Add live-style user scenario tests. | E2E AgentChat real backend tests | Query such as "帮我总结一些机器人资料" produces substantive analysis, not only counts. |
| C46-T08 | Add docs closure evidence after implementation. | this document and indexes | Validation commands and before/after answer sample are recorded. |

## Test Matrix

Required tests before this spec can be marked implemented:

1. `project.structured_data.search` transcript contains top `items` and read handles after compaction.
2. `project.context.bundle` transcript contains `evidence` or `model_evidence_manifest`, not only `material_categories`.
3. Model can call `project.structured_data.item.read` after a search result and receive full selected record text.
4. `project-context` turn does not auto-finalize through `project_tool_result_summary` on the normal path.
5. Fallback template is still available when provider fails or returns no usable final answer.
6. Final answer quality gate rejects responses that only list datasets/counts after local data access.
7. Frontend stream still receives tool events and final answer in order.
8. Source-library/catalog entries remain marked as collection entrypoints, not already-ingested evidence.

## Non-Goals

- Do not remove source discovery, URL-pool ingest, writing workbench writeback, or long-task stages.
- Do not turn every project record into prompt context eagerly.
- Do not hard-code one user's wording into routing logic.
- Do not make the backend synthesize the answer except as explicit failure fallback.

## Current State

Implemented in the 2026-05-14 closure pass. This document superseded the finality of `45` only for answer substance after local data access; the broader AgentCore high-fidelity migration remains structurally valid, and the contentfulness bar is now backed by manifest-first context, demand-read tools, and model-owned synthesis.

## Implementation Evidence

Code changes landed:

- `structured_data_search.py`
  - builds `model_evidence_manifest` for `project.structured_data.search`;
  - exposes `read_project_structured_data_item`, `read_project_structured_data_items`, and `read_project_context_resource`;
  - manifest entries include stable `item_id`, `resource_uri`, `read_tool`, `read_arguments`, category, snippets, source refs, and quality flags.
- `read_only_tools.py`
  - registers `project.structured_data.item.read`, `project.structured_data.items.read`, and `project.context.resource.read`;
  - adds fallback item resolution through the configured structured-data searcher so tests and custom providers can follow manifest handles without a real DB fixture;
  - adds `model_evidence_manifest` to `project.context.bundle`, including explicit `is_source_catalog_entry=true` for source-library catalog entries.
- `project_tools.py`
  - keeps manifest/items/evidence before inventory metadata in core compaction;
  - adds `writing.document.section.read` for bounded section/range/heading reads from the writing workbench;
  - registers the new read-only tools into the AgentCore registry.
- `tool_window.py`
  - exposes item/resource read tools in project-context, writing, and long-task investigation profiles.
- `core.py`
  - replaces field-order transcript compaction with tool-aware compaction for structured search, context bundles, demand-read tools, writing reads, and artifact reads;
  - preserves `omitted_read_handles` when manifest entries are omitted.
- `agent_chat.py`
  - disables normal-path `agent_core_auto_answer_after_project_tools`; project-context turns now return to the model after project tools unless an explicit fallback path is activated.
- `json_provider.py` and `native_provider.py`
  - instruct the model to use manifest read handles and produce evidence-based synthesis after local data access.
- `fake_provider.py`
  - records request context in test calls so API tests can assert the normal-path auto-template flag is disabled.

Validation commands:

```bash
python3 -m py_compile \
  main/backend/app/services/agent_runtime/structured_data_search.py \
  main/backend/app/services/agent_runtime/read_only_tools.py \
  main/backend/app/services/agent_core/core.py \
  main/backend/app/services/agent_core/project_tools.py \
  main/backend/app/services/agent_core/tool_window.py \
  main/backend/app/services/agent_core/json_provider.py \
  main/backend/app/services/agent_core/native_provider.py \
  main/backend/app/services/agent_core/fake_provider.py \
  main/backend/app/api/agent_chat.py \
  main/backend/tests/unit/test_agent_core_unittest.py \
  main/backend/tests/integration/test_agent_chat_api_unittest.py

cd main/backend && PYTHONPATH=. .venv311/bin/pytest \
  tests/unit/test_agent_core_unittest.py \
  tests/integration/test_agent_chat_api_unittest.py \
  tests/unit/test_structured_data_search_unittest.py -q
```

Observed results:

- Combined focused gate: `94 passed, 11 warnings`.

## Test Matrix Closure

| Requirement | Closure Evidence |
| --- | --- |
| `project.structured_data.search` transcript contains top `items` and read handles after compaction. | `test_structured_data_search_transcript_preserves_items_and_manifest` asserts second provider transcript contains `items[0].title` and `model_evidence_manifest[0].read_arguments.record_id`. |
| `project.context.bundle` transcript contains `evidence` or `model_evidence_manifest`, not only `material_categories`. | `test_project_context_bundle_transcript_preserves_evidence_manifest` asserts context bundle transcript preserves both `evidence` and manifest entry ids. |
| Model can call `project.structured_data.item.read` after search and receive full selected record text. | `test_project_structured_data_item_read_can_follow_search_manifest` and `test_agent_core_robot_material_summary_can_demand_read_local_record` run search -> item.read -> final and assert returned item title, manifest record id, and synthesized final content. |
| `project-context` turn does not auto-finalize through `project_tool_result_summary` on the normal path. | `test_project_context_default_returns_to_model_for_synthesis_after_project_tool` and API tests assert `agent_core_auto_answer_after_project_tools=false` and two provider calls. |
| Fallback template is still available when explicitly activated. | `test_project_context_can_auto_answer_after_project_tool_results` keeps explicit context flag coverage for the legacy fallback path. |
| Final answer quality avoids only datasets/counts after local data access. | Provider prompts require pattern/example/limit synthesis, and regression tests use concrete final answers after manifest/read tools. A stronger semantic quality gate remains a future evaluator hook rather than a hard-coded backend template. |
| Frontend stream still receives tool events and final answer in order. | `test_agent_core_stream_preserves_tool_metadata_for_project_answers` asserts stream includes tool events, tool metadata, final answer, and the disabled auto-template flag. |
| Source-library/catalog entries remain collection entrypoints, not already-ingested evidence. | `project.context.bundle` manifest marks catalog entries with `is_source_catalog_entry=true` and note `collection entrypoint, not already ingested evidence`. |
