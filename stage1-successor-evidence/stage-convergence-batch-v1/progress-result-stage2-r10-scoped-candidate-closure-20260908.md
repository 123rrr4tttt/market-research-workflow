# PROGRESS_RESULT — Stage 2 r10 scoped candidate closure

Status: `PASS_SCOPED_CANDIDATE_CLOSURE_NOT_AUTHORITY`

Observed date: `2026-09-08 Asia/Shanghai`

Scope: local Stage 1/2 successor rehearsal only. This is a scoped progress result, not Stage acceptance, a formal successor designation, publication authority, or production release authorization.

## Consumer-closure repair

- r7 candidate-local joint regression exposed one missing static input: `stage1-successor-evidence/stage2-v6-intake-remediation-v5/stage2-v6-intake-remediation-record.v5.json`.
- The Stage3 v6 remediation checker reads this exact historical record by fixed path and SHA-256, then checks only its schema and non-authority marker. It does not execute the v5 checker or recursively consume the v5 package.
- `scripts/formal_release/source_closure.py` now selects that exact path. It does not allow the entire v5 directory, raw output, cache, runtime, or arbitrary history.
- Two independent read-only audits agreed that this was the only missing path in the actual 269-test and five-successor-checker execution boundary. The five successor bundles' deduplicated static inputs were present `126/126`; Stage3 correction1 members were present `23/23`; correction2 recursive members were present `143/143`.
- Source checkout verification: Ruff passed and the affected four-file suite passed `269` tests.

Source files bound by this repair:

- `scripts/formal_release/source_closure.py`: `b5904cbe7e00596f29e599168cf14f040151235142d73d141a49a912c2608b75`
- `tests/formal_release/test_source_closure.py`: `3c0809dbcfcd686488016708950422a6b209d0513eb921f4f860f89ddb6261ba`
- `scripts/formal_release/materialize_stage2_candidate.py`: `a3de5f49f447f6892aeb9a00d181040e059d13f2a98ac68934d680c78f982f74`
- `tests/formal_release/test_materialize_stage2_candidate.py`: `e248949b8cfdf16daeb8e1f2529f26940864768c4b62215cca52a8190718b1d2`
- `scripts/formal_release/stage2_candidate_intake.py`: `aeaa252acddd20fea0027c5ca4372ad4ac93c52d940a95501fa5f2594ced3a00`
- `tests/formal_release/test_stage2_candidate_intake.py`: `2cada58a4559d8eb96a6e2be799556e6735ffd55a0749f39c54b7df82366819c`

## Preserved diagnostic attempts

- r7 remains the failed candidate with `267 passed / 1 failed`. Its persisted JUnit is `/Users/wangyiliang/.codex/release-rehearsals/mrw-stage2-20260908-v4-r7/evidence/joint-regression-268-r7.junit.xml`, SHA-256 `0de2f0d0c3449a18f10947706018f438fcdedc15f969223750e8b55800b633cb`. Its failure receipt is `/Users/wangyiliang/.codex/release-rehearsals/mrw-stage2-20260908-v4-r7/evidence/joint-regression-268-r7.receipt.json`, SHA-256 `362d9b3409dfda88512aa9b2499a5cb49c7ffc6d9faea852a9312a1f4533859e`.
- r8 is manifest-only and was not materialized. It omitted 34 explicit r7 Stage1 closure bindings when only selector-derived paths were replayed.
- r9 has a correct 7,790-entry manifest but was not materialized. Its initial target setup inherited a shallow marker from the source checkout and failed the full-history precondition.
- None of r7, r8, or r9 was overwritten or promoted.

## r10 candidate identity

- Root: `/Users/wangyiliang/.codex/release-rehearsals/mrw-stage2-20260908-v4-r10/candidate`
- Manifest entries: `7,790`
- Commit: `d3656b0ca7bbe74f0b2f7d2b03aa46b1a9cef452`
- Tree: `317c74501e8636a6d348d065311b51ea1b3984d7`
- Parent/base: `88ffcc3dab2e6cbdc1f389e16c4226df5a2e51c6`
- Full history: `true`
- Checkout: clean
- Manifest SHA-256: `6f67f4fe38300c766cedb3b97867a0ef9debe561f2365c2bae452fc542597c37`
- Materialization receipt SHA-256: `8adc1e9e0f67ddfdf878540aab5303956114f8699a92c4f3c9791dc4f40ec543`
- Selected immutable snapshots: `6,322`; missing `0`, writable `0`, non-regular `0`, bad link count `0`.

The r10 target was cloned locally with `--no-local` from the already full-history r7 candidate, reset to the fixed base, and given the already-bound remote URL without contacting it. No remote fetch, push, registry write, or signing operation occurred.

## Candidate-local validation

- Four-file affected joint regression: `269 passed`, failures `0`, errors `0`, skipped `0`.
- I1 micro specimens: `6 passed`, failures `0`, errors `0`, skipped `0`.
- C2-C9/I1 family candidate checks: all nine returned `CANDIDATE_VALID_NOT_AUTHORITY`.
- Current-byte successor checkers: v1 bindings `PASS`; v2 bindings `PASS`; v3 bindings `PASS`; v3 semantic bindings `PASS`; v4 zero-delta bindings `PASS`.

Evidence:

- Scoped validation receipt: `/Users/wangyiliang/.codex/release-rehearsals/mrw-stage2-20260908-v4-r10/evidence/scoped-validation.r10.json`, SHA-256 `90b2c8f5ef340ec3e647164f8491b4fe57c538a5a5a6c7e483932055541b867b`.
- Joint-regression JUnit: `/Users/wangyiliang/.codex/release-rehearsals/mrw-stage2-20260908-v4-r10/evidence/joint-regression-269-r10.junit.xml`, SHA-256 `c6809430673adc366e5c4f14750b42872b5a50714dc00af902576ae7305794e6`.
- I1 JUnit: `/Users/wangyiliang/.codex/release-rehearsals/mrw-stage2-20260908-v4-r10/evidence/i1-micro-specimens-6-r10.junit.xml`, SHA-256 `22cc8bd0797de8fc1b9be019d5ecc33a5cb2fcf4c3329cb746e85637aedfedad`.

## Remaining independent gaps and ceiling

- DB90 target remains `UNKNOWN`.
- LanceDB native FTS exit `139` remains open.
- Gitleaks findings `343-346` remain open.
- Complete gate inventory remains open.
- No database, container, service, remote, registry, or signing authority was exercised.
- `LOCAL_DEVELOPMENT_ONLY`
- `NOT_AUTHORITY`
- `PRODUCTION_RELEASE_NOT_AUTHORIZED`

This result closes only the scoped r7 consumer-input omission and establishes a candidate-local validation result for r10. It does not establish Stage PASS.
