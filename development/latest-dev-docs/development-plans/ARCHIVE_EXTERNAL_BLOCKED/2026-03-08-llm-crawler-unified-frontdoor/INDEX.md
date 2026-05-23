# LLM Crawler Unified FrontDoor Index

更新时间：2026-05-23 PST
状态：`external_blocked` / `wave23_checked`。本目录已迁入 `ARCHIVE_EXTERNAL_BLOCKED`；仓内 frontdoor、router、manifest、fixture 与 shard gates 已封住。目录内较早 `partial` / `not_closed_missing_real_evidence` 语句只保留为历史证据或外部 blocker 描述。

防误读：当前 canonical decision 以本 `INDEX.md` 与 `10_wave23-external-blocked-decision-2026-05-23.md` 为准。重新进入 `CURRENT_DEV` 前，必须先补齐真实 high-JS public browser/crawler replay、five-shard public outputs 与 45-site replay artifact。

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

## 当前状态

| 项 | 状态 | 证据 |
|---|---|---|
| 目录归属 | `ARCHIVE_EXTERNAL_BLOCKED` | `CURRENT_DEV/INDEX.md` 不再将本主题计入 `partial` |
| Frontdoor / router / manifest / fixture gates | sealed | Wave8-Wave19 topic-local evidence |
| Real high-JS public replay | external blocker | live public output artifacts absent by design |

## 验证命令

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_crawler_public_replay_shards.py --repo-root . --output /tmp/wave35-llm-crawler-public-replay-shards.json
```
