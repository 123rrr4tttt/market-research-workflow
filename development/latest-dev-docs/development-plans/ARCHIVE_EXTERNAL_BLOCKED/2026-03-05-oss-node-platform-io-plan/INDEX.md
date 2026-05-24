# OSS Node Platform IO Plan Index

更新时间：2026-05-23 PST
状态：`external_blocked` / `wave55_platform_io_checked`。本目录已迁入 `ARCHIVE_EXTERNAL_BLOCKED`；仓内 node manifest/runtime replay 已覆盖 `keyword` / `vector` / `hybrid` provider manifest consumption，Wave55 已补齐 scheduler / tenant DB / UI SLA live readback。早期 `partial` 文案仅作历史分期记录，不再是当前目录主状态。

防误读：当前 canonical decision 以本 `INDEX.md`、`08_wave29-oss-node-vector-manifest-replay-2026-05-23.md` 与 `09_wave55-oss-node-platform-io-live-sla-readback-2026-05-23.md` 为准。重新进入 `CURRENT_DEV` 前，仍需补齐 live embedding provider verification、local open-search quality 与 semantic relevance。

## 文件

- [01_oss-code-harvest-and-io-taskplan-2026-03-05.md](./01_oss-code-harvest-and-io-taskplan-2026-03-05.md)
  原始 OSS code harvest / IO task plan。
- [02_wave10-vectorization-quality-gate-2026-05-22.md](./02_wave10-vectorization-quality-gate-2026-05-22.md)
  Wave10 vectorization quality gate。
- [03_wave12-provider-readiness-gate-2026-05-22.md](./03_wave12-provider-readiness-gate-2026-05-22.md)
  Wave12 provider readiness gate。
- [04_wave14-vectorization-provider-capability-2026-05-22.md](./04_wave14-vectorization-provider-capability-2026-05-22.md)
  Wave14 provider capability gate。
- [05_wave18-vectorization-hybrid-readback-2026-05-22.md](./05_wave18-vectorization-hybrid-readback-2026-05-22.md)
  Wave18 hybrid readback gate。
- [06_wave19-vectorization-provider-manifest-2026-05-22.md](./06_wave19-vectorization-provider-manifest-2026-05-22.md)
  Wave19 provider manifest readback。
- [07_wave27-vectorization-closure-decision-2026-05-23.md](./07_wave27-vectorization-closure-decision-2026-05-23.md)
  Wave27 decision；当时仍保留 vector/node adjacent blockers。
- [08_wave29-oss-node-vector-manifest-replay-2026-05-23.md](./08_wave29-oss-node-vector-manifest-replay-2026-05-23.md)
  当前 canonical decision：OSS-node repo-local vector manifest replay blocker 已封住，剩余外部 SLA / provider 条件。
- [09_wave55-oss-node-platform-io-live-sla-readback-2026-05-23.md](./09_wave55-oss-node-platform-io-live-sla-readback-2026-05-23.md)
  Wave55 platform IO live SLA readback：scheduler / tenant DB / UI SLA 条件已通过 live backend/frontend probe。

## 当前状态

| 项 | 状态 | 证据 |
|---|---|---|
| 目录归属 | `ARCHIVE_EXTERNAL_BLOCKED` | `CURRENT_DEV/INDEX.md` 不再将本主题计入 `partial` |
| OSS-node vector manifest replay | sealed | Wave29 replay gate |
| Scheduler / tenant DB / UI SLA | sealed | Wave55 live platform IO readback |
| Live provider / open-search / semantic quality | external blocker | requires provider quality evidence |

## 验证命令

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 ops/search-lab/scripts/wave29_oss_node_vector_manifest_replay.py --out-dir development/latest-dev-docs/automation-runs/wave29-oss-node-vector-manifest-replay/2026-05-23
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 ops/search-lab/scripts/wave29_oss_node_vector_manifest_replay.py --out-dir development/latest-dev-docs/automation-runs/wave29-oss-node-vector-manifest-replay/2026-05-23 --live-api-base http://127.0.0.1:8000/api/v1 --live-ui-base http://127.0.0.1:5173/ --live-probe-timeout 5
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_wave29_oss_node_vector_manifest_replay_unittest.py
```
