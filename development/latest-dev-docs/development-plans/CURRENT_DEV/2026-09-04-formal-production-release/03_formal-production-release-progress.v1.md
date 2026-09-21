# MRW Formal Production Release Progress (v1)

- Status: `ACTIVE_MUTABLE_PROGRESS · NOT_AUTHORITY`
- Date: `2026-09-04`
- Frozen plan: `00_formal-production-release-development-plan.v1.md`
- Frozen gap ledger: `01_formal-production-release-gap-ledger.v1.json`
- Freeze manifest: `02_formal-production-release-development.freeze.v1.json`

## Current state

```text
R0_FREEZE_AND_CONCURRENCY_FENCE: COMPLETE
R0B_SHARED_PREFLIGHT_SUBSTRATE: COMPLETE
R1_CANDIDATE_IDENTITY_PREFLIGHT: COMPLETE
R2_RELEASE_EVIDENCE_VALIDATOR: COMPLETE
R3_STATIC_PRODUCTION_CONTRACT_PREFLIGHT: COMPLETE
R4_CI_RELEASE_GATE_WIRING: NOT_STARTED
R5_REPRODUCIBLE_IMAGE_BUILD: NOT_STARTED
R6_PRODUCTION_AUTHORITY_RUNTIME: NOT_AUTHORIZED
R7_OBSERVABILITY_CANARY: NOT_STARTED
R8_RECOVERY_DRILL: BLOCKED_BY_ENVIRONMENT_AND_AUTHORITY
R9_QUALIFICATION_PROMOTION: NOT_AUTHORIZED
```

## Authority ceiling

This progress file is mutable but non-authoritative. No entry in it may authorize candidate promotion, production canonical write, live provider, external delivery, cutover, authority transfer, credential creation, deployment, or legacy retirement.

## Package ledger

| Package | State | Changed files | Verification | Remaining risk |
| --- | --- | --- | --- | --- |
| R0 | COMPLETE | Plan, gap ledger, freeze manifest, progress | `freeze-exact-check: PASS`; JSON parse and `git diff --check` pass | Frozen bytes do not grant release authority |
| R0-B | COMPLETE | `scripts/formal_release/model.py`; `tests/formal_release/test_model.py` | `10 passed in 0.01s`; compile and diff check pass | Shared output remains a derived preflight |
| R1 | COMPLETE | `scripts/formal_release/check_candidate_identity.py`; focused test | Included in `38 passed, 7 subtests passed`; direct CLI works in root `.venv` and backend `.venv311`; live checkout correctly returns `FAIL` | Does not create a clean candidate; live snapshot had 528 tracked and 227 untracked status entries |
| R2 | COMPLETE | `scripts/formal_release/check_release_evidence.py`; focused test | Included in `38 passed, 7 subtests passed`; direct CLI help works in both repository Python environments | No exact release-evidence manifest has yet been authored for a clean candidate; the validator cannot grant authority |
| R3 | COMPLETE | `scripts/formal_release/check_static_production_contract.py`; focused test | Included in `38 passed, 7 subtests passed`; direct CLI works in both repository Python environments; live checkout correctly returns `FAIL` | Static findings do not prove an external runtime or remotely configured branch protection |

## First-wave integration evidence

Snapshot date: `2026-09-04`. The source task remained active while this snapshot was taken, so mutable worktree and baseline counts must be re-observed before any later promotion decision.

```text
focused_command=main/backend/.venv311/bin/python -m pytest -q tests/formal_release
exact_result=38 passed, 7 subtests passed in 2.43s

compile_command=main/backend/.venv311/bin/python -m py_compile scripts/formal_release/*.py tests/formal_release/*.py
exact_result=PASS

direct_cli_matrix=.venv/bin/python + main/backend/.venv311/bin/python across R1/R2/R3 --help
exact_result=6/6 PASS

architecture_command=PYTHONPATH=/Users/wangyiliang/Desktop/functorial-kit/python:/Users/wangyiliang/market-research-workflow/src python3.11 -m pytest tests/test_architecture.py -q
exact_result=268 passed in 1.77s
release_lane_new_architecture_findings=0

freeze_exact_check=PASS
plan_sha256=97801ddbe46233429309f218cfcb183ade785ffd1a2d0872223907851ca95087
gap_ledger_sha256=21df93d7c9dc1ac3cc77a9a449f3c37527001f0716551ce34db032c7c93754a0
json_parse=PASS
git_diff_check_scoped=PASS
```

## Live negative preflight snapshot

R1 was run against `HEAD=3706655f372f6d34fc62683551b8c3d1f4ff8146` and tree `5840bf9ba906c49f70020d226c54446f4ba5aa33` using `REMEDIATION_INCLUSIVE_RELEASE`. Commit and tree matched, but candidate identity correctly failed closed:

```text
candidate.dirty_tracked=FAIL (528 status entries)
candidate.untracked=FAIL (227 status entries)
candidate_cli_exit=1
origin_main_ahead=21 commits
```

R3 was run against the live checkout and correctly returned `FAIL` with exit code `1`. Observed failing families were:

