# LLM Crawler Unified FrontDoor Index

更新时间：2026-05-23 PST
状态：`external_blocked` / `wave55_t5_reduced`。本目录已迁入 `ARCHIVE_EXTERNAL_BLOCKED`；仓内 frontdoor、router、manifest、fixture 与 shard gates 已封住。Wave55 T5 已用真实 headless Chrome replay 证明 accessible high-JS public path 可跑通，剩余失败被收敛为外部平台 auth/anti-bot gates。目录内较早 `partial` / `not_closed_missing_real_evidence` 语句只保留为历史证据或外部 blocker 描述。

防误读：当前 canonical decision 以本 `INDEX.md`、`10_wave23-external-blocked-decision-2026-05-23.md` 与 `12_wave55-t5-accessible-high-js-replay-boundary-2026-05-23.md` 为准。重新进入 `CURRENT_DEV` 前，必须先解除或替换剩余外部平台门控，取得所有 declared high-JS public targets 的 target-specific public content。

## 文件

- [01_llm-crawler-unified-frontdoor-architecture-2026-03-08.md](./01_llm-crawler-unified-frontdoor-architecture-2026-03-08.md)
  原始 unified frontdoor 架构。
- [02_atomic-tasklist-llm-crawler-unified-frontdoor-2026-03-08.md](./02_atomic-tasklist-llm-crawler-unified-frontdoor-2026-03-08.md)
  原子任务清单。
- [03_a10-closure-and-validation-2026-03-08.md](./03_a10-closure-and-validation-2026-03-08.md)
  A10 closure / validation 记录。
- [04_wave8-2-fetch-router-gap-closure-2026-05-22.md](./04_wave8-2-fetch-router-gap-closure-2026-05-22.md)
  Fetch router gap closure。
- [05_wave10-tri-state-router-contract-2026-05-22.md](./05_wave10-tri-state-router-contract-2026-05-22.md)
  Tri-state router contract。
- [06_wave13-high-js-public-replay-readiness-2026-05-22.md](./06_wave13-high-js-public-replay-readiness-2026-05-22.md)
  High-JS public replay readiness。
- [07_wave15-high-js-replay-manifest-2026-05-22.md](./07_wave15-high-js-replay-manifest-2026-05-22.md)
  High-JS replay manifest。
- [08_wave18-browser-replay-fixture-readback-2026-05-22.md](./08_wave18-browser-replay-fixture-readback-2026-05-22.md)
  Browser replay fixture readback。
- [09_wave19-public-replay-shards-readback-2026-05-22.md](./09_wave19-public-replay-shards-readback-2026-05-22.md)
  Public replay shards readback。
- [10_wave23-external-blocked-decision-2026-05-23.md](./10_wave23-external-blocked-decision-2026-05-23.md)
  当前 canonical decision：仓内 repo-local blocker 清零，剩余为外部 public replay evidence。
- [11_wave55-c1-public-replay-shard-closure-2026-05-23.md](./11_wave55-c1-public-replay-shard-closure-2026-05-23.md)
  Wave55 C1：45-site shard outputs 已补齐；高 JS public replay 仍保持非 full closure。
- [12_wave55-t5-accessible-high-js-replay-boundary-2026-05-23.md](./12_wave55-t5-accessible-high-js-replay-boundary-2026-05-23.md)
  Wave55 T5：真实 Chrome replay 证明 accessible public high-JS path；剩余 X/Instagram 为外部 auth/anti-bot gates。

## 当前状态

| 项 | 状态 | 证据 |
|---|---|---|
| 目录归属 | `ARCHIVE_EXTERNAL_BLOCKED` | `CURRENT_DEV/INDEX.md` 不再将本主题计入 `partial` |
| Frontdoor / router / manifest / fixture gates | sealed | Wave8-Wave19 topic-local evidence |
| 45-site public replay shards | sealed | `crawler-public-replay-shards/2026-05-22/check.json` |
| Accessible high-JS public replay | reduced / evidence-backed | `llm-crawler-high-js-public-replay/2026-05-23/check.t5.json` |
| Remaining high-JS external gates | external blocker | `x_search_robotics` and `instagram_tag_robotics` auth/anti-bot gated |

## 验证命令

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_crawler_public_replay_shards.py --repo-root . --output /tmp/wave35-llm-crawler-public-replay-shards.json

PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_llm_crawler_high_js_replay_readiness.py \
  --public-artifact development/latest-dev-docs/automation-runs/llm-crawler-high-js-public-replay/2026-05-23/output.public.t5.json \
  --output /tmp/wave55-t5-llm-crawler-high-js-readiness.json
```
