# Wave42 Manual Open Search Live Closure

Date: 2026-05-23
Status: `closed`

## Decision

Move `2026-05-14-local-open-search-provider-isolation` from `ARCHIVE_EXTERNAL_BLOCKED` to `ARCHIVE_CLOSED`.

The remaining external condition was SearXNG / YaCy live availability, normalized result quality / latency, timeout-bounded behavior, and operator decision. Wave42 resolved that condition by starting the real local Docker services and exercising the backend adapters directly.

## Manual Evidence

Evidence bundle:

- `development/latest-dev-docs/automation-runs/wave42-manual-open-search-live-closure/2026-05-23/backend_search_sources_live_replay.json`
- `development/latest-dev-docs/automation-runs/wave42-manual-open-search-live-closure/2026-05-23/docker_ps.jsonl`
- `development/latest-dev-docs/automation-runs/wave42-manual-open-search-live-closure/2026-05-23/searxng_raw_embodied_ai.json`
- `development/latest-dev-docs/automation-runs/wave42-manual-open-search-live-closure/2026-05-23/yacy_raw_embodied_ai.json`

Manual checks:

- Docker daemon was started and `docker compose -f ops/search-lab/docker-compose.yml up -d searxng yacy` brought both services up.
- SearXNG returned HTTP 200 JSON search output from `127.0.0.1:8088`.
- YaCy returned HTTP 200 JSON search output from `127.0.0.1:8090` with `resource=global`.
- Backend `search_sources(provider="searxng")` returned 3 / 3 passing query rows.
- Backend `search_sources(provider="yacy")` returned 3 / 3 passing query rows.
- Every normalized backend row retained explicit provider trace: `provider_route=explicit:*`, `provider_family=local_open_search`, `provider_auto_included=false`, and populated `backend_trace`.
- Each provider/query row returned at least 3 results, at least 2 distinct domains, and latency under 4000ms.

## Operator Decision

`provider=auto` remains intentionally excluded for local open-search providers. That is the accepted product boundary, not a remaining blocker. The closed scope is optional explicit-provider operation through SearXNG / YaCy, with live runtime evidence attached.

## Remaining Scope Moved Elsewhere

This closure does not close:

- global vector semantic quality;
- embedding provider verification;
- OSS-node tenant / scheduler / UI SLA;
- symbolic batch search threshold-evaluated provider-auto rollout.

Those are tracked by their own target directories and remain external-blocked where applicable.
