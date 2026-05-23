# Wave11 Source-Library Extraction Runner Evidence (2026-05-22)

## Scope

This evidence advances the CURRENT_DEV topic
`2026-03-25-source-library-ingest-minimal-migration` for registered
external-project powered source-library items.

This is a deterministic in-repo contract only. It uses fixtures and patched
runtime calls. It does not access the public internet and does not claim live
external-project replay.

## Contract Landed

- Manifest/schema:
  - `external_item.manifest.v1` now accepts `execution_mode=article_extractor`.
  - `article-extractor://...` runner refs are accepted only for
    `article_extractor` manifests.
  - `runtime_config.parser` is normalized to a bounded parser identity.
- Provider registry:
  - `external_project.article_extractor` is registered as an
    `article_extraction_stack` provider with `article_body_extraction`
    capability family.
  - Registry output exposes parser capability and fallback states.
- Runner:
  - The external-project adapter runs a fixture-backed article extraction path
    from registered manifest + runtime `urls`.
  - Records carry `record_meta.article_extraction` with
    `external_project.article_body_extraction.v1`.
  - Runtime diagnostics carry `external_project.article_extraction_runner.v1`.
- Fallback states:
  - `article_body_extracted`
  - `metadata_only_fallback`
  - `fetch_error_fallback`
- Frontdoor bridge:
  - Materialized article-body records with `records_allow_extract` are promoted
    to a source-library document candidate.
  - Structured extraction and writer remain disabled in this bridge contract;
    the source-library runner proves body materialization, not downstream live
    writing.

## Deterministic Evidence

The contract checker now includes an `article_extraction_runner` evidence block:

- provider key: `external_project.article_extractor`
- parser capability: `heuristic.main_content.v1`
- fixture fallback states observed:
  - `article_body_extracted`
  - `metadata_only_fallback`
- frontdoor handoff:
  - `frontdoor_has_document_candidate=true`
  - `frontdoor_dispatch_reason=external_project_article_body_materialized`
  - `frontdoor_run_extraction=false`

Known gaps remain explicit:

- `live_article_extraction_stack_replay_not_run`
- `python_library_cli_container_runners_not_enabled`
- `live_external_project_replay_not_run`

## Validation

Commands run from this worktree:

```bash
python3 scripts/check_current_dev_wave11_plan.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_source_library_ingest_external_project_contract.py
/Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_source_library_external_project_adapter_unittest.py main/backend/tests/unit/test_source_library_external_project_registry_unittest.py main/backend/tests/unit/test_collect_runtime_source_library_adapter_unittest.py main/backend/tests/unit/test_source_library_ingest_external_project_contract_check_unittest.py
git diff --check
```

Current deterministic result:

- Wave11 plan gate: passed.
- External-project contract checker: `passed_with_known_gaps`, `failures=[]`.
- Focused pytest: passed.
- Whitespace gate: passed.
