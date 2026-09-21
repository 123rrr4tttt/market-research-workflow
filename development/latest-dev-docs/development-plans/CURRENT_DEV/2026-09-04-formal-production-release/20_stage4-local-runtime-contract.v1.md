# Stage 4：本地隔离运行执行合同

- Date: 2026-09-13
- Supervisor: `01a0748b-be3b-7da2-9cb2-4160756bf10b`
- Executor: `01a0990e-b033-7eb3-98d4-346498d7066b`
- Status: `DISPATCHED_LOCAL_STAGE4`
- Scope: `LOCAL_STAGE4_RUNTIME_ONLY / RELEASE_DEFERRED`

## 1. 准入、目标与顺序

用户已要求按正常流程推进 Stage 4–6，其余阶段暂不考虑。Stage 3 本地交付已验收，输入为 [r13x 本地交付结果](stage3-evidence/r13x/local-delivery/local-stage3-delivery-result.r13x.json) 与 [运行说明](stage3-evidence/r13x/local-delivery/local-runbook.r13x.md)。本指令授予本地隔离 Stage 4 准入，覆盖旧文档中的“Stage 4 尚未准入”，但不授予远端 staging 或生产部署权限。

本阶段目标是使用同一批制品，在任务专属本地环境验证生产配置、权限与完整业务运行，而不只是再次证明容器能启动。按冻结 `04` 第 7 节保留实际本地行为要求；远端发布、CI enforcement、registry、签名与完整发布 R2 不再前置。完成整个 Stage 4 后统一回传，监督验收后才发放 Stage 5；Stage 5 完成后发放 Stage 6，后者仅做本地范围独立验收，不冒称正式发布资格。Stage 7–9 不启动、不准备其发布任务。

## 2. 输入与实现边界

- 必读项目 AGENTS、[19 号流程缩减规则](19_direct-testing-batch-freeze-amendment.v1.md)、06 最新进度及本合同。复用已有 Compose override、业务测试、种子数据、provider composition 和 Stage 3 保留的三角色 tag/OCI/layout；身份从既有结果机器读取，不手抄新的 hash 表。
- 冻结 candidate/replay 和历史证据只读。日常修复在当前项目可写工作树或必要的最小测试副本进行，保留其他任务的改动；直接修复、最小相关测试，不逐修 successor、不退回 Stage 1/2。若真实产品变化必须更新制品，先稳定相关修复，仅重建受影响角色；阶段交付时统一记录最终身份及真实证据复用边界。
- 不重复 Stage 3 的无关全套、安全扫描和双重无缓存构建；只运行当前行为与实际变更需要的检查。普通问题自主修复，进度回传不停等，确定性环境问题不反复重现。

## 3. 本阶段必须完成的本地工作

执行路径遵循 [19 号文档“冗余审查后的执行落实”](19_direct-testing-batch-freeze-amendment.v1.md)：制品/配置预检 → 数据与迁移 → 整栈及权限 → 代表性业务 → 整阶段回传。此顺序不是新增审批点。后段失败只重做受影响步骤及必要下游；复用前核对真实输入与当前状态，失败日志与重试日志分开归属。原任务可对现有 runner 做必要的最小分步修复，不重启有效在途运行、不建设恢复框架；CI/冻结指纹的无关治理不并入本阶段。以下六项实现和退出要求不缩减。

1. 核对现有制品可用性和资源归属，建立唯一 Stage 4 Compose project、网络、端口和卷，不占用他人资源。基于已有已审定种子/合成脱敏数据，在任务数据库创建生产近似数据集，生成任务自有快照并恢复到隔离实例，核对摘要及数据身份；不得连接未知生产库、恢复 Docker 旧备份，合成数据不冒称真实生产快照。
2. 运行 migration fresh/upgrade 必要路径及 schema diff，启动 PostgreSQL、Elasticsearch、Redis、backend、Celery、frontend；验证 worker、API、前端代理和 deep health 在同一环境身份下可关联。Stage 3 旧 deep-health degraded 不当作本阶段配置好密钥的整栈验证。
3. 按已有生产契约验证秘密注入、TLS/secure cookie/CORS/body-size/rate-limit，以及 admin/metrics/health-deep 的认证和网络边界。仅使用 localhost、任务内证书和既有配置完成验证；不签发公网证书、不改域名/DNS。真实实现缺陷就地最小修复，不新建安全平台。
4. 验证项目解析、actor/scope/approval/authority epoch、canonical-write owner，以及 provider allowlist/timeout/retry/quota/日志脱敏。只在隔离租户和任务数据上验证权限，不能用全权限绕过来获得 PASS。
5. 跑已有最小代表性只读业务 journey、successor query，以及本阶段必要的隔离测试写入、readback、idempotency、failure/recovery journey。本次推进授权覆盖任务自有本地测试数据的这些写入与清理，不覆盖生产数据或外部业务写入。Stage 5 的完整监控、备份恢复/回滚演练留到下一阶段，不在此预做全部恢复矩阵。
6. 每项证据关联实际候选/制品/配置/数据库/trace 身份。交付可运行的启动、停止和清理说明，清理任务临时资源；必要保留状态列出 owner、路径和用途，以便 Stage 5 承接，不为清理迫使下一阶段重建。

