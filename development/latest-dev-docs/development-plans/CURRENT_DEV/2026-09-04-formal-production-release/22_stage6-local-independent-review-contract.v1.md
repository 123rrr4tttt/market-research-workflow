# Stage 6：本地独立验收合同

- Supervisor: `01a0748b-be3b-7da2-9cb2-4160756bf10b`
- Executor: `01a09a90-da93-7a31-ae01-dff45a5b8a4a`
- Status: `DISPATCHED_LOCAL_STAGE6`
- Scope: `LOCAL_INDEPENDENT_REVIEW / NOT_AUTHORITY / RELEASE_DEFERRED`

## 1. 输入与范围

用户已授权顺序完成本地 Stage 4–6，完成本阶段后停止，不启动 Stage 7–9。Stage 4 和 Stage 5 已获监督本地验收；这不是正式发布资格。

读取 AGENTS、19流程规则、06当前入口和本合同。Stage 4 输入在本合同目录 `stage4-evidence/`；Stage 5 输入在**仓库根** `stage5-evidence/`，读取主结果、INDEX、RUNBOOK及SHA256SUMS。Stage 5最终交付是 Stage 4镜像加明示source overlay，不冒称原镜像已包含新代码。RUNBOOK的20项source/config摘要明确最终输入与实际依赖。

## 2. 独立审核内容

1. 核对本地阶段条件到已有真实证据的覆盖，重算相关源码、制品、配置和证据摘要；准确区分原r13x、派生镜像、工作树overlay及不同时点的执行。已清理旧镜像只保留历史证据，不假装旧字节仍在。
2. 核对Stage 4实际效果、actor/scope/approval/writer、版本冲突、TERMINAL/replay及拒绝路径；核对Stage 5真实collector/worker链、指标来源、告警与恢复、备份数据不变量、迁移失败恢复和回滚无重复effect。优先复核已有原始结果与实现，不默认全量重跑。
3. 保留并核对明确上限：provider故障为本地模拟；外部投影sink未调用；恢复数据为合成任务数据；RPO/RTO为单次本地测量；独立进程receipt恢复探针不等于HTTP生产controller恢复；无有效production receipt时fail-closed不作为要求生产授权的理由。runtime-health gauge可能保留最后一次样本，当前UNKNOWN以alert-state解释，不冒称即时健康。
4. 核对运行/恢复说明实际可用、最终输入可定位、凭据不进入证据。仅对发现的明确缺口作最小只读诊断或focused验证，允许任务专属临时资源，不重复Stage 3双重构建、安全全套或Stage 4/5矩阵。无新增证据不扩测。

## 3. 自主修复与独立性

原Stage 5任务 `01a099f6-8ee3-7371-8e3b-91b8ebebac79` 正在按19清理无依赖旧产物，保留本阶段复核/恢复输入。冲突按具体文件/资源协调，不整体停工。

普通文档/路径/脱敏等小修复可原地处理，记录改动并只核对影响面。实质产品问题一次集中回传原owner修复，复核受影响部分，不因单个字段重返Stage1/2或重建整个候选链。自改产品逻辑不得称为独立验证，需另一个有界reviewer复核受影响部分。

不修改冻结04/r13x，不补远端CI、registry、签名、发布manifest完整R2、生产晋升或canary；这些后置事项不是本地验收blocker，也不写成已通过。不得全局prune或读取/删除其他任务数据。不得创建新监控/审批平台。

## 4. 输出与停止

产物在仓库根 `stage6-evidence/`：一个独立审核主结果、必要发现/证据索引和本地交付摘要即可。结果为 `PASS_LOCAL_STAGE6_INDEPENDENT_REVIEW_NOT_AUTHORITY` 或准确负状态，不使用 `FORMAL_RC_READY` 冒称正式发布资格。

必须向监督发送 `STAGE_RESULT(stageId:S6)`、主结果/索引路径、核验范围、实际命令/结论、改动和剩余边界。以完成整个Stage6为目标，普通进度不停等；同阶段返工留在本任务。审核通过后按19清理本阶段无用中间产物并保留必要本地交付/恢复输入，报告实际空间变化。Stage6完成后停止，不派发后续阶段。
