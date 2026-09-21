# Contract 13 item 2 — historical Stage 2 candidate verification

- Observed at: `2026-09-06T06:50:17Z`
- Status: `PASS`
- Scope: Contract 13 required bounded correction 2 only
- Authority: `NOT_AUTHORITY`
- Conclusion: `HISTORICAL_V3_V4_EXACT_AND_CLEAN_ALL_CONTRACT10_BOUND_HASHES_MATCH`

## Candidate roots

| Version | Actual root | Commit | Tree | Tracked | Untracked | Diff checks | Status |
|---|---|---|---|---:|---:|---|---|
| v3 | `/Users/wangyiliang/.codex/release-candidates/mrw-stage2-20260906-v3` | `f8d84afc2784cf91784da957e353e2b0c0d6952c` | `1be3dcbc009332ec225297d1b94430862287d816` | 0 | 0 | worktree PASS; cached PASS | `MATCH_CLEAN` |
| v4 | `/Users/wangyiliang/.codex/release-candidates/mrw-stage2-20260906-v4` | `e1aa59708a22e4238c4d9beaf7b7bd2d2095d483` | `d2003fbb8e54c8dd743fa4e84907a8a978ef5107` | 0 | 0 | worktree PASS; cached PASS | `MATCH_CLEAN` |

Both candidates have parent `88ffcc3dab2e6cbdc1f389e16c4226df5a2e51c6`. The candidate root inode/mtime and `.git/index` SHA-256/mtime were sampled before and after all checks and remained unchanged. Git reads used `GIT_OPTIONAL_LOCKS=0` and disabled hooks. No candidate code was imported and no cache was created in either historical root.

## Stage 2 evidence

| Version | Path | Expected SHA-256 | Actual SHA-256 | Parse | Status |
|---|---|---|---|---|---|
| v3 | `candidate-manifest.v3.json` | `a95e4103dfa3743c6a603079f838d48a20665b38afe7fa2a9b2623ab443522bf` | same | PASS | MATCH |
| v3 | `closure.final.v3.json` | `53497a752a9207b4dc54f8a5ab7e8af23d3f937a82fb71c8e8bc3092fc410808` | same | PASS | MATCH |
| v3 | `r1.final.v3.json` | `fdd6053faeada17b62c050207078ff5944a3c759eb5d6183a43ac4f74cc4774e` | same | PASS | MATCH |
| v3 | `stage2-record.final.v3.json` | `46d0df3f320619508130f87f6f8d60baba6c6080918293f3d021fbe7e26fb312` | same | PASS | MATCH |
| v4 | `candidate-manifest.v4.json` | `abc012b5c114d2d280db5bc5fc24c5591caa5bacc76840b154ec848dca5ae8b0` | same | PASS | MATCH |
| v4 | `closure.final.v4.json` | `6e3cf6dfd3ac7c336e81ab5c9b2e310373de7b981edce88109261ac031575c18` | same | PASS | MATCH |
| v4 | `r1.final.v4.json` | `79f7301e0c1e08553982ccc5c88f5854113825c81019ef6244da6bbd025260f0` | same | PASS | MATCH |
| v4 | `r2.pass.v4.json` | `8e37eee14ea2eb865a048f57fec7ca55346da642509dc65ac99899b3d69a87ce` | same | PASS | MATCH |
| v4 | `r3.pass.v4.json` | `86c67a4532a5a125f65c8f7405bd2b4b775472112e1577d85355fe6001ff5383` | same | PASS | MATCH |
| v4 | `stage2-record.final.v4.json` | `e2797d157c0a97f70b382d6ee6197bbcb073f6e55ac6ced5abe6946318345891` | same | PASS | MATCH |
| v4 | `candidate-primary.materialization.v4.json` | `76256addd9668a7d3a466fff2b2c98ab76be9e87ad9236878c8d483c5de0161b` | same | PASS | MATCH |
| v4 | `candidate-replay.materialization.v4.json` | `53aada9354d0c4410b7b359cd05b76e03899225f116107862e8fadd730beb6e6` | same | PASS | MATCH |

All paths above are under `/Users/wangyiliang/.codex/release-evidence/mrw-stage2-20260906-v3/` or `/Users/wangyiliang/.codex/release-evidence/mrw-stage2-20260906-v4/` according to their version. The two v3 materialization receipts also exist, parse, and bind the same commit/tree; Contract 10 does not supply expected hashes for those two, so the JSON receipt records their observed hashes without upgrading them to Contract 10-bound evidence.

## Contract 10 historical inputs

The following expected hashes all match current bytes:

- stage plan `04`: `d04ae870b5d2a13afacdc7a07e9d5a89b7ab77e7b6c2d6cdd4bd2101151f76fa`
- freeze `05`: `06d2ec76f7c59973997311ac7ae416005ae0b9c7784598b11127e436dcf8a2aa`
- Stage 0 completion v4: `4911df1c6450d9802ac7bd6b0669ef3a7343e3ce308d33f0a46dde2c4cb62dda`
- Stage 1 historical record: `3f5c745ce8253522fa7e3728ba112ed41c80f3b6aa7409ddf028621c6ae07f31`
- Stage 1 historical review: `10117a7c8c4eec19c33e3ad841c99fb301c43fcda71f8d7addbde4070646f72c`
- Stage 1 R2 remediation record: `97203433ca9dcf7f36e98f4dca2461d60f0159515f002127c153a5e061f74efe`
- Stage 3 v4 evidence index v2: `fbe1914ff111879edd1d1f5db02b7322232bdfa0bf05e752581ce2ea53992926`

The Stage 3 v4 index binds 18 current and 6 superseded retained evidence paths. All 24 paths exist and all 24 hashes match. The JSON receipt records each indexed path, expected hash and status.

## Validation and boundaries

- Receipt JSON parse: PASS.
- Receipt JSON SHA-256: `b21bc780b140792cc96b5f358fc02c2e818af8b0b29da722d2a8e12857526d89`.
- Candidate identity, clean state and diff checks: PASS.
- Historical evidence parse and expected hashes: PASS.
- Historical drift: none observed.
- Candidate imports, cache creation, historical writes, network, deployment, live/provider/database, production write and external delivery: none.
- Authority ceiling remains `NO_DEPLOY_NO_LIVE_NO_PRODUCTION_WRITE_NO_EXTERNAL_DELIVERY_NO_CANARY_NO_CUTOVER_NO_AUTHORITY_TRANSFER_NO_LEGACY_RETIREMENT_NO_PUSH_NO_REMOTE_MUTATION_NO_REGISTRY_WRITE_NO_SIGNING_WRITE`.

The complete machine-readable evidence is `historical-candidates-readonly-verification.v1.json` in this directory.
