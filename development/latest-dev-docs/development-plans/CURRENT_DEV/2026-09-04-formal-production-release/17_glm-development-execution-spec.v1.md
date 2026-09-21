# GLM 开发接续规格与执行路径

- Date: 2026-09-07
- Owner task: `01a079a6-d879-7312-9682-0ea6dc3ad4fb`
- Model: `glm-5.3-zhipu-glm-en`（当前接口不接受 reasoning effort 覆盖）
- Supervisor: `01a0748b-be3b-7da2-9cb2-4160756bf10b`
- Status: `ACTIVE_IMPLEMENTATION_SPEC_NOT_AUTHORITY`

用户要求直接切换当前开发任务为 GLM，并提供详细执行规格。本规格细化合同16，不取代完整门禁、不改冻结候选、不重新从零开发。主任务在安全工具边界换模型；已运行的有效工作包不重启，原子写入完成后协调，不并发抢写。

## 1. 先恢复当前状态

完整读项目 AGENTS、合同16、`stage1-successor-evidence/stage-convergence-batch-v1/execution-progress.md`、交接文件及现有worker消息。最新进度是可变线索，执行前核对实际源码、receipt输入hash和资源lease，不照抄旧状态。唯一集成owner仍为本任务；共享锁文件、registry、intake、aggregates和服务lease不交给多个writer。

2026-09-07监督读取到的线索：attempt6 backend unit=1805 passed/3 failed/1 skipped；ROOT=63 unique failing nodeids，已有13个遗漏路径和只读缓存分类；缓存路径/禁用配置已实现且3 focused通过；八个synthetic native cells均在成功create_table后default FTS创建崩溃；架构源码诊断342 passed；源码安全未裁决收敛到343–346。上述均非最终候选结论，已成功诊断不重复执行。

## 2. 执行顺序和停止边界

先并行关闭可独立的候选输入、缓存/runner和frontend问题；已有build、安全worker续作，集成owner串行更新共享输入。随后刷新一次完整临时preview及非权威绑定，运行受影响focused检查，再按完整gate inventory执行。native FTS阻塞单独保留，不能让它阻断无依赖门禁。

不得因为只修一个字段创建正式v7或全量rebind。源码批次稳定后统一做source→family→aggregate→manifest，正式candidate最终全门禁仍必需。只有阶段结果或真正需要语义/权限选择才回传监督。

## 3. 工作包A：闭包、绑定与ROOT

输入：当前63-nodeid分类、13路径清单、103 ROOT test独立枚举、intake/source_closure实现、I1 v3 direct-successor失败。

操作：
1. 对每个遗漏路径标记product/test/required tool/历史事实/runtime输出；只有门禁实际必需且允许入候选的字节进入projection。不能复制整个临时目录或恢复用户删除历史。
2. 修复选择策略而非为本次缺件手工堆allowlist；验证完整预期ROOT集合与projection集合差异为空，base-only遗漏/DELETE/动态数据与脚本输入同样核对。
3. I1修复使用已有exact cell/role/candidate匹配及8 focused正反例，保持直接引用与身份检查，不能扩大别名或接受任意新stage。
4. 分类剩余ROOT失败为独立根因；只读缓存是环境差异，真实架构违规按源代码修复，不以空baseline或放宽scanner消除。

输出：修复代码与回归、预期输入清单与actual diff、唯一nodeid→root cause→owner→receipt映射。验收：focused正反例通过，预演candidate完整ROOT与绑定检查给出真实结论；源码diagnostic不能代替candidate结果。

## 4. 工作包B：缓存与安全runner

当前源码已存在 `settings.llm_cache_enabled` / `llm_cache_path`，`app/services/llm/cache.py` 的setup_cache会在import时执行。先复用已有实现，不重复添加第二套环境变量或改默认语义。

