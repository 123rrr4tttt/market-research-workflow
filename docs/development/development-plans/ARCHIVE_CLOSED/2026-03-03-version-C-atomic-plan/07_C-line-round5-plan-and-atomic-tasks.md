<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-03-03-version-C-atomic-plan/07_C-line-round5-plan-and-atomic-tasks.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-03-version-C-atomic-plan/07_C-line-round5-plan-and-atomic-tasks.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# C线第5轮：开发文档 + 原子任务表（依赖/门禁/负责人/产物）

## 1) 目标
在第4轮 pre-release 分层流水线基础上，补齐“工件完整性校验”能力，并将 strict 模式纳入统一执行入口。

## 2) 原子任务表

| 任务ID | 任务名称 | 依赖 | 串行门禁 | 负责人 | 产物 |
|---|---|---|---|---|---|
| C5-AT-01 | 沉淀 round5 最佳实践到知识池 | 无 | G0: 文档存在且可引用 | C线文档owner | `信息源库/global/research/2026-03-03-C-line-round5-best-practices.md` |
| C5-AT-02 | 扩展 report bundle，新增 `artifact-manifest.json` | C5-AT-01 | G1: 语法可执行 | C线实现owner | `scripts/pre_release_report_bundle.py` |
| C5-AT-03 | 新增 artifact verifier（校验和 + strict 规则） | C5-AT-02 | G2: verifier 可独立执行 | C线实现owner | `scripts/pre_release_verify_artifacts.py` |
| C5-AT-04 | pipeline 接入 verify，并透传 strict | C5-AT-03 | G3: pipeline 流程闭环 | C线实现owner | `scripts/pre_release_pipeline.sh` |
| C5-AT-05 | 单测补齐（bundle + verify） | C5-AT-04 | G4: 单测通过 | C线测试owner | `main/backend/tests/unit/test_pre_release_report_bundle_unittest.py` |
| C5-AT-06 | 生成封口文档并更新索引 | C5-AT-05 | G5: 索引可导航 | C线文档owner | `08_C-line-round5-closure.md` + README/index/INDEX |

## 3) 并行编排
- 并行组 PG-A：C5-AT-01（知识池）
- 并行组 PG-B：C5-AT-02 + C5-AT-03（实现）
- 串行组 SG-C：C5-AT-04 -> C5-AT-05 -> C5-AT-06

## 4) 验收门禁
- 可执行门禁：`python3 scripts/pre_release_report_bundle.py ...` + `python3 scripts/pre_release_verify_artifacts.py ...`
- strict 语义门禁：verifier 在 `--strict` 下必须约束 `observability-check.result=pass`
- 文档门禁：README / index / development-plans/INDEX 必须新增 round5 链接
