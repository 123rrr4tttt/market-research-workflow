# B线第7轮封口文档（GatePlus Failure Diagnostics 增强）

- 时间：2026-03-04 00:24 PST
- 关联计划：`08_B-line-round7-plan-and-atomic-task-table.md`

## 1) 目标完成情况

已完成 Round7 目标：
1. 对齐 Round6 既有边界（required check 名称、门禁退出语义、artifact 路径与既有 summary 字段）；
2. 在 guard 脚本中实现结构化失败诊断（failure reasons / actionable hints / root cause code）；
3. 在 CI workflow 中增加 GatePlus diagnostics job summary 输出；
4. 完成成功路径、阈值失败路径、环境预检失败路径验证。

## 2) 本轮实际改动

1. 脚本实现：
   - 修改 `main/backend/scripts/gateplus_ci_guard.sh`
   - 新增 `summary.json` 字段：`status`、`failure_diagnostics`
   - 新增预检失败（`PYTEST_BIN` 缺失）时的结构化 summary 落盘
2. CI 编排：
   - 修改 `.github/workflows/backend-tests.yml`
   - 在 `gateplus-guard-check` 中新增步骤：`Render GatePlus diagnostics to job summary`（`if: always()`）
3. 文档索引：
   - 新增 `08_B-line-round7-plan-and-atomic-task-table.md`
   - 新增 `09_B-line-round7-closure.md`
   - 更新 CURRENT_DEV 与 latest-dev-docs 相关索引

## 3) 可执行验证证据

### 3.1 成功路径

```bash
cd main/backend
./scripts/gateplus_ci_guard.sh
```

关键输出：
- `46 passed, 4 warnings in 1.39s`
- `[gateplus-guard] PASS`
- 产物存在：`.artifacts/gateplus/junit.xml`、`.artifacts/gateplus/summary.json`

### 3.2 失败诊断路径（阈值失败）

```bash
cd main/backend
GATEPLUS_MIN_PASS=999 ./scripts/gateplus_ci_guard.sh
```

关键输出：
- `[gateplus-guard] FAIL: pass<999, got 46.`
- `exit_code=1`
- `summary.json` 关键字段：
  - `status=fail`
  - `failure_diagnostics.root_cause_code=min_pass_not_met`
  - `failure_diagnostics.failure_reasons=['passed count below minimum threshold (46<999)']`

### 3.3 失败诊断路径（环境预检失败）

```bash
cd main/backend
PYTEST_BIN=/tmp/not-found-pytest ./scripts/gateplus_ci_guard.sh
```

关键输出：
- `[gateplus-guard] pytest not found at: /tmp/not-found-pytest`
- `exit_code=2`
- `summary.json` 关键字段：
  - `status=blocked`
  - `failure_diagnostics.root_cause_code=missing_pytest_bin`

### 3.4 Workflow 语法检查

```bash
python3 -c "import yaml;yaml.safe_load(open('.github/workflows/backend-tests.yml','r',encoding='utf-8'));print('workflow yaml ok')"
```

关键输出：
- `workflow yaml ok`

## 4) 兼容性确认

- 保持 `gateplus-guard-check` job 名称不变；
- 保持 guard 脚本失败返回非零退出码；
- 保持 artifact 路径不变；
- 保持 `summary.json` 原有字段不变，仅做增量扩展。

## 5) 风险与后续

- 风险：`failure_excerpt/log_tail` 受 pytest 输出格式影响，后续可加入基于 `junit.xml` 的更稳健解析。
- 后续建议：在 PR 侧增加自动评论机器人，直接消费 `failure_diagnostics` 字段以减少人工排障路径。
