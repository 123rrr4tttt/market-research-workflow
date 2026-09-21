# Contract 12 supervisor review and bounded return v1

- Date: 2026-09-06
- Decision: `DISPOSITION_INTEGRITY_VERIFIED_ACCEPTANCE_INCOMPLETE`
- Dispatch: `PREPARED_NOT_SENT`
- Executor: reuse `01a074e1-da0d-7a70-9c45-daff7b8bc9ad`
- Supervisor: `01a0748b-be3b-7da2-9cb2-4160756bf10b`

## Verified

Supervisor independently recalculated return.v1.json SHA-256 `7757a5504213aea895b35eb39acbf3ec3d1ceeddbc524d34aebb94c8a7990b1b`, validation SHA-256 `4ecdb79bb21706b6b40ef70d8a710cc696b01244c7e4d7706257ab418fb3f933`, all 18 artifact-manifest member hashes and all 105 changed-path after hashes. All matched. Applying the single proposed process.py text replacement in memory produces `5687389bdad57881a0f96543ba32ac4eaaaeef0f7939f8f7e36e16316ed7ee61` from current `790b6cb90086d6ba1171309e572b7e7be4c906db3705170dbd4a12ca7ea16c63`.

These checks establish byte correspondence, not semantic acceptance or test replay. The retained complete selector remains 55 failed, 1712 passed; the worker explicitly states it was not workflow-equivalent. The 375 focused PASS is a separate scope. Reclassification into 30 missing evidence, 3 source defect, 3 stale semantics and 19 fixture defects is classification of the previous failure set, not a new full-selector result.

## Required bounded corrections

1. Correct process-api behavioral_analysis.query_default in a new version. `get_task_info` still declares `project_key=Query(None, ...)`; direct Python calls receive the Query object, whereas FastAPI resolves request defaults. Do not claim both receive None. Supply executable, isolated before/after evidence of the identity overlay defect and explicit provider task-id precedence, separately from direct-call fixture correctness. The proposed fix remains unintegrated pending exact-binding disposition. Preserve v1 artifacts.
2. Verify the actual historical Stage 2 v3/v4 release candidates and evidence, not Stage 0 completion.v3/v4 files. Read-only checks must bind v3 commit `f8d84afc2784cf91784da957e353e2b0c0d6952c`, tree `1be3dcbc009332ec225297d1b94430862287d816`; v4 commit `e1aa59708a22e4238c4d9beaf7b7bd2d2095d483`, tree `d2003fbb8e54c8dd743fa4e84907a8a978ef5107`; clean tracked/untracked state and contract 10 historical evidence hashes. Report any drift without repair. Do not import candidate code or create caches inside these historical roots.
3. Audit exact binding impacts for all changed runtime/contract/checker files, particularly the eight import-time DB boundary paths. The generic `REVIEW_REQUIRED_BEFORE_ANY_ADDITIVE_REBIND` and an assertion that history was not edited do not establish that current bindings are intact. List each affected current declaration and its old/current hash; separate inherited changes from this task using recorded task-start evidence. HEAD is not a substitute for missing task-start bytes in the dirty checkout.
4. For startup changes already made, provide the focused patch and preservation analysis required by contract 12: FastAPI startup order, Celery/CLI schema initialization, first-operation SQL failure/retry semantics, and concurrent first-use initialization ownership. Use isolated fixtures and actual relevant code; no live DB/network. Treat unproven preservation as an explicit local acceptance gap. Do not revert shared changes automatically or broaden the runtime refactor.
5. For the 30 factual-evidence failures, return a deduplicated claim-level decision table: actual historical receipt needed; fresh local deterministic evidence possible; or live observation required. Name the existing generator, allowed input, expected artifact, status/authority ceiling and dependent nodeids for each fresh-generation proposal. Synthetic validator fixtures may test behavior but cannot satisfy factual acceptance claims. Existing canonical closure/relocation decisions may be consumed with exact provenance; no new canonical status or deleted-file restoration is authorized by this review.

## Return and boundaries

Produce create-only v2 receipts and an updated structured return, retaining the v1 package. Fully distinguish `CORRECTION_REQUIRED`, bounded local repair, evidence-generation proposal and genuinely missing human authority. Keep Stage 1 unaccepted and Phase B/C/v5 gated. Do not rerun the full suite while known factual blockers remain; focused verification of actual corrections is sufficient for this return.

This instruction authorizes the bounded evidence corrections, read-only binding audit and isolated verification above; it does not authorize process.py source mutation, new exact-byte qualification, historical rewrite, deployment, live provider/database, production write, external delivery, canary, cutover, authority transfer, legacy retirement, push, remote mutation, registry write or signing write.

Use the existing task for execution and return. A successful task-message receipt is required before marking this document dispatched.