## 4. 密钥、资源与副作用

### 用户批准的接口批次开放（2026-09-13）

用户要求按 optimistic 思路开放接口并整体推进，不逐微小步骤报批。本合同将其操作化为：本阶段必要业务链路默认继续实现，使用现有版本/expected-base、事务、幂等和冲突拒绝机制兑现一致性；不把 optimistic 解释为先执行未授权副作用、事后补权限，也不新建乐观执行框架。

- 批次目标是闭合第 3 节的代表性业务写入、读回、幂等及失败路径。授权在可写源码中接通已有 successor 命令实现、正确 writer/端口、精确 effect contract 和任务租户 authority/approval 数据，并更新本地派生制品；这不再以“接口原本 blocked”或“需要绑定”为逐项申请理由。
- 以已有 C9 命令链为入口，连同完成实际业务效果所需的既有执行/读取接口一起实现。仅记录命令意图或回执不能冒称 rebuild_projection 已执行；如当前执行器尚有缺口，沿已有职责补齐必要实现，或使用已有能完成相同代表性业务目标的写入链路，不在提交回执处停止。无需把全部 legacy 路由迁移、全部业务类型或未来能力并入本批。
- 只开放实际有实现、精确能力/操作及正确 writer 绑定的相关接口。保留服务端 actor、项目 scope、approval、authority epoch 和并发版本校验；不批量把 blocked 改 admitted、不使用 wildcard grant、不借用 C7 标签冒充 C9 writer。测试授权数据仅覆盖任务自有租户、操作和请求，其他租户/接口仍按原权限处理。
- 正常实现修复、依赖接线、针对性验证和相关镜像更新自主完成，整批稳定后统一回传 Stage 4。只在生产/外部写入、新增付费范围、不可恢复数据操作或实质改变既定领域语义时请求决定。冻结 r13x 和历史证据不改，Stage 5/6 顺序、验收标准及验收后清理规则不变。

- 可从项目明确归属的 `main/backend/.env` 选取所需字段安全注入本地进程或权限受限的运行时 secret 文件，不复制整份 env、不 source 未核验 shell 内容、不打印密钥、不进入源码/镜像/证据。文件注入应使用任务自有的最小权限副本；不擅自改写用户原 env。
- 用户的密钥注入许可继续用于本阶段必要的有界真实 provider 验证。复用已有 gate，真实请求只用于必须证明的场景；开始前记录调用上限，计算 tool-call/final-answer 各自的模型请求，禁用不必要自动重试和批量/长耗时调用。新增超出已确定验证范围的付费工作应先说明，不上传生产或敏感数据。
- 所有服务仅 localhost/任务网络可达。不得触碰 `ops-scrapyd`、宿主已有 Redis、未知数据库及其他任务资源；不得恢复或删除 `/Users/wangyiliang/Library/Containers/com.docker.docker/Data.backup-20260909-1506`；不得全局 prune。Stage 3 当前仍被引用的制品保持可用；本阶段审核通过后，按 19 号文档“阶段验收后清理旧产物”执行已解除依赖的旧副本清理，不永久保留全部历史大文件。
- 禁止 GitHub push/dispatch/ruleset 写入、registry publish/promotion、签名/transparency 写入、远端部署及任何生产流量/数据操作。外部发布事项后置，不作为本地 blocker。

## 5. 退出条件与回传

阶段审核通过后，执行任务负责落实 19 号文档的旧产物清理规则，先保留并交接 Stage 5 需要的实际输入，再按精确对象清理无用镜像、缓存及重复大文件，并简报释放空间与可恢复性。此动作不在验收前删除待验制品，也不触发新的构建/测试或阶段审批循环。

全部第 3 节要求有实际结果，服务及权限边界正确，fresh/upgrade 与业务 journey 通过，写入可追踪且测试残留已清理或具名保留，才交付本地范围 PASS。真实未通过项不能包装为限定 PASS；仅与外部发布相关的延后事项不阻塞本地阶段。

产物使用本目录 `stage4-evidence/`：一个阶段主结果、必要原始日志/既有测试结果、一个索引及运行说明即可；不新增 validator/schema 平台。主结果列 `结果/改动文件/验证状态/风险`，包括必需要求到证据、实际命令/退出码、复用范围、资源生命周期与 Stage 5 输入位置。不要将完整请求/响应或密钥写进证据。

必须用 `send_message_to_thread` 向上述 Supervisor 发送 `STAGE_RESULT(stageId:S4)`、主结果及索引路径、准确候选归属、验证结论和剩余事项。中途只在有意义进展时汇报并自行继续；只有整阶段完成或真实缺权限/语义选择且已无独立工作时结束。返工留在本 Stage 4 任务，不新开同阶段任务；不要自行启动 Stage 5/6，不创建 Goal 或监控平台。
