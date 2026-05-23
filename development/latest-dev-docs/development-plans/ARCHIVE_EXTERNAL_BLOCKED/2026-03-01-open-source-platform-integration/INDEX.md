# Open Source Platform Integration Index

更新时间：2026-05-23 PST
状态：`external_blocked` / `wave30_checked`。本目录已从 `CURRENT_DEV` 迁入 `ARCHIVE_EXTERNAL_BLOCKED`；Wave29 OSS-node slice 与 Wave30 global-vector repo-local blockers 均已清零。本目录不再有独立仓内 blocker，不能作为新的 `partial` 当前开发入口继续补小 gate。

防误读：本目录历史文件中的 provider/vectorization gate 表示当时的仓内证据推进；当前 canonical readback 以本 `INDEX.md` 和 `09_wave30-open-source-external-blocked-decision-2026-05-23.md` 为准。重新进入当前开发前，必须先补齐 live provider、local open-search quality、semantic relevance 或 external runtime/SLA evidence；对应状态码为 `local_open_search_live_quality_not_sealed`、`semantic_embedding_quality_not_proven` 和 `oss_node_platform_io_sla_not_closed`。

## 文件

- [01_multi-agent-taskboard-open-source-platform-integration-2026-03-01.md](./01_multi-agent-taskboard-open-source-platform-integration-2026-03-01.md)
  原始 open-source platform integration taskboard。
- [02_wave10-vectorization-quality-gate-2026-05-22.md](./02_wave10-vectorization-quality-gate-2026-05-22.md)
  Wave10 vectorization quality gate evidence。
- [03_wave12-provider-readiness-gate-2026-05-22.md](./03_wave12-provider-readiness-gate-2026-05-22.md)
  Wave12 provider readiness gate evidence。
- [04_wave14-vectorization-provider-capability-2026-05-22.md](./04_wave14-vectorization-provider-capability-2026-05-22.md)
  Wave14 provider capability evidence。
- [05_wave18-vectorization-hybrid-readback-2026-05-22.md](./05_wave18-vectorization-hybrid-readback-2026-05-22.md)
  Wave18 vectorization hybrid readback evidence。
- [06_wave19-vectorization-provider-manifest-2026-05-22.md](./06_wave19-vectorization-provider-manifest-2026-05-22.md)
  Wave19 provider manifest readback evidence。
- [07_wave22-vectorization-provider-external-blocked-decision-2026-05-22.md](./07_wave22-vectorization-provider-external-blocked-decision-2026-05-22.md)
  Wave22 provider external-blocked decision。
- [08_wave27-vectorization-closure-decision-2026-05-23.md](./08_wave27-vectorization-closure-decision-2026-05-23.md)
  Wave27 vectorization closure decision showing adjacent blockers still existed then。
- [09_wave30-open-source-external-blocked-decision-2026-05-23.md](./09_wave30-open-source-external-blocked-decision-2026-05-23.md)
  当前 canonical decision：本目录 repo-local blocker 清零，剩余均为外部条件。

## 当前状态

| 项 | 状态 | 证据 |
|---|---|---|
| 目录归属 | `ARCHIVE_EXTERNAL_BLOCKED` | `CURRENT_DEV/INDEX.md` 只保留 external-blocked 指针，不再作为 partial 目录 |
| OSS-node adjacent blocker | cleared / external-blocked | `../2026-03-05-oss-node-platform-io-plan/08_wave29-oss-node-vector-manifest-replay-2026-05-23.md` |
| Global vector repo-local blocker | cleared | `../2026-05-14-global-vectorization-general-foundation/11_wave30-vector-closure-external-blocked-decision-2026-05-23.md` |
| Independent repo-local blocker | none | `09_wave30-open-source-external-blocked-decision-2026-05-23.md` |

## 仍需外部条件

- live provider
- local open-search quality
- semantic relevance
- external runtime/SLA evidence

## 验证命令

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 ops/search-lab/scripts/wave30_vector_closure_gate.py --out-dir development/latest-dev-docs/automation-runs/wave30-vector-closure-gate/2026-05-23
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q \
  main/backend/tests/unit/test_wave27_vectorization_closure_gate_unittest.py \
  main/backend/tests/unit/test_wave29_vector_schema_alignment_gate_unittest.py \
  main/backend/tests/unit/test_wave30_vector_closure_gate_unittest.py
/Users/wangyiliang/.local/bin/python3.11 scripts/checkers/check_search_vector_external_blocked_status.py --root .
```
