# Wave42 Live Provider Reliability Closure

Date: 2026-05-23
Status: `closed`

## Decision

Move `2026-05-22-clue-chain-successor-scopes` from `ARCHIVE_EXTERNAL_BLOCKED` to `ARCHIVE_CLOSED`.

Wave26 already closed the repo-local graph-submit conflict and UI matrix gates. The only remaining external condition was live provider reliability. Wave42 resolves that condition with direct SearXNG / YaCy runtime evidence through the backend search adapter.

## Manual Evidence

Evidence bundle:

- `development/latest-dev-docs/automation-runs/wave42-manual-open-search-live-closure/2026-05-23/backend_search_sources_live_replay.json`
- `development/latest-dev-docs/automation-runs/wave42-manual-open-search-live-closure/2026-05-23/docker_ps.jsonl`
- `development/latest-dev-docs/automation-runs/wave42-manual-open-search-live-closure/2026-05-23/searxng_raw_embodied_ai.json`
- `development/latest-dev-docs/automation-runs/wave42-manual-open-search-live-closure/2026-05-23/yacy_raw_embodied_ai.json`

Manual checks:

- SearXNG and YaCy containers were running from `ops/search-lab/docker-compose.yml`.
- Both providers returned live HTTP 200 JSON responses.
- Backend `search_sources(...)` returned 6 / 6 passing provider-query rows across SearXNG and YaCy.
- Every row preserved explicit provider attribution and normalized backend trace.
- Each row met result-count, domain-count, and latency thresholds.

## Closure Boundary

This closes the Clue Chain successor live-provider reliability condition for the explicit local open-search provider path. It does not change the broader symbolic search provider-auto rollout policy, which remains tracked under `2026-03-09-agent-symbolic-batch-search-architecture`.
