# MRW Search Lab

This directory isolates local open-search experiments from the main MRW stack.

The layout follows the current upstream interfaces:

- SearXNG reads `settings.yml` from `SEARXNG_SETTINGS_PATH` or `/etc/searxng/settings.yml`; this lab mounts `./searxng` to `/etc/searxng`.
- SearXNG JSON search uses `/search?q=...&format=json`, and `json` must be enabled in `search.formats`.
- YaCy JSON search uses `/yacysearch.json?query=...&resource=local|global&maximumRecords=...`.
- YaCy direct document push uses `/api/push_p.json`; the smoke script uses the documented GET-style test call for a single small text document. The current official image accepts the pushed body through `data-0$file`; `data-0` alone returns a server-side empty-data failure in this image.

## Services

- SearXNG: `http://127.0.0.1:8088`
- YaCy: `http://127.0.0.1:8090`

The compose file is intentionally separate from `main/ops/docker-compose.yml`.

## Commands

```bash
docker compose -f ops/search-lab/docker-compose.yml up -d searxng yacy
bash ops/search-lab/scripts/smoke_searxng.sh
YACY_ADMIN_USER=admin YACY_ADMIN_PASSWORD="${YACY_ADMIN_PASSWORD:-mrwlabpass}" bash ops/search-lab/scripts/smoke_yacy.sh
YACY_RESOURCE_MODE=global python3 ops/search-lab/scripts/compare_keyword_search.py --keywords "embodied ai" "robotics policy" --providers serper,searxng,yacy --out development/latest-dev-docs/automation-runs/search-provider-lab/2026-05-14/results.jsonl
PYTHONPATH=main/backend main/backend/.venv311/bin/python ops/search-lab/scripts/search_provider_trace_contract.py --out development/latest-dev-docs/automation-runs/search-provider-trace-artifacts/2026-05-22/search_provider_trace_contract.json
docker compose -f ops/search-lab/docker-compose.yml down
```

For a fresh YaCy data directory, set a lab-only admin password before running authenticated push smoke:

```bash
docker compose -f ops/search-lab/docker-compose.yml down
rm -f ops/search-lab/yacy/DATA/yacy.running
docker run --rm -v "$PWD/ops/search-lab/yacy/DATA:/opt/yacy_search_server/DATA" yacy/yacy_search_server:latest /opt/yacy_search_server/bin/passwd.sh "${YACY_ADMIN_PASSWORD:-mrwlabpass}"
```

The YaCy smoke validates two different official modes: `resource=global` for network search JSON parsing and `resource=local` for a pushed local test document. The compare script uses `YACY_RESOURCE_MODE=global` for general keyword comparison; keep backend default `YACY_RESOURCE_MODE=local` when using YaCy as a local corpus provider.

## Backend provider variables

```bash
SEARXNG_BASE_URL=http://127.0.0.1:8088
YACY_BASE_URL=http://127.0.0.1:8090
YACY_RESOURCE_MODE=local
SEARXNG_MAX_PAGES=5
```

`searxng` and `yacy` are explicit providers only. They are not part of `provider="auto"`.

SearXNG result volume is increased by paging the official `/search` API with `pageno=1..N`. The backend and compare script derive page count from `max_results`, cap it with `SEARXNG_MAX_PAGES`, and hard-limit it to 10 pages to avoid overloading the local metasearch instance or upstream engines.

The trace contract artifact command above is intentionally offline: it uses mocked SearXNG / YaCy payloads, does not start Docker, and records the required result keys `provider_route`, `provider_family`, `provider_auto_included`, and `backend_trace`. It also asserts that `provider="auto"` does not call SearXNG or YaCy. Use the Docker smoke / compare commands separately when runtime replay evidence is needed.

## Official references used

- SearXNG Search API: https://docs.searxng.org/dev/search_api
- SearXNG settings: https://docs.searxng.org/admin/settings/settings.html
- SearXNG Docker compose reference: https://github.com/searxng/searxng-docker/blob/master/docker-compose.yaml
- YaCy search API: https://wiki.yacy.net/index.php/Dev:APIyacysearch
- YaCy push API: https://wiki.yacy.net/index.php/Dev:APIpush
- YaCy Docker image: https://hub.docker.com/r/yacy/yacy_search_server
