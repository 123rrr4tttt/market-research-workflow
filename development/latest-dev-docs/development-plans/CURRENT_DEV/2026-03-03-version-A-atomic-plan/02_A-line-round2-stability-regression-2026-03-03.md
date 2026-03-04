# A线第2轮：稳定性与回归验证（2026-03-03）

## 1) 本轮目标与范围

- 目标：在 Version A 已落地改动基础上，补强最关键回归验证，确保 ingest 单链路的阶段契约字段（`reason_code/reason_category/stage_context`）稳定输出。
- 范围：
  - 仅补充回归测试，不改动生产逻辑路径。
  - 覆盖此前已改动核心路径：
    - `single_url` 轻过滤拒绝路径（light filter reject）
    - `single_url` pre-fetch URL gate 拒绝路径
  - 执行最小但可信验证链：相关单测 + 语法检查。

## 2) 原子任务执行顺序与实际偏差

### 计划原子任务顺序
1. 对齐分支与最近提交，锁定 A 线前序改动范围。
2. 选取最高风险回归点（阶段契约字段在拒绝路径是否稳定）。
3. 新增 1-2 个关键回归测试。
4. 运行最小验证链（单测 + 语法检查）。
5. 文档沉淀并更新索引。
6. 本地提交里程碑（不 push）。

### 实际执行偏差
- 偏差：无功能偏差。
- 微调：验证链中先执行了 `py_compile` 再执行目标 pytest；pytest 因本地依赖环境缺失触发 skip（非 fail），因此将结果明确记录为“可执行但当前环境未满足依赖门槛”。

## 3) 改动文件清单与关键设计点

## 改动文件
- `main/backend/tests/unit/test_single_url_ingest_unittest.py`
- `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-A-atomic-plan/02_A-line-round2-stability-regression-2026-03-03.md`
- `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-A-atomic-plan/index.md`
- `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-A-atomic-plan/README.md`
- `development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md`

## 关键设计点
1. **回归测试1：light filter reject 路径的阶段契约稳定性**
   - 在已有 `test_ingest_single_url_light_filter_rejects_and_emits_fields` 中补强断言：
     - `reason_code == static_asset_url`
     - `reason_category == technical`
     - `stage_context.run_id == job_id`
     - `stage_context.reason_code == static_asset_url`
   - 目的：确保“拒绝原因字段 + 阶段上下文”不会在后续重构中丢失。

2. **回归测试2：pre-fetch gate reject 路径的 reason 归一化与分类稳定性**
   - 新增 `test_ingest_single_url_pre_fetch_gate_exposes_stage_contract_fields`：
     - 验证 pre-fetch URL gate 被拒绝时，`reason_code` 经 alias 归一后为 `domain_blocked`
     - `reason_category == policy`
     - `stage_context.run_id/reason_code/degradation_flags` 与主结果一致
     - 且该路径下不触发网络抓取（`fetch_html` 未调用）
   - 目的：锁定“策略拒绝路径”的契约与短路行为。

## 4) 测试命令与 pass/skip/fail 结果

## 命令
1. 语法检查：
```bash
python3 -m py_compile tests/unit/test_single_url_ingest_unittest.py app/services/ingest/single_url.py
```

2. 相关单测（最小链路）：
```bash
python3 -m pytest -q tests/unit/test_single_url_ingest_unittest.py tests/unit/test_meaningful_gate_unittest.py
```

## 结果
- `py_compile`：**PASS**（无输出，成功返回）
- `pytest`：**SKIP=42 / FAIL=0 / PASS=0**
  - 原因：测试文件含依赖门槛检查，当前环境缺少后端依赖，触发 `SkipTest`。
  - 结论：当前环境下未出现回归失败信号；完整有效性需在依赖齐全环境复跑。

## 5) 回滚点 commit

- 本轮回滚点：`35b89b8`

## 6) 剩余风险与下一轮建议

## 剩余风险
1. 当前执行环境导致相关单测整体 skip，尚未在“依赖齐全环境”获得 pass 级别确认。
2. 阶段契约字段目前通过单测锁定拒绝路径；成功写入路径（含复杂 fallback 组合）仍可继续补全覆盖。

## 下一轮建议
1. 在完整后端依赖环境复跑本轮测试并收集 pass 证据。
2. 增加 1 个成功路径契约回归测试（例如 search_expand 成功插入后的 `reason_code=ok`、`stage_context` 完整性）。
3. 将契约字段校验提升为参数化测试，减少路径扩展时的漏测概率。
