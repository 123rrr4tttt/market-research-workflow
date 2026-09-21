# Stale status checkers v2 disposition

Date: 2026-09-06

Scope: `check_graph_typed_writing_consumer_status_boundary.py` and
`check_ingest_canary_closure_readiness.py` only. This disposition records the
current status authority used by their v2 contracts. It does not restore,
substitute for, or derive a closure claim from deleted JSON/JSONL evidence.

## Actual canonical decisions

Hashes are SHA-256 over the current checkout bytes.

| Topic | Current decision | SHA-256 | Current semantics |
|---|---|---|---|
| Graph editing and reporting | `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-07-graph-editing-and-reporting/12_wave46-manual-live-audit-closure-2026-05-23.md` | `d1ba3c83015d20ff4f86a6d90e355b506a8871c024736646b4980c065ddb7b95` | Wave46 `closed`; live tenant DB audit boundary closed |
| Typed knowledge organization | `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-07-typed-knowledge-organization/07_wave54-typed-writing-live-closure-2026-05-23.md` | `8e89d0589ccdd9e2a4edb7bd79cfa7641fd28ddc877df78f0925334b9a40fb41` | Wave54 `closed`; live gaps empty |
| Writing Workbench evolution | `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-07-writing-workbench-evolution/08_wave54-typed-writing-live-closure-2026-05-23.md` | `4f5b88a27adfcbac63cc008b277a0810622e9043318dc8afababb31ab4a3498a` | Wave54 `closed`; live gaps empty |
| Consumer-side modularization | `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-14-consumer-side-modularization/09_wave45-manual-live-api-closure-2026-05-23.md` | `266bf08a715d585328dd80dda17f9fef809e06df26b7dcb35340e4872a257097` | Wave45 `closed`; external blocker count zero |
| Ingest platformization assessment | `development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/2026-03-02-ingest-platformization-assessment/10_wave51-non-target-assessment-wrapper-reclassification-2026-05-23.md` | `44f724b61793bb3b9fa4b4288887fc9860bbbbd1390bf753c6211b6a37ce7582` | Wave51 non-target parent wrapper; successor targets own remaining conditions |
| Meaningful ingest guardrails | `development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/2026-03-02-meaningful-ingest-guardrails-plan/13_wave56-strict-promotion-final-gate-2026-05-24.md` | `305b03d206308722bf316224c0a43b56883e3b6e0ae50cf4aca75191a4d277e6` | Wave56 `external_blocked`; production 24h metrics and ops promotion remain open |
| Single URL first ingest | `development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/2026-03-02-single-url-first-ingest-allocation-plan/13_wave57-single-url-external-blocker-closure-2026-05-24.md` | `32f1f4e43b760852b578f2c498b386ed335c77efcd1d3b1201e999a758c42a44` | Wave57 `external_blocked`; explicit live/external conditions remain open |

The four closed topics also require their topic-local `INDEX.md` and the
canonical `docs/development/development-plans/ARCHIVE_CLOSED/INDEX.md` to point
to the listed later closure decision. The ingest topics require the
`ARCHIVE_EXTERNAL_BLOCKED/INDEX.md` current row to point to the Wave51/56/57
decision. `CURRENT_DEV/INDEX.md` is retained only as navigation compatibility;
the three topic directories must remain absent from `CURRENT_DEV`.

## Old expected statements

The v1 graph/typed/writing/consumer checker expected all four topics to have
current status `external_blocked`, treated Wave27 decision files as current
authority, required graph `closure_claim=false` with
`live_tenant_db_audit_open=true`, required typed/writing
`closure_claim_allowed=false` with non-empty live gaps, and required a consumer
live external blocker.

The v1 ingest checker expected all three topic directories to remain under
`CURRENT_DEV`, assigned every topic
`retained_partial_repo_local_blockers_open`, required repo-local blockers to
remain open, and prohibited migration candidates.

## Exact semantic difference

The graph-family v2 contract is a current-authority refinement: Wave27 records
are classified as pre-closure history, while Wave45/46/54 topic indices and
closure documents determine the present `closed` state. It no longer invokes
pre-closure gates without their historical live inputs and therefore does not
turn missing/deleted runtime artifacts into a false present-day blocker.

The ingest v2 contract preserves the still-open external boundary but updates
identity and ownership. Wave51 removes the platformization assessment from the
target set as a duplicate parent wrapper. Wave56 and Wave57 are the current
authorities for the two successor targets, both still `external_blocked` with
explicit external conditions. Wave27 and the old CURRENT_DEV placement are
history/navigation, not current state.

No deleted JSON or JSONL artifact is read, reconstructed, or replaced by prose.
The v2 checkers validate the canonical decision files and index ownership only;
they do not claim to replay the historical live runs described by those files.

## R100 lineage

Commit `8eda6ef85166729c74ede16a8eab29d3c36012d9`
(`feat: close wave29 current-dev blockers`) records 100-percent-similarity
renames of all three ingest topic files from `CURRENT_DEV` to
`ARCHIVE_EXTERNAL_BLOCKED`. Later Wave51/56/57 decisions refine status and
target ownership in that migrated location. Consequently an assertion that the
topic directories still exist under `CURRENT_DEV` is historically false even
when a compatibility navigation row remains there.

## Version classification and alternatives

Classification: **schema and semantic refinement with an intentional contract
version change**, from
`graph_typed_writing_consumer.status_boundary.v1` to `.v2` and from
`ingest.canary_closure_readiness.v1` to `.v2`. The report shapes change because
the former fields encode obsolete authority and cannot be truthfully preserved
as aliases.

Rejected alternatives:

- Path-only replacement: rejected because it would preserve the false Wave27
  status assertions after resolving newer files.
- Restore missing JSON/JSONL evidence: rejected because deletion is part of the
  current checkout and historical runtime evidence cannot be fabricated.
- Keep v1 fields with inverted meanings: rejected because consumers could read
  old names such as `remaining_live_gaps` or `recommended_location=CURRENT_DEV`
  as the former contract.
- Mark every ingest topic closed: rejected because Wave56 and Wave57 explicitly
  retain external/live conditions and `closure_claim=false`.

## Focused validation

Executed in the current checkout:

```text
PYTHONPATH=src:main/backend main/backend/.venv311/bin/python -m pytest -q main/backend/tests/unit/test_graph_typed_writing_consumer_status_boundary_unittest.py main/backend/tests/unit/test_ingest_canary_closure_readiness_unittest.py main/backend/tests/functorial_debt/test_c13_cli_graph_workflow_metadata.py
.......                                                                  [100%]
7 passed in 0.26s
```

Both checker CLIs returned `PASSED`. Ruff, Python `compileall`, and scoped
`git diff --check` also passed on the final file state.
