# DriftRegen 2026-09-02

## 范围与结论

工作树：`/Users/wangyiliang/.codex/manual-worktrees/mrw-functorial-successor-p0`。

本轮只重生成 `evidence/p3-fragments/C2.json` 与 P1-P3 semantic-movement 工件，并记录结果。未修改生产代码、frozen 原文、03/04/SUPERVISOR、review/manifest 原文，未 commit/push。

任务上下文描述为 9 个失败；本轮实测基线为 12 failed / 1532 passed / 119 skipped（命令见下）。重生成后为 5 failed / 1539 passed / 119 skipped，剩余 5 个失败全部是 capability-spec/manifest 仍绑定重生成前的旧 SHA，其修复面在本任务允许写入范围之外。

## 定位命令与基线结果

cwd=`main/backend`，Python 3.11：

```bash
/Users/wangyiliang/.local/bin/python3.11 scripts/generate_successor_p1_p3_semantic_movement.py --check
/Users/wangyiliang/.local/bin/python3.11 scripts/validate_successor_semantic_movement.py
/Users/wangyiliang/.local/bin/python3.11 scripts/generate_family_fragment_shared.py --family C2 --check
/Users/wangyiliang/.local/bin/python3.11 scripts/generate_family_fragment_shared.py --family C5 --check
```

结果：

- P1-P3 generator `--check`：`DRIFT`，12 个路径，60 movements / 0 blockers，exit 1。
- validator：`FAIL`，唯一失败项为 `canonical_rebuild_matches`，其余 13 项 PASS，exit 1。
- shared C2 `--check`：`DRIFT`，exit 1。
- shared C5 `--check`：`MATCH`，exit 0。C5.json 在本轮前已由工作树当前绑定重生成，未重复写入。

全量非 PG 基线命令与结果：

```bash
env -u SUCCESSOR_TEST_DATABASE_URL -u SUCCESSOR_DATABASE_URL /Users/wangyiliang/market-research-workflow/main/backend/.venv311/bin/python -m pytest -q -p no:cacheprovider tests/successor_runtime
```

基线：`12 failed, 1532 passed, 119 skipped, 3 warnings`。

## 重生成命令与结果

```bash
/Users/wangyiliang/.local/bin/python3.11 scripts/generate_family_fragment_shared.py --family C2
/Users/wangyiliang/.local/bin/python3.11 scripts/generate_successor_p1_p3_semantic_movement.py
```

结果：C2 `WROTE`；P1-P3 `WROTE`，40 inline + 20 external C7 = 60 movements，0 blockers。

重生成后只读复核：

- P1-P3 generator `--check`：`CHECK_OK` 60/0，exit 0。
- validator：`PASS`（14/14），refs 323/323 resolved，exit 0。
- shared C2 / C5 `--check`：均 `MATCH`，exit 0。

## 全量非 PG 后测结果

同一条全量命令复跑：

`5 failed, 1539 passed, 119 skipped, 3 warnings`，exit 1。

失败文件：

- `tests/successor_runtime/test_i1_micro_specimens.py`：3 项，均报 C1.1 spec 的 exact binding 指向旧 `P1P3SuccessorMovementMatrix.v1.json` SHA `9dc614c7...`，磁盘现为 `482ae293...`。
- `tests/successor_runtime/test_i1_rollback_rehearsal.py`：2 项，均报 rollback binding 指向旧 `p3-fragments/C2.json` SHA `5274116a...`，磁盘现为 `31d32ce3...`。

根因：重生成的 semantic-movement matrix 与 C2.json 被 `evidence/capability-specs`、`evidence/capability-spec-builds` 及 review 精确绑定；这些文件仍写旧 SHA。修复需要既有 generator 重生成 `evidence/capability-specs` 与 `evidence/capability-spec-builds`，属于本任务禁止改动的 spec/manifest 面，故本轮无法声明 0 failed。

## 改动文件与 SHA

改动前 SHA 为工作树本轮前字节（与 HEAD 一致），改动后 SHA 为本轮复核值。

### p3-fragment

| 文件 | 改动前 SHA-256 | 改动后 SHA-256 |
|---|---|---|
| `evidence/p3-fragments/C2.json` | `5274116a2a083ec1553d05c034f5490f1450851d805fb2590efec21be95c544b` | `31d32ce3d29eb2ed82063ba8c67d881ed3589cfdf23a616be520acabab1c9922` |

### semantic-movement 顶层工件

