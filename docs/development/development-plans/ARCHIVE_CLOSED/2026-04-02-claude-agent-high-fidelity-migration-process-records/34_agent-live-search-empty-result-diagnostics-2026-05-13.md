<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration-process-records/34_agent-live-search-empty-result-diagnostics-2026-05-13.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration-process-records/34_agent-live-search-empty-result-diagnostics-2026-05-13.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# Agent Live Search Empty Result Diagnostics

Date: 2026-05-13
Status: active gap reduction, no closure claim

## Scope

This pass addresses the next live-provider gap after `33_agent-source-candidate-decision-state-recovery-2026-05-13.md`: deterministic E2E proved the candidate-to-ingest loop, but a live non-E2E search probe returned zero results because the available DuckDuckGo fallback was rate-limited and no paid provider key was configured.

The target behavior is:

- a zero-result live search is not treated as evidence that the topic/source does not exist;
- AgentCore returns provider/config/rate-limit diagnostics;
- the final answer has actionable next gates instead of a purely formal or misleading "nothing found" response.

2026-05-14 sync: R3 in [`41_agent-high-fidelity-migration-closure-audit-2026-05-14.md`](./41_agent-high-fidelity-migration-closure-audit-2026-05-14.md) strengthens this rule. A zero-result from one query/provider branch is never enough for a source absence claim in a research workflow. The Agent must treat it as one matrix cell and continue through query variants, internal evidence checks, provider readiness diagnostics, manual candidate gates, or explicit user/environment blockers.

## Live Probe

Command:

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 - <<'PY'
from app.services.search.web import search_sources
from app.services.source_library.source_candidate_trust import build_source_candidate_plan
query = 'robotics commercialization policy source candidate official report'
results = search_sources(query, language='en', max_results=3, provider='auto', exclude_existing=True)
print('result_count', len(results or []))
for idx, item in enumerate(results or [], start=1):
    url = item.get('canonical_link') or item.get('link') or item.get('url') or ''
    print('item', idx, item.get('title'), url)
    if url:
        trust = build_source_candidate_plan(project_key='demo_proj', query=query, urls=[url], max_candidates=1, min_trust_score=40)
        print('trust', trust.get('counts'), (trust.get('candidate_urls') or trust.get('rejected_urls') or [{}])[0])
PY
```

Observed result:

- `search_sources: ddg rate limited in site fallback, skipping`
- `result_count 0`

## Implementation

- Added `provider_diagnostics` to `source.web.search` results.
  - configured paid providers: Google CSE, Serper, Serpstack, SerpAPI
  - whether each provider is configured
  - likely zero-result causes: provider rate limit, provider not configured, or query shape
- Added `empty_result_guidance` when live search returns zero candidates.
- Changed zero-result `next_gate` to `retry_configured_provider_or_manual_candidate_urls`.
- Updated native and JSON provider guidance so the model does not claim "no external evidence" from a zero-result provider response.

## Validation

- Focused backend test:
  - `PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/unit/test_agent_core_unittest.py -q -k "source_web_search"` -> `2 passed, 44 deselected, 3 warnings`
- Backend Agent matrix:
  - `PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/unit/test_material_ontology_unittest.py main/backend/tests/unit/test_interactive_agent_runtime_unittest.py main/backend/tests/unit/test_agent_run_loop_unittest.py main/backend/tests/unit/test_agent_core_unittest.py main/backend/tests/integration/test_agent_chat_api_unittest.py -q` -> `108 passed, 11 warnings`
- Live AgentCore probe after the change:
  - `candidate_count 0`
  - `next_gate retry_configured_provider_or_manual_candidate_urls`
  - `configured_paid_providers []`
  - `empty_result_likely_causes ['provider_rate_limited', 'provider_not_configured', 'query_too_broad_or_too_narrow']`
  - `empty_result_guidance No live candidates returned. Do not conclude absence of evidence; retry with a configured provider, narrow domains, or ask for/manual candidate URLs before ingest.`

## Result

| Row | Before | After |
| --- | --- | --- |
| Live provider empty result | Agent could surface zero candidates without explaining provider uncertainty. | Tool result explains provider/config/rate-limit uncertainty and next gate. |
| User interpretation | Empty search risked becoming "there is no external evidence". | Empty search is explicitly not treated as evidence absence. |
| Follow-up path | Retry path was implicit. | Next gate names configured-provider retry or manual candidate URLs. |

## Remaining Gap

This is still not a full external-source closure. Remaining work:

- configure and validate at least one non-DDG provider in the local environment, or mount an external-search MCP service;
- connect completed URL-pool task outputs back into writing/workbench evidence insertion so newly collected material can be cited or inserted in the same long task;
- add source-candidate history controls across sessions.
- add matrix empty-result validation: multiple query variants and provider/tool branches must be visible before the Agent reports an unresolved source gap.
