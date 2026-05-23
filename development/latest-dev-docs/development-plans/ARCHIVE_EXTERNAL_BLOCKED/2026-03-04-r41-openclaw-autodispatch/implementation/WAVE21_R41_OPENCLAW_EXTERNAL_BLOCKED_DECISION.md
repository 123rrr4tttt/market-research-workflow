# Wave21 R41 OpenClaw External Blocked Decision

Date: 2026-05-22
Scope: `2026-03-04-r41-openclaw-autodispatch`

## Decision

`2026-03-04-r41-openclaw-autodispatch` should move out of active
`CURRENT_DEV` tracking as `external_blocked`.

The repo-local work is sealed enough for a migration decision:

- `decision`: `move_to_external_blocked_recommended`
- `current_repo_status`: `local_mirror_passed`
- `remaining_status`: `external_runtime_unverified`
- `closure_claim_allowed`: `false`
- `extra_repo_local_gate_recommended`: `false`

Do not add another small repo-local gate for this topic. Wave20 already
read back the mirror/runtime handoff manifest and proves that all governed
repo artifacts are present. Another local-only gate would restate the same
boundary without proving the external OpenClaw runtime.

This branch intentionally does not move the directory or edit shared indexes.
Those changes belong to a later supervisor/integration migration lane.

## External Conditions

The only remaining condition is outside this repository:

1. Run a fresh R41 OpenClaw runtime/autodispatch invocation in the OpenClaw
   workspace, currently referenced as `/Users/wangyiliang/Desktop/openclaw`.
2. Preserve the run-state artifact produced by that invocation and copy the
   governed evidence into the repo-controlled evidence path.
3. Add or run a separate checker that proves the live OpenClaw run artifact
   before any closure claim.

Until those conditions exist, the topic must not be marked closed or archived
as internally complete. The correct state is `external_blocked`.

## Repo-Sealed Evidence

Wave12 sealed the repo-local autodispatch mirror boundary:

- `implementation/WAVE12_R41_OPENCLAW_AUTODISPATCH_GATE_EVIDENCE.md`
- The mirrored R41 state remains skipped/no-op and does not claim external
  OpenClaw execution.

Wave15 sealed the repo-local runtime handoff boundary:

- `implementation/WAVE15_R41_OPENCLAW_RUNTIME_HANDOFF_EVIDENCE.md`
- Observed evidence records
  `repo_local_handoff_mirror_consistent=true`,
  `mirror_line_rows=6`, `handoff_tasks=12`,
  `implementation_docs=3`, `reference_files=11`,
  `external_openclaw_runtime_live_verified=false`, and
  `external_runtime_checked=false`.

Wave20 sealed the mirror/runtime manifest readback boundary:

- `implementation/WAVE20_R41_OPENCLAW_MIRROR_READBACK_EVIDENCE.md`
- Automation run:
  `development/latest-dev-docs/automation-runs/wave20-openclaw-mirror-readback/2026-05-22/`
- Manifest readback records
  `status=passed`, `local_mirror_status=local_mirror_passed`,
  `missing_artifact_count=0`,
  `external_runtime_status=external_runtime_unverified`, and
  `closure_claim_allowed=false`.
- The readback table covers A-F handoff rows and all required mirror,
  reference-pool, implementation, and evidence artifacts without
  `missing_artifact`.

Current Wave21 validation re-ran the Wave20 gate and unit test. Condensed
output:

```text
python3 scripts/checkers/check_r41_openclaw_mirror_runtime_manifest_readback.py
{"contract_version": "wave20-openclaw-mirror-runtime-readback.v1", "external_runtime_status": "external_runtime_unverified", "local_mirror_status": "local_mirror_passed", "missing_artifact_count": 0, "out_dir": "development/latest-dev-docs/automation-runs/wave20-openclaw-mirror-readback/2026-05-22", "status": "passed"}

python3 -m unittest tests.checkers.test_check_r41_openclaw_mirror_runtime_manifest_readback_unittest
Ran 3 tests
OK
```

## Recommended Migration Path

Use a supervisor/integration lane to perform the actual migration:

1. Move the topic from
   `development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/2026-03-04-r41-openclaw-autodispatch/`
   to the canonical external-blocked holding area. If the taxonomy needs a
   physical directory, use:
   `development/latest-dev-docs/development-plans/EXTERNAL_BLOCKED/2026-03-04-r41-openclaw-autodispatch/`.
2. Update shared navigation and status surfaces in the same migration commit,
   including `CURRENT_DEV/INDEX.md`, `STATUS_AUDIT_2026-04-07.md`,
   `development-plans/INDEX.md`, `development/latest-dev-docs/README.md`, and
   `development/latest-dev-docs/MERGED_OVERVIEW.md`.
3. Keep this Wave21 decision document with the migrated topic so the migration
   has a local evidence trail.
4. Update checker invocation paths after the physical move. Either pass
   `--topic` to
   `scripts/checkers/check_r41_openclaw_mirror_runtime_manifest_readback.py`
   or revise the checker default in that integration lane.
5. Do not move to `ARCHIVE_CLOSED` unless the external runtime evidence above
   is added and verified.

The intended post-migration status is `external_blocked`, not `closed`.
