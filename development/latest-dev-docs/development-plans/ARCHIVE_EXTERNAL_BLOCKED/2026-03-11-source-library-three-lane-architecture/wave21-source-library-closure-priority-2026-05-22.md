# Wave21 Source-Library Closure Priority (2026-05-22)

## Scope

This note is the Wave21 closer for the deterministic source-library review
cluster spanning:

- [2026-03-11-source-library-three-lane-architecture](.)
- [2026-03-14-search-chain-source-library-mounting-audit](../2026-03-14-search-chain-source-library-mounting-audit)
- [2026-03-14-source-library-adapter-capability-remediation](../../../../../docs/development/development-plans/ARCHIVE_CLOSED/2026-03-14-source-library-adapter-capability-remediation/20_wave49-manual-public-replay-closure-2026-05-23.md)
- [2026-03-25-source-library-ingest-minimal-migration](../2026-03-25-source-library-ingest-minimal-migration)

No shared indexes are edited in this pass. Moving directories out of
`CURRENT_DEV` still requires a later integration pass because it must update the
shared navigation surfaces.

Wave33/Wave49 note (2026-05-23): this note is preserved as a Wave21 snapshot.
The later Wave27 decision moved `2026-03-25-source-library-ingest-minimal-migration`
to `external_blocked` after closing the former
`python_library_cli_container_runners_not_enabled` repo-local blocker. Wave49
then moved `2026-03-14-source-library-adapter-capability-remediation` to
`ARCHIVE_CLOSED` after the real 45-site public replay was attached. Do not
reuse the `retained_partial` or `external_blocked_candidate` rows below as
current status.

## Decision

The table below is a historical Wave21 snapshot. The `retained_partial` row is not current status after Wave27/Wave33.

| Topic | Decision | Move-from-CURRENT_DEV candidate | Reason |
| --- | --- | --- | --- |
| `2026-03-11-source-library-three-lane-architecture` | `external_blocked_candidate` | yes | Wave16, Wave18, Wave19, and Wave20 deterministic review batches are closed. Remaining evidence is human review, opt-in public replay, live source collection, or live ingest/external replay. No topic-local review runner/checker blocker was found in the Wave20 cluster. |
| `2026-03-14-search-chain-source-library-mounting-audit` | `external_blocked_candidate` | yes | Search-chain mounting has the no-network governance gate plus deterministic review batches through batch4. Remaining source-library review gaps are public replay, human review, live source collection, and live ingest/external replay. The separate entrypoint-marker follow-up belongs to the agent-batch/process lane, not this source-library review cluster. |
| `2026-03-14-source-library-adapter-capability-remediation` | `external_blocked_candidate` | yes | Historical Wave21 snapshot. Wave49 later closed this topic after a real opt-in 45-site public replay; broader human relevance review remains owned by other source-library promotion topics. |
| `2026-03-25-source-library-ingest-minimal-migration` | `retained_partial` | no | The deterministic review-batch handoff is closed, but the wider topic still carries an in-repo runner capability blocker: `python_library_cli_container_runners_not_enabled`. The external-project checker passes with known gaps, so this topic should stay in `CURRENT_DEV` until the runner scope is either closed or explicitly retired by owner decision. |

## Migration Candidates

Candidate for a later `external_blocked` archive/status pass:

- `2026-03-11-source-library-three-lane-architecture`
- `2026-03-14-search-chain-source-library-mounting-audit`
- `2026-03-14-source-library-adapter-capability-remediation` (moved to `ARCHIVE_CLOSED` by Wave49)

Not moved in this pass:

- `2026-03-25-source-library-ingest-minimal-migration`

Physical directory moves were intentionally skipped because this worktree is not
allowed to edit the top-level shared indexes.

## Cannot-Move Reasons

- `2026-03-25-source-library-ingest-minimal-migration` remains
  `retained_partial`: Wave11 closes the deterministic article-extraction runner
  fixture, but the topic still records `python_library_cli_container_runners_not_enabled`
  and live external-project replay gaps. This is more than a pure public
  replay/human review blocker.
- For the three `external_blocked_candidate` topics, the only reason not to
  move now is integration scope: moving them would require coordinated edits to
  `CURRENT_DEV/INDEX.md`, `development-plans/INDEX.md`, `README.md`, and
  `MERGED_OVERVIEW.md`, which are forbidden in this branch.

## Evidence Readback

- Latest deterministic batch checker:
  `main/backend/scripts/check_source_library_review_closure_batch4.py`
- Latest deterministic batch artifact:
  `development/latest-dev-docs/automation-runs/source-library-review-closure-batch4/2026-05-22/review_batch4.json`
- Batch4 output says:
  - `deterministic_batch4_closed=true`
  - `claims_human_review_complete=false`
  - `claims_public_replay_complete=false`
  - `claims_live_source_collection_complete=false`
  - `claims_live_ingest_migration_complete=false`
  - `shared_indexes_edited=false`
- Retained-partial ingest evidence:
  `../2026-03-25-source-library-ingest-minimal-migration/11_wave11-source-library-extraction-runner-evidence-2026-05-22.md`

## Verification Commands

```bash
PYTHONPATH=main/backend python3.11 main/backend/scripts/check_source_library_review_closure_batch4.py --repo-root .
python3.11 -m pytest -q main/backend/tests/unit/test_source_library_review_closure_batch4_unittest.py
PYTHONPATH=main/backend python3.11 main/backend/scripts/check_source_library_ingest_external_project_contract.py
git diff --check
```