操作：
1. 查当前settings实际环境变量映射，在各run receipt记录解析后的enabled/path（不得记录其他secret）。在不需要缓存的离线gate显式禁用；需要SQLite缓存的gate指向其唯一任务专属writable目录。
2. 将配置注入发生在导入web/LLM之前；源码mount仍只读，不以整个/code改可写掩盖错误。验证新源码和runner配置确实进入新preview，不能只改host源码。
3. focused覆盖：指定路径启用会写指定位置；禁用与prod不创建缓存；ro源码+外置cache可执行。已有3测试通过时只补缺失负例，不复制测试。
4. provider trace及wave12 skip-live必须在受控环境无Errno30；后者live observations仍not_run。确需消除全部import-time effect时作为单独有界兼容性修复，必须保留原运行初始化路径与回归，不悄悄删除setup而令缓存永久失效。

服务测试使用已交接的专用资源/网络和明确DB目标；禁止默认localhost探测、未知库重连、生命周期复现或回滚。Python guard不证明native/subprocess隔离；无有效隔离则不运行该类测试。

## 5. 工作包C：LanceDB native FTS

八格实验已给出“写表成功，default FTS创建SIGSEGV”线索。先读并验证现有cell receipts、exact image ID、package versions、native/target architecture、挂载和exit/signal/OOM字段；若可复用，不再跑原四格。

下一步按分支执行：
1. 若仍不能定位子调用，只运行一个有flush前后标记的最小create_table→FTS子进程，唯一临时dataset；不能跑整六步碰运气。
2. 若已定位FTS，先确认真实目标平台与emulation，并检查当前安装版FTS API及支持选项。任何选项须来自实际源码/官方文档，不猜参数。保持image/source/vector/dataset不变，每次只改一个诊断变量。
3. 可用现成已授权native runner时进行对照；不可用则标记平台证据缺口，不能自行开云机或remote作业。host/macOS通过不代替目标Linux。
4. 只有证据指向兼容问题时提出最小依赖/FTS配置修复，锁定版本/平台并验证相同语义。若需更换检索引擎、改变排名、删除FTS、减少功能或引入未授权基础设施，交监督判断，不自行实现替代品。
5. 禁止keyword fallback掩盖vector/hybrid失败、禁止省略FTS来宣称完整通过、禁止把exit139改成skip/xfail。保留所有失败receipt，不把synthetic native cell当application资格。

验收：真实runtime、benchmark均exit0；schema维度匹配，keyword/vector/hybrid executed_mode与请求一致、无未声明fallback，原ranking/filter断言全部保留。通过后仅顺序执行trace→Wave10→Wave12 skip-live→Wave14，显式绑定输入hash；live/closure资格不得因本地通过提升。

## 6. 工作包D：其余完整实现面

前端owner继续完整lint/type/build/Storybook/e2e；10个静态skip逐项恢复行为或保留真实需要用户裁决的身份，不能以替换路由证明退役。Node/lockfile固定，已有结果只在输入未漂移且范围一致时作为诊断复用。

build owner先检查磁盘预算和任务缓存owner，再跑构建。TLS失败保留证书验证，检查依赖源/代理/CA配置，只用可信来源，不加insecure/跳过签名、不重复完整构建消耗空间。三个角色制品、独立重建、SBOM/provenance/scan各自给真实结果，不因缓存或install成功升级资格。清理只限已核验task-owned可回收资源，不删除candidate、日志、DB或来源不明目录。

安全owner逐项裁决剩余发现343–346与依赖审计，脱敏输出；风险接受、凭据轮换、历史重写与未知DB恢复不是机械实现权限。不能将发现数当活凭据数。

## 7. 统一回执与阶段完成标准

沿用已有schema/runner，不重建调度框架。每项receipt至少保存attempt ID、owner、命令argv、cwd、source/preview commit/tree、工具/镜像/平台、环境差异、输入hash、start/end、exit/signal/OOM、结果计数、原始log/JUnit路径hash、资源及清理状态。JSON解析/唯一ID/计数/文件hash由程序核对，不人工维护巨大hash表。

中断必须记INTERRUPTED/UNKNOWN，无完整结论。最终完整gate inventory每项都有真实PASS/FAIL/BLOCKED/UNEXECUTED及blocked_by；既有预演或source PASS不能替代最终候选完整门禁。只有最终阶段结果请求监督验收。

90次tenant配置upsert事件目标UNKNOWN仍保留，禁止重连/读回/回滚；没有新授权不得发布、push、remote规则修改、registry/signing写入、deploy、live provider、生产写入、canary/cutover或authority transfer。Stage4未准入。
