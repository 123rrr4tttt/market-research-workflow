# Crawler Source Expansion Index

更新时间：2026-05-23 PST
状态：`closed` / `wave47_checked`。本目录已迁入 `ARCHIVE_CLOSED`；仓内 A1-A4/A6/A7 与 A5 full public replay review 均已封住。目录内早期 `partial`、`needs_update`、`not_closed`、`external_blocked` 只表示当时的历史推进快照，不再是当前目录主状态。

防误读：当前 canonical decision 以本 `INDEX.md` 与 `10_wave47-manual-public-replay-closure-2026-05-23.md` 为准。Wave22 的 `external_blocked` 判断是历史状态；Wave47 已补齐受控公网窗口的 45-site replay 真实证据 `development/latest-dev-docs/automation-runs/source-library-replay-scaleout/2026-05-22/output.public.json` 并完成人工复核。

## 文件

- [01_crawler-source-expansion-plan-2026-03-07.md](./01_crawler-source-expansion-plan-2026-03-07.md)
  原始 crawler source expansion 方案。
- [02_atomic-tasklist-crawler-source-expansion-2026-03-07.md](./02_atomic-tasklist-crawler-source-expansion-2026-03-07.md)
  原子任务清单，历史 `needs_update` / `not_closed` 语义仅作追溯。
- [2026-05-22-wave6-closure-gap-and-min-plan.md](./2026-05-22-wave6-closure-gap-and-min-plan.md)
  Wave6 closure gap 与最小计划。
- [2026-05-22-wave7-a5-public-replay-evidence.md](./2026-05-22-wave7-a5-public-replay-evidence.md)
  A5 public replay evidence。
- [2026-05-22-wave7-crawler-policy-matrix.md](./2026-05-22-wave7-crawler-policy-matrix.md)
  Crawler policy matrix。
- [2026-05-22-wave8-a7-validation-pack.md](./2026-05-22-wave8-a7-validation-pack.md)
  A7 validation pack。
- [2026-05-22-wave13-worker7-crawler-public-replay-gate.md](./2026-05-22-wave13-worker7-crawler-public-replay-gate.md)
  Wave13 deterministic public replay gate。
- [2026-05-22-wave19-public-replay-shards.md](./2026-05-22-wave19-public-replay-shards.md)
  Wave19 public replay shard readback。
- [2026-05-22-wave22-archive-external-blocked-decision.md](./2026-05-22-wave22-archive-external-blocked-decision.md)
  历史 Wave22 decision：当时仓内 checker 通过，剩余为外部公网 replay 证据。
- [10_wave47-manual-public-replay-closure-2026-05-23.md](./10_wave47-manual-public-replay-closure-2026-05-23.md)
  当前 canonical closure：真实 45-site public replay 已产出并完成 review，目录关闭。

## 当前状态

| 项 | 状态 | 证据 |
|---|---|---|
| 目录归属 | `ARCHIVE_CLOSED` | `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-07-crawler-source-expansion/` |
| Repo-local crawler gates | sealed | `check_crawler_source_expansion_closure.py` / public replay deterministic gates |
| Live public replay | closed | `output.public.json` records 45 targets, 40 public attempts, 5 policy skips, 0 operator-gate skips |
| A5 manual review | closed | `10_wave47-manual-public-replay-closure-2026-05-23.md` |

## 验证命令

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_crawler_public_replay_gate.py --repo-root . --output /tmp/wave47-crawler-public-replay-gate-check.json
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_crawler_source_expansion_closure.py --repo-root . --output /tmp/wave47-crawler-source-expansion-closure.json
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_crawler_public_replay_gate_unittest.py main/backend/tests/unit/test_source_library_public_replay_a5_gate_unittest.py main/backend/tests/unit/test_crawler_source_expansion_closure_check_unittest.py
```
