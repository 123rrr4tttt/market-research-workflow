# AgentCore Completion Audit And R25 Stream Contract

Date: 2026-05-13
Status: active audit, not final closure
Mainline: `agent_core_v3`

## Objective Restatement

Build the whole agent architecture to Claude Code level interaction quality, then verify it from real user-style prompts rather than only implementation checklists.

Concrete success criteria:

- normal conversational turns answer naturally, without mechanical classification, fake approvals, or debug metadata;
- the model owns tool choice through schemas and can call project data, graph, source-library, writing, task, artifact, skill, and MCP surfaces when relevant;
- long tasks can be split, resumed, retried, and inspected as durable work;
- multi-round investigation can persist leads, trace clues, and pass evidence into writing;
- the writing workbench works as a visible collaborator with versioned writeback, diff review, and provenance;
- Codex/Core stays replaceable and fast enough for chat, with persistent provider reuse and compact memory/tool context;
- external browser/search/MCP tools are truthfully represented and not shown as executable unless mounted and reachable;
- the user-facing stream exposes progress within the first second and hides internal paths/errors.
- post-tool answers must not be pure status/formal returns; they must include concrete affected objects, useful result content, and the next inspectable state.

## Prompt To Artifact Checklist

| Requirement / prompt | Expected artifact or gate | Current evidence | Status |
| --- | --- | --- | --- |
| `你好` free chat | no tools, no approval, natural answer | AgentCore unit coverage and AgentChat E2E free-chat path; live `free_chat_hello` artifact exists under `agent-core-live-user-audit-2026-05-13` | covered |
| ordinary factual question | no project tools, no "execute task" template | live `free_chat_capm` artifact and no-tool window behavior | covered, needs wider prompt set |
| "你现在能做什么" | capability/catalog summary, no `agent_batch` submission | R29 live matrix returned a natural capability summary using `project.summary.read`, `mcp.service.catalog`, `agent_runtime.tool_pool.list`, and `skill.search`; capability catalogue filtered to implemented/enabled entries; debug metadata hidden by default | covered |
| project data inventory | model-selected read-only project tools and natural answer | project-data tools are in high-signal window; auto-summary fallback added; previous timeout reproduced and fixed | covered |
| structured data search, e.g. "机器人" | query stored structured/graph data and return answer | `robot_structured_search_auto_summary_newbackend`: 8.289s, 4 tool events, final bundle | covered |
| structured data quality/cleaning audit | detect noisy stored web records without mutating raw evidence | R33 adds `project.structured_data.quality_audit` and a narrow `data-quality-audit` tool window; live audit scanned `documents 201` and `graph_nodes 3942`, found `303` noisy records, and returned dataset distribution without modifying data | covered |
| source-library evidence request | approval/continue boundary from same run state | R29 live matrix produced `approval-12799d9bc11d48b9`; `/agent-chat/approvals/{id}/continue` returned 200 and executed `ingest.source_library.run` | covered |
| model-owned tools, not classifier | no default `FastModelFirstTurnDecisionPlanner`/old scaffold | `agent_core_v3` default, old paths explicit only | covered |
| fake/formal tools removed | model-visible tools either executable or hidden | R10 cleanup, implementation state in tool pool, external boundary UI | covered |
| anti-formal final answers | post-tool answers include concrete object/data, useful counts/snippets/result IDs, and next inspectable state | `r29_contentfulness_gate.json` initially failed source-library continue and writing writeback; provider prompts and tool summaries were strengthened, then `r29_contentfulness_gate_after_fix.json` passed on live source-library continue and writing writeback reruns | covered |
| skill discovery/load/invocation | `skill.search -> skill.load -> skill.<id>` | unit chain coverage | covered |
| MCP boundary | `mcp.tools.list -> mcp.tool.call`, structured not-configured/unreachable errors | mounted test tool and external status matrix coverage | covered for contract, not real server maturity |
| long task split/resume | `agent_task.plan.append`, partial completion, resume bundle | unit/API coverage and AgentChat task tab | covered |
| natural cancel/retry/continue | control tools callable and visible | R27 backend integration replays `取消当前会话 -> 继续 -> 重试失败任务` in one AgentCore session; AgentChat E2E renders each control tool and rejects `agent_batch` fallback | covered |
| cooperative cancel | long-running executors abort quickly | R28 adds cooperative abort checks to `ingest.source_library.run`: cancellation before/after each item dispatch emits `agent_core.cooperative_abort.v1`, stops remaining item dispatch, and returns structured `canceled` with `skipped_items`; backend unit coverage proves the second item is not dispatched after session cancel | covered for source-library batch lane; broaden pattern as more long executors materialize |
| source discovery/investigation | source plan, leads append, trace read | R29 initial live probe exposed missing `leads.append`; provider guidance was strengthened and live re-run produced `agent_task.plan.append -> source.discovery.plan -> agent_investigation.leads.append -> agent_investigation.trace.read`, with 5 clue nodes and 4 edges | covered |
| writing workbench collaboration | versioned insert, provenance, diff review | R29 live matrix created `Robot Market Snapshot` through `writing.document.insert_paragraph` with source refs and workbench update metadata; R31 adds side-by-side paragraph anchors with locate/accept/reject/diff actions and E2E coverage | covered for paragraph writeback and side-rail collaboration; richer full-canvas editing remains polish |
| first-second stream contract | within 1s `assistant_delta` or `tool_call_requested` | R25 adds stream model-step `assistant_delta`; R26 live probe for `中国的首都是哪里？` saw `agent_core.assistant_delta` at 0.209s and final at 4.257s | covered |
| persistent Codex core | first call mounts, later calls reuse process, idle TTL 300s | app-server status and previous live reuse evidence | covered |
| latency and compact context | avoid full tool catalog and large result feedback | tool windows, native provider path, compact tool transcripts, project auto-summary | covered, long-tail provider latency remains |
| external search/browser hardening | mounted real service matrix and ingress safety | R30 live status prompt confirms `mcp.service.catalog`/`mcp.tools.list` are callable and browser/search services are truthfully disabled as `not_configured`; no concrete local browser/search MCP server is currently mounted | partial, blocked on concrete external service mount |
| docs-driven tracking | specs and indexes updated | this audit plus task/progress docs | covered |

