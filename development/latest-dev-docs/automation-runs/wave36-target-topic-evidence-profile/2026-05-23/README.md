# Wave36 Target Topic Evidence Profile

Date: 2026-05-23 PST

## Purpose

This run changes the development-docs closure metric from "all folders need closure" to a target-topic allowlist model.

Four directory roles are separated:

- real development target topics: `CURRENT_DEV`, `ARCHIVE_CLOSED`, `ARCHIVE_EXTERNAL_BLOCKED`, and `ARCHIVE_RETIRED` topics that need status, evidence, gates, and remaining blockers.
- evidence/process records: wave records, process records, and automation-run materials that need correct references, not topic-level closure.
- navigation/category directories: `A_ARCHITECTURE`, `B_API`, `C_INGEST`, `D_TEST`, `E_OPS`, `F_PLAN`, `G_REVIEW`, and `main`; these need navigation consistency, not closure.
- external/reference material: reference repos and third-party snapshots; these are excluded from development-plan landing metrics.

## Current Matrix

Source of truth: `development/latest-dev-docs/development-plans/TARGET_TOPIC_ALLOWLIST.json`.

| Metric | Value |
|---|---:|
| `CURRENT_DEV` `partial` | 0 |
| `CURRENT_DEV` `not_closed` | 0 |
| `CURRENT_DEV` `no_closure_claim` | 0 |
| Target topics | 61 |
| `closed` target topics | 26 |
| `external_blocked` target topics | 29 |
| `retired` target topics | 6 |
| `active_current` target topics | 0 |
| Non-target roots | 17 |
| Evidence roots | 2 |
| Evidence profiles | 61 |
| Checker problems | 0 |

## Classification Changes

Seven historical process/material directories were removed from the target-topic count and kept as non-target roots:

- `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-03-version-A-doc-normalization`
- `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-03-version-B-doc-normalization`
- `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-03-version-D-doc-normalization`
- `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-03-version-E-doc-normalization`
- `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-03-version-F-doc-normalization`
- `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-04-r8-c-minimal-slice`
- `docs/development/development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration-process-records`

`ARCHIVE_EXTERNAL_BLOCKED/MERGED_OVERVIEW` stays in the target-topic allowlist because it is a topic-local RAG/current-vector drift gate, not the top-level navigation overview.

## Gate Changes

`scripts/checkers/check_development_plans_status_matrix.py` now emits `target_profiles` and enforces evidence presence for target topics:

- code reference signal
- script reference signal
- test reference signal
- gate/readback/validation signal
- external-blocker signal for `external_blocked` topics

The checker also consumes `reference_excludes` from the allowlist so embedded reference repositories do not inflate target evidence or link metrics.

Focused unit coverage lives in `tests/checkers/test_check_development_plans_status_matrix_unittest.py`.

## Directory Entry Updates

Four Wave27 external-blocked true target topics now have canonical directory entries:

- `development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/2026-03-07-graph-editing-and-reporting/INDEX.md`
- `development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/2026-03-07-typed-knowledge-organization/INDEX.md`
- `development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/2026-03-07-writing-workbench-evolution/INDEX.md`
- `development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/2026-03-14-consumer-side-modularization/INDEX.md`

These are target-topic entrypoints, not a blanket rule that every process/material folder needs an `INDEX.md`.

## Subagent Closure

Nine subagents were used for the target/non-target audit and all were closed after their outputs were integrated.

## Validation

```bash
/Users/wangyiliang/.local/bin/python3.11 scripts/checkers/check_development_plans_status_matrix.py --root . --json
```

Observed summary:

```text
status=passed
current_dev_counts={'partial': 0, 'not_closed': 0, 'no_closure_claim': 0}
target_status_counts={'external_blocked': 29, 'retired': 6, 'closed': 26}
targets=61
target_profiles=61
non_target_roots=17
evidence_roots=2
problems=0
```

Full final validation for this wave also reruns py_compile, focused pytest, current-dev status evidence, latest-dev-docs structure links, and `git diff --check`.
