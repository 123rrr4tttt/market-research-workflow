# Agent External Search Provider Readiness Diagnostics

Date: 2026-05-14
Status: active gap reduction, no closure claim

## Scope

This pass follows the remaining external-source gap from `36_agent-url-pool-status-verified-evidence-gate-2026-05-13.md`.

The target behavior is:

- keep writing/material source decisions model-owned rather than hard-coded phrase routing;
- let writing requests use external search when the user explicitly asks for outside/new sources;
- expose whether live external search has a configured provider before the model treats zero results as evidence;
- avoid misleading provider diagnostics when the local environment uses the project-supported Google Search variable names.

2026-05-14 sync: provider readiness is now one dimension of the R3 matrix requirement in [`41_agent-high-fidelity-migration-closure-audit-2026-05-14.md`](./41_agent-high-fidelity-migration-closure-audit-2026-05-14.md). Readiness diagnostics must travel with each provider/search branch, and the Agent must not collapse a broad source task into one configured provider call without keyword variants, internal evidence checks, candidate ranking, and verification gates.

## Implementation

- Fixed `source.web.search` provider diagnostics to use the same Google readiness contract as the search stack:
  - `GOOGLE_SEARCH_CSE_ID` plus `GOOGLE_SEARCH_API_KEY`; or
  - `GOOGLE_SEARCH_CSE_ID` plus a valid `GOOGLE_APPLICATION_CREDENTIALS` file.
- Added richer readiness metadata in `provider_diagnostics`:
  - `provider_readiness` for Google, Serper, Serpstack, SerpAPI, and DDG;
  - `selected_provider_configured`;
  - `missing_configured_paid_providers`;
  - `recommended_provider_order`;
  - Google sub-flags for CSE, API key, and OAuth credentials file.
- Kept zero-result behavior conservative:
  - empty live search is provider/config/rate-limit uncertainty;
  - the next gate remains `retry_configured_provider_or_manual_candidate_urls`;
  - no source absence conclusion should be made from DDG-limited empty results.
- Added matrix interpretation requirement:
  - provider readiness explains whether a matrix branch is trustworthy;
  - missing provider config is a branch-level blocker, not a topic-level absence claim;
  - configured provider success still requires candidate deduplication and review before ingest or citation.

## Environment Probe

Current local provider readiness:

```text
SERPER_API_KEY: false
SERPAPI_KEY: false
SERPSTACK_KEY: false
GOOGLE_SEARCH_API_KEY: false
GOOGLE_SEARCH_CSE_ID: false
GOOGLE_APPLICATION_CREDENTIALS_FILE: false
```

Diagnostic output for an empty `auto` search now includes:

```text
configured_paid_providers: []
missing_configured_paid_providers: [google, serper, serpstack, serpapi]
empty_result_likely_causes: [provider_not_configured, provider_rate_limited, query_too_broad_or_too_narrow]
```

## Validation

- Focused backend tests:
  - `PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/unit/test_agent_core_unittest.py -q -k "source_web_search"` -> `3 passed, 45 deselected, 3 warnings`
- Direct readiness probe:
  - `PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 - <<'PY' ... _source_web_search_provider_diagnostics(provider='auto', result_count=0) ... PY`
  - returned no configured paid providers and explicit missing-provider diagnostics.

## Result

| Row | Before | After |
| --- | --- | --- |
| Google readiness | Diagnostic checked stale `GOOGLE_CSE_ID` / `GOOGLE_API_KEY` names and could misreport readiness. | Diagnostic uses `GOOGLE_SEARCH_CSE_ID` / `GOOGLE_SEARCH_API_KEY`, matching the actual search stack. |
| Empty external search | Zero results exposed only coarse uncertainty. | Zero results include concrete provider readiness, missing provider list, and next gate. |
| Writing/source behavior | Model could see external search as implemented but not know whether live provider quality was configured. | Model receives readiness metadata and should keep pending/manual-candidate path when no stable provider exists. |

## Remaining Gap

This does not configure a provider by itself. Remaining work:

- configure at least one stable provider (`SERPER_API_KEY`, Google CSE, Serpstack, or SerpAPI) or mount an external-search MCP;
- rerun a non-E2E live search probe with that provider returning concrete candidates;
- keep UI candidate/source history across sessions visible enough for long writing investigations.
- validate R3 matrix behavior: query variants, provider/tool routes, readiness per branch, candidate merge/rank, and explicit unresolved gaps.
