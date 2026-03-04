# SA3-R3 F线路执行记录（Data/AI Governance）

## 1. 参考包消费与映射
- 采用参考包（仓内可解析，按时间新到旧）：
  - `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-04-sa3-r3-f-llm-report-must-minset/01_sa3-r3-f-implementation-2026-03-04.md`（2026-03-04 00:21:24 PST）
  - `docs/implementation/SA3-R3-F.md`（2026-03-04 00:22:36 PST）
  - `development/latest-dev-docs/root-plans/F_PLAN/llm-report-best-practices-2026-03-03.md`（2026-03-03 23:16:44 PST）
  - `main/backend/docs/version-F-llm-report-delivery-2026-03-03.md`（2026-03-03 23:16:59 PST）

> 说明：当前目录未发现显式 `reference_pack.md` / `research_note.md`，因此以上述 F 线文档作为参考包代理。

### 映射说明
- F线 Must：
  - 数据/特征/模型/评估版本化与可追溯 -> 映射到治理基线文档“四件套”
  - 上线门禁（离线+在线+回滚） -> 映射到治理基线文档门禁章节
  - 高风险审计与人工复核 -> 映射到治理基线文档高风险控制章节

## 2. Repo-level 映射
- 项目入口与测试/CI说明：`README.md`
- CI 门禁流水线：`.github/workflows/backend-tests.yml`
- 后端文档目录：`main/backend/docs/`

## 3. 最小实现
新增：
- `main/backend/docs/AI_GOVERNANCE_MIN_BASELINE.md`

内容包括：
- 版本化追溯最小集合
- 上线门禁最小要求
- 高风险审计/人工复核要求
- 参考标准映射与假设

## 4. 验证结果
已在当前会话本地执行：
```bash
python3 main/backend/scripts/check_llm_report_must_minset.py
cd main/backend && python3 -m pytest -q tests/unit/test_llm_report_generator_unittest.py tests/unit/test_llm_report_api_unittest.py
```

结果：
- `check_llm_report_must_minset.py`：`11 passed, 9 skipped`
- 目标单测集合：`11 passed, 9 skipped`

## 5. 回滚点
- 当前仓库 `HEAD`：`c4f89bfc9f8bfd60ed793d56c11d2e87cc4c3a67`
- 精确回滚（仅本次文档）：
```bash
git checkout -- main/backend/docs/AI_GOVERNANCE_MIN_BASELINE.md docs/implementation/SA3-R3-F.md
```
