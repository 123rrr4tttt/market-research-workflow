# Stage 1 local evidence execution contract v1

- Date: 2026-09-06
- Status: `READY_FOR_DISPATCH_NOT_AUTHORITY`
- Executor: reuse `01a074e1-da0d-7a70-9c45-daff7b8bc9ad`
- Supervisor: `01a0748b-be3b-7da2-9cb2-4160756bf10b`
- Input return: `stage1-successor-evidence/contract13-bounded-corrections-v2/return.v2.json`
- Input SHA-256: `0b9dda0595b84176bd38c60b69030b930a128146c98a8da893ce4aec897b1bbc`
- Claim table SHA-256: `8362b368b5f4d944bb1bddf70f397e73c1b3716bc0bdb6244e61699b38e719b3`

## Supervisor disposition

The return and validation hashes match; all 32 artifact-manifest member hashes independently match. The bounded v2 disposition is accepted as a work inventory, not Stage 1 completion. Its startup gaps, two observed current-binding drifts and retained non-green selector remain open. NOT_BOUND applies only to the enumerated declaration search scope. No missing task-start hash is reconstructed from HEAD.

This contract advances independent local work already within remediation scope. It does not require a new user authorization for read-only history inspection or bounded offline deterministic generation. It does not authorize restoration of deleted evidence or live observations.

## Work package L: execute eligible local proposals

Input: claim-003, claim-005, claim-008, claim-009, claim-010, claim-011, claim-013, claim-015 from the exact claim table, with their listed generators, current anchors and prerequisite dependencies.

Output root: create-only `stage1-successor-evidence/contract14-local-execution-v1/`. If present, stop with TARGET_ALREADY_EXISTS; never overwrite or choose another suffix silently. Use unique task temporary directories for intermediate local fixture stores and receipts. Final artifacts must bind generator hashes, input hashes, actual commands/options, outputs, exit status and observation scope.

Before each generator runs, inspect its effect and output boundaries. Override legacy default output paths explicitly. Block network, DNS, external providers, container/service startup, user databases and implicit model downloads. Pure in-process repo-local hashing embeddings are permitted; a script containing 'live' in its name does not authorize any live service. Preserve raw observations and distinguish its local terminology from external live authority.

Execute dependencies once, share immutable output references, and parallelize only independent generators with disjoint stores/output paths. Existing generator APIs may be invoked with explicit input paths; a minimal evidence wrapper may adapt paths and serialization. Do not duplicate generator logic, mutate production runtime or change factual expected values. If a generator needs a source-code change, provide the exact patch and reason as a review artifact rather than expanding implementation here.

Do not assume all eight proposals are executable: claim-009 needs fresh Wave8/Wave10/Wave12/Wave14 receipts, while claim-016 concerns historical Wave8 reuse. A fresh non-live successor must have independently justified inputs and its own scope; it cannot borrow the historical claim's PASS. Missing prerequisites block only dependent claims. Run available upstream work and record the precise dependency, not a global BLOCKED.

Retain all failure/partial observations. A deterministic receipt can close only the factual claim it actually establishes. Do not rewrite the required selector, reclassify tests, add skip/xfail, or substitute fixtures for historical/public/live receipts. Proposed consumer rebinding must show which original acceptance assertion is preserved and which new scope is being proposed; no automatic full-gate closure follows from artifact generation.

## Work package H: inspect historical facts without restoring files

For the five ACTUAL_HISTORICAL_RECEIPT_REQUIRED claims, use only the exact commit/blob identities already enumerated by the claim table. Read them through Git's read-only object interface. Verify existence, size, hash, parseability and the manifest/output/review relationships in memory. Do not execute historical code, checkout files, restore deleted paths or copy a historical tree into the current workspace.

Create a new derived history-verification receipt with references and actual findings. Distinguish (a) object exists and bytes match; (b) a stored record asserts a run/review; (c) independently corroborated run identity; and (d) current qualification, which this work cannot grant. Reading historical objects is authorized; inventing a custodian approval or certifying an unsupported human review is not. If the historical set is incomplete or contradictory, preserve the precise gap.

No historical receipt is automatically made current. Any later consumer change or historical recovery/successor decision must preserve original scope and be separately reviewed. The nine live-observation-dependent nodeids remain open with zero live execution.

## Integration and acceptance

Use bounded worker IO ownership for L and H, with the main executor responsible for ordered prerequisite integration. Source runtime, current/frozen bindings, contracts 00–14, v3/v4 candidates and prior evidence packages remain read-only. process.py and the two startup-related drifting paths are not modified under this contract. Their correction/rebind and startup-preservation gaps remain separate work, without preventing L/H progress.

For new wrappers run focused tests and lint/compile; for evidence run deterministic schema/reference/hash/unique-id checks. Check every claim's prerequisites and map only actually supported nodeids. Do not rerun the known-blocked full selector or enter Phase B/C/v5.

Return a create-only structured result containing: completed local claims with actual scope; failed/blocked claims and exact dependencies; history verification at the four levels above; changed artifact paths/hashes; focused verification; resource cleanup; unchanged history check; and only remaining blockers. Include explicit `authoritative=false` and production-release-not-authorized semantics.

Permanent ceiling: NO_DEPLOY_NO_LIVE_NO_PRODUCTION_WRITE_NO_EXTERNAL_DELIVERY_NO_CANARY_NO_CUTOVER_NO_AUTHORITY_TRANSFER_NO_LEGACY_RETIREMENT_NO_PUSH_NO_REMOTE_MUTATION_NO_REGISTRY_WRITE_NO_SIGNING_WRITE.

Send the return to the Supervisor in this same task. Record dispatch only after an actual successful task-message or executor acceptance receipt. Stage 3 later reuses `01a074c0-5786-7121-8a0b-ffef1e32a2a9`; no new same-stage task is created.
