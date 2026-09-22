# Successor 生产安全清单

> 状态：`CHECKLIST_DOCUMENTED`。逐项依据候选源码/仓库结构核对；凡未在真实环境执行或缺少证据的项明确标为“待真实环境验证/未满足”。本轮没有创建 `.env`、没有 provider 凭据、没有运行生产栈。

状态图例：

- `满足`：候选字节或仓库文件可证明。
- `部分/待验证`：存在机制，但生产有效性未验证。
- `缺口`：候选/仓库当前没有对应实现或配置。

## 本轮执行记录（2026-09-03，Lane C drills）

本轮在候选 `3706655f` 的干净快照上执行了三项可复现 drill，全部 local-only、零残留；live worktree 当时正被另一条线并发改写（15 个未提交文件），故 drill 未在半成品字节上执行，正式 cutover 前需在 Lane A 收口字节上复跑。

- 真实 rollback drill：compose 独立 project `mrw-alllines-rehearsal`（db/es/redis internal ports，backend 8000/frontend 5174 暴露），cycle 1 start→health→stop→cycle 2 start→health 全部 exit 0/200，teardown `down -v` 后容器/网络/volume 残留 = 0/0/0。wrapper `rollback-drill` 因宿主 5432/6379 占用且不透传 `--force` 而 exit 1（已记录为脚本限制，改用等价 compose 步骤）。
- DB 备份/恢复 drill：disposable local PG `mrw_cutover_drill_backup_20260903`，`alembic upgrade head`（version `20260831_000002`）→ seed `project_scope_registry` → `pg_dump` → drop → recreate → `pg_restore` 校验版本与行恢复成功；另跑 C7 canonical write focused PG `9 passed / 0 failed`。
- DB 迁移 downgrade drill：disposable local PG `mrw_cutover_drill_downgrade_20260903`，`upgrade head` → `downgrade 20260402_000004`（successor 表归零）→ 再次 `upgrade head` 成功。
- 未修改生产代码、真实数据库、compose 业务文件；未 commit/push；无 provider 调用。

环境事实更新（取代上方较早期“本轮 `.env` 不存在”的生成时刻状态）：live worktree 的 `main/backend/.env` 存在且被 `.gitignore` 排除（不入库）；本轮 drill 快照使用 `.env.example` 复制件，不携带真实密钥。

以下缺口在 2026-09-03 之后仍然存在，未被本轮标记为满足：TLS 终结、镜像 digest/tag 固定、Prometheus/Alertmanager 在线告警、secret 与依赖漏洞扫描、生产 successor registry resolver + 端点认证、successor 前端页面接线、计划备份/RPO 自动化、生产 owner/ACL 与 volume 级恢复 drill。

## A. 密钥与凭据管理

| 检查项 | 状态 | 证据/说明 | 生产动作 |
| --- | --- | --- | --- |
| `.env` 不入库 | 满足 | `.gitignore` 明确忽略 `.env`、`.env.local`、`.env.*.local`、`*.credentials.json` 等；仓库只提交 `.env.example` | 保持；用 git 预提交/secret scanner 防回退 |
| 模板不含真实密钥 | 满足 | `main/backend/.env.example` 的 key 值为空或占位 | 真实 key 只放环境注入 |
| 本机存在真实 `.env` | 缺口（本轮） | 实测 `main/backend/.env` 不存在；因此无真实凭据可泄漏，也没有 live provider 可调用 | 部署时由 secret manager/受限文件注入，禁止复制进代码 |
| 密钥不被日志/错误输出 | 部分/待验证 | 请求日志只记录 path/status/duration，不打印 body；但未在真实 provider 调用链路做泄漏扫描 | 日志样例审计 + secret scanner |
| 密钥轮换/吊销 | 缺口 | 未发现轮换脚本或凭据失效测试 | 建立轮换 SOP 与吊销演练 |

## B. Provider 调用与执行边界

| 检查项 | 状态 | 证据/说明 | 生产动作 |
| --- | --- | --- | --- |
| successor 默认不调用 live provider | 满足（默认装配） | `app/successor_runtime/assembly/app_assembly.py` 默认 `local_only_closed_fixture_options`，authority ceiling 全 false | 不要在生产用默认 LOCAL_ONLY 宣称 provider 已上线 |
| wire DTO 不能夹带 authority/execute 字段 | 满足 | `app/contracts/successor_runtime.py` `extra="forbid"` + 挂载测试断言未知控制字段返回 422 且不进 facade | 保留回归测试 |
| actor/scope 由服务端注入 | 满足 | `app/api/successor_runtime.py` `bind_server_command/bind_server_query` | 生产 resolver/actor provider 需单独验证 |
| 生产 registry resolver | 缺口 | `LocalOnlyProjectScopeResolver.resolve_expected` 抛 `ProjectScopeValidationError`，无生产 resolver 实现 | 新 authority 里程碑 |
| legacy 调用边界 | 部分/待验证 | legacy 业务路由存在 provider 调用（`LLM_PROVIDER`/search keys）；候选 successor 不新增调用，但同一 backend 进程共享这些 legacy 能力 | 在真实环境审计出站调用白名单与限额 |

## C. 输入校验与访问控制

