# MRW 全量原生函子开发框架迁移：评估与实施方案

日期：2026-09-22。状态：评估完成后的实施建议；本轮仅创建分支、检查现状、运行 C8 定向验证和编写方案。

## 1. 目标与范围

目标是让 MRW 的领域类型、能力、接口、组合和必要见证成为单一原生声明，由项目规则派生既有 Runtime 装配、注册、投影和验证接入。能力作者负责语义与特殊实现，框架承担已经确定的机械工作。现有业务执行、持久化与权限 owner 继续承担其职责。

本方案将“新框架”解释为当前本地 `functorial-kit` 的 native contribution compiler、typed binding、显式 catalog 与 verification 派生能力，接入 MRW 已有 Python Runtime 及 TypeScript 前端。它不等于迁往研究产品 Successor Research Workbench。

“全量”包括后端 C1–C9、跨领域 ports、ops surfaces、实际 API/worker/services、前端领域接口与模块接入、开发验证和构建依赖。普通纯函数、组件渲染、SQL 实现等，在没有真实结构压力时保留原生实现。第三方 reference-pool、历史快照、冻结证据不作为代码迁移对象。全量覆盖按实际消费者和语义 owner 核对，不能以 C8 或 30-cell 矩阵代替全产品覆盖。

迁移默认属于观察边界下的兼容重表达：保持身份、顺序、失败、权限、持久化与外部协议；如发现必须改变这些语义，明确局部扩展/精化/有损边界及版本，不静默解释旧数据。

## 2. 已核对的当前状态

- 当前工作树：`/Users/wangyiliang/market-research-workflow`。
- 从 `codex/all-lines-donor-cutover` 当前 HEAD `5a742be1ebbacb50390a20c35d7bd8526abcdffd` 创建并切换到 `codex/mrw-native-functorial-migration`，未新建 worktree。
- 分支创建前 tracked 工作树无改动；已有大量 untracked 快照与制品，全部保留，不纳入本次提交范围。
- 本地 kit：`/Users/wangyiliang/Desktop/functorial-kit`，HEAD `5f7623f073a20f1d398edd8aeb2d0b8c694a5410`；检查时有 7 个 tracked 修改。因此 HEAD 本身不能完整标识本次开发依赖。
- MRW `pyproject.toml` 与 backend requirements 的正式 Git 依赖仍为 `785ff25e201c9eae84c862e68e786bc975e7a800`；本地 uv 指向 sibling editable kit，local-user Compose 也挂载该 kit。开发、测试、镜像输入存在需要收敛的版本边界。
- `scripts/dev.py` 固定 `contributions/c8_catalog.py`，`test` 是 9 个 C8/I1 定向测试文件；`tests/test_architecture.py` 同样绑定 C8 catalog。
- C8.1–C8.3 复用 `C8_NATIVE_CONTRIBUTION_RULE`，C8.4 使用 `C8_GRAPH_PROJECTION_NATIVE_RULE`。当前规则已派生原生定义、profile、contract、codec 与 binding，需继续沿实际生产消费者核验，不重造试点。
- C8 仍有收口工作：`specification/c8_p4.py` 保留 operation binding/body、观察与 rollback 摘要；各族 `CapabilityCellSpec`、`c2_p3.py`–`c9_p4.py` 和 assembly 之间存在重复描述面。派生当前可变 spec/投影时，历史 exact bindings 与实际观察证据保持原样，不能由声明生成执行结果。
- 新 kit 已有 `verification(definition, native)`、`plan_contribution_verification`、`register_verification_plan`。MRW 上述两条规则尚未提供 verification slot，现有定向测试清单仍手工维护。
- `successor_assembly.py::ALL_I1_CELLS` 有 30 cells；横向装配有 4 个 S1 ports、11 个 S2c surfaces。这些横向结构目前明示无 Runtime binding/无执行授权，迁移不得将其登记状态提升为业务完成。
- 前端已有 `moduleManifest` → `moduleRegistry` 派生，可复用；render 分派与 API domain 类型仍分别维护。`main/frontend-modern/package.json` 尚无 functorial-kit 依赖，根 kit 配置没有覆盖前端。
- 生产阶段进度入口记录本地 Stage 4–6 已验收、清理完成、停止、发布后置；本次开发迁移不重开历史发布流程，也不复用旧 PASS 证明新字节。

静态规模（`git ls-files`，只数 `.py/.ts/.tsx/.sh/.mjs`）：backend app 778 文件，其中 successor runtime 245、services 378；backend tests 591；frontend src 172；项目 src 24；scripts 133。这些是检查范围，存在包含关系，不能相加或当成待修改文件数。注册表有 ports 13、codecs 8、failures 77、vocabularies 20、sketches 21 条；条目数也不等于完成率。