| 文件 | 改动前 SHA-256 | 改动后 SHA-256 |
|---|---|---|
| `P1P3LegacyDonorSemanticMovementInventory.v1.json` | `31e59601a7fef35afc5cf2a3e784fc1692d40ad3a53b816e3439eeb4f27990cc` | `c032207f0070424b83fc81a8d49167dbb8f5624f08aaa97853e34f7a6f296be9` |
| `P1P3SuccessorMovementMatrix.v1.json` | `9dc614c73f6ce48202f7087a8971e812c5eae44844e9453267e6550bb0f8712e` | `482ae2934fbe8ffd19a2e8d43365d4f910ff8cb82398cfd885086f07bb2740db` |
| `P1P3SemanticMovementGate.v1.json` | `f70e1fbebf31bd44cef85a2517d69ceb816b6ac1d6892a2b3ffe40c937ad5913` | `74ade16f3113d68ff1642e5bf0a87aac7cc91dac868f5f3e9bcbbe06b0ca3ce0` |

### semantic-movement fragments（9 个全部重生成）

| 文件 | 改动前 SHA-256 | 改动后 SHA-256 |
|---|---|---|
| `fragments/C1.v1.json` | `924f121290c88d46ac2a4b17017b897fcfd98cdb85900696fa898c34f86d1277` | `0ffd28226ff542f7f4d011ccf612bad8a84b35fd390be59c7694318e4b5ef138` |
| `fragments/C2.v1.json` | `0efbc9693655bbad729054e262b779b169bf8ad0d8e6d9a68ec258630206ab8e` | `92d0824ec35f8d56f3a530ce484139922a08e3c3a7a6a7869dfbc6099a25aa02` |
| `fragments/C3.v1.json` | `609715c3301b2269e98039f462eab284990ad83a41e9ca41d49bc393279df385` | `4d073060363d703a2ecd67368ac7f91ef1c15491e81a8ad696bbd34f04393eca` |
| `fragments/C4.v1.json` | `3647433225c07fa6baef83ec41d8104b5fc487dadf05aa2eaaf63b9e28680ecc` | `c9db07f3383fdc34cb3343ab392acdfac408eb89efa48e9f4ce3d81908a227a5` |
| `fragments/C5.v1.json` | `42225281ee4891dfcfbec1706017f39ebd8b1964a9da886d10d9536940a1bd79` | `3ac6b67ebd0ec0b708a0e4d7ff48d8b61686d08db3bce64e1820c86f6164ed2d` |
| `fragments/C6.v1.json` | `6a064e8fbd2cb46ab7c530ded44993eb4deda9e853cf05a1b046363545b2bbca` | `8f201c3d730d1c3e2429abdb4b7d982abd6eafed361941702e590a82536c31a8` |
| `fragments/C7.v1.json` | `a427551585bda69d777677e5fb95d2e991a7fa310dc549eae83588ee187c6867` | `3d55cff419f4d926f627e75f7a2058dbfee538ce2cce9a2e722c03b1cd52d3a6` |
| `fragments/C8.v1.json` | `46c400ea5f7d213a6ab9e17a42b1aebfda063ffabf8665223832e15c8ab3faa1` | `82975be377ab3e0da81da5b96623c26624dce36a0edd01cbf2a5afbf94a56e71` |
| `fragments/C9.v1.json` | `f4f2407f1ebf39d27423127d4795db6f70dd94c24fa3864ecd9d405b3cf98192` | `88a63d5293f827b46bb97d4269aada2c539dac494b2e2e117f19521a022f4230` |

## 残留绑定记录（不改原文）

以下 review/spec/manifest 仍绑定旧 SHA，本轮只记录：

- `evidence/capability-specs/C1.1.v1.json` 等 specs 绑定 matrix `9dc614c7...`。
- `evidence/capability-specs/C2.*.v1.json` 与 `evidence/capability-spec-builds/C2.*.BuildManifest.v1.json` 绑定 C2 `5274116a...`。
- `evidence/capability-specs/C5.*.v1.json`、C5 build manifests、`reviews/C2C6AdoptionReview.v1.json`、`reviews/P3AggregateExactReview.current.json` 等仍引用 C5 旧 SHA `38ce2188...`；C5.json 磁盘当前为 `3706a5f5...`（本轮前已由工作树当前绑定更新，本任务未重写）。

未改任何 review/spec/manifest 原文；后续如需 0 failed，需要在其授权 lane 中用既有 pilot generator 重生成 capability-spec 与 build manifest，再重跑同一全量命令。
