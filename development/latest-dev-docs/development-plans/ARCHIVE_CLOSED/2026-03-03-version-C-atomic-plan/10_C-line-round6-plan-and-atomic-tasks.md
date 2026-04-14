# C线第6轮：开发文档 + 原子任务表（依赖/门禁/负责人/产物）

## 1) 目标
在 round5 的 manifest 校验基础上，新增 contract-first 机制，形成“契约声明 + 完整性校验 + strict 策略”三层闭环。

## 2) 原子任务表

| 任务ID | 任务名称 | 依赖 | 串行门禁 | 负责人 | 产物 |
|---|---|---|---|---|---|
| C6-AT-01 | 联网检索并写入统一知识池 | 无 | G0: 单一入口索引更新 | C线文档owner | `信息源库/global/research/2026-03-03-C-line-round6-best-practices.md` + `INDEX.md` |
| C6-AT-02 | report bundle 产出 artifact-contract | C6-AT-01 | G1: bundle 脚本可执行 | C线实现owner | `scripts/pre_release_report_bundle.py` |
| C6-AT-03 | verifier 按 contract 驱动校验与 strict 策略 | C6-AT-02 | G2: verifier 独立执行通过 | C线实现owner | `scripts/pre_release_verify_artifacts.py` |
| C6-AT-04 | 单测补齐 contract 断言 | C6-AT-03 | G3: 单测通过 | C线测试owner | `main/backend/tests/unit/test_pre_release_report_bundle_unittest.py` |
| C6-AT-05 | pipeline 实跑验证并输出 closing | C6-AT-04 | G4: pipeline 产物齐全且 verify pass | C线集成owner | `11_C-line-round6-closure.md` |

## 3) 并行编排
- 并行组 PG-A：C6-AT-01（知识池）
- 并行组 PG-B：C6-AT-02 + C6-AT-03（实现）
- 串行组 SG-C：C6-AT-04 -> C6-AT-05

## 4) 验收门禁
- `python3 scripts/pre_release_report_bundle.py ...` 产出 `artifact-contract.json`
- `python3 scripts/pre_release_verify_artifacts.py --output-dir ...` 按 contract 校验
- `bash scripts/pre_release_pipeline.sh ...` 端到端通过
