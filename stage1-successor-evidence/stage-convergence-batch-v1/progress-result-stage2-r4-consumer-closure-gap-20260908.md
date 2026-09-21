# PROGRESS_RESULT — Stage 2 r4 consumer-closure gap

Status: `RUNTIME_MODE_FIXED_BUT_CONSUMER_CLOSURE_FAILED`

Observed date: `2026-09-08 Asia/Shanghai`

Scope: local Stage 1/2 successor rehearsal only. This record is mutable progress evidence, not a release candidate acceptance record and not authority.

## Source repair now present

- Materializer: `scripts/formal_release/materialize_stage2_candidate.py`
- Materializer SHA-256: `a3de5f49f447f6892aeb9a00d181040e059d13f2a98ac68934d680c78f982f74`
- Focused tests: `tests/formal_release/test_materialize_stage2_candidate.py`
- Focused-test file SHA-256: `e248949b8cfdf16daeb8e1f2529f26940864768c4b62215cca52a8190718b1d2`
- Repair: after final checkout/reset and before candidate clean/tree validation, restore manifest-selected Stage0/Stage1 `snapshots/*` regular, single-link files to mode `0444` through a constrained dirfd open using `O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC` where available.
- Failure behavior: a restore failure enters the existing post-CAS ref/checkout/object rollback.
- Verification: Ruff passed; the source-checkout materializer suite passed `61` tests, including success restoration, scope limitation, non-blocking FIFO rejection, and rollback after restore failure.

## Preserved failed rehearsals

- r2: `/Users/wangyiliang/.codex/release-rehearsals/mrw-stage2-20260908-v4-r2`; diagnostic failure because all `6,318` selected snapshots were materialized as writable `0644`.
- r3: `/Users/wangyiliang/.codex/release-rehearsals/mrw-stage2-20260908-v4-r3`; manifest-only attempt invalidated before materialization by the later FIFO-race hardening.
- r4: `/Users/wangyiliang/.codex/release-rehearsals/mrw-stage2-20260908-v4-r4`; retained unchanged as the first runtime-mode-fixed rehearsal that exposes the next projection defect.

## r4 identity and checks

- Manifest SHA-256: `7f514ec746a6d735057a32f973e06eec67ccc7952dc48788900226ea67299529`
- Manifest entries: `7,748`
- Commit: `f07280bc58fab0d3835739a2f4839e3816e8388c`
- Tree: `6bfb4fb59f8882982a4616ff81c325ac39161ba4`
- Parent/base: `88ffcc3dab2e6cbdc1f389e16c4226df5a2e51c6`
- Materialization receipt SHA-256: `8428aca784713124e3337e0ed8691f3eb18f007a8569a17d34b1acf461e0ff3a`
- Selected immutable snapshots: `6,318`; missing `0`, writable `0`, non-regular `0`, bad nlink `0`.
- Candidate checkout: clean.
- C2-C9/I1 family checkers: all reported `CANDIDATE_VALID_NOT_AUTHORITY`.
- Candidate materializer suite: `61 passed` with `PYTHONPATH=<candidate>/main/backend`.

## Current candidate-shaped failure

The I1 consumer test failed:

```text
main/backend/tests/successor_runtime/test_i1_micro_specimens.py::test_i1_current_successor_is_live_and_frozen_candidates_are_history_only
FileNotFoundError: stage1-successor-evidence/current-byte-remediation-v1/bindings/artifact-manifest.v1.json
```

This is not a regression in the runtime-mode repair. The Stage 2 manifest omits a transitively required predecessor-bundle member in the current-byte remediation chain. The selector, not the r4 candidate, must be corrected. The next candidate must be a create-only r5/rN with a new manifest and a new full-history target.

## Remaining boundaries

- r2, r3, and r4 must not be overwritten, promoted, or presented as the formal successor.
- LanceDB native FTS exit `139` remains independent.
- Gitleaks findings `343-346` remain independent.
- DB90 target remains `UNKNOWN`.
- Complete gate inventory remains open.
- `LOCAL_DEVELOPMENT_ONLY`
- `NOT_AUTHORITY`
- `PRODUCTION_RELEASE_NOT_AUTHORIZED`

