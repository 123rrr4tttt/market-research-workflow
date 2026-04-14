# B线第5轮（R5）Repo-Level 映射与实施记录

更新时间：2026-03-04 PST

## 最新参考包选择依据
1. `docs/reference-pool` 不存在（已检索）。
2. 使用 `docs/knowledge-pool/CURRENT_DEV/2026-03-03-B-line-round5-streamplus` 作为最新批次参考包。
3. 该批次包含 `references.md / patterns.md / adoption-checklist.md / anti-patterns.md`，并与本轮目标一致。

## Repo-Level 映射（模块 -> 职责 -> 依赖 -> 现状差距）
| 模块 | 职责 | 关键依赖 | 现状差距 |
|---|---|---|---|
| `main/backend` | API、服务编排、数据处理、任务执行 | FastAPI、pytest、DB/任务服务 | 门禁脚本对环境路径耦合；兼容策略审计字段缺失 |
| `main/frontend` + `main/frontend-modern` | 旧版模板与现代前端并存 | 后端路由与静态资源 | 双轨过渡导致行为一致性成本高（本轮不改） |
| `scripts/` | 根级运维与测试入口 | shell、docker、backend scripts | R5 计划中的 `scripts/safe-test.sh` 缺失，导致 T5 gate 不可执行 |
| `scripts/orch` | 轮次编排与下一轮草案生成 | `state/runs`、`artifacts/runs` | 缺少统一 safe gate 调度 |
| `docs/*` + `development/latest-dev-docs/*` | 开发文档沉淀与索引导航 | INDEX/README/MERGED_OVERVIEW | R5 映射与实施结果未入索引 |

## 简版实施清单（先清单后实施）
- [x] 新增 `scripts/safe-test.sh`，补齐 T5 门禁入口。
- [x] 增强 `main/backend/scripts/gateplus_ci_guard.sh`：`GATEPLUS_COMPAT_LEVEL`（`BACKWARD|FULL`）+ 审计字段落盘。
- [x] 更新 `main/backend/tests/unit/test_gateplus_ci_guard_unittest.py` 覆盖新增配置校验。
- [x] 更新 `.github/workflows/backend-tests.yml`，显式注入兼容级别并展示审计信息。
- [x] 运行格式/静态检查、单测/关键脚本、smoke 验证。

