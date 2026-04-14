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
