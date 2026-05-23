# Open Source Platform Integration Index

更新时间：2026-05-23 PST
状态：`non_target_superseded_parent_wrapper` / `wave50_reclassified`。本目录已从 external-blocked target set 中移除；Wave29 OSS-node slice 与 Wave30 global-vector repo-local blockers 均已清零，剩余 provider/SLA 条件由具体 successor 目标承接。本目录不再有独立仓内 blocker，不能作为新的 `partial` 或 `external_blocked` 当前开发入口继续补小 gate。

防误读：本目录历史文件中的 provider/vectorization gate 表示当时的仓内证据推进；当前 canonical readback 以本 `INDEX.md` 和 `10_wave50-non-target-wrapper-reclassification-2026-05-23.md` 为准。重新进入当前开发前，应直接开到 successor 目标，而不是复用这个父级汇总目录。

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
  历史 decision：本目录 repo-local blocker 清零，剩余均为外部条件。
- [10_wave50-non-target-wrapper-reclassification-2026-05-23.md](./10_wave50-non-target-wrapper-reclassification-2026-05-23.md)
  当前 canonical decision：本父级 wrapper 不再作为独立 external-blocked target 计数，剩余条件由 global-vector 与 OSS-node successor targets 承接。

## 当前状态

| 项 | 状态 | 证据 |
|---|---|---|
| 目录归属 | `non_target_superseded_parent_wrapper` | `TARGET_TOPIC_ALLOWLIST.json` excludes this parent wrapper from the external target set |
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
