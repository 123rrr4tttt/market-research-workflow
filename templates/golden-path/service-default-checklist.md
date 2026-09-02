# Golden Path Service Default Checklist (R9 E)

## Rollback
- [ ] 发布脚本包含一键回滚命令与回滚前置校验
- [ ] 明确回滚责任人与触发阈值（错误率/延迟/SLO burn-rate）

## Observability
- [ ] 默认输出 trace_id / span_id / service / env / error.code
- [ ] 核心旅程具备链路追踪与告警跳转 runbook

## Security Gate
- [ ] 依赖扫描 + secret 扫描为必经门禁
- [ ] 发布制品具备签名/验签策略（验签失败阻断发布）

## DORA Hooks
- [ ] 发布流水线自动写入 lead_time / deploy_frequency / CFR / MTTR
- [ ] 发布后自动生成回看链接与行动项

## Migration / Semantic Preservation
- [ ] 迁移/重构/successor/backend replacement/code generation 已建立 legacy/donor semantic movement inventory（文件数/测试数不是完整性）
- [ ] 每条 movement 含 source object / target object / named transformation / owner / effect / failure / resource / authority / recovery / projection-loss / source evidence / target realization / acceptance trace
- [ ] disposition 使用标准枚举且 `UNASSIGNED_BLOCKER = 0` 才允许 promotion / retirement
- [ ] 已有旧端到端 trace 到新 trace 的结构保持验证、一个失败/反向返回 case、以及 declared loss 或 zero-loss 声明
- [ ] 未接线/contract-only 能力已明确落位或拒绝，不因缺少 live owner 被删除
- [ ] review 同时覆盖 declared-scope correctness 与 predecessor-to-successor completeness
- [ ] 遵守 [semantic-movement-completeness-standard.md](../../docs/governance/semantic-movement-completeness-standard.md)

## Mechanical Implementation Routing
- [ ] IO 契约固定后的机械化开发默认路由给 DeepSeek（批量实现/机械重构/样板/测试生成/文档同步/格式化/确定性序列化与哈希脚本）
- [ ] 每个 DeepSeek 包声明目标/输入/输出/允许读写/验收，固定回传结果/改动文件/验证/风险
- [ ] 主线 reviewer 负责架构、semantic movement inventory/matrix、normative/frozen authority、风险接受、promotion、整合与最终审核
- [ ] DeepSeek 不修改 frozen semantics、不决定 authority/cutover/promotion、不把绿色测试当完成
- [ ] 机械生成先通过 semantic movement completeness gate
