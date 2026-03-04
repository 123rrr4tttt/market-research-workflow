# API Versioning Policy (R8.1-A)

## 1) Compatibility window
- 每个 `vN` 主版本至少维持 **2 个小版本窗口**兼容（例如 v1.4 -> v1.6）。
- 破坏性变更必须先在 `vN+1` 预发布版本灰度，不得直接覆盖旧版本路由。

## 2) Deprecation policy
- 弃用分三阶段：
  1. `announce`（公告）
  2. `dual-run`（双轨兼容）
  3. `remove`（移除）
- 每个阶段必须记录开始/结束日期、owner、回滚条件。

## 3) Migration announcement template
- API: `<name>`
- Old version: `<vN>`
- New version: `<vN+1>`
- Breaking changes: `<list>`
- Migration guide: `<link>`
- Rollback trigger: `<metric threshold>`
- Owner: `<team/service owner>`

## 4) Rollback guardrails
- 必须存在 kill switch（默认关闭新行为）。
- 回滚指令必须在发布单中可直接执行。
