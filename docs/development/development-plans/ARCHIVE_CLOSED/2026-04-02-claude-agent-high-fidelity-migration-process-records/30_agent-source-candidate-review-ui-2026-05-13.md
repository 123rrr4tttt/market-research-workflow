<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration-process-records/30_agent-source-candidate-review-ui-2026-05-13.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration-process-records/30_agent-source-candidate-review-ui-2026-05-13.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# Agent Source Candidate Review UI

Date: 2026-05-13
Status: active gap reduction, no closure claim

## Scope

This note covers the next source-intake UX gap from `28_agent-live-external-source-search-tool-2026-05-13.md` and `29_agent-writing-workbench-selection-rewrite-rollback-e2e-2026-05-13.md`.

The previous state exposed `source.web.search` as an AgentCore tool, but the AgentChat UI primarily surfaced `source.discovery.plan` trust cards. Concrete external search candidates could remain buried in raw tool results, making the user-facing boundary unclear:

- candidate found by search;
- trust assessment;
- not yet ingested;
- next step is review before source-library or URL-pool ingest.

## Implementation

- `AgentChatPage` source quality cards now consume both:
  - `source.discovery.plan.candidate_urls`;
  - `source.web.search.candidates`.
- Candidate cards now show:
  - source title;
  - URL;
  - trust status / score / level;
  - trust reason;
  - snippet;
  - provider metadata when available;
  - `next_gate`, such as `review_candidates_then_source_library_or_url_pool_ingest`.
- The real-backend AgentChat E2E now asserts the `source.web.search` candidate card is visible, not only the discovery-plan trust card.

## Validation

- Mocked AgentChat long-task browser scenario:
  - `npm run test:e2e -- tests/e2e/agent-chat.spec.ts --grep "long task" --reporter=line` -> `1 passed`
- Frontend lint:
  - `npm run lint -- src/pages/AgentChatPage.tsx src/pages/agent-chat.css tests/e2e/agent-chat-real-backend-long-task.spec.ts` -> `0 errors, 1 existing CSS ignored warning`
- Real-backend AgentChat matrix:
  - backend: `AGENT_CORE_E2E_SCRIPTED_PROVIDER_ENABLED=true PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m uvicorn app.main:app --host 127.0.0.1 --port 8021`
  - frontend: `AGENT_CORE_REAL_BACKEND_E2E=1 VITE_API_PROXY_TARGET=http://127.0.0.1:8021 npm run test:e2e -- tests/e2e/agent-chat-real-backend-long-task.spec.ts --reporter=line` -> `2 passed`

## Result

The source side is now less formal:

| Row | Before | After |
| --- | --- | --- |
| External candidate visibility | `source.web.search` executed, but concrete candidates were mostly visible only in raw tool detail. | Source quality cards show search candidate title, URL, snippet, trust and review gate. |
| Ingest boundary | User could see `ingest.source_library.run`, but candidate-vs-ingested boundary was implicit. | UI explicitly shows the search candidate and `review_candidates_then_source_library_or_url_pool_ingest` before collection. |

## Remaining Gap

This is still not a full source workflow closure. Remaining work:

- clickable approve/defer/reject controls per candidate;
- conversion from approved candidates into concrete source-library items or URL-pool ingest payloads;
- live provider quality validation beyond deterministic E2E fixtures.