```text
compose.latest_image_tags
database.default_credentials
compose.elasticsearch_security
compose.public_ports
pyproject.file_dependency
pyproject.root_version
frontend.version_alignment
branch_protection.required_checks
artifact_metadata.immutable_release
```

`workflow.security_scans=PASS` means only that the checked workflow text contains Bandit, `pip-audit`, and gitleaks declarations. It does not establish that they ran on an exact candidate or are required by live remote branch protection.

## Claim ceiling after first wave

```text
FORMAL_RELEASE_GAP_MODEL_FROZEN
DETERMINISTIC_PREFLIGHT_FIRST_WAVE_IMPLEMENTED
PRODUCTION_RELEASE_NOT_AUTHORIZED
```

Remaining ordered work is R4 required-CI convergence, R5 reproducible immutable artifacts, R6 authority/runtime closure, R7 observability and canary, R8 recovery drill, and R9 exact-candidate qualification/promotion. Historical candidate or runtime evidence remains non-transferable until rebound to the remediation-inclusive candidate bytes.

Rollback route for R0-B through R3 is deletion of only `scripts/formal_release/` and `tests/formal_release/` plus this mutable progress entry. Frozen plan and gap-ledger bytes remain unchanged.

## Required update fields

Each completed package appends:

```text
package
changed_files
focused_command
exact_result
claim_ceiling
remaining_gaps
rollback_route
```

## 2026-09-06 Stage 1/2 successor convergence

```text
package=STAGE_1_SOURCE_STATIC_CLOSURE_AND_STAGE_2_V5_SUCCESSOR
stage1_result=PASS_SOURCE_STATIC_NOT_AUTHORITY
stage2_result=REBUILD_REQUIRED_AGAIN
candidate_root=/Users/wangyiliang/.codex/release-candidates/mrw-stage2-20260906-v5
candidate_commit=fa650d46e2bc16ff1258fb27d3545e8568037dab
candidate_tree=1025e121a23adfdb174fe358274748aa5e393c0f
manifest_entries=6462
primary_replay=PASS_IDENTICAL_COMMIT_TREE
r1=PASS
r2=PASS_SYNTHETIC_VALIDATOR_CONFORMANCE_ONLY
r3=PASS_15_FINDINGS
candidate_backend_selector=FAIL_COLLECTION_226_ERRORS_0_FAILURES_1_SKIPPED_872_DESELECTED
closure_receipt=/Users/wangyiliang/.codex/release-evidence/mrw-stage2-20260906-v5/closure.rebuild-required.v5.json
closure_sha256=0a3847f54a5c5fe3207f101d6e06fe0b30dad2a7f785e1733a39119b8a1d89e7
claim_ceiling=REBUILD_REQUIRED_AGAIN_NOT_AUTHORITY
remaining_gaps=V5_CANDIDATE_BYTE_IMPORT_GRAPH_INCOMPLETE;STAGE3_NOT_REDISPATCHABLE;PRODUCTION_RELEASE_NOT_AUTHORIZED
rollback_route=retain_v5_as_failed_create_only_history;authorize_new_successor_target;broaden_projected_source_closure;rerun_candidate_local_selector
```

The v5 candidate is exact, clean, non-shallow and reproducible, but it is not
workflow-equivalent to the current source checkout. The candidate-local selector
found 226 collection errors grouped under missing or stale candidate bytes; the
largest groups are the stale runtime failure-policy edge (148) and crawler base
contract (39). Static R1/R3 success and deterministic replay therefore do not
qualify the candidate. No Stage 3, deployment, live action, registry/signing
write, push, canary, cutover or authority transfer is authorized.

## 2026-09-06 Stage 1/2 v6 final successor closure

