# Version B（GatePlus）第2轮迭代交付记录（可验证可集成）

- 时间：2026-03-03 22:49 PST
- 分支：`feature/version-B-gateplus`
- 目标阶段：从“可运行”提升到“可验证可集成”

## 1) 本轮目标与范围

### 目标
1. 让 `gate_plus/reason_code` 相关测试在本地真实执行通过（非 skipped）。
2. 增加下游 schema 兼容性保护测试，确保新增字段（`gate_plus`）不破坏旧字段消费链路。
3. 保持最小侵入，不改变主业务流程，只修复优先级/兼容性风险点并补齐验证。

### 范围
- 后端 API 聚合侧的 skip reason 提取逻辑。
- 单元测试层（GatePlus + single_url + process fallback）。
- CURRENT_DEV 文档与索引同步。

## 2) 原子任务执行顺序与实际偏差

基于 `01_atomic-task-table-and-sequence.md` 执行：

1. **B-AT-01/G0**：确认分支与工作树状态（通过）。
2. **B-AT-02/03/G1**：本轮不重复改动 gateplus 主实现（已在前序轮次落地）；转入验证闸门。
3. **B-AT-04/G2**：验证 `single_url` 中 `gate_plus` 已接入且不破坏 legacy 输出（通过测试覆盖）。
4. **B-AT-05/G3**：新增兼容性保护测试 + 运行目标测试集。
5. **B-AT-06/G4**：本地 commit 归档 + 结果输出。

### 实际偏差说明
- 偏差点：为实现“真实执行通过（非 skipped）”，先补齐本地测试依赖（`uv pip install -r requirements.txt`），该步骤未在原子表中显式列出，但属于测试可执行前置条件。
- 处理原则：仅环境层补齐，不改业务代码路径。

## 3) 改动文件清单与关键设计点

### 代码改动
1. `main/backend/app/api/process.py`
   - 调整 `_extract_skip_reason` 的 gate 字段优先级：
   - 从 `page_gate -> pre_write_content_gate -> pre_fetch_url_gate -> provenance_gate`
   - 调整为 `page_gate -> pre_fetch_url_gate -> pre_write_content_gate -> provenance_gate`
   - 设计点：当 `pre_fetch` 拦截真实发生时，下游旧消费者应优先获得 pre-fetch 原因，不被 pre-write 非阻断信息覆盖。

2. `main/backend/tests/unit/test_collect_runtime_process_fallback_unittest.py`
   - 新增：`test_process_skip_reason_prefers_legacy_gate_fields_even_with_gate_plus`
   - 设计点：在 payload 同时包含 `gate_plus` 新字段与 legacy gate 字段时，断言 skip reason 解析结果保持 legacy 兼容行为。

### 文档改动
3. `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-B-atomic-plan/02_B-line-round2-verifiable-integrable-delivery.md`（本文件）
4. `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-B-atomic-plan/index.md`
5. `development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md`

## 4) 测试命令与 pass/skip/fail 结果

### 执行命令
```bash
cd main/backend
.venv311/bin/pytest -q tests/unit/test_meaningful_gate_unittest.py tests/unit/test_single_url_ingest_unittest.py tests/unit/test_collect_runtime_process_fallback_unittest.py
```

### 结果
- **pass:** 46
- **skip:** 0
- **fail:** 0
- warnings: 4（均为已知依赖 deprecation warning，不影响本轮门禁结论）

## 5) 回滚点 commit

- 里程碑 commit #1（代码+测试）：`37efbef`
- 里程碑 commit #2（文档+索引）：`c68b537`

## 6) 剩余风险与下一轮建议

### 剩余风险
1. 当前测试集为目标子集验证（GatePlus / single_url / process fallback），尚未覆盖全量回归矩阵。
2. 运行日志存在 LangChain/Pydantic deprecation warning，短期不影响功能，但中期可能在版本升级时放大风险。
3. 本地环境通过补装依赖解锁测试；CI 需确保同等依赖完整性，避免再次出现大量 skipped。

### 下一轮建议
1. 增加一条 contract 级测试：针对 `/process` 对外响应，验证引入 `gate_plus` 后旧字段消费端 schema 不变。
2. 把当前目标测试集纳入 CI 必跑清单，门禁规则设为 `skip==0`（至少对 GatePlus 相关套件）。
3. 计划清理 deprecation 导入（如 `langchain.cache`）并分离为独立低风险维护任务。