| 检查项 | 状态 | 证据/说明 | 生产动作 |
| --- | --- | --- | --- |
| typed payload + discriminator | 满足 | `command_kind` 必须等于 `payload.payload_kind`，`query_kind` 必须等于 `params.params_kind` | 保持 |
| 未知字段拒绝 | 满足 | Pydantic `extra="forbid"`；挂载测试有 `execute=true`/authority 注入被 422 的用例 | 保持 |
| 长度/格式约束 | 满足 | min_length、source digest regex、generation >= 0 等 | 生产 schema 变更需补约束测试 |
| project key 校验 | 满足（默认装配） | resolver `validate_project_key` + schema identifier 负例测试 | 生产 project registry 需真实授权映射 |
| successor 端点认证 | 缺口 | `codex_auth_protected_prefixes` 默认不包含 `/api/v1/successor-runtime`，且 `codex_auth_enabled` 默认 false；`/api/v1/health`、`/metrics` 也不受默认 auth 保护 | 在反向代理加白名单/认证，或显式启用 codex auth 并把前缀加入保护列表后再验证 |
| 授权/审批 | 部分/待验证 | runtime 层有 approval/qualification/authority-grant 表和本地状态机；默认 closed fixture 不执行 | 生产 approval owner 与 actor 映射待里程碑验证 |
| 输入大小/速率限制 | 缺口 | 未发现 rate limit/body size limit 中间件 | 网关层限流，payload 大小上限测试 |
| CORS/浏览器跨域 | 缺口 | 未发现显式 CORS allowlist；正常同源走 Vite/nginx 代理，但直接跨域调用无白名单机制 | 生产网关按域名白名单配置 |

## D. 审计与可观测

| 检查项 | 状态 | 证据/说明 | 生产动作 |
| --- | --- | --- | --- |
| 请求 trace/request id | 满足 | middleware 注入 `X-Request-Id/X-Trace-Id`，日志记录 `request_id/trace_id` | 接 trace collector 验证端到端 |
| 请求级访问日志 | 满足（进程内） | 每请求 `app.request` 日志含 method/path/status/duration/error_code，不含 query secrets | 日志保留策略与脱敏待环境验证 |
| successor 命令/投影审计 | 部分/待验证 | runtime 表含 commit_intent、approval、qualification、receipt 等持久化记录；但没有生产审计导出/只读回放门禁 | 定义审计导出、保留期与读回放验证 |
| 变更审计（文件/部署） | 部分/待验证 | `rollback.sh` snapshot 记录 git head；无 CI/CD 发布审计 | 接入部署审计与 artifact 签名 |
| 安全事件告警 | 缺口 | 未发现 IDS/异常访问告警 | 接入网关/WAF/日志告警 |

## E. 依赖与镜像供应链

| 检查项 | 状态 | 证据/说明 | 生产动作 |
| --- | --- | --- | --- |
| Python 依赖漏洞扫描 | 缺口 | 未发现 pip-audit/safety/dependabot 配置；CI 只跑功能测试 | 部署 CI 加 `pip-audit` 并设阻断策略 |
| 前端依赖扫描 | 缺口 | 未发现 `npm audit` 阻断步骤 | 加 `npm audit --audit-level` |
| 仓库级 secret 扫描 | 缺口 | 未发现 gitleaks/trufflehog 等 | 加 CI secret scanner |
| 镜像 tag 固定 | 缺口 | compose 使用 `latest`/非 digest tag（pgvector、redis、ES、searxng、yacy、scrapyd）；backend/frontend 无 registry image tag | 固定 digest/tag，镜像签名与 SBOM |
| 构建来源可复现 | 部分/待验证 | Dockerfile 从源码构建；无 artifact 校验 | 锁依赖哈希 + 构建日志归档 |

## F. 传输、网络与部署环境

| 检查项 | 状态 | 证据/说明 | 生产动作 |
| --- | --- | --- | --- |
| HTTPS/TLS | 缺口 | compose/nginx 只提供容器内 HTTP，无 TLS 终结 | 生产入口 TLS，cookie `Secure` 置位 |
| OAuth cookie 安全 | 部分/待验证 | `codex_oauth_cookie_secure` 默认 false；生产必须 true | 真实域名/HTTPS 下验证 |
| 数据库默认凭据 | 缺口（生产） | compose 默认 `postgres/postgres` 并映射 5432；ES `xpack.security.enabled=false` | 生产覆盖强凭据与最小端口暴露 |
| successor 端口暴露面 | 部分/待验证 | backend 8000 默认宿主机映射；`/metrics` 与 successor 端点同一面 | 内网隔离，指标端点鉴权/不对外 |
| 资源限额与重启策略 | 部分/待验证 | celery/可选服务有 restart；backend 默认无 restart policy | 生产编排加资源 limit/restart/backoff |
| 依赖数据卷持久化 | 满足（compose 配置） | `db_data`、`es_data` 等 named volume 存在 | 独立备份与恢复演练 |

## G. 优先待办（按风险排序）

1. 为 successor 端点与 `/metrics` 增加真实认证/白名单；当前默认装配不满足生产暴露条件。
2. 生产环境使用强凭据、TLS、最小端口暴露，并去掉 `latest`/未固定镜像。
3. 接入依赖漏洞扫描与 secret scanner（Python/前端/镜像）。
4. 建立 provider 出站白名单、限额与日志脱敏审计；在默认 LOCAL_ONLY 之外新增 authority 里程碑后才能谈 live provider/cutover。
5. 对数据库备份、schema downgrade、镜像回退做真实环境 drill；不要用 `stop-all.sh --volumes` 做回退。
