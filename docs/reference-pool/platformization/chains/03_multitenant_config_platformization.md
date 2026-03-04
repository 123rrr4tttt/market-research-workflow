# 链路3：Multi-tenant & Config Platform 平台化参考池

## 仓库链接
- 当前仓库（本机路径）：`/Users/wangyiliang/market-research-workflow`
- 当前工作副本：`/Users/wangyiliang/market-research-workflow-parallel-20260303-215619`

## 1) 现状痛点（context fallback, env写入）

### 1.1 多租户上下文（`main/backend/app/services/projects/context.py`）
- `current_project_key()`在`ContextVar`无值时，直接回退`settings.active_project_key`，属于“全局默认租户兜底”。
- `_normalize_project_key()`在输入为空/非法时，也会回退到`settings.active_project_key`或`default`。
- `project_schema_name()`按前缀拼接 schema，`public`被特殊保留，但未见显式“强制租户存在校验 + 请求级身份绑定”闭环。

痛点：
- fallback 语义过强，容易将“缺失租户上下文”静默转为“默认租户读写”。
- 以字符串规范化 + schema 拼接为核心，缺少租户目录（tenant registry）和状态（启用/冻结/删除）约束。
- 若后续接入细粒度授权，当前上下文对象不足以承载 `subject/user`、`tenant`、`resource`、`action` 四元组。

### 1.2 配置与 Secret 管理（`main/backend/app/api/config.py` + `settings_manager.py`）
- `/config/env` 提供读取；`POST /config/env` 可写入`.env`（`set_key`）并同步到`os.environ`，然后`reload_settings()`。
- `EnvSettingsPayload`中包含大量敏感字段（如`OPENAI_API_KEY`、`AZURE_API_KEY`等）。
- `.env`路径固定在`backend/.env`，更新策略是“应用层 API 直接改文件 + 进程内热重载”。

痛点：
- Secret 以明文写入`.env`，缺少专用 secret backend、版本化、轮转与审计。
- 运行时配置与部署配置耦合，难以区分“租户级配置、环境级配置、实例级配置”。
- 缺少最小权限边界：谁可改哪些 key、是否按租户隔离、是否可审计回滚。

### 1.3 部署侧配置注入（`main/ops/docker-compose.yml`）
- backend/worker 通过 `env_file + environment` 注入变量，默认值覆盖逻辑分散。
- compose 未体现统一密钥来源（如 Vault Agent、External Secrets、SOPS 渲染）链路。

痛点：
- 配置来源多头（`.env`、compose 默认值、进程内环境），最终值可解释性弱。
- 难以在多环境/多租户场景稳定复用，且 secret 生命周期管理缺位。

## 2) 开源替代方案（3-5个）

以下给出 5 个可组合方案池（满足 Keycloak/ORY、Vault/SOPS、OpenFGA/Casbin 覆盖）：

1. 方案A（偏企业标准）
- 身份：Keycloak（OIDC/SAML、组织与组管理）
- Secret：HashiCorp Vault（KV v2 + dynamic secret + audit）
- 授权：OpenFGA（关系模型，适合多租户 ReBAC）
- 配置：保留现有 settings，新增“配置元数据表 + 租户覆盖表”

2. 方案B（云原生轻量）
- 身份：ORY Kratos + ORY Hydra（身份与 OAuth2/OIDC 分治）
- Secret：SOPS + KMS（GitOps 加密文件）
- 授权：Casbin（RBAC/ABAC，内嵌策略执行）
- 配置：以数据库配置中心为主，SOPS 只管敏感基线

3. 方案C（K8s 友好）
- 身份：Keycloak
- Secret：Vault + External Secrets Operator
- 授权：OpenFGA
- 配置：ConfigMap/DB 双层，应用只读聚合视图

4. 方案D（成本敏感）
- 身份：ORY（自托管最小组件）
- Secret：SOPS（age/GPG）
- 授权：Casbin
- 配置：数据库配置中心 + 发布版本号

5. 方案E（渐进改造）
- 身份：先接入 Keycloak（仅认证）
- Secret：先上 SOPS（替代明文 `.env`）后续演进 Vault
- 授权：先 Casbin（应用内）后续迁 OpenFGA（外置服务）

推荐基线：
- 中长期：`Keycloak + Vault + OpenFGA`
- 短平快：`Keycloak/ORY + SOPS + Casbin`

## 3) 身份-租户-权限-配置 目标架构