```text
package=STAGE_1_SOURCE_STATIC_CLOSURE_AND_STAGE_2_V6_SUCCESSOR
changed_files=mutable_progress_append_only;create_only_/Users/wangyiliang/.codex/release-evidence/mrw-stage2-20260906-v6/closure.final.v6.json
focused_command=tests/formal_release source+intake focused suite;ruff;compileall;full required selector on source,v6 primary,v6 replay;manifest validation;R1/R2/R3;historical v3/v4/v5 read-only identity/fsck
exact_result=139 focused passed;source selector 1793 passed,2329 deselected,25 warnings,52 subtests passed,0 skipped;v6 primary selector identical;v6 replay selector identical;manifest 7354 entries (7001 UPSERT,353 DELETE);R1 PASS;R2 PASS synthetic-validator-conformance-only authoritative=false;R3 PASS 15 findings
candidate_root=/Users/wangyiliang/.codex/release-candidates/mrw-stage2-20260906-v6
candidate_commit=909eb608e538b6427bcbacca974f1efb05fef611
candidate_tree=a60b795e509aa5dc479904a321fba32ed0ab9ab2
candidate_base=88ffcc3dab2e6cbdc1f389e16c4226df5a2e51c6
manifest_path=/Users/wangyiliang/.codex/release-evidence/mrw-stage2-20260906-v6/candidate-manifest.v6.json
manifest_sha256=020ea3fe312fe5a21f5c064455fc7e2fb1d53440ca0a2dfa9bf115777c80ece1
closure_path=/Users/wangyiliang/.codex/release-evidence/mrw-stage2-20260906-v6/closure.final.v6.json
closure_sha256=d2f0607fbf29422f78887c5c72ac17af2d867e719044fa03a545ba19a1e30e73
stage1_result=PASS_SOURCE_AND_STATIC_CLOSURE_NOT_AUTHORITY
stage2_result=PASS_EXACT_V6_SUCCESSOR_NOT_AUTHORITY
historical_v3_v4_v5=PASS_CLEAN_IDENTITIES_AND_FROZEN_HASHES_UNCHANGED
claim_ceiling=PASS_STAGE1_STAGE2_V6_NOT_AUTHORITY;PRODUCTION_RELEASE_NOT_AUTHORIZED
remaining_gaps=SUPERVISOR_INDEPENDENT_ACCEPTANCE;STAGE3_NEW_V6_BOUND_CONTRACT_NOT_YET_AUTHORIZED;STAGE4_UNADMITTED;NO_LIVE_OR_PRODUCTION_AUTHORITY
rollback_route=retain_v3_v4_v5_and_v6_create_only_evidence;remove_only_this_mutable_progress_entry_if_correcting_the_ledger;never_rewrite_candidate_or_frozen_receipts
```

The accepted candidate-local gate is
`candidate-selector.no-network-final.v6.{log,xml}`. The earlier unrestricted
26-failure run and workspace-sandbox 2-failure run remain retained as
diagnostic history and are not treated as the accepted gate. The v6 candidate
is clean, detached, non-shallow, has no alternates, passes `git fsck`, shares
zero object inodes with v5, and its independently materialized replay produced
the same commit/tree and the same complete selector result. This closes Stage
1/2 execution only; it grants no Stage 3 result, deployment, live action,
production write, registry/signing write, push, canary, cutover, authority
transfer, or legacy retirement.

## 2026-09-12 Stage 3 r13v local reconciliation

2026-09-13 执行纠偏：以下是历史结果快照；其中 `rollback_route` 的“任何构建输入或 Dockerfile 变化创建 successor”不再作为普通开发前置条件。强制执行 [19 号流程缩减规则](19_direct-testing-batch-freeze-amendment.v1.md)：直接修复、最小相关验证、保留待验制品，稳定后仅按真实交付需要统一封存。当前规则和待落地范围见 [06 进度文档](06_production-deployment-stage-progress.v1.md)的 2026-09-13 条目；本次文档修订不建立新测试或阶段 PASS。

```text
package=STAGE_3_R13V_LOCAL_RECONCILIATION
changed_files=stage3-evidence/r13v security+artifact+stage-result;manifest/r13v preflight+gap-map;mutable_contract_and_progress
focused_command=exact r13v affected selectors;exact Gitleaks disposition;seed exact-byte verification;linux/amd64 backend and migration candidate/replay build comparison;R2 validator
exact_result=107 passed;Gitleaks 417 raw/403 stable/369 context FP/34 exact snapshot exceptions/0 unresolved;seed 12 tests plus disposable PostgreSQL load PASS;same-window backend and migration manifest/config/ordered layers equal;cross-time recovery rebuild digests drifted;exact-digest Trivy NOT_RUN;R2 1 PASS/5 BLOCKED/4 UNEXECUTED/0 FAIL
candidate_root=/Users/wangyiliang/.codex/release-rehearsals/mrw-stage2-20260912-v4-r13v
candidate_commit=8427e3d626cd12f41e45d38e00223f2ef86d692f
candidate_tree=4146bcab51e437920a006875e06ed8cdcc32470a
stage3_result=REBUILD_REQUIRED
claim_ceiling=LOCAL_SCOPED_EVIDENCE_NOT_AUTHORITY;PRODUCTION_RELEASE_NOT_AUTHORIZED
remaining_gaps=FREEZE_OR_IDENTIFY_APT_PIP_BUILD_INPUTS;ATTESTATION_STATEMENT_SUBJECT_BINDING;EXACT_DIGEST_TRIVY_AND_THRESHOLD;OPENAI_API_KEY;REMOTE_EXACT_SHA_CHECKS_AND_ENFORCEMENT;REGISTRY_IMMUTABILITY;SIGNING_AND_TRANSPARENCY;ACTUAL_RELEASE_MANIFEST_R2
rollback_route=retain_r13v_and_failed_attempt_evidence;create_a_new_stage1_stage2_successor_for_any build-input or Dockerfile change;never modify frozen r13v in place
```

The incorrect retry4 aggregate claim `TRIVY_GATE_PASSED` is superseded by
`stage3-evidence/r13v/artifacts/backend-migration-amd64-final/result.json`.
The raw role evidence was `NOT_RUN`, and recovery images drifted before they
could be bound to the retry4 exact digests. No release manifest was generated,
and no push, workflow dispatch, ruleset mutation, registry/signing write,
deployment, production write, or Stage 4 admission occurred.
