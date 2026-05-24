# OSS Node Platform IO Plan Index

更新时间：2026-05-23 PDT
状态：`closed` / `wave57_public_corpus_semantic_closed` / `archived_closed`。本目录已迁入 `ARCHIVE_CLOSED`；仓内 node manifest/runtime replay 已覆盖 `keyword` / `vector` / `hybrid` provider manifest consumption，Wave55 已补齐 scheduler / tenant DB / UI SLA live readback 和 repo-local open-search / semantic quality gate，Wave57 已补齐 target-local public-corpus semantic relevance gate。早期 `partial` / `external_blocked` 文案仅作历史分期记录，不再是当前目录主状态。

防误读：当前 canonical decision 以本 `INDEX.md`、`08_wave29-oss-node-vector-manifest-replay-2026-05-23.md`、`09_wave55-oss-node-platform-io-live-sla-readback-2026-05-23.md`、`10_wave55-oss-node-search-quality-gate-2026-05-23.md` 与 `11_wave57-oss-node-public-corpus-semantic-relevance-2026-05-23.md` 为准。live embedding provider 已由 Wave55 全局 gate 读回；local open-search quality 已在 repo-local deterministic scope 封住；semantic relevance 已由 Wave57 的 public-corpus route 封住。全局 manifest/index 已同步移除本目录的 external target 记录。

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
- [10_wave55-oss-node-search-quality-gate-2026-05-23.md](./10_wave55-oss-node-search-quality-gate-2026-05-23.md)
  Wave55 repo-local open-search / semantic quality gate：controlled `searxng` / `yacy` ranking、repo-local semantic retrieval 与 retrieval-run readback 已通过；production/live-container scope 仍保留。
- [11_wave57-oss-node-public-corpus-semantic-relevance-2026-05-23.md](./11_wave57-oss-node-public-corpus-semantic-relevance-2026-05-23.md)
  Wave57 public-corpus semantic relevance gate：读取 `reference-pool/oss` 的 7 个公共 OSS 语料行段，验证 semantic ranking、hard-negative margin 与 retrieval-run readback；target-local `oss_node_provider_quality` 已成为 closed candidate，未声明 live container 质量。

## 当前状态

| 项 | 状态 | 证据 |
|---|---|---|
| 目录归属 | `ARCHIVE_CLOSED` | `CURRENT_DEV/INDEX.md` 不再将本主题计入 `partial` 或 `external_blocked` |
| OSS-node vector manifest replay | sealed | Wave29 replay gate |
| Scheduler / tenant DB / UI SLA | sealed | Wave55 live platform IO readback |
| Live embedding provider | sealed for repo-local provider path | Wave55 live embedding provider gate |
| Local open-search quality | sealed for repo-local deterministic scope | Wave55 OSS node search quality gate |
| Public-corpus semantic relevance | sealed for target-local public OSS corpus route | Wave57 OSS node public-corpus semantic relevance gate |
| Target-local closure decision | `closed` | Wave57 artifact reports `remaining_conditions=[]` / `target_archive_closed_candidate=true` |
| Live SearXNG / YaCy container quality | not claimed | Wave57 explicitly keeps live container quality outside claim scope |

## 验证命令

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 ops/search-lab/scripts/wave29_oss_node_vector_manifest_replay.py --out-dir development/latest-dev-docs/automation-runs/wave29-oss-node-vector-manifest-replay/2026-05-23
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 ops/search-lab/scripts/wave29_oss_node_vector_manifest_replay.py --out-dir development/latest-dev-docs/automation-runs/wave29-oss-node-vector-manifest-replay/2026-05-23 --live-api-base http://127.0.0.1:8000/api/v1 --live-ui-base http://127.0.0.1:5173/ --live-probe-timeout 5
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 ops/search-lab/scripts/wave55_oss_node_search_quality_gate.py --out-dir development/latest-dev-docs/automation-runs/wave55-oss-node-search-quality-gate/2026-05-23
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 ops/search-lab/scripts/wave57_oss_node_public_corpus_semantic_relevance_gate.py --out-dir development/latest-dev-docs/automation-runs/wave57-oss-node-public-corpus-semantic-relevance-gate/2026-05-23
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_wave29_oss_node_vector_manifest_replay_unittest.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_wave55_oss_node_search_quality_gate_unittest.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_wave57_oss_node_public_corpus_semantic_relevance_gate_unittest.py
```