## R25 Change

The stream contract in the reconstruction spec says a stream connection must produce `assistant_delta` or `tool_call_requested` within one second. Prior work emitted `agent_core.stream_opened` and `agent_core.stream_started`, but those are transport lifecycle events, not model/tool progress events.

R25 adds a real model-step status event:

- when `AgentCore` enters a streamed model step, it emits `assistant_delta` with `delta=""`, `phase="model_step"`, `status="thinking"`, and contract `agent_core.model_step_status.v1`;
- this event is not appended to the model transcript and does not fake assistant text;
- existing final answer and tool-call events still carry the substantive answer/tool result.

## Current Completion Assessment

Current completion remains below final closure:

- AgentCore mainline: high confidence.
- Free chat and project-data tool loop: high confidence after live R24/R25 probes.
- Long-task/investigation/writing backend contracts: high confidence for covered tool chains after R29 live matrix and targeted tests.
- User-facing long-task and writing product polish: medium confidence; writing update review is materially improved after R31 side-rail anchors.
- Post-tool answer quality: high confidence for the currently tested source-library and writing paths after the anti-formal contentfulness gate v2 passed.
- External browser/search/MCP real service hardening: high confidence for truthful boundary/status reporting, low confidence for real browser/search execution because no concrete service is mounted.
- Cooperative cancellation and structured retry resume tokens: medium confidence for source-library batch dispatch, still partial across all possible future long executors.
- Structured data quality: improved for user-visible answers through R29 query normalization, display-noise filtering, and visible-evidence ranking; R33 now adds a live callable quality-audit lane for old noisy stored records. Raw evidence is preserved; destructive or writeback cleanup remains deliberately separate.

## Remaining Development Queue

1. R30: mount or configure a concrete browser/search MCP server, then run the real execution matrix; current local runtime only supports truthful disabled-state reporting for these external services.
2. R32: extend cooperative abort beyond source-library dispatch when additional materialized long executors are added.

## Closure Rule

Do not mark this lane complete until every row above is either `covered` with current live/test evidence or deliberately rescoped into a separate named project by the user.