## 3. 难度判断

总体为高难度、可分批推进的工程迁移（主观等级 4/5）。已有 Runtime 和 C8 路径降低了从零建设成本；主要工作是明确不同语义形状及其共同规则，并保持实际消费者兼容。

| 工作面 | 难度 | 主要原因 |
| --- | --- | --- |
| 已支持的 C8 形状与投影接入 | 中 | 复用现有规则；补规则派生验证、默认与非默认定义一致性 |
| C2–C6 能力、程序与 handler 装配 | 中高 | profile、operation、codec、ordered program、handler 的事实来源需逐族核对 |
| C1/C7/C9 与 PostgreSQL/恢复/权限 | 高 | 控制流、持久化与 facade 不能硬套普通 program atom；失败和写入边界必须保持 |
| 横向 ports、ops 与 services/API/worker | 中高 | 注册不等于接入；必须跟到生产 composition 和持久结果 |
| 前端模块与跨语言 API | 中高 | 一部分已派生，一部分仍为独立声明；需保留 wire envelope、版本、交互及异步状态 |
| 依赖、测试派生、Docker/CI | 高 | 本地 kit 与固定依赖不同；验证选择的覆盖性不能由词法扫描推断 |

最容易低估的成本是：把 C8 当成所有能力的通用模板；只改 catalog 而遗留生产手工装配；让新旧两套声明长期同时拥有事实；开发可导入但 clean build 缺少新 API；测试读取同一派生值造成自证。

粗粒度工作量预算为 **20–40 工程人日**，包含规则建设、规则使用、前后端接入与整体验证，非模型运行时长或交付承诺。当前没有可比的全量迁移耗时样本；该区间置信度低。完成第一种非 C8 形状和一次生产消费者贯通后，按实际修改量、返工与验证耗时重新估算。不能据此直接宣称多 Agent 可线性加速。

## 4. 必须保持的语义

| 对象/变换 | 权威与迁移约束 | 验证观察点 |
| --- | --- | --- |
| 领域对象、operation、codec | 原生定义唯一；wire/storage 是有方向的投影 | 默认与非默认定义通过原消费者，codec roundtrip 与既有版本数据 |
| Program 与执行步骤 | 原 Program 定义顺序；catalog 顺序只承担明确声明的组合依赖 | 原始顺序 oracle、失败短路、不得重排有副作用步骤 |
| canonical values、receipt、offset | 原 PostgreSQL writer 与事务边界 | 真实读回、冲突拒绝、幂等、恢复后的不变量 |
| capability、scope、admission、facade | 原权限 owner；compile/assemble 不授予执行权 | 缺权限、错误 scope、错误 binding 拒绝，拒绝时无越界 effect |
| API task 与 worker 执行 | 既有队列和业务 operator | API→真实 worker→Process/document/result 持久读回 |
| 前端模块与任务状态 | UI 只表达实际 API 状态 | 路由兼容、提交/等待/失败/成功链与刷新读回 |

这些是本次迁移的验证义务，不因写进表格就成为已证明等式。已存在的断言与 oracle 复用；新增规则只补受影响的真实语义见证。

## 5. 分批实施

| 批次 | 目标、主要输出和边界 | 完成条件 |
| --- | --- | --- |
| A：开发基线与共同入口 | 在现有 dev.py/catalog 路径扩展全项目组合入口；明确当前 kit 实际输入及构建依赖；先在 C8 接入规则派生 verification，复用现有 pytest | 单一有效 catalog 供装配/投影/验证消费；纯 check 不装配、不执行 effect；定向检查保持可单独运行 |
| B：首个非 C8 真实形状 | 优先选择 C3.1–C3.2 的 ordered traversal/fold，核对与 C8 的共同项及差异；只补该形状需要的项目规则 | 一个真实默认用例和第二个非默认定义贯通原 assembly；改一处声明更新所有确定投影，旧行为 oracle 通过 |
| C：能力族扩展 | C1/C4 按 command/program 与 dependent state transition，C2/C6 按 capability/effect interpreter 分包；独立的 S1 port 与只读 surface 规则可同时推进 | 每族通过实际 bundle/handler 消费；共享装配与 catalog 由集成 owner 合并；重复机械映射消除；C1 recovery 留到 D 联合验证 |
| D：持久化和控制边界 | 迁移 C5/C7/C9 与 PostgreSQL/facade/runtime 接线；保留原 recovery、transaction 与 authority owner；不能表达的形状建立独立项目规则 | I1 30-cell 组合与真实持久化验证闭合；对错误权限、失败、重放和写入边界有受影响验证 |
| E：产品全链与前端 | 追查 services/API/Celery/ops 的实际入口，将适用的手工绑定导入同一规则路径；前端复用 moduleManifest，统一适用的 render/API 派生 | 30-cell 之外的产品入口同样覆盖；页面、提交、worker 和读回真实贯通；纯接口记录保持原声明边界 |
| F：整批收敛 | 清除失去消费者的可替代手工接线；同步有效生成物；将所需新 kit 版本纳入实际构建输入；执行全量适用 gate | 当前输入上的本地构建/静态/业务验收通过；未通过与 declared loss 如实列出；仅真实交付需要时批次封存 |

