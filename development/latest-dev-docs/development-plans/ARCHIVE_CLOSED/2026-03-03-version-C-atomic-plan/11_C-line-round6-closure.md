# C线第6轮封口文档（contract-first 收敛）

## 1) 本轮范围
按固定流程完成：
1. 联网检索并写入统一知识池（单入口）
2. 基于统一池产出原子任务表
3. 实现并执行验证
4. 输出 closing 并更新索引

## 2) 跨版本去重与差异化声明
- 去重：不重复新增 round5 已有能力（manifest 哈希校验、strict 开关、四件套报告）。
- 差异化新增：
  - 新增 `artifact-contract.json`（契约单一真源）
  - verifier 从 contract 读取 `required_files` 与 `strict_policy`
  - manifest + contract 双层协同（完整性 + 语义门禁）

## 3) 关键实现变更
- `scripts/pre_release_report_bundle.py`
  - 新增输出 `artifact-contract.json`
  - manifest 纳入 contract 文件摘要
- `scripts/pre_release_verify_artifacts.py`
  - 新增 contract schema_version 校验（v1）
  - required_files 改为 contract 驱动
  - strict 规则改为 contract.strict_policy 驱动
- `main/backend/tests/unit/test_pre_release_report_bundle_unittest.py`
  - 新增 contract 断言与 manifest 包含 contract 的断言

## 4) 可执行验证证据
### 4.1 单测
```bash
python3 -m pytest -q main/backend/tests/unit/test_pre_release_report_bundle_unittest.py
```
结果：`1 passed`

### 4.2 端到端 pipeline
```bash
bash scripts/pre_release_pipeline.sh \
  development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-C-atomic-plan/artifacts/pre-release-round6
```
结果：PASS（verify 返回 `{"result":"pass"}`）

产物：
- `artifact-contract.json`
- `artifact-manifest.json`
- `gate-result.json`
- `observability-check.json`
- `quality-metrics.json`
- `release-notes.md`

## 5) 风险与回滚
- 风险：contract schema_version 目前为 v1，未来字段扩展需兼容升级策略。
- 回滚最小集合：
  - `scripts/pre_release_report_bundle.py`
  - `scripts/pre_release_verify_artifacts.py`
  - `main/backend/tests/unit/test_pre_release_report_bundle_unittest.py`

## 6) 下一轮草案
见：`12_C-line-round7-draft.md`
目标：strict 真阻断演练（故障注入）+ CI 中 contract 漂移检测。
