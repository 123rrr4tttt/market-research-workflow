# Wave9-9 AT-EXT Current Contract Evidence (2026-05-22)

## Scope

This evidence closes a deterministic narrow AT-EXT current-state gate for
`2026-03-25-source-library-ingest-minimal-migration`.

It does not edit shared indexes. It reads:

- [08_atomic-tasklist-external-project-powered-item-2026-03-27.md](./08_atomic-tasklist-external-project-powered-item-2026-03-27.md)
- [references/2026-03-27-external-project-powered-item-design.md](./references/2026-03-27-external-project-powered-item-design.md)
- [references/2026-03-26-batch-helper-input-boundary-and-runtime-target-contract.md](./references/2026-03-26-batch-helper-input-boundary-and-runtime-target-contract.md)

## Implemented Gate

- Checker: `main/backend/scripts/check_source_library_ingest_external_project_contract.py`
- Unit gate:
  `main/backend/tests/unit/test_source_library_ingest_external_project_contract_check_unittest.py`

Checker contract:

- `contract_version`: `source-library-ingest-at-ext-current-contract.v1`
- `scope`: `deterministic_current_state_no_live_external_probe`
- `status`: `passed_with_known_gaps`

Wave33 note (2026-05-23): this Wave9 snapshot is historical. Wave27 and the
current checker now close the former `python_library_cli_container_runners_not_enabled`
repo-local blocker by marking `AT-EXT-05` and `AT-EXT-08` as
`closed_repo_local_v1`; the remaining blockers are live article-extraction stack
replay and live external-project replay only.

## Current AT-EXT Status

| Task | Status | Current evidence |
| --- | --- | --- |
| `AT-EXT-01` | `closed_narrow_v1` | External items require `channel_key=external_project.manifest` plus `extra.external_project_manifest`; channel mismatch is rejected. |
| `AT-EXT-02` | `closed_narrow_v1` | `external_item.manifest.v1` normalizes `rss_feed`, `sitemap`, and `http_api` manifests. |
| `AT-EXT-03` | `closed_narrow_v1` | Provider registry exposes bounded `external_project.rss_feed`, `external_project.sitemap`, and `external_project.http_api` bindings. |
| `AT-EXT-04` | `closed_narrow_v1` | High-confidence endpoint evidence builds a stable manifest through deterministic context probe without LLM fallback. |
| `AT-EXT-05` | `partial_narrow_v1` | The bounded runner executes `http_api` and has registered `rss_feed` / `sitemap` runners. |
| `AT-EXT-06` | `closed_narrow_v1` | Runner records preserve artifact refs and map into `terminal_output -> frontdoor_ingress -> postprocess_frontdoor`. |
| `AT-EXT-07` | `closed_narrow_v1` | External items keep definition-first semantics and expose `execution_plan` only by opt-in. |
| `AT-EXT-08` | `partial_narrow_v1` | Manifest-backed items are runnable through the external-project adapter with deterministic patched runtime evidence. |
| `AT-EXT-09` | `partial_pending_external_replay` | Validation now has current-state evidence and explicit remaining blockers. |

## Remaining Blockers

The checker intentionally leaves these gaps open:

| Blocker | Applies to | Reason |
| --- | --- | --- |
| `article_extraction_stack_runtime_not_closed` | `AT-EXT-05`, `AT-EXT-06`, `AT-EXT-08`, `AT-EXT-09` | Current deterministic runtime proves candidate/article-metadata records, but does not prove Fundus/news-please style article-body extraction. |
| `python_library_cli_container_runners_not_enabled` | `AT-EXT-05`, `AT-EXT-08`, `AT-EXT-09` | Provider registry intentionally exposes `rss_feed`, `sitemap`, and `http_api` only. |
| `live_external_project_replay_not_run` | `AT-EXT-08`, `AT-EXT-09` | This gate uses patched deterministic runtime evidence and does not probe a live third-party endpoint. |

## Validation Snapshot

Commands run from
`/Users/wangyiliang/market-research-workflow.worktrees/devdocs-wave9-source-library-ingest-ext`:

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_source_library_ingest_external_project_contract.py
```

Result:

- `status`: `passed_with_known_gaps`
- `failures`: `[]`

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_source_library_ingest_external_project_contract_check_unittest.py
```

Result:

- `1 passed, 2 warnings`

## Closure Interpretation

This worker does not mark the whole topic fully closed. It moves AT-EXT from
undifferentiated pending to a test-backed narrow current state:

- supported now: registered external manifests for `rss_feed`, `sitemap`, and
  `http_api`; deterministic manifest synthesis; provider registry selection;
  item-surface plan derivation; frontdoor-compatible record handoff.
- still pending: article extraction stacks, python/CLI/container runners, and
  live external-project replay evidence.