A 中依赖基线和验证接入先集中收敛；B 只约束依赖它的同形包。前端独立模块规则、横向纯 port、已有支持形状可与其他后端规则工作并行。D 的集成验证依赖上游接口一致，E 的真实全链依赖对应后端可用，F 统一收敛。

具体高风险点：C2 provider effect 与 terminal derived projection 分权；C4 submit 保留 quality-promotion 边界；C5 durable reconcile/readback 不被 metadata 替代；C6 保留 model/tool failure；C7 canonical commit 与 projector driver 分工；C9 分别处理 facade、前端观察和 offset anchor/CAS，不能套用单一 Program atom。C8.3 export/token-state 安装和 C8.4 per-run source key 继续由 assembly context 提供，规则可以派生接线，但不能凭静态定义制造运行权限。

主线负责语义设计、跨包接口和最终审查；一个集成 owner 维护共享 assembly/catalog/dev.py/注册投影。规则 owner 先打通一个真实案例；能力作者不各自再造解析和装配器。具体派发时给出 cwd、已确认解释器、权威符号、独占写面、直接可运行的定向命令与完成条件。未定规则不阻塞独立工作。

## 6. 验证与交付口径

本次实际执行（仓库根，现有脚本自行选择 `main/backend/.venv311`，未安装依赖）：

```sh
python3 scripts/dev.py check
# exit 0，clean=true，issues=[]，changed_paths=[]
python3 scripts/dev.py test
# exit 0，70 passed in 1.08s
```

这是当前 C8/I1 定向证据，不代表全仓、真实业务链、全套架构 gate 或正式构建通过。本次未执行 sync、全量测试、Docker 重建或外部发布。

实施时：

1. 每包运行既有最小行为/失败/权限测试及适用类型检查。验证元数据由规则派生，pytest/既有 runner 执行；Python async 测试继续走原 async runner。
2. 共同声明稳定后集中 sync/check；规则派生的验证计划遇到未知变更或覆盖不完整时扩大至有效 catalog，但仍不能代替 catalog 外的全项目测试。
3. 集成边界运行 `python3 scripts/dev.py gates` 的七项架构规则及扩展后的 catalog 检查。当前根 pyright 只覆盖 src/tests，实施时须覆盖新规则、生产消费者与相关 fixture；不能将旧范围 typecheck 称为后端全覆盖。
4. 后端完整集成复用 `bash scripts/test-standardize.sh ci-pr -q` 等现有适用入口；实际业务/DB/worker 验证优先复用项目专属 Docker 环境。执行前核对各入口真实 selector，不用单个命令替代全部交付要求。
5. 前端复用 `npm run build`、`npm run lint`、既有页面合同及 `test:e2e:real-backend-business-lines`，按真实依赖设置运行环境。跨语言投影从已有 wire 合同 owner 派生，不新增第二份业务 schema。
6. 以实际用户入口覆盖导入/检索/图谱/写作等适用业务链，观察真实 worker/operator 与持久结果。环境或凭据受限的链单列未验证，不能以 health/noop 或历史结果填充。

交付只维护本方案所在的现有开发记录与必要实际结果，不新增审批平台、测试 scheduler 或缓存系统。直接修复→最小相关验证→稳定批次按需封存，执行规则沿用生产计划 19 号文档。旧 release/freeze 证据不重写；推送、发布和生产切换不属于本轮评估。

## 7. 实施前仍待实证收敛的项目

- 各非 C8 族能否复用同一规则：本轮是静态评估，B 批次通过真实消费者确定。
- services/API/worker 与 30-cell 拓扑之外的完整覆盖：实施中沿正式入口补齐到消费者映射，不能仅靠文件数量给百分比。
- 新 kit 包含未提交改动时的可重现构建身份：保留他人改动；集成交付前明确被消费的实际版本，历史锁定证据保持原义。
- 前端 wire schema 的精确覆盖、全仓基线及新 kit 全套机制验证：本轮未执行，按对应变更与集成边界验证。
