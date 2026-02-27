# 后端文档索引

> 最后更新：2026-02-27

本目录存放 `main/backend` 的设计说明、接口规范、配置指南与阶段性研究资料。

---

## 目录

1. [快速入口](#1-快速入口)
2. [按角色阅读](#2-按角色阅读)
3. [架构与接口](#3-架构与接口)
4. [数据摄取](#4-数据摄取)
5. [数据模型与图谱](#5-数据模型与图谱)
6. [第三方配置](#6-第三方配置)
7. [设计文档](#7-设计文档)
8. [归档](#8-归档)

---

## 1. 快速入口

| 文档 | 说明 |
|------|------|
| [../API接口文档.md](../API接口文档.md) | API 完整参考（含规范与补充接口） |
| [DOC_MERGE_PLAN.md](DOC_MERGE_PLAN.md) | 文档合并与归档记录 |

---

## 2. 按角色阅读

**开发**：接口层调查 → API 规范 → 数据库说明 → 摄取架构

**配置/运维**：第三方配置（Reddit/Twitter）→ 数据摄取内容

**图谱相关**：社交平台图谱生成标准 → 社交平台内容图谱API → 政策数据结构

**设计/重构**：UNIFIED_COLLECT → LOTTERY_DECOUPLING → STRUCTURED_VS_GRAPH

---

## 3. 架构与接口

| 文档 | 说明 |
|------|------|
| [接口层调查文档.md](接口层调查文档.md) | 后端/前端/内部接口分层与路由清单 |
| [API_CONTRACT_STANDARD.md](API_CONTRACT_STANDARD.md) | API 响应与错误码规范（已并入 API接口文档 第 0 节） |

---

## 4. 数据摄取

| 文档 | 说明 |
|------|------|
| [INGEST_ARCHITECTURE.md](INGEST_ARCHITECTURE.md) | 摄取架构与流程总览 |
| [INGEST_DATA_SOURCES.md](INGEST_DATA_SOURCES.md) | 数据源能力与选型 |
| [数据摄取内容.md](数据摄取内容.md) | 采集任务清单草稿 |
| [文档去重逻辑说明.md](文档去重逻辑说明.md) | 去重逻辑（URI/text_hash） |
| [日期提取与修复总览.md](日期提取与修复总览.md) | 发布日期提取策略与效果 |
| [RESOURCE_POOL_EXTRACTION_API.md](RESOURCE_POOL_EXTRACTION_API.md) | 资源池提取模块接口设计（文档提取 + 任务捕获） |
| [RESOURCE_LIBRARY_DEFINITION.md](RESOURCE_LIBRARY_DEFINITION.md) | 信息资源库定义（item、channel、来源采集） |
| [RESOURCE_LIBRARY_IMPLEMENTATION_PLAN.md](RESOURCE_LIBRARY_IMPLEMENTATION_PLAN.md) | 信息资源库功能实现计划 |
| [政策可视化数据校验与实时性说明.md](政策可视化数据校验与实时性说明.md) | 统计一致性与热力图实时性 |

---

## 5. 数据模型与图谱

| 文档 | 说明 |
|------|------|
| [数据库说明文档.md](数据库说明文档.md) | 数据库结构（含扩展表） |
| [政策数据结构说明.md](政策数据结构说明.md) | 政策数据结构 |
| [社交平台图谱生成标准文档.md](社交平台图谱生成标准文档.md) | 图谱系统标准与架构 |
| [社交平台内容图谱API.md](社交平台内容图谱API.md) | 社交图谱 API 文档 |

---

## 6. 第三方配置

| 文档 | 说明 |
|------|------|
| [REDDIT_API_SETUP.md](REDDIT_API_SETUP.md) | Reddit API 配置 |
| [REDDIT_API_LIMITS.md](REDDIT_API_LIMITS.md) | Reddit API 限制 |
| [TWITTER_API_SETUP.md](TWITTER_API_SETUP.md) | Twitter/X API 配置 |

---

## 7. 设计文档

| 文档 | 说明 |
|------|------|
| [UNIFIED_COLLECT_ARCHITECTURE.md](UNIFIED_COLLECT_ARCHITECTURE.md) | 统一采集架构（横向/纵向） |
| [STRUCTURED_VS_GRAPH_ALIGNMENT.md](STRUCTURED_VS_GRAPH_ALIGNMENT.md) | 结构化提取与图谱元素对齐 |
| [LOTTERY_DECOUPLING_INVENTORY.md](LOTTERY_DECOUPLING_INVENTORY.md) | 彩票耦合点清单（解耦基线） |

---

## 8. 归档

阶段性报告与历史版本，按主题分类：

| 目录 | 内容 |
|------|------|
| [archive/date-extraction/](archive/date-extraction/) | 日期提取排查、修复对比、残余分析 |
| [archive/ingest-research/](archive/ingest-research/) | 数据源发现与抓取适配器调研 |
| [archive/ingest-architecture/](archive/ingest-architecture/) | 摄取流程图与深度分析原始版 |
| [archive/policy-visualization/](archive/policy-visualization/) | 政策统计与热力图检查报告 |
| [archive/social-retrospectives/](archive/social-retrospectives/) | 社交平台数据获取流程反思 |
| [archive/testing-reports/](archive/testing-reports/) | 测试结果与验证报告 |
| [archive/graph-specs/](archive/graph-specs/) | 图谱数据结构历史规范 |

## 9. 第8节路线追踪（readme-8x）

以下文档用于同步 `README.md#8-进一步开发规划` 的实施状态：

| 文档 | 说明 |
|------|------|
| `../README.md` | 根目录“进一步开发规划”主表（含状态与下步动作） |
| `../../plans/status-8x-2026-02-27.md` | 第8节执行清单（owner / 证据 / 验收） |
| `../../plans/8x-multi-agent-kickoff-2026-02-27.md` | 多智能体启动稿（角色边界与执行规则） |
| `../../plans/8x-round-1-2026-02-27.md` | 第1轮执行记录（任务卡 + 验收前置） |
| `../../plans/8x-round-2-2026-02-27.md` | 第2轮执行记录（P0 优先项） |
| `../../plans/8x-round-2-2026-02-27-taskboard.md` | 第2轮任务看板（8.2/8.5/8.6） |
| `../../plans/decision-log-2026-02-27.md` | 关键决策与执行边界记录 |
| 状态枚举 | `planned / in_progress / partial / blocked / done` |
| `UNIFIED_SEARCH_ENHANCEMENT_PLAN.md` | 统一搜索增强计划（与 8.1 的细化工作相关） |
| `DOC_MERGE_PLAN.md` | 阶段性文档归并记录 |
| `RESOURCE_LIBRARY_IMPLEMENTATION_PLAN.md` | 资源库执行计划（含当前占位项） |
