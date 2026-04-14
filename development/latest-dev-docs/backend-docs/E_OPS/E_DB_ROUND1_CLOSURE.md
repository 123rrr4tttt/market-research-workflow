# E-db 第1轮封口文档（数据库线）

工作副本：`/Users/wangyiliang/market-research-workflow-parallel-20260303-215619-E-db`  
基线分支：`feature/version-C-streamplus`  
当前分支：`feature/version-E-db`

## 交付清单

1. **数据库最佳实践检索与知识沉淀**
   - `DB_BEST_PRACTICES_RESEARCH_2026-03-03.md`
2. **原子任务表**
   - `DB_ATOMIC_TASKS_E1.md`
3. **最小数据库工程化增强**
   - 迁移脚本：`migrations/versions/20260303_000006_db_perf_indexes_and_observability.py`
   - 连接池模板化：`app/settings/config.py` + `.env.example`
   - 健康检查增强：`app/main.py` + `app/models/base.py`
   - 观测探针脚本：`scripts/db_observability_probe.py`

## 验证结果

- `python3 -m py_compile` 已通过：
  - `app/settings/config.py`
  - `app/models/base.py`
  - `app/main.py`
  - `migrations/versions/20260303_000006_db_perf_indexes_and_observability.py`
- 迁移脚本为幂等（`IF NOT EXISTS` + 表存在检查）。

## 差异化声明（去重清单 + 独特点）

### 与 A/B/C/D/F/G 其他线去重策略
- **不重复实现** UI、采集策略、业务流程编排、提示词工程等非 DB 核心改动。
- 对可能重叠的健康检查能力：
  - 若其他线已改动基础 health 路由，E 线仅补充**数据库池状态/延迟观测字段**，不复制其业务逻辑。
- 对可能重叠的性能优化：
  - E 线仅做**数据库层索引与连接池工程化**，其他层优化统一引用对应线成果，不平移代码。

### E-db 独特点（满足“至少两项不同”）
1. **目标差异**：聚焦“数据库可运营性/可观测性”，而非功能扩展。  
2. **架构差异**：新增 DB pool 状态暴露（health/deep details）+ 独立 DB 观测探针脚本。  
3. **关键模块差异**：新增数据库迁移 revision（索引策略）与连接池参数模板化体系。  
4. **验证指标差异**：使用 DB ping 延迟、pool checkedout/overflow、seq_scan 热表观测作为首轮指标。

## 后续建议（第2轮）

- 加入 `EXPLAIN (ANALYZE, BUFFERS)` 基线样例并落库为回归基准。
- 引入慢查询采样（应用层阈值日志 + pg_stat_statements）。
- 对高写入表评估部分索引/并发建索引策略（生产窗口执行）。
