# 数据库工程化最佳实践检索（E-db 第1轮）

日期：2026-03-03 PST  
范围：schema 演进、迁移、索引、连接池、观测

## 联网来源（官方优先）

1. SQLAlchemy Pooling（连接池）  
   https://docs.sqlalchemy.org/en/20/core/pooling.html
2. Alembic Cookbook（迁移策略）  
   https://alembic.sqlalchemy.org/en/latest/cookbook.html
3. PostgreSQL CREATE INDEX（索引策略）  
   https://www.postgresql.org/docs/current/sql-createindex.html
4. PostgreSQL Monitoring Statistics（数据库观测）  
   https://www.postgresql.org/docs/current/monitoring-stats.html
5. Azure Architecture - Monitoring（应用侧观测实践）  
   https://learn.microsoft.com/en-us/azure/architecture/best-practices/monitoring

## 可复用结论（沉淀为本项目基线）

### 1) Schema 演进
- 采用**前向兼容、可回滚**迁移：新增字段/索引优先，避免破坏式 DDL。
- 对多 schema/多租户场景，迁移脚本需具备**schema 发现与循环执行能力**。
- 为高频业务表增加索引时，优先与查询模式一一对应（过滤字段 + 排序字段）。

### 2) 迁移管理
- Alembic 迁移保持**原子化**（每个 revision 聚焦单一变更意图）。
- 迁移应具备幂等保障（`IF NOT EXISTS`/存在性检查），便于跨环境重复执行。
- downgrade 至少保证结构回退可执行；复杂数据回退需文档化风险。

### 3) 索引策略
- 高价值索引优先：
  - 任务表：`status + started_at desc`（状态筛选 + 最近任务）
  - 外部跟踪：`external_provider + external_job_id`
  - 文档检索：`status + publish_date desc`
- 仅对有明确查询命中场景的列建索引，防止写放大与膨胀。

### 4) 连接池策略
- 默认配置可运行，但应暴露为环境变量，支持按环境调整：
  `pool_size / max_overflow / timeout / recycle / pre_ping / connect_timeout`
- 本地与容器环境保留不同兜底参数（本地偏快速失败，线上偏吞吐稳定）。

### 5) 观测与健康检查
- health/deep 除了连通性，还应包含**延迟与连接池状态**。
- 数据库池指标建议最小暴露：`size/checkedin/checkedout/overflow/status`。
- 与应用指标统一到 `/metrics` + `/health/deep` 双通道。

## 本轮落地对照
- [x] 迁移脚本：新增数据库性能索引 revision
- [x] 连接池：参数模板化（Settings + .env.example）
- [x] 健康检查：deep health 增加 DB/ES 延迟和 DB pool 状态
- [x] 文档沉淀：本文件 + 原子任务表 + 封口文档
