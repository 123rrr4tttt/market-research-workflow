# MRW 结构整理方案与分发包

上一轮（2026-10-04）状态：`IMPLEMENTATION_COMPLETE / LOCAL_DAILY_RUNTIME_VERIFIED`，范围与证据见 §8。

本轮（2026-10-05）维护框架与分发方案见 [§10](#10-当前维护收敛框架与串并行分发包)。用户已授权整组实施，状态为 `IMPLEMENTATION_COMPLETE / LOCAL_MAINTENANCE_VERIFIED`；各包的实际派发与验证记录见 §10.11。§1–§7 为上一轮设计，§9 为已执行合同的历史快照；其中旧环境、资源分配和进行中措辞不构成本轮执行指令。

本方案首先退役现用产品和当前文档中的开发编号语义，让用户直接按业务目的操作；同时承接已完成的清简和本机日常链修复，整理源码归属、运行入口、跨模块接缝和历史入口。原 [实现清简方案](MRW实现清简方案.md) §2 继续拥有事实 owner 定义；[清简分发包](MRW清简分阶段实施分发包.md) §7 保留实施历史；[全量核查修复分发包](MRW全量核查修复分发包.md) 的“日常入口整链闭合与宿主 OAuth 同步”段继续拥有本机运行报告。本文件拥有后续结构整理的目标和任务依赖，不成为新的运行状态库。

执行规则仍引用 [19 号流程缩减规则](../../development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/19_direct-testing-batch-freeze-amendment.v1.md)；[06 号阶段进度](../../development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/06_production-deployment-stage-progress.v1.md) 保持本地发布验证已停止、生产发布延后的状态（原历史编号仅供追溯）。设计记录与历史发布证据保持原位；上一轮实施结果与验证范围见 §8，原执行合同见 §9，本轮已实施的维护框架与分发包见 §10。

## 1. 要减少的理解与维护成本

平台继续提供能力声明、组合、执行、权限、持久化和恢复；当前研究业务通过这些能力实现。整理优先让用户按“来源采集、材料入库、批量任务、知识写作、投影查询与恢复”等真实能力理解系统，退出Stage、C1/C2.1、P0等开发期编号和successor/legacy代际叙述；并解决入口、事实owner、源码复现与历史合同介入当前执行的问题。目录深度只用于寻找问题。

最高优先要求：当前可用入口不再要求用户解释任何开发编号才能理解操作、错误或结果。改显示是第一步，API合同、能力注册、canonical identity和现用模块出口的迁移属于同一完整变化；不能把Stage换T、C换别的编号，也不能只加对照表宣布退役。历史冻结ID/字节仅供追溯，退出默认操作和阅读入口。

完成后的可观察变化是：

1. 用户界面、能力列表、图节点、可见错误、API说明和当前README只用业务语义。新canonical identity从原native定义派生；旧编号身份只允许明确版本的历史解码/受控过渡，不再成为新能力或新记录的默认标识。
2. 根 README 的开发入口直接进入 `docs/development/README.md`，读者可直接到达当前方案、本机运行证据和生产阶段状态，各状态不互相覆盖。旧树服务历史与原路径兼容。
3. WebUI 源码和依赖声明在主仓 `main/ops/codex-webui/` 可复现；本机启动不再隐式依赖个人 manual-worktree。运行状态、OAuth 与唯一源码分开保管。
4. 项目贡献只从 `contributions/project_catalog.py` 组合现有 native family 定义；失去真实消费者的 per-family CLI 转发文件退出。测试验证原定义和原消费者，不再只证明转发文件仍存在。
5. 运行时的长期 adapter 与迁移比较/冻结证据有明确归属；只有原消费者迁移完毕才删除桥。必要的 API envelope 投影、scope 校验、effect gateway 和恢复读取继续存在。
6. Collect 和 native Agent 的当前选项只表达实际支持行为；没有作用的旧字段、为未来编排预留的空转路由不能继续被当前界面当成功能。

“增加说明但保留冲突默认入口”“搬目录但保留两套可写事实”“删除测试后宣称桥已退役”均不满足完成条件。

## 2. 从对象与关系确定目标结构

沿用原 owner 表，将同一平台分成五个阅读视图。视图共享对象引用，不要求五个服务或五套目录。

| 阅读视图 | 对象及其成立条件 | 现有承载 | 依赖方向与保留原因 |
|---|---|---|---|
| 业务能力 | 项目、来源、材料、任务、检索结果和写作产物；由原 writer 产生身份与状态 | `app/services/`、models、project customization | 业务入口调用能力并读回事实；不把页面状态当执行事实 |
| 平台执行与效果 | 有类型的 program、assignment、run、receipt、scope 和持久化观察 | `successor_runtime/language`、`capabilities`、`runtime`、`substrate` | 合同→有序组合→原解释器→effects→持久读回；权限与失败有独立语义，继续保留 |
| 原生声明与装配 | 能力定义及其真实组合、注入和派生索引 | `src/mrw_functorial_kit/contributions`、`contributions/project_catalog.py`、`app/composition`、`successor_runtime/assembly` | 原生定义→原装配/派生 registry；composition 构造具体 effect，assembly 组合运行时对象；两者无同义重复时均保留 |
| 运行宿主与产品入口 | 日常 host、隔离 Compose、Codex WebUI 和 MRW native binding | `scripts/local-deploy.sh`、`scripts/docker-deploy.sh`、`main/ops`、前端/API | 明确选择一个运行模式；WebUI 与后端 native binding 各有宿主和会话，不新造同步 store |
| 历史与见证 | 冻结字节、迁移对照、回滚输入、阶段结果及其适用条件 | `successor_migration` 中的历史 adapter、specification、development 历史树、stage evidence | 历史记录按原身份读取；当前状态入口引用它们，历史叙述不反向成为现行规则 |

可把同一业务操作的定义、API、运行、存储、页面看作一个以观察语境为索引的表示族。每个语境说明可见字段和权限，跨语境映射只保留合同承诺的观察。`CollectResult` 与 C3 typed aggregate 就是两个表示；单向 projection 有实际信息边界，因而不能由“同一个操作”推断可删。相反，两个模块若只导出同一个 Python 对象，且没有独立生命周期、权限、失败或恢复消费者，其关系只是实现层的同一性转发，可收敛。

跨路径兼容要求比较同一输入、scope、失败和持久结果，不要求日志/时间戳字节相同。新旧执行对照属于有条件的二维见证：先执行后投影与先转换后执行在指定观察上相容；现有测试支持哪一部分，就只使用哪一部分。独立的业务能力可组合，测试并行还须满足 §5 的资源条件。

### 2.1 保留、收敛、退役和归档

| 对象 | 决定 | 目标与边界 |
|---|---|---|
| `services` 与 `successor_runtime` | 保留语义分工 | 不整树改名，不把所有服务套进新 facade；现有长期adapter按真实消费者判断；本轮六个已审查migration文件没有在线绕行，不为归位新增迁移 |
| language / runtime / substrate / specification | 保留 | language 定义、runtime 执行、substrate 实现资源边界、specification 形成具体见证；只移除已证明重复的实现 |
| `successor_migration/legacy_*` | 按原消费者分类后保留或退出当前入口 | parity、rollback、冻结输入有真实用途；旧 Agent Core/C6 与彩票执行已退役，不恢复 |
| `services/collect_runtime/successor_bridge.py` | 保留 | C3 aggregate→`CollectResult` 单向投影；不得吸收 provider effect 或成为另一份任务状态 |
| `WorkflowRoutingAdapter` 与双模式解析 | 收敛候选，采集接缝收敛 | 当前类仅解析同一 channel adapter 后调用 `.run`，注释将将来 Temporal/Dagster 编排作为存在理由；原语义见证后收敛到既有 dispatcher，真实差异保留 |
| 根 per-family catalog 转发文件 | 退役无消费者部分，贡献出口收敛 | project catalog 和 native family 为现用入口；历史路径字节引用先核对，保留必要的明确兼容入口 |
| `horizontal_native_catalog` | 保留声明状态 | 现有 S1/S2c 平台能力尚未进入项目 catalog；不因 test-only 判删，也不自动宣称装配成功 |
| Agent native 请求旧控制字段 | 收敛，原生请求收敛 | 前端停止发送，后端明确 native 合同；旧 runtime/approval 仍为退役响应；不借清理实现新 tool-loop 或增量 streaming |
| `docs/development` 与 `development/latest-dev-docs` | 当前导航统一，内容按owner保留 | 当前人类默认入口在前者；后者保留规则、阶段事实、历史和兼容路径，不能整体删除 |
| stage / exact-byte / recovery 证据 | 原路径保留 | 对应 restore、校验、hash 和 source closure 依赖解除前不移动，不覆写 manifest |
| WebUI 外部 manual-worktree | 源码归主仓后退出默认启动依赖 | 独有未提交文件先保全并验证；不删除源工作树或其登录状态，不把源码复制等同部署切换成功 |

### 2.2 实施前观察快照

以下保留方案制定时的观察；已完成项与最终验证以 §8 为准。

- `daily-chain-state.json` 实测状态为 `LOCAL_DAILY_FULL_CHAIN_VERIFIED`，scope 是本机单用户；生产 `DEFERRED`。已有完整后端 exit 1 保留，局部关闭不能改写成全套 PASS。
- `run_collect` 已有明确顺序：显式 `SUCCESSOR_RUNTIME_COLLECT` 优先；`on/canary` 走 C3，显式其他模式走原路径；未设置时读取 `INGEST_WORKFLOW_ADAPTER`。`shadow` 在合同中存在，产品入口当前落入旧执行分支。现成 `composition/collect_runtime.py` 注入真实 channel effect，Celery 使用同一入口。
- `docs/development/README.md` 仍称自己为 2026-05 目标根，并把当前可读入口指回旧树；根 README 仍称旧树为第一入口。已有迁移 manifest 中许多内容已是 target-authoritative，故“所有内容仍归旧树”不能继续作总体表述。
- `scripts/dev.py` 的默认贡献测试列表未包含已进入 project catalog 的 `test_retrieval_native_catalog.py`。这是一项明确覆盖缺口，不是新增全量测试平台的理由。
- `AgentChatTurnRequest` 仍接受 `dry_run`、retry/branch/tool-loop/high-risk 字段；native 路径未使用这些控制。写作工作台仍发送后两项。`/turn/stream` 先完成调用再发积累 events，其现有行为要准确描述。

### 2.3 实施前已确认的开发语义暴露

有界检查未发现当前前端pages中显式Stage编号标签；这不等于全系统语义已清理。当前明确问题集中在运行时合同、诊断错误和默认文档。以下是首批真实消费者，不作全仓清单；实施沿原catalog和consumer补齐受影响闭包，不建立全量命名审计平台。

| 现用来源 | 实际消费者/语义 | 处理 |
|---|---|---|
| `production_observability/health.py` 的“active C9 semantic-source…”和“C9 projection source…” | deep-health响应与运行诊断 | 直接改为语义投影offset缺失/投影源读取失败等业务说明 |
| `runtime/facade_contracts.py` 的 `C9RollbackTransitionReceipt.v1` | API回退回执与前端读取校验 | 新版本`projection.rollback_transition.v2`；旧回执原codec只读 |
| 同文件的 `C9RequestIdentity.v1` | API命令幂等摘要 | 新版本`projection.request_identity.v2`；历史幂等键不重算 |
| 前端 `lib/api/domains/successor-runtime.ts` 的 `C9FrontendCommandIdentity.v1` | 本地命令指纹与重试 | 新版本`projection.client_command_fingerprint.v2`，不与后端摘要混成一个事实 |
| `substrate/postgres/facade_commands.py` 的 `capability:successor-runtime:c9` | admission、锁、持久命令、health authority | 用投影命令/查询的业务capability新身份；存量读取/锁域/权限同步迁移，不能仅改字符串 |
| `substrate/postgres/c9_projection_sources.py` 的source identity与`c9_semantic_source` | offset、health和projection读回 | 业务source-kind版本；旧offset显式解码/迁移，不能错误制造source incarnation变更 |
| `capabilities/collect_c3.py` 的payload/codec/catalog owner编号 | 采集执行元素/有序结果折叠的runtime和贡献声明 | 已有`collect.execute_batch_element.v1` / `collect.fold_ordered_results.v1`语义操作名保留；其余编号身份沿各自版本迁移 |
| `capabilities/c8_graph_projection_contribution.py` 的family/cell/owner/codec编号 | 图投影贡献注册、bundle、projector | 统一图投影业务语义；历史graph offset/receipt保持原身份 |

错误族与`main/backend/app/successor_runtime/capabilities/c9_evidence_matrix.py`的可见异常说明一并沿原API错误envelope处理；更换错误code需保留版本识别和客户端分类，不用批量字符串替换。代码文件名与类型名在现用consumer迁完后退旧出口；只剩受控历史读取依赖者继续保留于明确历史边界。

### 2.4 六个迁移adapter的审查结论

当前静态import面未发现下列六文件被API/Celery/main在线导入。C7现用production substrate是 `substrate/postgres/c7_projector_driver.py`，没有导入这组六文件。由此，本轮不搬它们，不建立兼容wrapper；未来只有出现真实在线接入或可合并的实现才触发迁移。

| 文件（均位于 `app/successor_migration/`） | 实际责任与原消费者 | 本轮处置 |
|---|---|---|
| `document_canonical_read.py` | `DocumentCanonicalReadPort`的只读Postgres实现；`p0c_postgres_fixture.py`、`test_p0c_document_read.py`、`test_p0c_submission_postgres.py`消费 | 保留长期port语义与现路径；不得称为一次性废代码 |
| `document_repository_c7.py` | C7 readback-only合同和test repository；`specification/c7_p4.py`及P4/C7测试消费；canonical commit被禁止 | 保留；与`substrate/postgres/c7_document_readback.py`的部分形似不足以证明同义 |
| `projection_common_c7.py` | canonical source/offset DTO与digest；search/graph projector、C7 spec消费 | 保留其依赖`CanonicalDocumentState`的整体 |
| `search_projector_c7.py`、`graph_projector_c7.py` | deterministic declared-loss投影，均不写真实index/graph；C7 spec与projection-diff/Postgres见证消费 | 保留纯对照；真实写入仍归PG driver |
| `ingest_recovery_c7.py` | C7 recovery/non-start policy，委托`EffectReconciler`；C7 spec与reconciliation测试消费 | 保留恢复见证，不塞入Postgres目录 |

这些模块是平台实现、对照和恢复边界的一部分，目录名不代表退役授权。旧 `legacy_collect_runtime` 等族也有specification/assembly/rollback消费者；未逐一核对者保留身份，不推断全树冗余。

WebUI归属已确认：外部路径是嵌套独立Git仓库，HEAD为 `44ad73a99c4d4385fa60d0c519c243baf8f160b7`，主仓该路径缺失。外部有16个tracked文件差异以及8个未跟踪源/配置路径，包含应排除的备份plist；数量只作本次快照。运行LaunchAgent从外部`dist/main.js`启动。`scripts/codex_webui.py`不存在，真实入口是该源码树的`start.sh`/`stop.sh`和宿主 `~/Library/LaunchAgents/com.mrw.codex-webui.plist`。当前运行Codex为宿主 `0.160.0`，package却pin `0.152.1`；源码归属包必须一并消除此运行/声明漂移。

## 3. 验证入口和共同环境

以下是后续实施命令，本轮设计没有执行这些产品测试。cwd 均为 `/Users/wangyiliang/market-research-workflow`。复用 [全量修复包](MRW全量核查修复分发包.md) §4 的 `mrw-repair-tests-20261004:latest`；kit 按 `pyproject.toml` 所声明的绝对路径 `/Users/wangyiliang/Desktop/functorial-kit/python` 挂入同一路径。已有daily第一次`/opt`挂载因wrapper找不到绝对源码而exit1，第二次绝对挂载才exit0；宿主wheel来源不满足此wrapper的editable校验，不把宿主dev.py作为默认fallback。

集成收口先执行一次 `docker image inspect mrw-repair-tests-20261004:latest` 确认镜像；镜像缺失时沿原Dockerfile.test重建一次。Docker不可用只阻断依赖Docker的执行；文档与源码准备可继续。以下函数仅是本合同内的原runner调用缩写，不新增仓库调度器；默认拒绝误连用户业务服务，真实PG测试另获专属实例后显式替换连接配置。

```bash
cd /Users/wangyiliang/market-research-workflow
st_test() (
  docker run --rm --entrypoint python \
    -v "$PWD:$PWD:ro" \
    -v /Users/wangyiliang/Desktop/functorial-kit/python:/Users/wangyiliang/Desktop/functorial-kit/python:ro \
    -w "$PWD" \
    -e PYTHONPATH="$PWD:$PWD/src:$PWD/main/backend:/Users/wangyiliang/Desktop/functorial-kit/python" \
    -e PYTHONDONTWRITEBYTECODE=1 \
    -e DATABASE_URL=postgresql+psycopg2://postgres:postgres@127.0.0.1:1/postgres \
    -e REDIS_URL=redis://127.0.0.1:1/0 -e ES_URL=http://127.0.0.1:1 \
    mrw-repair-tests-20261004:latest -m pytest -p no:cacheprovider -q -rs "$@"
)
st_dev() (
  st_mount_access=ro
  if [ "$1" = sync ]; then st_mount_access=rw; fi
  docker run --rm --entrypoint python \
    -v "$PWD:$PWD:$st_mount_access" \
    -v /Users/wangyiliang/Desktop/functorial-kit/python:/Users/wangyiliang/Desktop/functorial-kit/python:ro \
    -w "$PWD" -e MRW_DEV_PYTHON=/usr/local/bin/python \
    -e PYTHONPATH="$PWD/src:$PWD/main/backend:/Users/wangyiliang/Desktop/functorial-kit/python" \
    -e PYTHONDONTWRITEBYTECODE=1 \
    mrw-repair-tests-20261004:latest scripts/dev.py "$@"
)
```

共享声明实际改变后由集成收口在稳定输入上顺序运行 `st_dev sync`、`st_dev check`、`st_dev test`、`st_dev gates`，每条保留原退出码。sync仅集成owner运行且取得共享生成物写窗口；其余为只读挂载。声明未改变的文档包不触发这些gate。宿主 `.venv311/bin/python`仍可做已核对依赖的局部只读工具，但不让各包另行修理或安装wrapper环境。

前端共享检查 cwd 为 `main/frontend-modern`，使用已装依赖：`npm run lint`、`npm run build`；mock e2e 使用现有 Playwright 配置，真实用户链由 集成收口 使用原 API→worker→持久读回流程。不得临时脚本代写领域 receipt。

## 4. 可直接分发的工作包

共同要求：保留他人 dirty 和未跟踪文件；不 reset/clean/commit、不改历史冻结字节。包作者不再 spawn。普通返工留原包，无法表达的公共规则缺口回 集成收口。输出统一为“结果 / 改动文件 / 原命令与退出码 / 删除对象与保留理由 / 风险与 blocked_by”。实际分发与执行状态见 §8；迁移边界审查 已作为设计边界审查完成，不再派发无收益的源码搬移。

### 业务入口语义归一（最高优先）

- **目标：** 当前UI/API说明、能力名、诊断图、错误和文档默认入口退出全部开发编号语义；随后迁移现用wire/canonical identity、注册和代码出口，使业务语义成为默认事实身份。保持通用平台的能力边界，移除开发期命名负担。
- **权威输入/现成接口：** 原native能力定义与 `src/mrw_functorial_kit/contributions/*` 是能力语义源；原 `business_line_vocabulary.py` 维护既有业务线；`app/successor_runtime/runtime/facade_contracts.py` 拥有当前命令/回执合同，`app/contracts/successor_runtime.py` 和API消费它，前端 `lib/api/domains/successor-runtime.ts` 投影和构造请求；`moduleManifest`、业务诊断API和图renderer消费现成投影。当前stage状态的规则/事实owner保持，默认导航只呈现“本地验证完成、生产部署延后”等实际状态。
- **业务名称：** 工作流定义与组合、来源解析与采集、采集批处理、批量任务、任务与会话观察、材料入库与一致性、知识/图谱/写作/报告、投影查询与重建/回退分别对应现有能力内容。一个旧family内有多个真实能力时逐个命名，不把整个family换一个大号标签；已退役Agent循环和彩票不重新命名复活。
- **输出与顺序：** 先从原native定义补/改业务语义名称，让当前label、说明、错误和默认导航立即可读；再以投影查询/回退真实链为首例打通合同owner→API→前端→持久回执与恢复→原catalog/派生检查。新合同采用 `projection.rollback_transition.v2`、`projection.request_identity.v2`、`projection.client_command_fingerprint.v2` 三种业务身份，分别替代当前 `C9RollbackTransitionReceipt.v1`、`C9RequestIdentity.v1`、`C9FrontendCommandIdentity.v1`；后端请求摘要与前端本地指纹是不同对象，各保留原owner；版本编码、digest/幂等与receipt解码明确分流，旧字节按原codec读取，禁止重新hash覆盖旧身份。
- **公共规则：** 业务名称和新身份只在原native/合同定义写入一次，通过既有contribution规则派生注册与当前读模型；kit若已有verification/alias能力直接复用。确实缺少旧ID解析槽时只扩当前协议一次，由同一owner完成首例；不建立一套平行编号映射库。规则owner交付首例后，其余已确认同形family按原生定义逐批迁移；不同失败/权限/持久身份保持其差异。
- **兼容及退役：** 新创建的能力/请求/回执默认使用业务identity；旧版本仅在明确的兼容decoder/历史readback可用，当前写入先拒绝或显式转换成新版本后重新校验，不能默默重读旧bytes。旧提交入口、默认catalog旧ID、错误码前缀和代码re-export在原consumer迁移完后退役。若旧运行仍在途，按原版本完成/取消后解除旧写入口，不伪造新receipt。历史冻结文件和恢复输入保留原ID，隔离在历史读取边界。只留下历史读取兼容不算现用开发语义残留；仍能默认新建旧身份则未完成。
- **独占写面：** 原native能力/合同owner文件中的身份和名称、当前业务语义projection与专属测试；首例 `runtime/facade_contracts.py`、`contracts/successor_runtime.py`、`api/successor_runtime.py`、前端 `lib/api/domains/successor-runtime.ts` 及直接消费者。共享catalog/registry/global前端types由集成收口单写。与贡献出口收敛同一catalog测试按“语义迁移→出口删除”交接；与入口归一/原生请求收敛只交换业务名和确定接口，不同时写同文件。
- **直接验证：** 先 `rg -n --glob '*.ts' --glob '*.tsx' --glob '*.py' --glob '*.md' 'Stage[ _-]*[0-9]|STAGE_[0-9]|C[1-9](\.[0-9]+)?|C[1-9][A-Z]' main/frontend-modern/src main/backend/app/api main/backend/app/contracts README.md docs/development/README.md` 定位当前暴露；另定向检查 `facade_contracts.py`、`main/backend/app/successor_runtime/capabilities/c9_evidence_matrix.py`、当前native定义和错误投影，不扫全历史。过滤注释、颜色hex、SVG、普通数学变量与明确旧版本decoder，逐项关联实际产品consumer。先执行 `st_test main/backend/tests/successor_runtime/test_p4_c9_1_facade_contracts.py main/backend/tests/successor_runtime/test_p4_c9_3_transport_dto.py main/backend/tests/successor_runtime/test_c9_generalized_rollback_identity.py main/backend/tests/successor_runtime/test_c9_native_catalog.py`。前端cwd为`main/frontend-modern`，执行 `npx playwright test tests/e2e/successor-runtime-client.spec.ts tests/e2e/successor-runtime-page-wiring.spec.ts tests/e2e/successor-runtime-observation.spec.ts --workers=1`；专属PG实例上才运行`main/backend/tests/successor_runtime/test_c9_typed_source_evolution_postgres.py`及`test_c9_projection_sources_postgres.py`。原 `st_dev check`、`st_dev test`、`st_dev gates`集中验证注册。浏览器另检查当前导航、能力选择、图节点、错误及一次真实读写后读回。
- **完成条件：** 当前可用入口无需理解任何开发编号；新API/能力注册/默认record只用业务身份；旧身份只能经明示历史/过渡入口消费且不能偷偷新建；原scope、ordered effect、幂等和rollback/ref完整保持。现用source/export仍以编号作为唯一理解入口时继续迁移，不能只改文案交付。当前引用到同一历史原件可在“历史记录”入口保留。
- **blocked_by：** 只有依赖首例规则的同形identity迁移等待首例；业务label/当前文档、WebUI归仓、独立请求清理立即推进。精确绑定只约束相关旧ID退役，不挡其余当前用户语义替换。兼容对象的owner/数量/移除条件并入本包现有结果，不新建长期兼容治理平台。

### 集成收口

- **目标：** 维护本方案的语义决定、跨包消费者和最终一致性；继承原清简§2，不新建事实合同或控制层。
- **权威输入/接口：** 原 owner 表、19、06、daily-chain-state、`project_catalog.py`、kit 配置及原 `scripts/dev.py`。
- **输出：** 本文件的实际状态更新；每个共享写面的交接；按实际影响执行同步、gate和用户链。仅维护现有日志摘要，不新增进度schema。
- **独占写面：** `contributions/project_catalog.py`、`functorial-kit.json`、共享 registry/sketch/`.functorial` 派生物、全局 composition/startup/API 聚合、共享前端类型、本文及旧三文档；具体包获交接的文件在下表例外列明。
- **验证：** §3共享命令，声明覆盖稳定后运行适用完整gate；将包级局部通过与本次整体通过分开，未知覆盖执行原runner。
- **完成条件：** §6全部成立；跨包消费者无旧入口悬挂；当前归属/失败/权限/历史恢复保持；未验证范围单列。
- **blocked_by：** 仅最终集成依赖其下各项交付；具体缺口不阻断无依赖包。

### 入口归一

- **目标：** 根 README→`docs/development/README.md` 成为单一开发阅读路径，直接区分本机日常、生产阶段与历史内容；更新原链接和原措辞，移除 README 的迁移流水账作为默认正文。
- **输入/现成接口：** 根 README 的开发入口；两棵树 README；原 `latest-dev-docs-entry-manifest.json` / `content-plan.json`；三个清简文档；19/06；`scripts/local-deploy.sh`、`scripts/docker-deploy.sh` 和 `main/ops/README.md`。
- **输出：** 现有 `docs/development/README.md` 的精简当前入口；旧树头部指回；历史迁移叙述折叠/链接到已有归档记录；ops说明分别给宿主日常和Compose隔离模式的入口、端口与数据归属。AGENTS仍是工程规则入口。
- **独占写面：** 根 `README.md`、`docs/development/README.md`、`development/latest-dev-docs/README.md`、`main/ops/README.md`；仅确需导航一致时更新既有可变入口manifest。19/06和历史冻结内容只读。
- **直接验证：** 根目录依次 `python3 scripts/check_latest_dev_docs_structure.py`、`python3 scripts/check_docs_root_migration_manifest.py`、`python3 scripts/checkers/check_docs_root_content_plan.py`、`python3 scripts/checkers/check_docs_root_navigation_drift.py`。若旧checker将“人类默认导航”误当“历史文件内容authority”，先定位该条断言，由00给现成checker做有界修正；不能把所有旧内容authority改为新根以改绿。
- **完成条件：** 从根入口两次以内点击到现行方案/本机证据/生产状态；无“两个默认开发根”互指；启动模式写清而不删合法模式；原冻结/恢复路径可达。
- **blocked_by：** 无业务前置；最终写入 WebUI启动说明依赖 WebUI归仓 的确定路径，其他导航可先交付。

### WebUI归仓

- **目标：** 将当前在线源码以vendoring方式纳入主仓 `main/ops/codex-webui/`，把默认启动路径切到主仓；保留明确外部 override 作为有用开发模式时必须显式。选择vendoring是因为主仓须直接保存当前MRW本地集成改动，而外部HEAD不含这些改动；不引入submodule或嵌套Git仓库。
- **权威输入/接口：** 外部 `/Users/wangyiliang/.codex/manual-worktrees/mrw-functorial-successor-p0/main/ops/codex-webui`；当前宿主进程命令/launchd配置；前端 `/codex/` proxy、后端 `api/codex_auth.py`；只读核对两处Git身份、源码/lockfile与实际启动差异。
- **输出：** vendor原`src/`、`web/src/`及构建需要的public/config/migrations、package/lock/workspace/build定义、LICENSE和原README；在该README记upstream地址/HEAD与本地改动来源。复制前逐文件核对，不整棵复制外部树。禁止`.git`、node_modules、dist、数据库、日志、`.tmp`、auth、个人plist、备份和token进入仓库；宿主配置只转成无秘密模板。`mrw_mcp_server.py`与`refresh-business-snapshot.sh`先核对原consumer及与主仓同名能力差异，独有源码保全在原树，未证明需要不纳入默认启动。
- **版本决定：** 以本轮实测宿主Codex `0.160.0`作为此次迁入的显式兼容基准，更新WebUI package/lock并由同版本CLI生成/核对schema，宿主使用明确同版本`CODEX_BIN`。若验证不兼容，保留现用实例并报告具体协议gap，不静默降为0.152.1或用`latest`掩盖漂移。OAuth继续共享宿主文件，不归这个版本声明管理。
- **独占写面：** `main/ops/codex-webui/**`、本机WebUI原启动配置中的该服务条目及原路径解析入口；前端proxy/后端auth仅若真实需要由00交接，默认保留协议。`main/ops/README.md`归01，02仅回传准确命令。
- **直接验证：** cwd为主仓 `main/ops/codex-webui`，既有package manager为`pnpm@10.18.3`。执行 `pnpm install --frozen-lockfile`、`pnpm exec codex --version`、`pnpm exec vitest run src/auth/auth.controller.spec.ts`、`pnpm run build`、`pnpm --dir web run build`；版本/lock更新本身先由02一次完成，随后frozen安装验证。不运行带`--fix`的根lint来证明只读。MRW侧运行 `st_test main/backend/tests/production_composition/test_production_codex_webui_exchange.py`，前端原 `tests/e2e/simp08-codex-auth-proxy.spec.ts`。构建与临时端口验证成功后才切本机8172；切换后读回iframe/WS、JWT/bootstrap边界、原thread/一次turn。未切换时只能报告源码准备完成。
- **完成条件：** 一份主仓源码与lockfile可构建启动；主仓默认启动无personal worktree硬依赖；原OAuth symlink仍指宿主 `~/.codex/auth.json`，不重复登录；localhost与远端sink-only边界保持；停止/继续归原WebUI宿主。
- **blocked_by：** `G-WEBUI-SOURCE` 只约束源码准确搬运与切换；`G-WEBUI-RESOURCE` 只约束8172切换窗口。主仓有界准备可先做。外部源保留直到本机回读成功，不在本包清理它。

### 贡献出口收敛

- **目标：** 清除只为旧名字存在的 per-family catalog CLI转发，补齐当前组合的默认验证覆盖。
- **输入/现成接口：** `contributions/project_catalog.py` 直接导入 native C1–C5/C7–C9/retrieval；`src/mrw_functorial_kit/contributions/c8.py` 已组合graph；原 `scripts/dev.py` 只使用project catalog。
- **输出/顺序：** 先以 `contributions/c8_graph_projection_catalog.py` 真实首例，把原身份断言迁到native/组合消费者并删除无用转发；再按同一规则核对其余per-family出口。`PILOT_TESTS`补入已装配retrieval的原测试；已有贡献协议若能提供验证引用则复用，不能为这一项新造family→test注册层。
- **独占写面：** `contributions/*_catalog.py` 中除 `project_catalog.py` 的出口文件及直接守卫它们的catalog测试；`scripts/dev.py` 与 `tests/checkers/test_dev_entry.py`；native family定义默认只读。00拥有project catalog与同步。
- **直接验证：** `st_test main/backend/tests/successor_runtime/test_c8_graph_projection_contribution.py main/backend/tests/successor_runtime/test_c8_native_catalog.py main/backend/tests/successor_runtime/test_retrieval_native_catalog.py tests/checkers/test_dev_entry.py`；同形迁移后 `st_dev test`；00集中 `st_dev check`和`st_dev gates`。
- **完成条件：** 删除的每个出口没有活动脚本/CLI/恢复消费者；有效断言迁入原事实owner的测试；当前project catalog内已装配family有相应默认见证。历史快照原样保留，horizontal未装配状态不被改成完成。
- **blocked_by：** 首例之外的删除仅依赖该出口的真实consumer清单；冻结路径引用有疑问则保留那个出口，不挡已核实对象。

### 迁移边界审查（设计完成，不下发搬移）

六个adapter的分类与consumer已在§2.4列明。当前没有在线consumer绕行证据，移动只改变目录并扩大exact-binding影响，因此本轮保留。唯一集成owner在贡献出口收敛删除某个catalog出口、或未来修改某个真实adapter时，定向核对其精确路径消费者；这个局部条件不阻断其他包。无需新建分类清单、schema或日常测试。

若后续实现发现与现结论不符的实际在线import，00只重新打开该对象：输入是原port和真实consumer，目标位置复用现有substrate，原错误/scope/事务合同与历史恢复必须保持。可用验证为 `st_test main/backend/tests/successor_runtime/test_p0c_document_read.py main/backend/tests/successor_runtime/test_p0c_boundaries.py`；涉及真实PG读写再按专属测试资源执行 `test_p0c_submission_postgres.py`。这不是本轮默认实施任务。

### 采集接缝收敛

- **目标：** 收敛当前产品选择逻辑，移除没有真实编排职责的转发，同时保持C3与既有API/effect差异。
- **输入/现成接口：** `services/collect_runtime/runtime.py` 的 `run_collect`、`_run_collect_no_batch`、`WorkflowRoutingAdapter`；`collect_c3.collect_runtime_mode`；composition gateway；`successor_bridge.project_successor_aggregate`。
- **输出/决定：** 本次不建设shadow执行器。产品入口明确拒绝未实现的shadow请求并报告原API envelope错误；历史shadow/replay能力仍保留。对 `INGEST_WORKFLOW_ADAPTER` 先在原dispatch上验证身份、顺序与failure site，若仅转发则保留旧配置解析为兼容输入、共用原dispatcher并退class，不新增selector。若发现可观察差异，保留差异对应小分支并交代原因。
- **独占写面：** `services/collect_runtime/runtime.py` 与专属tests；桥的projection接口保持；composition注入如需改由00单写；能力模式parser作为历史/产品共用定义不得为拒绝产品shadow而删除历史值。
- **直接验证：** `st_test main/backend/tests/unit/test_collect_runtime_auto_batch_unittest.py main/backend/tests/unit/test_collect_runtime_composition_unittest.py main/backend/tests/unit/test_collect_runtime_native_binding.py main/backend/tests/successor_runtime/test_p3_c3_contracts.py main/backend/tests/successor_runtime/test_p3_c3_rollback.py main/backend/tests/successor_runtime/test_p3_c3_replay_shadow.py`。增加/复用参数覆盖未设置、off、workflow、shadow、canary/on、未知channel、effect缺失和部分失败；随后00按原API→worker真实入口读回。
- **完成条件：** 每个暴露模式有真实行为；无默默shadow→legacy；same adapter effect不重复调用；C3失败不fallback、typed结果/receipt/delivery观察保持；旧配置兼容范围清楚。
- **blocked_by：** `G-COLLECT-BOUNDARY` 仅限制转发class删除；shadow明确拒绝和测试可独立准备。不得借此改变当前默认采集模式或启用生产cutover。

### 原生请求收敛

- **目标：** 移除旧Core遗留且native不实现的控制面，减少“请求被接受但无作用”的选项。
- **输入/现成接口：** `api/agent_chat.py:AgentChatTurnRequest`、native执行分支；`WritingWorkbenchPage.tsx`的 `runAgentChatTurnStreaming`；现有domain客户端与tests。保留显式native binding、session、project、idempotency及现有错误envelope。
- **输出/决定：** 内部消费者先停止发送 `dry_run/enable_bounded_retry/enable_limited_branching/enable_model_tool_loop/require_high_risk_approval`。当前native请求显式出现这些旧控制时返回可理解的unsupported-option拒绝，不让Pydantic extra-ignore静默接受；旧runtime和approval请求继续410。SSE仅描述当前“调用完成后发送events”合同，不在此包实现真增量流。
- **独占写面：** `api/agent_chat.py`、native请求专属API客户端、`WritingWorkbenchPage.tsx`的调用段和直接tests；共享 `F/src/lib/types.ts` 由00接收确定字段删除后单写。
- **直接验证：** `st_test main/backend/tests/unit/test_codex_native_macro_binding.py main/backend/tests/integration/test_agent_macro_entry.py main/backend/tests/integration/test_agent_chat_api_unittest.py`；前端运行现有writing合同检查；00在F运行lint/build及对应writing e2e。保留旧字段拒绝、项目scope和native不可用失败见证。
- **完成条件：** 原写作调用仍能取得native结果并刷新实际产物；UI不再发送无效控制；缺少/退役binding仍按原边界拒绝；不复活旧Core，不复制WebUI会话。
- **blocked_by：** 共享前端类型交接与对旧请求字段的API兼容处理落实；独立前端删除可先准备，联合验证须同一候选。

## 5. 阶段、串并行与测试资源

阶段是依赖层次，不是审批点。集成收口贯穿集成；本表已固定公共接口，不要求实施者重新设计整套结构。

| 工作阶段 | 可启动包 | 实际串行依赖 | 可并行条件 |
|---|---|---|---|
| 当前入口可用 | 业务入口语义归一的显示/错误/导航；入口归一；WebUI归仓准备；独立请求清理 | 原名称owner固定后投影，当前阅读入口直接采用业务名 | 不同写面可立即并行；不等待全部identity迁移 |
| 业务身份迁移 | 业务入口语义归一首例；WebUI离线构建；采集/原生请求收敛 | 投影命令/回执首例→原API/读回→派生规则→同形能力；不同kernel无依赖可并行 | 贡献出口先只读准备，拿到identity与测试交接才删出口 |
| 默认入口切换 | 业务入口语义归一余下consumer；WebUI本机切换；贡献出口收敛 | 新旧decoder明确→consumer同步→停止旧新建→退旧出口；WebUI构建验证→8172切换→原thread读回 | 同账户/数据库/共享生成物串行，独立文档与mock检查并行 |
| 集成收口 | 集成owner统一派生、适用gate、用户链、默认入口复核 | 真实依赖稳定后验证；不以只改label代替identity和消费者迁移 | 无无关全量重跑；有效旧结果标为kept |

```mermaid
flowchart LR
  S[业务语义源与当前名称] --> D[当前界面与文档入口]
  S --> P[投影命令与回执身份首例]
  P --> R[现成规则与其余能力consumer迁移]
  R --> C[旧catalog与代码出口退役]
  W[WebUI源码归仓] --> WB[构建及临时验证]
  WB --> WL[本机切换与读回]
  A[原生请求与采集接缝收敛] --> I[集成收口]
  D --> I
  C --> I
  WL --> I
```

| 测试资源端口/共享文件 | 唯一写入规则 | 不冲突的工作 |
|---|---|---|
| project catalog、registry/sketch、生成配置 | 00单写；sync时只暂停依赖这些输入的测试 | 文档、WebUI离线源码整理 |
| 根导航与ops README | 01单写；02提供命令，不同时写说明 | 后端局部实现 |
| 前端types、dist、tsbuildinfo、Playwright输出/端口 | 00按06交接集中；build/e2e串行 | 后端纯mock测试 |
| 8172 WebUI、CODEX_HOME、OAuth/session/provider账户 | 02取得切换窗口后独占；00的真实native turn另排队 | 无网络的源码检查；临时端口不能自动证明账户隔离 |
| 8000/5173日常服务、DB/Redis/ES、正式host worker | 00拥有受影响用户链窗口；同实例写测试串行 | 独立tmp/mock测试，不同project key不自动隔离DB reset |
| C7/P0-C测试Postgres、固定fixture数据库 | 本轮无改动不运行；若真实后续影响才由00分配独立实例 | 无DB的catalog和collect纯测试 |
| source checkout/kit checkout | 被测闭包修改期间不消费对应旧结果；不暂停整仓 | 无依赖文件与只读证据 |

## 6. 整体退出条件与有界缺口

首先统计当前产品/文档开发编号暴露及现用旧canonical identity的实际退役；再统计冗余出口、旧选项和默认硬依赖，不设“至少减少多少行/目录”的指标。整体完成需同时满足：当前用户操作无需解释开发编号、新建业务身份与注册已迁移、原消费者得到同义或明确版本化行为；默认入口唯一；主仓WebUI可复现且live切换读回；声明/注册/装配一致；必要projection和历史恢复保留；测试实际覆盖及原失败状态清楚。方案写完不满足实施完成。

以下为实施前的缺口分派表，全部本轮结构缺口的收口结果见 §8；不作为未完成清单。

| 缺口ID | 数量/对象 | owner | 解除路径 | 只阻断 |
|---|---|---|---|---|
| G-SEMANTIC-IDENTITY | 首例三种投影identity及其后活动family/consumer，准确数量按原catalog派生 | 业务入口语义归一/集成收口 | 名称先行；原合同首例→版本化解码/幂等→原消费者→其余同形迁移 | 相关identity退役，不挡显示/文档及独立包 |
| G-WEBUI-SOURCE | 已确认1个nested repo；仍需核对2个未跟踪辅助脚本与前端静态产物来源 | WebUI归仓 | 限定源码/模板allowlist，0.160.0依赖一致构建与原consumer验证 | WebUI归仓准确迁入与切换 |
| G-WEBUI-RESOURCE | 1个8172宿主及共享OAuth/session | 集成收口/WebUI归仓 | 取得无在途turn的切换窗口；保留原启动路径可恢复 | WebUI归仓live验收，不挡准备 |
| G-MIGRATION-CONSUMERS | 已关闭：6个adapter分类完成，无在线consumer | 集成收口 | §2.4保留；不下发搬移 | 无 |
| G-EXACT-BINDING | 贡献出口收敛候选出口内精确路径消费者，数量须按候选引用实查 | 集成收口/贡献出口收敛 | 原binding保持；无法解除者只保留该出口，已证实无消费者者继续删除 | 对应单出口删除 |
| G-COLLECT-BOUNDARY | 1个WorkflowRoutingAdapter的观察差异 | 采集接缝收敛 | 原dispatcher参数与失败/顺序对照；配置使用只读核对 | class退役，不挡模式明确化 |
| G-NATIVE-COMPAT | 5个旧请求字段与1个写作调用点 | 原生请求收敛/集成收口 | 消费者同步删除+显式拒绝测试；旧API合同变更记录在现有文档 | 原生请求收敛联合交付 |

生产远端、可选Qdrant旧点迁移、香港历史材料与旧全量backend失败不变成结构整理的全局阻塞；保留原具名状态，结构变化影响其中某项时再做该项验证。

### 6.1 已确定的实施决定与需保留的判断

本方案最高优先采用业务语义命名与canonical identity迁移，开发编号仅在历史追溯；同时默认采用主仓vendoring、当前人类导航转入`docs/development`、既有本机Codex0.160.0兼容基准、产品shadow明确拒绝、native旧控制字段显式拒绝、六个migration adapter本轮保留。这些是后续包的确定输入，不交给每位作者重新选方案。

仍需实施时判断的是：两个外部辅助脚本是否有真实consumer；每个catalog旧出口是否被精确恢复入口引用；WorkflowRoutingAdapter的failure site/批处理观察是否允许共用dispatcher。判断在各自现成模块内完成，不新增审批或平台。若实际发现外部客户依赖被删native字段，应由00按已注册客户/版本处理兼容，不能静默忽略；只阻断该API切换。

## 7. 设计与首次分派历史

本节保留方案完成、尚未实施时的记录；其 NOT_STARTED 和待实施状态不覆盖 §8。

本次使用函子方法读取原owner表、kit配置、registry/sketch和现用消费者后设计。主设计由显式 `gpt-6-astra / high` 路由承担；四个独立只读包实际路由均为 `default + glm-5.3-flash-zhipu-glm-en / low / fork_turns=none`：runtime_evidence、docs_evidence、webui_evidence、entrypoints_evidence。各包禁止递归spawn和文件修改。运行时包另做同一六文件的有界补查；用户追加语义退役后，原entrypoints_evidence以同一路由补查8处当前暴露，已停止扫描。

设计依据为本轮直接读取的代码和文件；旧记忆仅用于定位并已核对当前消费者。当前产品运行状态引用 `.data/readiness-repair/20261004-daily-chain/daily-chain-state.json`，本轮未重演其PASS。四包调用/token成本工具未提供，不记为零，不据此报告提速。

本轮只更改本文和旧三文档的承接/优先级说明。文档链接、文件路径、命令定位与diff校验结果在最终回传记录；后续业务入口语义归一、集成收口、入口归一、WebUI归仓、贡献出口收敛、采集接缝收敛、原生请求收敛均为 `NOT_STARTED`；迁移边界审查仅设计审查完成，无源码迁移。

本次文档校验：9个本轮Markdown链接、29个现有命令/源码目标和1段bash语法检查全部通过，原退出码0；`git diff --check`原退出码0。新文件另检查尾空白。两次初步链接提取器分别把明示不存在的路径和代码内正则误判为目标，均保留为校验脚本误报并修正提取边界；未执行任何产品测试，未改运行事实。

主线已复核目标结构、最高优先语义退役、分包写面、依赖及共享测试资源；正文链接和旧三入口承接链接复核通过，`git diff --check` exit0。当前方案可直接分发，产品实施尚未开始。


## 8. 实际实施进度

2026-10-04：该轮全部实施包与统一验收已完成。该轮完成事实由本节维护；§2、§7保留实施前观察与设计历史，§9保留执行合同。机器观察摘要为 `.data/structure-cleanup/20261004/execution-state.json`。本节不覆盖 §10 新增维护包的实施状态；下方磁盘数值和临时资源为当时观察，本轮不据此判断当前容量或重新创建已清理资源。

| 工作面 | 实际结果 |
|---|---|
| 产品与运行身份 | workflow/source/acquisition/batch/task/material/knowledge/projection 八类实际 operation、handler、assembly、codec、failure 与新持久记录使用业务身份；历史 reader 保留旧 schema、ID、digest和原始字节 |
| 声明与装配 | 27个默认业务cell由八类原生作者声明派生；project catalog组合15个贡献；两个投影sketch由原权威派生；horizontal只保留声明，不自动增加运行权限 |
| 贡献入口 | 十个无消费者catalog转发出口已删除，保留唯一project catalog；原消费者与测试同步 |
| 产品选项与采集 | native五个无效控制字段退出客户端/共享类型，显式提交返回400，旧core返回410；Collect重复路由收敛到原dispatcher，shadow明确拒绝 |
| WebUI与认证 | 源码迁入主仓，Codex依赖固定0.160.0；SQLite、原会话及宿主OAuth保持；LaunchAgent与最新版生命周期脚本实际切换、重启和读回通过 |
| 当前导航 | 默认入口统一到业务说明与当前实施结果；旧树、冻结证据和精确历史路径保留原位 |

数据库八组本轮实际执行217项，全部通过、无跳过。统一贡献sync/check均clean；原生贡献测试156项通过；共享声明/原装配148项及13个子测试通过；七项架构门禁280项全部通过，最终exit0（`integration-gates-final-attempt3.log`）。前端lint/build和67项测试沿未变化输入保留原通过归属。各包纯测试有重叠，不与集成测试相加声称总覆盖率。

本机后端与正式worker在queue0/unacked0时重载。前端5173提交材料，正式worker完成task `7afe6c39-5732-448e-ad67-4530481b0443`，doc3正文与URI两次持久读回一致，doc1原材料保留。实际浏览器iframe、宿主认证bootstrap/status、WebSocket及两个原回合marker均读回，page error为0；本轮最终核查未再发provider回合。最终worker注册包含业务观测任务，旧Stage5任务注册缺席，queue0/unacked0且ping成功。

运行证据：`.data/structure-cleanup/20261004/live-user-chain-result.json`、`live-browser-readback.json`、`host-final-runtime-attempt1.log`、`integration-postgres-final-summary.json`。隔离tmpfs测试Postgres和任务网络已关闭，保留镜像、原日志与业务服务；未执行全局prune。

失败与成本保留：GLM429后的五个剩余包由实际GPT5.6sol路由续接；C5作者曾越过共享写面执行一次adoption sync，随后由主线恢复单写并通过一致性核查。初次统一门禁、共享authority、投影组合、历史fixture和环境探针失败均有原attempt日志；最后材料导入时raw raise已在原权威修复，由现有测试承载分区一致性见证。调用/token与首次共同验收精确耗时工具未提供，不记为零，不宣称提速。

本机日常链可工作。远端生产发布延后；可选Qdrant旧点迁移、香港历史材料和原后端全量exit1保持具名状态，本次结构相关通过不覆盖这些结果。宿主磁盘约98%、剩余约12GiB，容量状态仍需留意。

后续资源清理：用户授权清理Docker与本地旧快照后，已删除24个旧/临时容器（包括依赖已停服务、重启99次的旧ops worker）、5个过期镜像标签、5个空网络和5处临时验证/浏览器缓存目录。数据卷、scrapyd、当前测试镜像、历史发布恢复输入、OAuth与WebUI数据库保留。r13x canonical layouts的16个相同内容blob改为硬链接共享，约140MiB重复内容去重；原路径及SHA256逐项保持，manifest未修改。Docker报告镜像占用17.27GB→16.44GB，宿主净空闲变化单独记录，不把镜像逻辑大小当作Docker.raw实际回收。共享BuildKit缓存与未确认数据卷保留。结果与精确对象见 `.data/structure-cleanup/20261004/redundancy-cleanup-result.json`；清理后8000/5173健康和8172可达。

## 9. 真实运行身份迁移的剩余分发包

本节是 2026-10-04 执行期间快照，已由 §8 的最终完成记录收口。保留下文的原状态、旧路径和验证归属供追溯；其中 `IN_PROGRESS`、尚待迁移、正在修复及已分配测试实例均只描述当时状态。本轮新分发只使用 §10。

<details>
<summary>展开上一轮运行身份迁移合同与执行中记录</summary>

2026-10-04 续接：本节保留运行身份迁移的执行合同，实际完成状态和验证归属统一见 §8。§8 已通过部分继续保留其验证范围；catalog 的业务标签、contribution ID 或声明 codec 已更新，并不证明实际 operation、cell、handler、assembly、持久记录已迁移。本轮补齐下列六包，知识产物由原 `native_semantics` owner 继续承担，其余由各 family owner 实施；不重新分派已完成的工作。

只迁移仍携带 C/Stage 开发编号或 successor 代际语义的真实 current identity。已经稳定的业务操作名及其 v1 不为格式统一强行升版，例如 `collect.execute_batch_element.v1` 和 `collect.fold_ordered_results.v1` 保持。实际改变身份的对象必须有明确的新版本，业务命名沿 workflow/source/acquisition/batch/task/material/knowledge/projection 展开；不得以另一套编号替换原编号。旧文件名可作为定位和精确历史绑定暂留，现用默认对象与消费者须使用业务身份。

### 9.1 共同合同、写面与执行资源

每包在原 native authority 写入语义一次，由既有规则供装配、注册与消费者读取。先打通一个真实 native→assembly→原 effect/持久化→readback 实例，再扩展已证明同形的部分。不得只在 catalog 宣告新 codec，却仍调用旧 codec 写入；不得在 `src/mrw_functorial_kit/contributions/` 重录 native 词表事实。遇到公共规则缺口交集成 owner 修复，不新增映射平台或重复适配器。

新建受影响的 program、operation、bundle/cell、receipt、artifact、offset 和 metadata 使用对应业务版本。历史字节经显式历史 decoder/specification/replay 读取，保留原 ID、digest、幂等键和事实 owner；禁止重算旧摘要覆盖旧记录或按新版静默解释旧 bytes。effect 的权限、失败归属、恢复、有序性与幂等条件保持；新身份不能扩大写权限。每包需交付当前写入、历史读取及错误版本拒绝三类实际见证，适用范围由真实受影响对象确定，不给无关稳定对象增测试。

| 写面 | 唯一 owner 与交接 |
|---|---|
| `assembly/base.py`、`assembly/successor_assembly.py`、共同 native-author 消费者 | 集成 owner；family 包交确定接口和受影响引用 |
| PostgreSQL schema、global canonical tables、共同 reconciliation/observations | 集成 owner；各包不各自迁 schema 或改共同事实源 |
| `src/mrw_functorial_kit/contributions/`、project catalog、registry/sketch、共享前端类型 | 集成 owner；原 `native_semantics` 已有修改先交接，之后集中同步，不能双写 |
| 各 family native-author 源与本节 family 装配 | 已按本节释放给对应 owner；知识 family 继续由 `native_semantics` 单写 |
| C9 facade、投影 source 与相关脚本 | 原 `projection_identity` / source owner；材料、观察、知识只提供接口，不越界修改 |
| 历史冻结输入、exact-byte manifest | 保留原 bytes；历史读取兼容在现有 reader/spec 边界实现 |

下文路径相对 `main/backend/app/successor_runtime/`，测试文件相对 `main/backend/tests/successor_runtime/`；例外均写全仓库相对路径。cwd 统一为 `/Users/wangyiliang/market-research-workflow`，纯测试直接复用 §3 的 `st_test`。测试依赖使用同一镜像、绝对源码挂载及绝对 sibling kit 路径；保留 `--entrypoint python`，不退回已知不满足 editable 校验的宿主 wrapper。

PG 实例已分配：容器 `mrw-structure-postgres-20261004`，网络 `mrw-structure-20261004`，宿主端口 `18543`，镜像 `postgres:16-alpine`，存储为本轮专属 tmpfs；权威资源记录为 `.data/structure-cleanup/20261004/test-resources.json`。全部 PG selectors 由集成 owner 在已配置该实例连接的同一 Docker 测试入口**串行**运行；不得把 §3 指向拒绝连接端口的纯测试配置直接用作 PG 验收，也不得连接日常数据库。各作者提交下列准确 selectors，集成 owner 保留原命令、退出码和 skip 原因；环境未满足导致的 skip 不算通过。

### 9.2 来源解析与采集

- **目标：** 将真实来源解析、计划、provider effect、终端投影的默认身份改为业务语义；保持四个不同职责与其权限。
- **权威输入与现成接口：** `capabilities/source_library_c2_native_contribution.py` 的 `DEFAULT_C2_NATIVE_SOURCE`、`source_library_c2_shared.py` 共享身份/codec、各 stage 原 program/interpreter；`assembly/c2_assembly.py` 与 PostgreSQL source handler/canary、terminal projection。现 contribution 已为 `mrw.source.resolve-and-acquire.native.v2`，实际 `C2.1` 至 `C2.4`、旧 stage owner 和 terminal owner 仍须沿运行对象收敛。
- **输出：** 原 native 定义、实际 stage/codec、装配 metadata 与新持久 readback 一致；显式旧来源 decoder 保留历史身份；先交付 batch 已依赖的共享来源身份接口。
- **独占写面：** `capabilities/source_library_c2_*.py`，`assembly/c2_assembly.py`，`substrate/postgres/source_library_c2_1_handler.py`、`source_library_c2_1_canary.py`、`source_library_c2_23_canary.py`，`substrate/projections/source_library_terminal.py` 及本包专属测试。共享 schema 和 C9 source 不在此包。
- **直接验证：** `st_test main/backend/tests/successor_runtime/test_c2_native_catalog.py main/backend/tests/successor_runtime/test_p3_c2_shared_identity.py main/backend/tests/successor_runtime/test_p2_c2_1_contracts.py main/backend/tests/successor_runtime/test_p2_c2_1_parity.py main/backend/tests/successor_runtime/test_p3_c2_2_contracts.py main/backend/tests/successor_runtime/test_p3_c2_3_contracts.py main/backend/tests/successor_runtime/test_p3_c2_3_recovery.py`。PG selectors：`test_p3_c2_1_rehydration_postgres.py`、`test_p3_c2_23_runtime_canary_postgres.py`、`test_p3_c2_4_postgres.py`。
- **完成条件：** 原来源入口产生并持久读回业务身份；解析/计划不会取得 provider 写权限，终端投影不成为事实 writer；重试恢复能读取旧版本且不重算历史身份。
- **blocked_by：** 共享 schema 的实际变更由集成 owner 接入；先发布 `source_library_c2_shared.py` 的确切接口给批任务 owner，仅该依赖段等待，不阻断来源其余准备。

### 9.3 采集批处理

- **目标：** 使默认采集 bundle、cell、owner 和真实 codec 与业务声明一致，保留元素执行→有序结果折叠的顺序及产品 API 投影。
- **权威输入与现成接口：** `capabilities/c3_native_contribution.py`、`collect_c3.py`、program/interpreters；`assembly/c3_assembly.py`；`main/backend/app/services/collect_runtime/` 的真实消费者。当前声明已广告 acquisition v2 codec，实际 bundle `mrw.functorial-successor.collect.c3` 和 `C3.*` 默认对象仍待迁移。
- **输出：** 真实运行使用原 native 业务身份与实际 codec；原 `CollectResult` 投影及模式处理复用 §8 已有修复；历史 replay/rollback 仍按原版本，不能以迁移恢复已拒绝的产品 shadow。
- **独占写面：** `capabilities/collect_c3.py`、`collect_c3_program.py`、`collect_c3_interpreters.py`、`c3_native_contribution.py`，`assembly/c3_assembly.py`，`substrate/postgres/collect_c3_canary.py`；`main/backend/app/services/collect_runtime/` 仅处理真实受影响身份消费者并保留原包现有改动，composition 共享注入由集成 owner 写入。
- **直接验证：** `st_test main/backend/tests/successor_runtime/test_c3_native_catalog.py main/backend/tests/successor_runtime/test_p3_c3_contracts.py main/backend/tests/successor_runtime/test_p3_c3_micro.py main/backend/tests/successor_runtime/test_p3_c3_rollback.py main/backend/tests/successor_runtime/test_p3_c3_replay_shadow.py main/backend/tests/successor_runtime/test_i1_c1_c3_assembly.py main/backend/tests/unit/test_collect_runtime_auto_batch_unittest.py main/backend/tests/unit/test_collect_runtime_composition_unittest.py main/backend/tests/unit/test_collect_runtime_native_binding.py`。PG selector：`test_p3_c3_canary_postgres.py`。
- **完成条件：** 原 API→worker→采集 effect→结果读回闭合，新 metadata 无默认开发身份；ordered fold、部分失败、原错误 envelope 和一次 effect 调用保持；稳定的 collect 业务操作 v1 保留。
- **blocked_by：** 共同装配或 composition 接口变更只交集成 owner；不依赖未完成的来源共享接口就不等待来源包。

### 9.4 批量任务

- **目标：** 将批量任务真实计划、重试归约、提交与持久回执的开发身份迁入业务版本，保持质量晋升的独立权限边界。
- **权威输入与现成接口：** `capabilities/agent_batch_c4_native_contribution.py`、`agent_batch_c4.py`、program/interpreters；`assembly/c4_assembly.py`；PG repository、restartable submission handler、quality promotion handler。当前声明的 `batch.task.build_plan.v2`、`batch.task.reduce_retry.v2`、`batch.task.submit.v2` 必须对应真实对象；PG handler 仍有 `mrw.successor.agent-batch.c4-3.receipt.codec.v1` 及旧 receipt provenance。
- **输出：** 计划→归约→提交的实际 operation、codec、receipt 与装配同源；原 repository 重启读回和幂等保持；与任务观察通过持久结果交接，不把 observer 变成提交者。
- **独占写面：** `capabilities/agent_batch_c4*.py`，`assembly/c4_assembly.py`，`substrate/postgres/agent_batch_c4.py`、`agent_batch_c4_3_handler.py`、`agent_batch_c4_canary.py`、`agent_batch_c4_quality_promotion_handler.py` 及专属测试。来源共享定义归来源包，观察 projection 归任务观察包。
- **直接验证：** `st_test main/backend/tests/successor_runtime/test_c4_native_contribution.py main/backend/tests/successor_runtime/test_p3_c4_1_plan.py main/backend/tests/successor_runtime/test_p3_c4_1_program.py main/backend/tests/successor_runtime/test_p3_c4_2_retry_reducer.py main/backend/tests/successor_runtime/test_p3_c4_3_submission.py`。PG selectors：`test_p3_c4_4_postgres.py`、`test_p3_c4_5_runtime_postgres.py`；两包稳定后集成 owner 运行 `st_test main/backend/tests/successor_runtime/test_i1_c4_c5_assembly.py`。
- **完成条件：** 新任务经原提交 handler 落业务版 receipt，重启读回与 retry reducer 观察一致；旧 receipt 按原 decoder 读取，幂等不会因历史重编码产生重复提交；质量晋升仍需原权限。
- **blocked_by：** `assembly/c4_assembly.py` 导入 `source_library_c2_shared.py` 的共享身份段等待来源接口交接；独立 plan/reducer/PG 准备可先执行。跨包观察联合验证等待双方接口稳定。

### 9.5 任务与会话观察

- **目标：** 将会话快照、effect reconciliation 读回、runtime run 投影和 process observation 的当前身份业务化，保持纯观察权限。
- **权威输入与现成接口：** `runtime/c5_native_contribution.py`、`assembly/c5_assembly.py`；`runtime.reconciliation:EffectReconciler/AuthoritativeEffectReadback`；原 session read adapter、runtime projector、line-event readback。native rule 已为 `mrw.task.observation.native-rule.v2`，实际 `C5CellId` 和 snapshot/offset/process contracts 尚须逐个核对；原观察定义明确不授权生产写入或 durable authorization。
- **输出：** 实际 cell/assembly 与受影响 snapshot codec 对应业务版本；reconciliation 沿原 authoritative readback；旧快照明确版本读取。已是稳定业务身份的 offset 或 observation v1 经核对保持，不能因在同文件出现而统一升版。
- **独占写面：** `runtime/c5_native_contribution.py`，`assembly/c5_assembly.py`，`substrate/projections/agent_session.py`、`runtime_run.py`、`legacy_process.py` 及专属测试。共同 `runtime/reconciliation.py`、observations、line-event port 和 schema 只给集成 owner 确定变更。
- **直接验证：** `st_test main/backend/tests/successor_runtime/test_c5_native_catalog.py main/backend/tests/successor_runtime/test_p3_c5_1_session_projection.py main/backend/tests/successor_runtime/test_p3_c5_2_attempt_replay_reconciliation.py main/backend/tests/successor_runtime/test_p3_c5_4_process_observations.py`。PG selectors：`test_p3_c5_2_reconciliation_postgres.py`、`test_p3_c5_3_projection_postgres.py`；批任务联合 selector 见 §9.4，由集成 owner 单次执行。
- **完成条件：** 新观察记录和 readback 使用受影响业务身份；对同一权威 effect 的成功、失败、未知与恢复判定保持；观察器不能写业务事实或制造 acceptance/receipt。
- **blocked_by：** 如真实旧记录需要共同 decoder/schema 支持，该具体 consumer 等待集成 owner；纯投影和 native 源可独立推进。

### 9.6 材料入库与一致性

- **目标：** 收敛真实材料 program、registry、movement、canonical writer、admission 与 projector driver 中的开发身份，保留 canonical 事实写入和有损投影的边界。
- **权威输入与现成接口：** `capabilities/ingest_c7*`、`c7_native_contribution.py`、`assembly/c7_assembly.py`；PG candidate values、registry/admission、`c7_canonical_write.py`、`c7_projector_driver.py`。当前 `mrw.successor.c7.*`、`c7:projection`、`c7:structured`、`ingest_index.c7.v1` 沿实际创建/读回路径迁移。
- **输出：** canonical commit、movement 与 projector 元数据从原业务定义取得身份；历史 admission/receipt/readback 保留版本；交付 C9 source 所需确定字段，不改其事实 owner。
- **独占写面：** `capabilities/ingest_c7*.py`、`c7_native_contribution.py`，`assembly/c7_assembly.py`；`substrate/postgres/ingest_c7_candidate_values.py`、`ingest_c7_registry_handler.py`、`ingest_c7_movement_admission.py`、`c7_canonical_write.py`、`c7_projector_driver.py`、`c7_document_readback.py`、`c7_production_admission.py` 及专属测试。global canonical table/schema 和 C9 facade/source 属集成及其原 owner；§2.4 的历史 migration adapter 不作批量搬移。
- **直接验证：** `st_test main/backend/tests/successor_runtime/test_c7_native_catalog.py main/backend/tests/successor_runtime/test_p4_c7_1_program.py main/backend/tests/successor_runtime/test_p4_c7_2_commit_readback.py main/backend/tests/successor_runtime/test_c7_movement_decision_parity.py main/backend/tests/successor_runtime/test_c7_movement_failure_reverse.py main/backend/tests/successor_runtime/test_c7_semantic_movement_completeness.py main/backend/tests/successor_runtime/test_s2b_c7_ingest_registry.py`。PG selectors：`test_c7_canonical_write_projector_postgres.py`、`test_c7_movement_admission_postgres.py`、`test_c7_production_admission_runner_postgres.py`；C9 接口稳定后集成 owner 运行 `st_test main/backend/tests/successor_runtime/test_i1_c7_c9_assembly.py`。
- **完成条件：** 原 admission→canonical write→projector→readback 使用受影响业务身份，projection 不能冒充 canonical write，failure/reverse 与重试范围保持；旧记录不因改名获得新 admission 或权限。
- **blocked_by：** 精确 schema/global table 改动和 C9 接口由对应 owner 合入；仅这些相关持久集成验证等待，无依赖的程序和 registry 部分继续。

### 9.7 知识产物、报告与导出

- **目标：** 在原知识 native/core/assembly 迁移基础上，把实际 artifact handler、production authority、导出 token 与交付读回闭合。该包复用 `native_semantics` 原 owner，不并行创造第二位 C8 写入者。
- **权威输入与现成接口：** 原知识 capabilities/`assembly/c8_assembly.py` 已采用的业务对象；`substrate/postgres/c8_artifact_handler.py` 的报告 binding、`c8_production.py` 的 `c8.production.v1`、graph-loss/registry/projector 默认身份；`c8_export_token_state_handler.py`、`staged_artifacts.py`、`research/artifacts.py`。稳定的 report/export-token 业务存储状态仍归原 store。
- **输出：** 真实知识 artifact/report 绑定、production authority、交付与 export-token receipt 使用对应业务版本；原 canonical artifact 与 staged/export state 边界保持，native 定义供 consumers 直接读取；历史 artifact/graph offset/receipt 原版本可读。
- **独占写面：** 原 `native_semantics` 已拥有的知识 capability core、`assembly/c8_assembly.py`，加 `substrate/postgres/c8_artifact_handler.py`、`c8_production.py`、`c8_export_token_state_handler.py`、`c8_graph_projector.py`、`c8_material_handler.py`、`staged_artifacts.py`、`research/artifacts.py` 的实际受影响身份及专属测试。`src/mrw_functorial_kit/contributions/` 已有工作向集成 owner 交接后不再双写；若真实消费者要求改 `main/backend/app/services/llm_report_export_token_state.py` 或 `main/backend/app/models/llm_report_export_token_state.py`，先报确切字段，由集成 owner 协调写面，不能把稳定业务 v1 自动升级。
- **直接验证：** `st_test main/backend/tests/successor_runtime/test_s2b_c8_export_token_state.py main/backend/tests/successor_runtime/test_i1_c8_3_delivery_assembly.py main/backend/tests/successor_runtime/test_c8_movement_closure_pure.py`；复用原 owner 已验证 native/report 接口范围，身份变更影响时追加 `st_test main/backend/tests/successor_runtime/test_c8_native_catalog.py` 及其原报告 selectors。PG selectors：`test_c8_movement_closure_postgres.py`、`test_c8_research_artifact_delivery_bridge_postgres.py`。
- **完成条件：** 原知识写作/报告执行到 artifact delivery 与持久 readback 的默认身份一致；stage、issue、export-token 的原权限、状态迁移、失败与幂等保持；实际 delivery 证据独立于 catalog 命名或测试注册。
- **blocked_by：** 仅共享 schema、贡献消费者和外部 export-token store 的受影响字段需集成 owner 协调；native/core 与 PG 面同 owner 顺接，已有产物不重派重做。

### 9.8 默认运行装配补充包：工作流与投影

默认装配检查继续发现工作流和投影的 family、cell、kernel ID 仍有旧身份。以下两包已分派，状态均为 `IN_PROGRESS`；方案整体保持 `IMPLEMENTATION_IN_PROGRESS`。此前 catalog 的 9 项通过仅证明其原检查范围，不计作 default runtime 身份迁移完成。

| 当前包 / owner | 目标与权威输入 | 独占写面与输出 | 验证与完成条件 |
|---|---|---|---|
| 工作流真实运行 / `structure_native` | 原 `capabilities/c1_native_contribution.py` 拥有工作流定义编译、运行观察和状态恢复；family 为 `mrw.workflow`，三 cell 为 `workflow.definition.compile.v2`、`workflow.runtime.observe.v2`、`workflow.state.restore.v2` | 原 owner 继续单写该 native-author 源、`assembly/c1_assembly.py` 及专属测试；真实默认 family/cell/kernel metadata 从该权威定义读取，历史身份仍按 §9.1 显式读取 | `st_test main/backend/tests/successor_runtime/test_c1_native_catalog.py main/backend/tests/successor_runtime/test_p5_c1_slice_programs.py main/backend/tests/successor_runtime/test_i1_c1_c3_assembly.py`；原默认装配须实际产生业务身份并保持编译、观察与恢复边界 |
| 投影真实运行 / `projection_identity` | 原 `runtime/c9_native_contribution.py` 拥有命令查询、客户端合同与读模型；family 为 `mrw.projection`，三 cell 为 `projection.command-query.v2`、`projection.client-contract.v2`、`projection.read-model.v2` | 同一原 owner 扩写该 native-author 源、`assembly/c9_assembly.py` 及专属测试，复用已有 facade/identity 迁移；默认 family/cell/kernel metadata 消费同一权威定义 | `st_test main/backend/tests/successor_runtime/test_c9_native_catalog.py main/backend/tests/successor_runtime/test_p4_c9_1_facade_contracts.py main/backend/tests/successor_runtime/test_p4_c9_3_transport_dto.py`；默认装配、原命令回执及查询读回一致，原权限和历史 decoder 保持；材料联合 selector 仍由集成 owner 按 §9.6 执行 |

两包均沿 §3 的 cwd、Docker/kit 环境执行。主线独占 aggregation base、`assembly/successor_assembly.py` 与 expected-coverage 消费者，从 family owner 的权威 cells 派生实际聚合和预期覆盖，禁止手抄第二份 cell 清单。各包交付接口后才执行相关整体装配验证；仅聚合消费与跨包验证等待此依赖，各自 native/kernel 工作可继续。集成验证入口为 `st_test main/backend/tests/successor_runtime/test_i1_assembly_composition_root.py`，并沿 §3 在一致声明上运行适用 check/gates。

### 9.9 收敛顺序与本节验收状态

| 依赖或资源 | 顺序与解除条件 | 可以先做的独立工作 |
|---|---|---|
| 来源共享身份→批任务装配 | 来源 owner 交付确切 shared 接口，批任务消费者随后同步 | 批任务计划/归约、来源其余 stage、其他四包 |
| 批任务持久结果→任务观察 | 双方固定 receipt/readback 字段后运行一次联合装配 selector | 各自原 program 与只读 projection |
| 材料/知识→投影 source | family 提交字段/codec，原 C9 owner 接入；联合验证使用一致候选 | canonical writer 或 artifact handler 的局部实现 |
| native→共享贡献/registry | 各 family 定义稳定，集成 owner 从同一 authority 派生并运行适用 check/gates | 无依赖的 family kernel 与历史 decoder |
| 工作流/投影权威 cells→聚合与 expected coverage | 两包原 owner 交付真实默认定义，主线统一消费，随后运行整体装配 selector；无第二份手抄清单 | 各自 native/kernel 与无依赖 family 实现 |
| 各包 PG fixtures/数据库 | 专属实例只有一个写测试窗口；每组完成释放资源，再运行下一组 | 无数据库且使用独立 tmp 的纯测试 |
| 真实 API→worker→持久读回 | 集成 owner 在受影响依赖稳定后集中执行 | 文档、纯测试、无共享写面的实现 |

每包按“结果 / 改动文件 / 实际命令与原退出码 / 历史兼容边界 / 未完成对象与 blocked_by”回传。已存在局部 PASS 只有依赖未变才可标记 `kept`；实际本轮执行标为 `passed`，skip/blocked/not_run 不计通过。集成 owner 统一维护共享声明、用户链与整体完成判断；不要把各包的源文件修改或 catalog 通过加总成真实运行迁移完成。

本节为分发合同；追加时仅核验路径、测试 selector 文件存在性与 Markdown/bash 结构，没有执行上述产品测试，也没有新增运行事实。

2026-10-04 实施续接：十个根贡献转发出口已退出；剩余八类真实运行身份迁移继续按 §9 分发。原 GLM 执行因 429 中断，五个未完包保留局部改动并转交 `gpt-5.6-sol/high`，没有重做已完包。聚合预期覆盖已从八类作者声明派生为27项业务 cells；目前仅 import 通过，不计运行完成。重建持久化验收发现源指针与重建偏移 owner 碰撞，投影 owner 正在共同来源修复；同批材料 HTTP 只读链通过。各 PG 包仍由主线串行验收。

</details>

## 10. 当前维护收敛框架与串并行分发包

2026-10-05，状态：`IMPLEMENTATION_COMPLETE / LOCAL_MAINTENANCE_VERIFIED`。本节解决开发入口不自洽、活动源码仍以开发编号命名、Graph 页面职责集中、工具声明与接线重复、当前说明夹杂旧执行叙述五类维护问题。它沿用 §2 的业务对象与事实 owner，保留通用平台能力、Codex Core、主仓 WebUI、宿主 OAuth、项目数据及当前业务运行身份。上一轮的运行身份迁移与本轮源码维护是两个完成范围；本轮不重开生产阶段，不以文件数、目录数或代码行数作为验收门槛。

### 10.1 从业务对象确定维护结构

平台由项目范围内的业务操作及其有序组合成立：工作流描述可执行关系，来源与采集取得候选，批任务承载提交和重试，材料与知识由原 writer 落事实，观察与投影只读回这些事实。工具是这些操作对 Codex 的有权限入口，Graph 是信息关系和操作结果的可视表示，开发入口负责装配与验证声明。三者不重新拥有业务事实。

把这些对象及允许的变换记为 `D`。观察语境 `C` 包含 native 声明、工具调用、API/持久读回和页面显示；只在确有受限读映射时加入语境箭头。每个语境的表示由原 owner 给出，映射沿真实接口投影，因此可用预层环境描述局部视图：

$$
X : \mathcal C^{\mathrm{op}} \longrightarrow \mathbf{Set}.
$$

这里的限制映射只表示删减可见信息，不执行工具、不修改状态，也不授予权限。实现保留现成类型、模块、贡献与投影；没有实际重叠条件和粘合见证的视图不宣称满足层条件。旧文件名到业务名的改写是实现表示替换，受信任的 project scope、已业务化的 codec/digest/operation ID 和持久字节保持同一对象身份。§10.8 单列的检索面板仍默认构造旧编号 schema，需在原 authority 增加业务版本并保留显式旧版读取；这是具名合同迁移，不扩大到其他身份。

对受影响的操作，实施包须比较“原声明→原消费者”与“业务名声明→同一消费者”两条路径。所需二维兼容见证是工具可见 schema/权限/失败、Graph 交互、运行装配及读回在约定观察下相同；纯 import、注册数量或生成成功不构成该见证。保留有序复合不推出工具可以并发执行；开发与测试是否并行另由依赖和资源表决定。

| 对象 / 唯一权威 | 派生方向 | 本轮收敛与保留约束 |
|---|---|---|
| kit 依赖来源：`pyproject.toml` 的固定 Git revision；后端 `requirements.txt` 消费相同 revision | 安装来源→导入位置/安装 metadata 核验→原 `scripts/dev.py` 子命令 | 默认依赖可复现；显式本地 kit 开发可覆盖来源且必须核对实际导入路径，不默默退回另一来源 |
| 业务 native 定义：`successor_runtime/capabilities`、`runtime` 下原作者定义 | native→family contribution→唯一 project catalog→原装配与 registry/sketch | 业务名称成为活动 import/export；既有业务 ID/codec/digest 不变，删除已无消费者的旧编号转发；检索面板的具名 schema 迁移按 §10.8 处理 |
| 项目工具：原 `CoreToolSpec` / handler，已有 `FacilityBinding` 与原业务 service | 同一原生定义→spec/handler 投影→`CoreToolRegistry`→`codex_macro_binding` | 人工确定业务参数、权限、失败和特殊 handler；规则派生机械包装与注册，不把模型参数变成 scope 来源 |
| Graph 信息、编辑与运行结果：原 API、workflow DSL、staging/rollback 和 audit 接口 | 原事实/用户编辑意图→现有 hooks、realizer、renderer→页面 | 页面负责组合与交互；纯几何/归一化、模板状态与数据读取按现成职责归位；可复用重复删除，语义不同的转换保留 |
| 当前文档与历史记录：各原事实 owner、§8 和生产 06 顶部 | 当前入口→现行说明 / 明确历史入口 | 当前说明移除已退役 core 的执行叙述；冻结、恢复、hash 与历史路径不变，业务草稿/暂存 `stage` 不是开发编号 |

### 10.2 当前问题、共同接口与阶段依赖

已复核：`scripts/dev.py check` 因 venv 的已安装 kit 与强制 Desktop editable 路径不一致而 exit 1；这是开发入口问题，原错误不改写为贡献检查失败。GraphPage 为约 7082 行、project_tools 为约 7033 行，仅作为职责集中的定位证据。C1/C9 等活动 Python 导出仍含编号，§8 已完成的运行 identity 保持其业务版本；补查的检索面板默认 schema 仍含旧编号，属于 §10.8 具名声明层缺口，不推翻或扩张 §8 的验收范围。`agent_chat.py` 的旧 core 入口返回 410，现有工具合同仍被 Codex 消费。后端 README 的 2026-02 进度与宏架构中已退役 `core.py` 引用需要更新。以上检查不在方案阶段重复运行。

方案制定时每包初始状态为 `NOT_STARTED`；下表列可开发前沿，实际实施状态见 §10.11。设计与接口由主线维护；包作者复用明确规则，禁止递归派发。同形规则先有一个真实消费者见证，再扩批；无依赖工作可直接推进。

| 阶段（业务名称） | 可并行工作包 | 串行交接与真实前置 |
|---|---|---|
| 开发入口与责任边界 | 开发依赖来源、Graph 页面职责、当前文档与根对象盘点、工具贡献首例、工作流源码出口、投影源码出口 | 各包独占写面；规则 owner 单写 `project_tools.py`；共享 catalog 与装配引用由集成 owner 串行合入 |
| 工具族与业务出口收敛 | 查询与发现工具、写作与工作流工具、其余业务源码出口分族 | 两个工具包依赖首例的实跑接口；已有业务内核可先分析。其余源码族复用工作流首例的身份保持/消费者迁移方式，投影包独立推进 |
| 原消费者组合验证 | 纯测试可按独立临时目录并发；文档路径核对可继续 | 集成 owner 统一合入共享消费者、sync/check、贡献测试和适用七项 gate；frontend build/e2e、PG、宿主读回各占独立窗口 |
| 当前入口交付 | 现行文档落定、准确根对象处置、结果汇总 | 文档依赖已采用的命令与命名；删除/归档仅对已核实对象执行，冻结恢复原件不移动；所有实施包达到本节退出条件才报告本轮完成 |

```mermaid
flowchart TD
  env[开发依赖来源] -->|提供验证环境| integration[原消费者组合验证]
  graph[Graph 页面职责] -->|交付交互与投影| integration
  pilot[工具贡献首例] -->|规则与原消费者见证| query[查询与发现工具]
  pilot -->|规则与原消费者见证| write[写作与工作流工具]
  query -->|交付声明及内核| integration
  write -->|交付声明及内核| integration
  workflow[工作流源码出口] -->|迁移方式与保持见证| families[其余业务源码出口]
  workflow -->|交付确定接口| integration
  projection[投影源码出口] -->|交付确定接口| integration
  families -->|交付确定接口| integration
  docs[当前文档与根对象盘点] -->|精确引用与处置建议| delivery[当前入口交付]
  integration -->|已采用命令与验证结果| delivery
```

共同接缝：工具规则交付 typed 原生定义、由同一定义派生的 spec/handler 投影、实际注册调用和验证入口；Graph 包不改 API 合同，若发现合同缺口只向集成 owner 提交具体字段；各源码包交付新业务符号、被删除出口、保留历史入口及全部直接消费者，集成 owner 统一改项目目录与跨族 imports。新增规则只解决当前不能表达的真实形状；不预建通用 runtime、恢复、调度、schema 或证据平台。

### 10.3 验证环境与资源窗口

本节命令供后续实施使用，本轮方案只验证命令与路径可定位。cwd 根目录固定为 `/Users/wangyiliang/market-research-workflow`。§3 的镜像、Desktop 挂载和 §9 的 PG 实例是上一轮环境记录；已清理的实例不能作为当前可用前提。集成 owner 接手时只读核对所需环境一次，已有兼容 Docker 测试镜像优先复用；不存在时由其沿 `main/backend/Dockerfile.test` 准备，依赖包作者不各自安装。

以下 `maint_test` 是文档内原 pytest runner 的调用缩写，不写入新调度脚本。只用于已确认 mock/纯逻辑 selectors；它使用现有 Python 3.11 venv，显式拒连本机业务数据库、Redis、ES。此处设置 `PYTHONPATH` 仅提供仓库源码，不注入个人 kit checkout；kit 来源由开发依赖包核验。若依赖不满足，记录同一个环境原因，待恢复后重跑相关组，不将 skip 算作通过。

```bash
cd /Users/wangyiliang/market-research-workflow
maint_test() (
  PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$PWD:$PWD/src:$PWD/main/backend" \
  DATABASE_URL=postgresql+psycopg2://postgres:postgres@127.0.0.1:1/postgres \
  REDIS_URL=redis://127.0.0.1:1/0 ES_URL=http://127.0.0.1:1 \
  main/backend/.venv311/bin/python -m pytest -p no:cacheprovider -q -rs "$@"
)
```

Docker 同等执行使用既有镜像的 Python、仓库绝对路径只读挂载和同一 selectors，保留原退出码；确需构建时的现成入口是 `docker build -f main/backend/Dockerfile.test -t mrw-maintenance-tests:local .`。镜像构建只属于后续集成资源准备，本轮不执行。默认依赖修复后，`scripts/dev.py check/test/gates` 必须使用声明的固定来源成功运行；`sync` 仍仅在集成 owner 的可写窗口运行。

| 资源端口 / 可变面 | 持有人、冲突与使用范围 |
|---|---|
| Python venv、kit checkout、安装 metadata | 开发依赖 owner 独占安装窗口；运行测试期间不改依赖。显式本地 kit 模式验证用任务专属环境，不能修改运行宿主的 kit |
| 纯 pytest / 全局工具 registry | 每个命令独立进程和 pytest 临时目录；不在同一进程并发改 `_MOUNTED_MCP_TOOLS`、环境变量或 registry。无共享文件写入的只读组可并发 |
| `contributions/project_catalog.py`、`src/mrw_functorial_kit/contributions/`、`registries/`、`sketches.json`、`.functorial/contributions.json`、`functorial-kit.json` | 集成 owner 单写；sync 前后与 check 使用同一稳定声明，包作者不手改派生文件 |
| `main/frontend-modern/dist`、`node_modules/.tmp`、Vite cache、`test-results`、`playwright-report` | Graph owner 提交后集成 owner 单窗口运行 build/e2e；不能以测试文件不同判断可并发 |
| Playwright `4173` | 原配置 `reuseExistingServer=false`、`--strictPort`，mock 代理固定 `127.0.0.1:1`；不占日常 `5173`、API `8000` 或 WebUI `8172`。端口占用仅阻塞该组 |
| PostgreSQL / Redis / Celery / 业务上传目录 | 本轮默认源码表示维护不变更持久语义；实际改到事务/codec/writer 或无法排除投影 source 路径影响时，按 §10.8 的 `SUCCESSOR_TEST_DATABASE_URL` guard 和两个固定数据库名要求，由集成 owner 在专属 PG 实例串行执行；不能仅换共享实例的库名，不复用已删除实例或日常 DB，不以纯测试代替 |
| 宿主 OAuth、WebUI SQLite、原会话、provider 账户 | 所有包只读保留；mock/native-binding 测试不登录、不中断宿主服务。仅实际改变线上接线时由集成 owner 追加受影响读回窗口；不默认重演付费 provider turn |
| 冻结/恢复/evidence、根旧对象 | 原件只读；清理包核对精确对象、引用、恢复依赖后逐项交接。无全局 prune、广域删除或冻结 manifest 重写 |

### 10.4 开发依赖来源包

- **目标：** 让项目默认开发命令在可复现安装来源上自洽，同时支持显式本地 kit 开发。
- **权威输入与现成接口：** `pyproject.toml`、`main/backend/requirements.txt` 的相同固定 Git revision；`scripts/dev.py` 的 `_python_executable`、`_command_environment`、`_require_local_kit`、`setup/check/sync/test/gates`；现有 `tests/checkers/test_dev_entry.py`。
- **输出：** 默认模式核对实际安装 provenance 与固定 revision；显式本地模式允许传入用户自选 checkout 路径，核对实际导入位于该路径并标明本地来源。缺失或错配仍报可操作错误；不能只删校验，也不能仅比较包版本。`setup` 在选定 Python 中安装选定来源，普通 `check` 不隐式安装。具体选项名由该包在原 CLI 中确定并回传，文档不把未实现参数当现成命令。
- **独占写面：** `scripts/dev.py`、`tests/checkers/test_dev_entry.py`、`pyproject.toml` 的开发来源配置；确有重复固定依赖需同步时包括 `main/backend/requirements.txt` 该依赖行。固定 revision 不因维护自动升级。README 由文档/集成 owner 接收确定命令后更新。
- **直接验证：** 根目录 `maint_test tests/checkers/test_dev_entry.py`；修复后 `PYTHONDONTWRITEBYTECODE=1 python3 scripts/dev.py check`。在原测试增加默认固定来源、任意合法本地路径、来源错配拒绝和子命令退出码传播用例；显式本地模式的实测准确命令随包回传。安装探针只在专属环境执行。
- **完成条件：** 默认和显式本地两种来源都经过真实导入核验；固定来源可重建；不要求他人拥有同一 Desktop 目录；source mismatch 不被吞掉；原 catalog/check/test/gates 分界保持。
- **blocked_by：** 源码修复无前置。固定来源首次安装若缺网络或制品仅阻塞该模式实测，保留具体恢复条件；已可用纯测试与独立包继续。

### 10.5 Graph 页面职责包

- **目标：** 页面只组合业务状态与交互，把纯几何/样式、workflow DSL 转换、模板 staging/rollback、audit/dry-run 归一化放回现有适合的职责边界，删除已确认语义相同的重复。
- **权威输入与现成接口：** `main/frontend-modern/src/pages/GraphPage.tsx`，同级 `graph/hooks/`、`graph/renderers/`、`graph/realizer/`、`GraphWorkspace.tsx`；原 workflow API、Graph 类型与现有 e2e。
- **输出：** 纯变换有明确输入/输出；需要 React 生命周期的状态复用/扩充原 hook；renderer 继续负责显示；模板草稿与回滚保持原状态和失败归属。只有实际职责无法放入现有模块时新增小模块，不新增 manager/store 或重复 API DTO。先提交真实重复及原消费者清单，移除其中可消除部分，而非整段换文件后宣称清简。
- **独占写面：** `GraphPage.tsx`、`src/pages/graph/` 和 `tests/e2e/graphpage.spec.ts`、`graph-clue-chain.spec.ts`、`information-topology-graph.spec.ts`、`graph-runtime-pixel-gate.spec.ts` 的受影响断言；共享 API 类型、module manifest 与后端由集成 owner 单写。
- **直接验证：** cwd `main/frontend-modern`，依次 `npm run lint`、`npm run build`、`npm run check:graph-force3d-frontend-contract`、`npm run check:graph-page-i18n-slice`；`FRONTEND_E2E_PORT=4173 VITE_API_PROXY_TARGET=http://127.0.0.1:1 VITE_CODEX_PROXY_TARGET=http://127.0.0.1:1 npx playwright test tests/e2e/graphpage.spec.ts tests/e2e/graph-clue-chain.spec.ts tests/e2e/information-topology-graph.spec.ts tests/e2e/graph-runtime-pixel-gate.spec.ts --workers=1 --reporter=line`。使用已安装 Node/npm/pnpm/Playwright；build 与 e2e 占 §10.3 同一 frontend 资源窗口。
- **完成条件：** 现有图模式、选择/编辑、模板 staging/rollback、audit/dry-run、拓扑与渲染行为在原消费者中保持；确认重复被移除；页面不再内嵌可独立的纯转换和成组模板状态责任。体积是结果描述，不设行数目标。
- **见证缺口：** 现有四个 e2e 已覆盖模式切换、curated submit/conflict、template dry-run、clue chain 和只读拓扑刷新；未覆盖完整模板 create/rename/delete/version/stage promotion/diff/rollback/audit/replay。实际迁出的控制职责须在原测试补相应行为，不能把已有 mock 通过当作全部保持。pixel gate 允许 fallback framing，不证明布局完全等价。`GraphWorkspace` 当前服务 WorkflowManager，仅在 node/edge/interaction 合同确实相同时共享其 ECharts、visual-state 与图例逻辑。
- **blocked_by：** 实现无后端前置；browser binaries/4173/构建资源只限制对应验证。真实 API 合同变化若出现，由集成 owner 先处理该接口，其他纯变换继续。

### 10.6 工具贡献首例包

- **目标：** 以原 `FacilityBinding` 和 `facility_tool_projection` 为起点，让一个真实工具的 spec、handler、注册和 Codex binding 消费同一声明，稳定可被后续工具族复用的最小规则。
- **权威输入与现成接口：** `main/backend/app/services/agent_core/contracts.py`、`registry.py`、`macro_tools.py`、`project_tools.py`；`services/llm/codex_macro_binding.py` 的 registry 消费；既有 `NativeContributionRule` / `compile_native_contribution` 机制。`CoreToolSpec` 的输入 schema 只用于实际工具参数解析，不再平行描述一次业务 schema。
- **首例与输出：** 复用已接入的 `project_retrieval_current_facility` 所用 `FacilityBinding` 通路，以原 `source.discovery.plan` 为迁移首例：其原 spec/handler→`CoreToolRegistry`→Codex native dynamic tool 的调用与结果均须保持；现有来源信任测试已有真实 registry 断言及 DNS mock。再将一个现有 `skill.load` 查询工具用同一规则表达，确认规则不暗取首例 singleton。工具名、业务 spec、handler 内核及权限声明人工确定；注册循环、机械 wrapper 和投影从同一定义派生。Codex namespace 按原 `codex_macro_binding.py` 的规则从逻辑名派生，不复制一张别名表。仅当当前协议不能表达真实依赖注入/失败形状时扩原项目规则；kit 机制确有缺口才由主线单独接手，不让各工具包另造 adapter。
- **独占写面：** `project_tools.py` 的装配/公共投影区与首例实现、`macro_tools.py` 的绑定复用、必要的原 `contracts.py`/`registry.py` 接缝及首例测试。允许在同一 `agent_core/` 下新增一个项目工具贡献规则模块；源清单仍只在原工具装配入口维护。Codex shared binding 的必要消费者变更由集成 owner 合入。
- **直接验证：** 根目录 `maint_test main/backend/tests/unit/test_source_candidate_trust_unittest.py main/backend/tests/unit/test_agent_macro_facilities.py main/backend/tests/unit/test_codex_native_macro_binding.py main/backend/tests/functorial_debt/test_w02_agent_core_no_throw.py main/backend/tests/functorial_debt/test_w02.py`；原测试中补原消费者的首例与非默认实例、错误声明拒绝、权限/scope/失败不变见证。首例交接后来源信任测试写面随之转给查询工具包。需要 kit 协议变更时其独立小领域测试结果与 MRW 消费者结果分别报告。
- **完成条件：** 首例和非默认工具由一份原生定义到达原 Codex 工具消费者；注册不执行业务 effect；错误 spec/缺失 handler 不静默落回旧表；所有实际依赖的绑定检查仍存在。规则接口、准确文件和验证结果交接后，才开放后续工具族。
- **blocked_by：** 原设施可复用路径无业务前置；实际 kit 来源测试受开发依赖包环境约束。未解决的规则形状只阻塞依赖它的工具，独立 handler 分析可继续。

### 10.7 查询与发现工具包 / 写作与工作流工具包

两包在 §10.6 的工具规则完成验证后复用；共用 `project_tools.py` 由首例 owner（进入本阶段后为集成 owner）单写。包作者在下表拟新增的职责模块中提供声明与特殊 handler，交集成 owner 一次替换旧定义/装配；不能两包同时删同一个大文件的不同片段。拟新增路径是分派写面，不宣称文件已经存在。

| 包 | 目标与权威输入 | 独占输出/写面 | 直接验证（根目录，`maint_test`） | 完成条件 / blocked_by |
|---|---|---|---|---|
| 查询与发现工具 | 原 `project_tools.py` 的 skill search/load、graph/structured query、source web search、candidate review 与诊断；复用 `CandidateSearchRequest`、`discover_candidates`、read-only runtime，不能因为工具显示为查询就删其已有持久记录或 provider effect | 拟新增 `main/backend/app/services/agent_core/query_tools.py`；只迁入已核对的查询/发现声明与特殊 kernel。专属 `test_agent_core_clue_chain_tool_unittest.py`、`test_source_candidate_trust_unittest.py`、`test_project_retrieval_execution.py` 中该包断言；公共 spec/registry 交集成 owner | `maint_test main/backend/tests/unit/test_agent_core_clue_chain_tool_unittest.py main/backend/tests/unit/test_source_candidate_trust_unittest.py main/backend/tests/unit/test_project_retrieval_execution.py main/backend/tests/unit/test_retrieval_candidate_consumers.py` | 原工具名/schema/result、搜索来源/候选资格、失败/读回保持；重复参数转发/registration 已由规则替代。依赖首例接口；外部搜索由原 mock 验证，无 live provider 前置 |
| 写作与工作流工具 | 原写作 save/conflict/citations、workflow/report、`ingest.url_pool.*`、batch/task 控制；保留原 service/原权限及 cooperative abort 的运行观察 | 拟新增 `main/backend/app/services/agent_core/authoring_tools.py`；专属测试在原 `test_agent_core_functorial_projection_unittest.py` 与 `test_agent_core_unittest.py` 中扩受影响行为。MCP mount/abort 共享生命周期仍由集成 owner 保持在原边界，不拆出第二控制器 | `maint_test main/backend/tests/unit/test_agent_core_functorial_projection_unittest.py main/backend/tests/unit/test_agent_core_unittest.py main/backend/tests/unit/test_rapid_native_macro.py` | 版本冲突、取消/延迟/需审批结果、权限及持久 readback 仍由原 owner 产生；不以 tool completed 推导业务完成。依赖首例；若新增真实写通路测试，先使用专属 fixture，不能调用日常数据或假造 receipt |

共同输出必须列出从原 `project_tools.py` 删除的定义和仍保留的真实职责；MCP 挂载属于开放扩展轴，静态项目工具属于有明确定义的贡献族，不把二者强并成固定词表。现有合同类虽然含 `AgentCore` 名称，仍有活动消费者；只有依赖迁移完成才移除别名，旧 core 执行器不恢复。原装配还被 `main/backend/scripts/mrw_mcp_server.py`、`services/project_retrieval/execution.py`、`services/project_retrieval/service.py`、`agent_core/functorial/operator.py` 和 `run.py` 消费，集中集成须核对其接口；MCP 模块加载会构造 session service，不把启动 stdio bridge 当无副作用导入检查。

### 10.8 业务源码出口包

**共同目标：** 当前活动 import、public export、类型/函数说明直接使用 workflow/source/acquisition/batch/task/material/knowledge/projection 业务名。此包改变源码表达，不再次迁移已完成的运行 ID；唯一新增身份接缝为下文已确认仍默认构造旧编号 schema 的检索面板。先以工作流入口打通“native 作者→family contribution→装配→原测试”，投影出口可独立推进；随后复用同一命名与引用迁移方式，按下表分族实施。若只换文件名而活动消费者仍依赖编号别名，包未完成。

**共同权威与输出：** 原 native 定义与当前真实消费者是输入；业务名源模块及导出、原调用语义不变、无消费者旧出口删除、确有历史依赖的保留项是输出。新业务模块承接同一 native 对象，不能重新录入词表或复制实现。需要保留的每个旧入口在本节实际结果中逐项记“路径/符号、数量、真实消费者、owner、解除条件”；未盘点前数量为 `UNKNOWN`，不得写成 0。历史 decoder/version/幂等 digest 与冻结原路径原字节保持；源码重命名不统一升版，不修改业务草稿/暂存 stage。

下表路径前缀为 `main/backend/app/successor_runtime/`，列的是各包的现有源范围；对应的新业务命名文件归同一 owner。`src/mrw_functorial_kit/contributions/`、project catalog、共同 aggregate/装配根、各族之间的 imports、registry/sketch/config 引用全部交集成 owner 串行合入，包作者不双写。专属测试归该族；共享联合测试归集成 owner。

| 包 / 独占现有作者与装配范围 | 直接验证（根目录，`maint_test`，测试前缀 `main/backend/tests/successor_runtime/`） | 依赖与保留重点 |
|---|---|---|
| 工作流源码出口：`capabilities/c1_native_contribution.py`、`capabilities/c1_legacy_dsl.py`、`capabilities/c1_slice_acceptance.py`、`assembly/c1_assembly.py` | `maint_test main/backend/tests/successor_runtime/test_c1_native_catalog.py main/backend/tests/successor_runtime/test_p5_c1_legacy_oracle.py main/backend/tests/successor_runtime/test_p5_c1_legacy_dsl_parity.py main/backend/tests/successor_runtime/test_p5_c1_slice_programs.py` | 无规则前置；同一 owner 迁移当前 DSL 编译/验收的活动出口，保留历史 schema/decoder；集成 owner 接 family contribution 和跨族消费者，不能只改 native 外壳即交付 |
| 投影源码出口：`runtime/c9_native_contribution.py`、`capabilities/c9_2_search_retrieval_panel.py`、`capabilities/c9_evidence_matrix.py`、`assembly/c9_assembly.py`、`substrate/projections/c9_sources.py`、`substrate/postgres/c9_projection_sources.py` | `maint_test main/backend/tests/successor_runtime/test_c9_native_catalog.py main/backend/tests/successor_runtime/test_p4_c9_1_facade_contracts.py main/backend/tests/successor_runtime/test_p4_c9_3_transport_dto.py main/backend/tests/successor_runtime/test_c9_generalized_rollback_identity.py main/backend/tests/successor_runtime/test_s2c_worker_and_retrieval_surfaces.py main/backend/tests/successor_runtime/test_s2b_c9_evidence_matrix.py` | 独立于工作流实现；面板与证据矩阵按下文职责裁定；跨族消费者由集成 owner 接入；触及两个 source 模块的持久读写/历史解码路径时，必须完成下文专属 PG 验证 |
| 来源源码出口：`capabilities/source_library_c2_*.py`、`assembly/c2_assembly.py` | `maint_test main/backend/tests/successor_runtime/test_c2_native_catalog.py main/backend/tests/successor_runtime/test_p3_c2_shared_identity.py main/backend/tests/successor_runtime/test_p2_c2_1_contracts.py` | 复用工作流迁移方式；共享 source identity 先给批任务包，当前 source stage owner/codec 保持 |
| 采集源码出口：`capabilities/c3_native_contribution.py`、`capabilities/collect_c3*.py`、`assembly/c3_assembly.py` | `maint_test main/backend/tests/successor_runtime/test_c3_native_catalog.py main/backend/tests/successor_runtime/test_p3_c3_contracts.py main/backend/tests/successor_runtime/test_p3_c3_rollback.py main/backend/tests/successor_runtime/test_p3_c3_replay_shadow.py` | 复用工作流迁移方式；业务 service imports 交集成 owner，不改变 `CollectResult` 投影及产品 shadow 拒绝 |
| 批任务源码出口：`capabilities/agent_batch_c4*.py`、`assembly/c4_assembly.py` | `maint_test main/backend/tests/successor_runtime/test_c4_native_contribution.py main/backend/tests/successor_runtime/test_p3_c4_1_plan.py main/backend/tests/successor_runtime/test_p3_c4_2_retry_reducer.py` | 复用工作流迁移方式；来源共享 imports 等待来源符号，独立 reducer 可先改；原提交/重试身份保持 |
| 任务观察源码出口：`runtime/c5_native_contribution.py`、`assembly/c5_assembly.py` | `maint_test main/backend/tests/successor_runtime/test_c5_native_catalog.py main/backend/tests/successor_runtime/test_p3_c5_1_session_projection.py main/backend/tests/successor_runtime/test_p3_c5_2_attempt_replay_reconciliation.py` | 复用工作流迁移方式；共同 reconciliation 与投影 imports 交集成 owner，只读观察不能升级成事实写入 |
| 材料源码出口：`capabilities/c7_native_contribution.py`、`capabilities/ingest_c7*.py`、`assembly/c7_assembly.py` | `maint_test main/backend/tests/successor_runtime/test_c7_native_catalog.py main/backend/tests/successor_runtime/test_p4_c7_1_program.py main/backend/tests/successor_runtime/test_p4_c7_2_commit_readback.py main/backend/tests/successor_runtime/test_c7_semantic_movement_completeness.py` | 复用工作流迁移方式；writer/codec/admission 引用由集成 owner 定向同步，canonical 事实不搬迁 |
| 知识源码出口：`capabilities/c8_native_contribution.py`、`assembly/c8_assembly.py` 及其现有知识 native 作者模块 | `maint_test main/backend/tests/successor_runtime/test_c8_native_catalog.py main/backend/tests/successor_runtime/test_p4_c8_4_graph.py main/backend/tests/successor_runtime/test_p4_c8_5_program.py main/backend/tests/successor_runtime/test_c8_movement_closure_pure.py` | 复用工作流迁移方式；不得移动导出 token store、重编码 artifact 或恢复旧 core |

四个混合对象的裁定与交接如下；路径仍相对 `main/backend/app/successor_runtime/`。同一文件存在历史读取，不使其当前职责整体成为历史对象。

| 原对象 / family owner | 当前职责与源码业务出口 | 必须保留的历史范围 / 直接消费者 |
|---|---|---|
| `capabilities/c1_legacy_dsl.py` / 工作流 | 原生定义和装配实际调用的 DSL parse/validate/compile authority。将 `C1LegacyDSLReceipt`、`C1LegacyDSLFailure`、`build_c1_*` 及当前编译出口纳入业务名迁移；DSL 接受既有图格式的语义保持，不复制编译器 | schema/failure 继续引用 `capabilities/workflow_common.py` 的唯一声明；`HISTORICAL_*`、`decode_workflow_compile_schema`、read/replay 的旧版本、原 bytes/hash 保留。直接消费者为 `c1_native_contribution.py`、`assembly/c1_assembly.py`，同 family owner 维护；跨族引用由集成 owner 合入 |
| `capabilities/c1_slice_acceptance.py` / 工作流 | 当前 program/plan/observation 验收 authority；`C1SliceAcceptance`、`C1NamedStepObservation`、`accept_c1_slice`/`try_accept_c1_slice` 等活动类型/函数进入同一业务出口迁移 | 当前 `WORKFLOW_ACCEPTANCE_SCHEMA` 保持；`HISTORICAL_C1_ACCEPTANCE_SCHEMA` 及 `decode_workflow_acceptance_schema`、read/replay 的旧版 bytes/digest 保留。原 `assembly/c1_assembly.py` 继续消费该唯一验收实现，旧 exact-binding 只在真实依赖未解除时保留原路径 |
| `capabilities/c9_evidence_matrix.py` / 投影 | 证据矩阵投影 authority；当前 `EVIDENCE_MATRIX_SCHEMA` 已是 `mrw.projection.evidence-matrix.v2`，只收敛源码业务出口与说明，不再升版 | 集成 owner 单写直接消费者 `substrate/projections/evidence_matrix.py` 的 import/接线及共享测试；既有失败、authority ceiling、只读矩阵判断及历史证据保持，不能在消费者重写矩阵规则 |
| `capabilities/c9_2_search_retrieval_panel.py` / 投影 | `project_search_retrieval_panel()` 默认构造旧 `SURFACE_SCHEMA`；`assembly/s2c_ops_domain_surface_assembly.py` 在 current registry 消费该 schema。它是活动声明和纯构造器，不是仅冻结原件 | 注册状态为 `DECLARED_TYPED_READONLY_CONTROL_SURFACE_NO_RUNTIME_BINDING`，本次未发现线上 API/前端直接调用证据，不能宣称已部署 panel。旧 schema 属须保留的版本合同；当前默认声明/构造出口按下段迁业务版，原历史合同不原地改写 |

**检索面板必要接缝：** 投影 owner 在原面板 authority 将新构造默认 schema 定为 `mrw.projection.search-retrieval-panel.surface.v2`；旧 `mrw.successor.c9-2.search-retrieval-panel.surface.v1` 作为明示历史版本读取，不能让旧 payload 静默进入新构造器，也不能重新编码/重算其原摘要。当前文件尚无独立历史 decoder，该 owner 仅在同一原合同边界补明确版本分流与原字节读回；不另建映射表或第二套投影实现。状态判定、只读 authority、declared loss 与无 provider/index effect 保持；旧 movement/decision 记录仍作为历史 provenance，不变成新执行权限。集成 owner 单写 `assembly/s2c_ops_domain_surface_assembly.py` 的模块引用、schema_ref 与共享派生消费者，新 schema 从原定义读取。验证层级限定为纯构造器与 current registry，不新增 API/前端部署任务。原 `test_s2c_worker_and_retrieval_surfaces.py` 补新默认/旧版本显式读回/未知版本拒绝；集成 owner 执行 `maint_test main/backend/tests/successor_runtime/test_s2c_surface_assembly_wiring.py main/backend/tests/successor_runtime/test_s2b_cell_extension_wiring.py main/backend/tests/successor_runtime/test_s2b_c9_evidence_matrix.py`，以原消费者验证，不能只改 schema 字符串断言。此接缝未闭合仅阻塞该 panel 的迁移完成，其他投影源码可继续。

**投影持久兼容验证：** 当 `substrate/projections/c9_sources.py` 或 `substrate/postgres/c9_projection_sources.py` 的改名/导入迁移进入实际持久读写、历史 decoder、closure/source identity 或幂等路径时，集成 owner 必须在专属 PG 实例串行执行 `test_c9_projection_sources_postgres.py` 与 `test_c9_typed_source_evolution_postgres.py`，核对旧版 decoder、exact bytes/digest、同一 closure 重试幂等及历史版本不可变。无法证明不影响这些路径时也运行这两项；只有依赖面确定未变才按原归属记录 `kept`。

两文件读取的环境变量是 `SUCCESSOR_TEST_DATABASE_URL`，缺省会连接 `localhost/postgres`；fixture 会把 URL 的数据库部分替换为 `postgres`，再对固定名称 `mrw_c9_projection_sources_test`、`mrw_c9_typed_source_evolution_test` 执行 `DROP DATABASE ... WITH (FORCE)`、创建和清理。因而必须分配整个专属 PG 实例及有建库权限的测试账户，不能仅给共享宿主实例换一个 database 名；不得使用 `maint_test`、日常数据库或默认连接。以下命令仅供实施时在集成 owner 已核对实例归属、端口和账户后执行；未设置 URL 的 guard 立即失败，未回显 URL/凭据。

```bash
(
  cd /Users/wangyiliang/market-research-workflow || exit
  : "${SUCCESSOR_TEST_DATABASE_URL:?必须先设置已分配专属PG实例的URL，禁止宿主默认连接}"
  export SUCCESSOR_TEST_DATABASE_URL
  PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$PWD:$PWD/src:$PWD/main/backend" \
  DATABASE_URL=postgresql+psycopg2://postgres:postgres@127.0.0.1:1/postgres \
  REDIS_URL=redis://127.0.0.1:1/0 ES_URL=http://127.0.0.1:1 \
  main/backend/.venv311/bin/python -m pytest -p no:cacheprovider -q -rs \
    main/backend/tests/successor_runtime/test_c9_projection_sources_postgres.py \
    main/backend/tests/successor_runtime/test_c9_typed_source_evolution_postgres.py
)
```

该命令不使用 xdist；专属实例与两个固定 DB 名在整个命令期间只给集成 owner 一个写窗口。连接失败可能被原 fixture 记为 skip，故须同时读取原退出码和 skip 摘要；选中项有 skip/not_run 就不能完成此验证。实例未分配时只记该持久验证 `blocked_by=专属PG实例未分配`，不启动或删除任何现有服务；本轮文档编制不运行此命令。

源码扫描使用 `rg -n 'C[1-9][A-Z_]|\bc[1-9]_|source_library_c2|collect_c3|agent_batch_c4|ingest_c7' main/backend/app src/mrw_functorial_kit contributions`，匹配只作候选，逐项区分当前依赖、真实历史读取和普通值；不批量替换字符串。

**整组完成条件：** 活动业务调用链不再通过编号转发才能到达 native 对象，包括上述 DSL/验收和两个投影 authority；同一身份只有一份实现；无消费者旧出口删除；保留项均有具体数量、owner、历史消费者和解除条件。既有业务 ID/codec/digest 的保持见证通过；检索面板新业务版与旧版显式读取分别在原声明消费者验证；受影响投影持久路径按专属 PG 条件验证。未知历史依赖只阻塞其对应出口删除，不能笼统阻塞全部源码工作。任何新增永久别名必须有真实消费者理由，而非为了少改测试。

### 10.9 当前文档与根对象包

- **目标：** 根导航、后端 README 和宏架构说明可按现行能力阅读；旧进度与根目录杂物分开，降低阅读负担。
- **权威输入与现成接口：** 根 `README.md`、`docs/development/README.md`、`main/backend/README.md`、`main/backend/docs/AGENT_MACRO_ARCHITECTURE.md`；当前 `agent_chat.py`/Codex binding/主仓 WebUI；19/06、§8；根 `0`、release notes、截图、stage evidence 仅为待逐项核对的对象。
- **输出：** 修正当前说明中的旧 8.x 开发状态和 `core.py` 执行叙述；需要保留的历史段落明确日期与历史入口。根对象在本节交付结果中列精确路径、当前引用、归属、恢复用途及保留/归档/删除决定；未知用途标 `UNKNOWN`。当前方案只做盘点，后续实施才执行已核实的逐项操作；stage evidence 与冻结恢复输入原位保留。
- **独占写面：** 上述四份现行文档及本方案状态段；实际根对象处置须在盘点完成后由主线指定精确文件。`AGENTS.md`、19/06、历史执行证据只读。本轮设计 owner 只写本方案，其他文档由主线负责，后续实施接手时重新明确单写 owner。
- **直接验证：** 根目录依次 `python3 scripts/check_latest_dev_docs_structure.py`、`python3 scripts/check_docs_root_migration_manifest.py`、`python3 scripts/checkers/check_docs_root_content_plan.py`、`python3 scripts/checkers/check_docs_root_navigation_drift.py`；仅维护正文时先检查新增相对链接及 `git diff --check -- docs/development/MRW结构整理方案与分发包.md main/backend/README.md main/backend/docs/AGENT_MACRO_ARCHITECTURE.md README.md docs/development/README.md`。引用盘点用 `rg -n -F -- '精确相对路径' README.md docs development scripts main`，退出 1 仅代表此观察面无匹配，不能独自证明无运行/恢复依赖。
- **完成条件：** 当前入口中的实现状态与原事实 owner 一致；旧 Agent Core 不再被描述为现行执行核心；旧记录原事实保留；根对象的实际动作与保留项可逐一读回，未确认对象不误删。
- **blocked_by：** 当前历史错位可独立修；新 CLI/源码名字的最终说明等待对应包确定；单个对象的恢复依赖只阻塞该对象的归档/删除。旧磁盘 98% 是历史观察，不作为本轮 blocker，也不再次开展 Docker 清理。

### 10.10 集成收口、退出条件与交付口径

集成 owner 拥有唯一 project catalog、family contribution 的共享出口改名、registry/sketch/配置、`assembly/base.py`/`successor_assembly.py`、共享前端类型、Codex binding 和跨族消费者。它从包交付的原生定义派生接线并删除旧重复，不手工重录各族 cell、failure 或 codec 清单。工具规则、family 改名和派生 sync 按共享写面串行合入；开发阶段不逐小修冻结，不为包级结果新增审批链。

直接验证：根目录在依赖包修复且声明稳定后依次 `PYTHONDONTWRITEBYTECODE=1 python3 scripts/dev.py sync`、`PYTHONDONTWRITEBYTECODE=1 python3 scripts/dev.py check`、`PYTHONDONTWRITEBYTECODE=1 python3 scripts/dev.py test`、`PYTHONDONTWRITEBYTECODE=1 python3 scripts/dev.py gates`。联合装配使用 `maint_test main/backend/tests/successor_runtime/test_i1_assembly_composition_root.py main/backend/tests/successor_runtime/test_i1_c1_c3_assembly.py main/backend/tests/successor_runtime/test_i1_c4_c5_assembly.py main/backend/tests/successor_runtime/test_i1_c7_c9_assembly.py main/backend/tests/unit/test_codex_native_macro_binding.py`。选择器与门禁缺少可靠影响选择时运行原完整相关扫描一次；这不扩展成全后端 suite、生产构建或发布验证。仅实际改变运行接线/持久语义时追加原受影响 API→worker/工具→持久读回，未涉及的上一轮运行证据只记原归属下的 `kept`。

本轮独立退出条件如下，全部满足才将 §10 实施状态改为完成：

1. 默认固定 kit 来源和显式本地来源均真实可核验，`scripts/dev.py` 不依赖固定个人路径，来源错配仍拒绝。
2. Graph 的独立转换、模板状态与渲染职责有唯一承载；确认重复已消除，原用户交互与失败行为有适用见证。工具原生定义经统一规则进入原 Codex 消费者，同形能力不再手写第二套 spec/registration/机械 wrapper；权限、取消、冲突及读回保持。
3. 活动源码消费者直接使用业务名；已无消费者的旧编号出口删除。每一保留历史路径/别名都有精确对象、数量、owner、真实依赖及解除条件；已有业务身份、冻结和恢复字节未被重新解释或改写。检索面板的具名新业务 schema 与旧历史版本显式分流，并仅按实际声明层消费者报告完成范围。
4. 唯一 project catalog、原装配与派生 registry/sketch 一致；所需 sync/check、贡献测试、七项 gate 和受影响 frontend 检查实际通过。blocked/not_run/skip 不计通过；复用记录不冒充本轮执行。
5. 当前 README/架构说明与实际入口一致，历史 `IN_PROGRESS` 不覆盖 §8 的完成事实，也不覆盖 §10 的新实施状态；根对象只按精确依赖决定处置，业务数据、OAuth、WebUI 会话和必要恢复输入保留。
6. 每包回传结果、改动文件、原命令与退出码、删除重复/出口、保留项及剩余 `blocked_by`；剩余问题按对象和 owner 记录，不能用全局完成掩盖已知缺口。远端发布、可选 Qdrant、香港历史材料、旧全后端 exit 1 继续保留原边界。

方案编制实际委派两个 `glm-5.3-flash-zhipu-glm-en / low` 只读证据包，分别核对工具/源码出口与 Graph/开发入口。编制结束时实施派发数为 0；用户随后已授权本轮整组实施，实际派发见 §10.11。这不是上一轮实施包的重新派发。调用/token/精确耗时未完整提供，保留缺失；实施的完成/派发数、共同验收耗时、失败、主线补修与机械接线情况从原日志汇总，不要求作者填新表，不宣称未经比较的提速。

本轮文档验证（补齐分发边界后）：方案作者定位了 100 个现有路径/文件模式，2 个拟新增工具模块已明确为未来输出。主线复核本方案及开发入口的 45 个本地链接（含标题 anchor）、51 个测试 selector、2 段 bash 的 `bash -n` 语法、Markdown fence/details 配对和新增/替换行尾空白，均通过；bash 只做解析，未执行 PG guard 或测试。与修改前快照比较，§8 的表格与后续证据正文不变，§9 的原合同正文完整保留，仅增加历史归属说明和折叠入口。`git diff --check -- docs/development/README.md` exit 0；未跟踪的本方案另以快照逐行检查，不把 Git 未检查到的文件算作通过。独立局部复核确认 C1/C9 混合权威归属及专属 PG 验证合同的两处缺口均已解除。文档编制与复核已完成；产品代码、服务、清理、PG 实例和全量测试均未在方案编制中执行，方案编制时实施包为 `NOT_STARTED`；用户授权后的当前实施状态见下节。


### 10.11 本轮实施与集成结果

2026-10-05，15/15 工作包完成，状态为 `IMPLEMENTATION_COMPLETE / LOCAL_MAINTENANCE_VERIFIED`。14 个包委派，1 个包由主线负责共享集成；以接任务时的可写工作树为基准，保留已采纳的 v2 身份与其他任务改动。

| 包 | 结果 | 实现与实际验证 |
| --- | --- | --- |
| 开发入口 | 完成 | 固定 Git kit、显式本地 kit、来源错配拒绝；17 tests、Ruff、真实 default/local/default 安装切换通过；宿主旧 wheel 已替换为声明的固定 Git 版本，默认 check/test 可直接执行 |
| Graph 职责整理 | 完成 | 几何、样式、模板纯转换、模板控制、图例分别唯一承载；lint/build、Force3D/i18n 检查 exit 0，Playwright 15 passed |
| 工具贡献规则与试点 | 完成 | 原生声明派生同一 FacilityBinding 和 Core registry；整组先验证后注册；真实 Codex 消费者及5项规则测试通过 |
| 工具查询 | 完成 | 9个原始工具进入统一规则；spec/handler保持，原查询/检索26项通过 |
| 工具写作与任务 | 完成 | 16个静态工具及原 workflow/report 动态能力进入同一规则；25项静态原交错顺序和动态 capability 原位置保持；141个重复函数、3个重复常量退出 project_tools，当前1128行；相关工具/宏/边界80项通过 |
| 工作流源码出口 | 完成 | 业务作者、DSL、验收和装配唯一承载；原43项通过，plan/catalog/assembly/kernel保持见证通过 |
| 投影源码出口 | 完成 | 6个业务权威模块；默认业务v2面板、旧v1原字节和摘要读取、未知版本拒绝；38项纯测试通过，专属PG 23项通过且无skip |
| 来源源码出口 | 完成 | 业务作者和唯一共享类型；原v2 contract digest及历史schema保持 |
| 采集源码出口 | 完成 | 业务作者及原有canary、specification消费者直连；恢复两个真实legacy/programmer-defect边界注释，原异常ABI与失败值见证通过 |
| 批任务源码出口 | 完成 | 业务提交、计划、重试、装配与submission store；公开SourceCandidateView和导出一致；原selects通过 |
| 任务观察源码出口 | 完成 | 业务native作者和装配；session与task历史status权威各自保留，修复机械改名导致的覆盖；原selects通过 |
| 材料源码出口 | 完成 | 业务作者、movements、program、interpreters、registry和装配；原codec、canonical写边界、身份保持；原selects通过 |
| 知识源码出口 | 完成 | 知识读、写、报告、图投影贡献的业务作者；修复装配自引用；export/token effect原owner保持；原selects通过 |
| 当前文档与根对象 | 完成 | 根/后端README、宏架构和开发阅读入口反映当前Codex实现与开发命令；历史资料按下表处置 |
| 共享集成 | 完成 | 9个贡献作者和4个core semantics使用业务名，唯一catalog派生注册；活动能力/装配不经过编号转发；sync/check、贡献测试161项、架构门禁280项、最终投影/联合装配65项、面板及证据矩阵共享装配22项全部通过 |

六个源码包的原21 selectors曾执行216 passed/1 dependency lint failed；删除无消费者shim后，原失败与受影响batch selector真实复验7 passed。最终该组唯一测试覆盖217项，其中最后7项为重新执行，210项按未变化依赖保留为 `kept`。不把复用项冒充最后一次命令的执行计数。其余测试组存在覆盖交叠，不把各组数量相加为总分母。

源码整理退出67个临时编号转发模块；另2个采集canary/specification作者直接改为业务名。4个旧core与9个旧kit贡献作者位置退出。当前作用域未保留编号转发别名；旧schema、codec、owner ID、law ID、历史wire字段、冻结源码绑定和恢复证据继续保留其原事实。原底层生产effect、历史诊断generator及版本decoder仍由原实现拥有，未因本轮源码维护转移事实权限，也不声称整个仓库所有历史编号字面量均消失。

当前投影事件词表原先误登记旧SESSION事件，而当前纯task source声明的是TASK事件。本轮修正当前v2注册投影并通过唯一catalog同步，原历史decoder和冻结注册字节未改。检索面板仅完成原声明消费者，不声明新增API/WebUI运行绑定。

工具规则显式保持三类原权限边界：默认macro只接受可信request scope；project工具保留原project selector和serial session write；原URL提交以静态声明明确引用既有governed frontdoor，serial且引用与原metadata相等才保留原allow合同。权限/role输入、缺失或错配frontdoor和parallel外部dispatch均拒绝。原工具spec未为通过编译改成其他权限或伪造session-write身份。

**统一验证入口与结果：** 根目录 `python3 scripts/dev.py setup`、`sync`、`check`、`test`均exit 0；固定kit为 `6dbae536a72ab235998b21c9647b8b00d15a71e6`。`gates`在项目Docker测试环境exit 0，280 passed；贡献test在同一固定Git来源宿主环境161 passed，受影响投影与联合装配随后在Docker中65 passed。专属PG两文件串行23 passed，无skip。Graph合同要求的5个命令全部exit 0；原用户交互mock API见证15 passed。Ruff F821/F822覆盖当前源码、迁移、相关tests/scripts与kit，exit 0；整仓 `git diff --check` exit 0。文档4项gate按原入口完成，最终正文修订只影响文档，另读回链接与状态。

历史检查与当前维护分开：冻结来源packet通过现有historical_fixture恢复精确revision `9fa8aefaae8f30a080f3d2dcac6dfb6ff9f773e0`，覆盖其17个source bindings的原字节后执行原历史canary断言；C9 sidecar按现有historical_bytes及原摘要读取；W06仅对冻结packet的源码定位作显式当前观察投影。相关原测试完成，未改旧packet/digest让当前v2冒充旧候选。共享CLI generator原ABI selector、source/材料/知识/投影注册声明的原测试已通过。

| 根对象 | 归属与当前依赖 | 实际处置 |
| --- | --- | --- |
| `.DS_Store` | macOS索引，18436 bytes，无业务依赖 | 删除 |
| 字面目录 `mkdir -p `（末尾空格） | 误执行命令形成的4个pytest cache文件，共532 bytes | 精确删除 |
| `0`、`nodes.md` | 未确认旧试验资料/用户资料，owner `UNKNOWN` | 原位保留，未知用途不推断为垃圾 |
| 六个根 `RELEASE_NOTES_*.md` | 历史发布叙述 | 原位保留，退出当前运行说明 |
| 根截图 | 旧视觉检查产物/用户资料，5个盘点对象 | 原位保留 |
| `stage1-successor-evidence`、`stage3-evidence`、`stage5-evidence`、`stage6-evidence` | 冻结、源码绑定与恢复实际依赖 | 原位保留；本轮不修改历史字节 |
| `arch-baseline.json` | 现行架构检查实际输入 | 保留 |
| 本轮专属PG测试容器和测试镜像 | 本轮测试独占，无业务数据卷；固定来源与Dockerfile可重建 | 已删除本轮专属容器 `mrw-maintenance-pg-20261005` 和唯一镜像标签 `mrw-maintenance-tests:local`；未进行全局prune |

GLM服务限流导致部分作者中断，保留产物后执行2个专题恢复、1个六族合并恢复及1个旧出口审查/机械收尾子任务；没有重复派发整棵任务树。初始14个委派包均交付，主线承担公共import endpoint/缩进修复、catalog/authority同步、作用域符号冲突、纯边界见证恢复、历史/当前测试分流和共同验证。共同验证曾出现1个gate真实失败、3个贡献测试失败及5个PG消费者失败，均在权威来源或真实消费者修复；sandbox连接、Docker停止和provider限流作为环境失败单独记录，skip不计通过。调用/token和精确起止耗时未完整提供，记为缺失，不计零，不宣称提速。

本轮15包无剩余开发blocker。Graph E2E为mock API，保留原force3d/fallback framing观察边界；远端发布、可选Qdrant及旧香港材料/全后端测试的原范围不变。本轮没有以本地维护测试冒充生产部署、线上provider业务完成或新一轮全链发布验收；此前本机日常链证据继续保留原归属。

收尾清理读回：Docker Images统计从6个/5.429GB降为5个/3.958GB，专属PG容器已移除；剩余其他任务容器、9个volume和共享builder cache均保留。宿主可用空间前后均约58GiB，不把镜像逻辑大小差当作Docker.raw实际收缩。本轮误命令cache目录与`.DS_Store`共18968 bytes精确删除，未知根资料原位保留。
