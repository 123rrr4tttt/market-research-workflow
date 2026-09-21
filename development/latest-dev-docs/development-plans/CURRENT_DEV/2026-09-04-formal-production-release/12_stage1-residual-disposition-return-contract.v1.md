# Stage 1 residual disposition return contract v1

- Date: 2026-09-06
- Status: `READY_FOR_DISPATCH_NOT_AUTHORITY`
- Executor: reuse `01a074e1-da0d-7a70-9c45-daff7b8bc9ad`
- Supervisor: `01a0748b-be3b-7da2-9cb2-4160756bf10b`
- Scope: complete the residual disposition required by contracts 10/11; Stage 1 remains unaccepted.

## Verified input

Worker returned `BLOCKED`, with 55 failed, 1712 passed, 0 skipped, 2328 deselected, 14 warnings, 42 subtests passed. Supervisor independently recomputed both hashes and parsed JUnit: 1809 test records including subtests, 55 failures, 0 errors, 0 skipped. The log and JUnit are:

- `/private/tmp/mrw-stage12-v5-backend-final.4e2HdA/backend-unit-final.log`: `33d48a566619950f40125467c5a5a53f728b2bb76f9e28b44a5eb14894c10397`
- `/private/tmp/mrw-stage12-v5-backend-final.4e2HdA/backend-unit-final.xml`: `e07c7ae3322bfd3c77e18b47fefce67f82db8e0517640a81b6db22ac2272bb94`

This verifies a completed failing execution. It does not independently accept every implementation change, the full effect inventory, history integrity, or workflow equivalence. The four reported blocker categories remain bounded Stage 1 gaps, not a global failure of all completed work.

## 1. Complete the auditable return

Create additive receipts under `stage1-successor-evidence/residual-disposition-v1/`. Preserve the prior raw log/XML and their hashes using create-only copies or the existing create-only evidence writer; never overwrite an existing receipt. Provide JSON with exact changed paths, before/after hashes where recorded, ownership, reason, focused command/result, and frozen-binding impact. A prose list such as “A1 isolation” is insufficient for path-level acceptance.

Produce a deterministic 55-nodeid inventory from JUnit, one owner and primary cause per failure, with shared causes grouped by actual input path. Check uniqueness, totals, parseability, and references before hashing. Distinguish missing evidence, stale expected semantics, source defects, and test fixture defects. Treat proposed classification as provisional until its underlying evidence is provided.

## 2. Process API and binding disposition

Supervisor verified `main/backend/app/api/process.py` currently hashes to `790b6cb90086d6ba1171309e572b7e7be4c906db3705170dbd4a12ca7ea16c63`. Worker proposed `5687389bdad57881a0f96543ba32ac4eaaaeef0f7939f8f7e36e16316ed7ee61`, but has not supplied the patch in this return.

Provide the exact proposed patch as an additive review artifact; identify every affected B23 source/test binding and the current binding declaration. Explain separately the direct-call `Query` default and the `{**task_info, **runtime_projection}` overlay behavior, using focused evidence. Determine whether a correct isolated test invocation suffices or an observable production defect exists. Do not weaken assertions or freeze an incorrect identity. Provide before/after observations and the smallest proposed successor/rebind operation. A target hash alone is not rebind approval. Historical candidate/fragment/snapshot bytes remain immutable.

## 3. Missing evidence and stale semantics

For each unique missing evidence source provide old path, dependent nodeids, required factual claim, bounded current-source search result, and available provenance. HEAD blobs establish historical identity only; do not restore user-deleted artifacts to their old paths.

Separate deterministic validator behavior that can be tested using explicitly synthetic fixtures from acceptance assertions that require actual recorded history/current evidence. Existing fixture-focused repairs are allowed only when the original claim remains tested; missing factual evidence must continue to fail explicitly. Do not replace a historical/live receipt with a synthetic record and call the acceptance gate closed.

For the graph/typed/writing/consumer and ingest-canary groups, provide the actual current canonical decision and R100 lineage with hashes, the old expected statements, and the exact semantic difference. Derive proposed versioned successor contracts only from existing authorized decisions. A currently failing assertion is not itself permission to invent a new canonical status. Where a human decision is genuinely missing, state that decision and its concrete alternatives in the return. Otherwise prepare the additive contract and focused validation within the authorized remediation scope.

## 4. Import-time database effect

Provide the exact import/stack, attempted schema action, configuration and test owner. Permission denial is not effect isolation. First identify the existing test fixture/startup hook that should own this effect and propose the minimum correction. Test fixture fixes that preserve production startup semantics may proceed under contract 11. Moving production schema bootstrap or changing startup ordering requires a concrete patch and preservation/recovery analysis before integration; do not perform broad startup refactoring based on the failure label alone.

Use isolated fixtures with fail-fast network/DB guards for diagnostics. Do not contact the user's existing database, start live services, or repeatedly rerun an import known to attempt those effects.

## 5. Verification, order and handoff

Independent work packages may proceed concurrently with explicit file ownership; current binding decisions and final integration remain sequential. Reuse existing implementations and tests. Run focused checks for actual changes. The next full selector is justified only after its known causes and import effect are resolved; retain all failures and do not shrink its marker/path scope.

Return `RETURN_RESULT` using contract 10 plus the exact residual inventory, patch proposals, provenance mapping, semantic decisions, effects receipt, and changed-path hashes. Continue already-authorized independent fixes while preparing these artifacts. Do not claim full Stage 1 PASS until contracts 10/11 acceptance holds. Phase B/C and v5 remain gated by Phase A. Stage 3 is resumed only after v5 independent acceptance; Stage 4 remains unadmitted.

Preserve contracts 00–12, v3/v4, all historical records and user changes. No commit/reset/clean/stash/push, remote mutation, registry/signing write, deployment, live provider, production write, external delivery, canary, cutover, authority transfer, or legacy retirement.

Send the structured return to Supervisor in the same task. All further Stage 1/2 remediation reuses this executor; Stage 3 reuses `01a074c0-5786-7121-8a0b-ffef1e32a2a9`. This document is prepared locally; dispatch must be confirmed separately through a successful task-message tool receipt.