```text
[User/Service]
   -> OIDC Login (Keycloak/ORY)
   -> JWT(含 subject, tenant claims, roles)
   -> API Gateway / Backend
      1) 认证：校验JWT签名与过期
      2) 租户解析：从claim/header/path提取tenant_id（禁止静默fallback）
      3) 授权：OpenFGA/Casbin 判断 subject 对 resource/action 是否允许
      4) 配置解析：
         - Base Config（环境级）
         - Tenant Overlay（租户级）
         - Runtime Override（受控、可审计）
      5) Secret 获取：Vault/SOPS解密后注入进程内短生命周期缓存
   -> DB schema/row policy + downstream services
```

关键原则：
- 无 tenant 上下文即拒绝（4xx），不落默认租户。
- Secret 与普通配置分离存储、分离权限、分离审计。
- 配置读取“可回放”：任一请求可追溯读取到哪个版本的配置。
- 权限决策外置或策略化，避免散落在业务 if/else。

## 4) 代码/IO映射与最小改造路径

### 4.1 映射（现状 -> 目标）
- `services/projects/context.py`
  - 现状：`ContextVar(project_key/schema)` + `settings.active_project_key` fallback
  - 目标：`TenantContext(subject, tenant_id, roles, trace_id)`；无 tenant 则报错
- `api/config.py`
  - 现状：可通过 API 直接更新 `.env`
  - 目标：拆分为
    - `Config API`（非敏感 + 租户级）
    - `Secret Ref API`（仅引用，不回传明文）
- `services/settings_manager.py`
  - 现状：`dotenv_values/set_key/os.environ/reload_settings`
  - 目标：`ConfigProvider`（DB/文件）+ `SecretProvider`（Vault/SOPS）抽象层
- `ops/docker-compose.yml`
  - 现状：`env_file + environment` 混合注入
  - 目标：仅保留基础非敏感环境变量；敏感值改为启动时拉取或 sidecar 注入

### 4.2 最小改造路径（建议 4 步）
1. 第一步：租户上下文收敛
- 在请求入口新增 tenant 解析中间件。
- `current_project_key()` 改为“缺失则抛错”，仅在离线任务允许显式默认租户。

2. 第二步：配置与 secret 解耦
- 将 `ENV_KEY_MAPPING` 拆分成 `PUBLIC_CONFIG_KEYS` 与 `SECRET_KEYS`。
- `/config/env` 禁止直接写 secret 明文，改写为 secret 引用（如 `vault://path#key`）。

3. 第三步：引入策略授权
- 管理接口（配置更新、secret 绑定）前置 Casbin/OpenFGA 鉴权。
- 审计日志记录：操作者、tenant、key、旧值摘要、新值摘要、request_id。

4. 第四步：部署注入标准化
- compose/运行脚本移除关键 secret 默认值。
- 改为启动时从 Vault/SOPS 渲染临时环境，定期轮转。

## 5) 迁移风险与验证清单

### 5.1 主要风险
- 风险1：去掉 fallback 后，历史调用链未传 tenant 导致大量 4xx。
- 风险2：secret 从 `.env` 迁移后，启动时序与权限配置错误导致服务不可用。
- 风险3：授权引擎接入初期策略不完整，出现误拒绝或越权。
- 风险4：多来源配置并存阶段，读取优先级不清导致行为漂移。

### 5.2 最小验证清单（上线前）
- 租户隔离
  - 无 tenant 请求必须失败；错误码与错误体稳定。
  - tenantA 凭证不得访问 tenantB 的配置与数据。
- 配置正确性
  - 同一 key 在 base/tenant/override 层的优先级符合设计。
  - 配置版本可追溯（请求日志可定位配置版本）。
- Secret 安全
  - API/日志/审计中不出现明文 secret。
  - Secret 轮转后服务可无损切换。
- 权限控制
  - 管理员、租户管理员、只读角色的权限边界测试通过。
  - 至少覆盖“允许/拒绝/跨租户拒绝”三类策略回归。
- 回滚能力
  - 配置发布失败可一键回滚到前一版本。
  - 身份或授权服务不可用时有明确降级策略（fail-close/fail-open 需显式选择）。

## 附：开源项目参考链接
- Keycloak: https://www.keycloak.org/
- ORY: https://www.ory.sh/
- HashiCorp Vault: https://www.vaultproject.io/
- SOPS: https://github.com/getsops/sops
- OpenFGA: https://openfga.dev/
- Casbin: https://casbin.org/
