# Wave29 Ingest Blocker Alignment

Date: 2026-05-23

Scope: `2026-03-02-single-url-first-ingest-allocation-plan`

Decision marker:
`wave29_repo_local_blockers_closed_external_blocked_candidate`

## Result

The three Wave27 repo-local blocker labels are now split into local closure evidence and retained external/live boundaries. Repo-local evidence is sufficient for this topic's current code contract.

| blocker | Wave29 repo-local status | retained boundary |
| --- | --- | --- |
| `broader_fetch_router` | `closed_repo_local` | Public browser/runtime replay across high-JS domains was not run in this worker. |
| `official_api_adapter` | `closed_repo_local` | Non-arXiv official-provider catalog, credentials, and live API quota behavior remain outside this repo-local gate. |
| `dashboard_tri_state` | `closed_repo_local` | Configured-service single-URL canary and production 24h metrics readback remain operations/live evidence. |

## Evidence

Broader fetch-router repo-local closure:
- `main/backend/app/services/ingest/frontdoor_router_contract.py` pins `success`, `degraded_success`, and `failed`, plus the high-JS `needs_browser_runtime` boundary.
- `main/backend/app/services/ingest/url_pool.py` emits route profile and `frontdoor_status_summary` projection without claiming public browser replay.
- `main/backend/tests/unit/test_frontdoor_fetch_router_contract_unittest.py` covers high-JS route intent and router-boundary status projection.

Official API adapter repo-local closure:
- `main/backend/app/services/source_library/adapters/official_access.py` implements arXiv official API feed search, HTML fallback, and short TTL cache, while unknown providers remain explicit placeholders.
- `main/backend/app/services/resource_pool/unified_search.py` routes `api_preferred` site policies through `official_access.api` instead of scraping those search pages.
- Unit coverage pins arXiv candidates, HTML fallback, cache reuse, unknown-provider placeholder behavior, and `official_access_site_entries` routing.

Dashboard tri-state repo-local closure:
- `/api/v1/dashboard/stats` now returns `tasks.frontdoor_tri_state` from `etl_job_runs.params.frontdoor_status_summary.dashboard_status_counts`.
- `main/frontend-modern/src/pages/DashboardPage.tsx` renders the same three states instead of forcing users to infer frontdoor admission from only outer job status.
- Frontend i18n and TypeScript types now include the tri-state field.

## Archive recommendation

Recommendation: `ARCHIVE_EXTERNAL_BLOCKED` after the integration worker updates shared indexes.

This worker did not edit shared indexes. The topic can move because the remaining conditions are external/live-operational rather than repo-local implementation blockers:
- configured-service single-URL canary for `demo_proj`
- production 24h metrics from URL pool output
- operations-owned all-project strict-gate promotion decision
- public browser/runtime replay coverage for high-JS domains
- non-ArXiv official API provider catalog and credential/quota validation

## Validation

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_single_url_wave29_blocker_alignment.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_single_url_wave29_blocker_alignment_unittest.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_frontdoor_fetch_router_contract_unittest.py main/backend/tests/unit/test_source_library_official_access_adapter_unittest.py main/backend/tests/core_business/test_admin_dashboard_process_core_contract.py
cd main/frontend-modern && npm run build
git diff --check
```
