# Wave55 C3 Live Replay Closure (2026-05-23)

## Scope

This worker closes the two remaining live replay gaps for
`2026-03-25-source-library-ingest-minimal-migration`. Supervisor integration
then moved the topic from `ARCHIVE_EXTERNAL_BLOCKED` to `ARCHIVE_CLOSED` and
updated the global target counts.

Closed gap codes:

- `live_article_extraction_stack_replay_not_run`
- `live_external_project_replay_not_run`

## Implementation

- Added a skip-safe live replay runner:
  `main/backend/scripts/source_library_ingest_live_replay.py`
- Extended the AT-EXT current-state checker so it can require and validate a
  live replay artifact:
  `main/backend/scripts/check_source_library_ingest_external_project_contract.py`
- Added unit coverage for the live runner and artifact-driven checker closure.

The live runner uses the existing source-library external-project adapter and
frontdoor/authority bridge:

- article extraction stack: `article_extractor` manifest over
  `https://peps.python.org/pep-0008/`
- external-project replay: `http_api` manifest over
  `https://api.github.com/repos/python/cpython`

## Live Evidence

Artifact:

- `live-replay-artifacts/2026-05-23-wave55-c3-source-library-ingest-live-replay.json`
- `live-replay-artifacts/2026-05-23-wave55-c3-source-library-ingest-live-replay.log`

Live run command:

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 \
  main/backend/scripts/source_library_ingest_live_replay.py \
  --allow-public-network \
  --strict \
  --output docs/development/development-plans/ARCHIVE_CLOSED/2026-03-25-source-library-ingest-minimal-migration/live-replay-artifacts/2026-05-23-wave55-c3-source-library-ingest-live-replay.json \
  --log-output docs/development/development-plans/ARCHIVE_CLOSED/2026-03-25-source-library-ingest-minimal-migration/live-replay-artifacts/2026-05-23-wave55-c3-source-library-ingest-live-replay.log
```

Result:

- article extraction: `status=completed`, runner `status=ok`, records `1`,
  normalized `1`, errors `0`
- extracted article body: `46584` chars via `heuristic.main_content.v1`
- external-project replay: `status=completed`, runner `status=ok`, records `1`,
  normalized `1`, errors `0`
- live validation:
  - `live_article_extraction_stack_replay_closed=true`
  - `live_external_project_replay_closed=true`
  - `live_evidence_sufficient=true`

## Closure Gate

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 \
  main/backend/scripts/check_source_library_ingest_external_project_contract.py \
  --live-replay-artifact docs/development/development-plans/ARCHIVE_CLOSED/2026-03-25-source-library-ingest-minimal-migration/live-replay-artifacts/2026-05-23-wave55-c3-source-library-ingest-live-replay.json \
  --require-live-replay
```

Result:

- `status=passed`
- `scope=deterministic_current_state_with_accepted_live_replay_artifact`
- `remaining_gaps=[]`
- `failures=[]`
- AT-EXT-09: `closed_live_replay_v1`

## Focused Test Gate

```bash
/Users/wangyiliang/.local/bin/python3.11 -m pytest -q \
  main/backend/tests/unit/test_source_library_ingest_live_replay_unittest.py \
  main/backend/tests/unit/test_source_library_ingest_external_project_contract_check_unittest.py \
  main/backend/tests/unit/test_source_library_external_project_adapter_unittest.py
```

Result: `11 passed, 2 warnings`.

```bash
/Users/wangyiliang/.local/bin/python3.11 -m pytest -q \
  main/backend/tests/unit/test_source_library_ingest_live_replay_unittest.py \
  main/backend/tests/unit/test_source_library_ingest_external_project_contract_check_unittest.py
```

Result: `4 passed, 2 warnings`.

## Boundary Notes

This is a bounded public-network replay, not a general public replay suite and
not a production DB/API/UI write test. The live evidence is sufficient for the
two named ingest-minimal-migration gaps because it exercises the existing
source-library adapter, terminal output, frontdoor ingress, postprocess
frontdoor, and authority-output path with live external fetches.
