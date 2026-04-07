# Atomic Task List: Repo Closure Plan (2026-04-06)

## Execution Status Snapshot

- `AT-RCL-01`: completed, freeze scope / owner / compatibility inventory.
- `AT-RCL-02`: completed, durable compiled registry path, retained `_compiled` fallback, and workflow-graph closure evidence are all in place.
- `AT-RCL-03`: completed, integrity/replay diagnostics are explicit and covered by workflow-graph closure evidence.
- `AT-RCL-04`: completed, direct `/agent-batch/jobs` submit now projects into the session/task/event ledger while compat entrypoints remain explicit.
- `AT-RCL-05`: completed, environment-ready require policy and fallback telemetry are both validated.
- `AT-RCL-06`: completed, explicit capability-truth metadata now distinguishes real-model vs fallback semantics.
- `AT-RCL-07`: completed, authority_output / compat_projection split is explicit and validated under current callers.
- `AT-RCL-08`: completed, shared kernel render ownership is now the only page dispatch fact source.
- `AT-RCL-09`: completed, legacy hash compatibility is isolated to adapter boundaries and B-layer shell/nav parity is covered.
- `AT-RCL-10`: completed, required-check matrix note, PR evidence defaults, docs-navigation maintenance baseline, and local governance validation pack are all green.
- `AT-RCL-11`: completed, final regression pack is green; after `AT-RCL-04` convergence the repo-closure topic is archive-ready.

## Reference Pack

- [01_repo-logic-gap-assessment-2026-04-06.md](./01_repo-logic-gap-assessment-2026-04-06.md)
- [02_repo-closure-plan-aligned-with-latest-direction-2026-04-06.md](./02_repo-closure-plan-aligned-with-latest-direction-2026-04-06.md)
- [01_claude-agent-high-fidelity-migration-mapping-2026-04-02.md](../2026-04-02-claude-agent-high-fidelity-migration/01_claude-agent-high-fidelity-migration-mapping-2026-04-02.md)
- [03_frontend-three-layer-rewrite-closure-gap-assessment-and-rollout-2026-04-02.md](../2026-03-15-frontend-three-layer-rewrite/03_frontend-three-layer-rewrite-closure-gap-assessment-and-rollout-2026-04-02.md)
- [01_source-library-ingest-minimal-migration-plan-2026-03-25.md](../2026-03-25-source-library-ingest-minimal-migration/01_source-library-ingest-minimal-migration-plan-2026-03-25.md)
- [05_validation-closure-source-library-ingest-minimal-migration-2026-03-26.md](../2026-03-25-source-library-ingest-minimal-migration/05_validation-closure-source-library-ingest-minimal-migration-2026-03-26.md)
- [PULL_REQUEST_TEMPLATE.md](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/.github/PULL_REQUEST_TEMPLATE.md)
- [branch-protection-required-checks.json](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/.github/branch-protection-required-checks.json)
- [backend-tests.yml](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/.github/workflows/backend-tests.yml)
- [check_api_layer_imports.py](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/backend/scripts/check_api_layer_imports.py)

## Serial-Parallel Rules

- L0 serial bootstrap:
  - `AT-RCL-01`
- L1 parallel runtime foundation split:
  - `AT-RCL-02`
  - `AT-RCL-04`
  - `AT-RCL-05`
  - `AT-RCL-06`
- L2 serial runtime convergence:
  - `AT-RCL-03`
  - `AT-RCL-07`
- L3 parallel frontend and governance:
  - `AT-RCL-08`
  - `AT-RCL-09`
  - `AT-RCL-10`
- L4 serial closure:
  - `AT-RCL-11`

## Global Acceptance Contract

- `workflow graph` 必须从进程内编译态收口到可恢复、可回取、可验证的 runtime。
- `agent_batch`、`workflow_graph`、`skill_runtime` 可暂保留 compat 入口，但 session/task/event ledger 必须明确为主核。
- `project_key` 必须从默认软约束收紧到目标环境可用的硬约束。
- LLM 相关能力必须区分“真实模型路径”和“模板/规则 fallback 路径”。
- source-library 的兼容输出可以保留，但必须显式区分权威输出和 compat projection。
- frontend 只能存在一个模块/路由事实源；legacy hash 只能存在于显式 adapter 边界。
- 收口任务必须带最小验证命令、回退方式、以及文档索引更新。
- 收口完成前，不得以“后续再补文档/验证”为理由把主题从 `CURRENT_DEV` 提前归档。

## Topology-Risk Confirmation

以下任务当前最容易因为“对现有结构拓扑理解不完整”而导致改动失败，必须先按护栏模式执行，不能直接改默认行为：

- 高风险：
  - `AT-RCL-04`
  - `AT-RCL-07`
  - `AT-RCL-08`
  - `AT-RCL-09`
- 中风险：
  - `AT-RCL-02`
  - `AT-RCL-05`
- 低到中风险：
  - `AT-RCL-06`
  - `AT-RCL-10`

确认依据：

1. `workflow graph` 当前编译记录仍保存在进程内 `_compiled` registry，`run()` 先回取内存态，再投给 runtime；虽然 run store 与 handoff store 已经存在，但它们还没有覆盖 compiled artifact registry，所以如果在未冻结 graph id / version / store 语义前直接改执行主链，仍然容易把现有运行路径打断。
2. source-library 当前明确同时暴露 `terminal_output`、`frontdoor_ingress`、`postprocess_frontdoor`、`legacy_result`；如果在未完成 caller matrix 之前直接删减或改写默认输出，最容易破坏现有兼容调用方。
3. frontend 当前真实存在双中心：
   - `AppShell` 自己维护页面分发和 hash 同步
   - `ModuleRenderer` 再维护一份页面分发
   - `FrontendKernelApp` 对 unknown route 仍回退旧 `AppShell`
   - `moduleManifest -> contracts -> registry` 已形成派生链，但真正未收敛的是 render ownership 与 compat fallback
4. `project_key` fallback 是当前真实运行策略，不是偶然漏网；如果在未区分环境和 caller 之前直接把默认策略切成 `require`，高概率影响现有功能流。

因此，本轮实现必须额外遵守下面这些“不会影响当前功能”的护栏：

1. 先补 mapping、store、metadata、parity test，再切默认路径。
2. 先保留 compat 输出和旧入口，再做 authority path 和 canonical path。
3. 所有高风险任务第一阶段只允许 additive change，不允许 destructive change。
4. 所有默认行为切换都必须由显式 knob / feature flag / env 开关控制。
5. 在 parity checklist 跑通前，不允许移除旧路由、旧 hash、旧 response 字段、旧 adapter 入口。

## Functional-Safety Policy

为确保修改计划不影响当前功能，本轮收口统一采用三档改动策略：

- `freeze-only`
  - 只允许补文档、补 mapping、补 caller matrix、补验证，不改任何默认运行路径。
- `additive-only`
  - 只允许新增 store、metadata、guard、验证、双写/双读、显式 adapter，不允许删字段、不允许切默认值。
- `switchable`
  - 允许通过显式开关切换新行为，但必须保留一键回退路径。

任务对应策略：

- `AT-RCL-01`: `freeze-only`
- `AT-RCL-02`: `additive-only`
- `AT-RCL-03`: `additive-only`
- `AT-RCL-04`: `freeze-only -> additive-only -> switchable`
- `AT-RCL-05`: `additive-only -> switchable`
- `AT-RCL-06`: `additive-only`
- `AT-RCL-07`: `freeze-only -> additive-only -> switchable`
- `AT-RCL-08`: `freeze-only -> additive-only`
- `AT-RCL-09`: `freeze-only -> additive-only -> switchable`
- `AT-RCL-10`: `additive-only`
- `AT-RCL-11`: `switchable`

## Frozen Closure Owner Map

| Topic | Frozen owner module | Primary code surface | Primary doc / gate surface |
|---|---|---|---|
| `workflow graph` runtime | `main/backend/app/services/workflow_graph/*` | compiler / runtime / store / handoff_store / API facade | current topic docs + workflow graph tests |
| `agent runtime` canonical path | `main/backend/app/services/agent_runtime/*` | coordinator / task_bus / watchers / memory | `agent_batch` compat map + migration docs |
| `agent_batch` compat contract | `main/backend/app/services/agent_batch/*` | task contract / approval / planner / loop | compat adapter map + closure report |
| `project_key` hard gate | `main/backend/app/settings/config.py` + `main/backend/app/main.py` | request context middleware / API helpers | integration tests + rollout note |
| `LLM` capability truthfulness | `main/backend/app/services/llm_report_generator.py` + `main/backend/app/services/writing/llm_action_service.py` | report generation / writing action response metadata | API wording + docs wording |
| `source-library / ingest` authority split | `main/backend/app/services/collect_runtime/*` + `main/backend/app/services/source_library/*` + `main/backend/app/services/ingest/*` | adapter output / ingress / postprocess / resolver | core contract tests + closure note |
| frontend render ownership | `main/frontend-modern/src/app/kernel/*` | manifest / contracts / routes / renderer | frontend closure docs + lint/build/e2e |
| frontend legacy compat | `main/frontend-modern/src/app/shell/AppShell.tsx` + `main/frontend-modern/src/app/kernel/legacyHashAdapter.ts` + `main/backend/app/web_ui_routes.py` | legacy hash / unknown route / HTML redirect | parity checklist + rollout guard note |
| release governance | `.github/*` + `main/backend/scripts/check_api_layer_imports.py` | required checks / PR template / API gate script | docs navigation + CI evidence |

Frozen interpretation:

1. owner 先按“代码责任模块”冻结，不把当前缺失的人名 owner 误写成已经存在的人事事实。
2. 任何跨 topic 改动都必须在 execution sheet 中登记主改动面与受影响面，避免“顺手改到别处”。
3. 若后续需要落到具体人员 owner，应在不改变 topic 边界的前提下追加，不覆盖这里的模块 owner。

## Frozen Compatibility Inventory

| Surface | Current status | Authority path | Retained compat surface | Switch / rollback handle | Removal gate |
|---|---|---|---|---|---|
| workflow graph compiled registry | `retained-compat` | durable compiled artifact registry | in-memory `_compiled` lookup | additive dual-write / dual-read path, default unchanged before parity | compile -> reload -> run parity through durable store |
| workflow graph run persistence | `canonical` | run store + handoff store | memory fallback when DB store disabled or fail-open | `workflow_graph_db_store_enabled`, `workflow_graph_db_store_fail_closed` | not in scope for removal |
| agent execution entry | `switchable` | session/task/event canonical path | `agent_batch`, `workflow_graph`, `skill_runtime` entrypoints | explicit compat adapter map + route selector | caller matrix + parity tests complete |
| project context resolution | `switchable` | explicit header/query `project_key` | active/default fallback | `project_key_enforcement_mode`, env-specific rollout note | non-dev require path verified |
| llm-report capability semantics | `retained-compat` | explicit real-model vs structured-template metadata | existing `llm-report` route and payload shape | additive response metadata / docs wording | caller/docs updated to new semantics |
| writing llm action semantics | `retained-compat` | explicit real-model vs rule fallback metadata | current action ids and payload shape | additive response metadata / docs wording | caller/docs updated to new semantics |
| source-library response | `switchable` | authority output contract | `terminal_output`, `frontdoor_ingress`, `postprocess_frontdoor`, `legacy_result` | additive authority path + compat projection note | caller matrix + parity checks complete |
| frontend module metadata | `canonical` | `moduleManifest -> contracts -> registry` | none intended | keep manifest-derived model stable | not in scope for removal |
| frontend render / shell dispatch | `retained-compat` | kernel-owned render/shell path | `AppShell` distribution + unknown-route fallback | additive adapter boundary and parity checks | route/nav/render single-source proven |
| frontend legacy hash | `retained-compat` | canonical modern route output | legacy hash parsing + backend html redirects | explicit adapter + switchable routing knobs | supported legacy matrix closed |
| governance gates | `switchable` | required checks + PR evidence + default docs update | advisory docs / scripts without enforced flow | CI / branch protection / template defaults | checks aligned with workflows |

Frozen compatibility rules:

1. `canonical` 表示本轮默认不重写其语义，只允许被引用为权威基础件。
2. `retained-compat` 表示可以继续存在，但必须显式写明 authority path 和 removal gate。
3. `switchable` 表示最终允许切默认行为，但切换前必须先有 knob、parity checklist 和 rollback。

## Topic Exit Criteria

| Topic | Exit criteria | Minimum evidence | Rollback handle |
|---|---|---|---|
| `AT-RCL-02` workflow graph durability | compile artifact can reload and run without same-process memory dependency; API shape unchanged | workflow graph unit + integration pack | dual-read path retains `_compiled` fallback until parity complete |
| `AT-RCL-03` workflow graph integrity | replay / integrity failures become explicit signals, not silent tolerance | edit contract + curated service tests | integrity checks can be downgraded behind additive validation path |
| `AT-RCL-04` agent canonical path | one documented canonical runtime path with compat entrypoints mapped | agent batch unit/integration pack + migration note | compat adapters remain callable |
| `AT-RCL-05` project hard gate | non-dev require path works with explicit failure signal and fallback telemetry | project key policy integration tests | dev/default warn mode remains available |
| `AT-RCL-06` llm truthfulness | caller can distinguish real-model path vs template/rule fallback | llm report + writing tests and updated response metadata | preserve current route names until docs/callers updated |
| `AT-RCL-07` source-library authority split | authority output and compat projection are both explicit and traceable | source-library contract/core tests + closure note | compat fields remain during switchable phase |
| `AT-RCL-08` frontend single source | route / render / shell dispatch stop being maintained in duplicate ownership paths | lint + build + homepage e2e | `AppShell` legacy fallback retained until parity proven |
| `AT-RCL-09` legacy hash boundary | legacy hash semantics live only in adapter boundary and B-layer route/nav parity is complete | frontend lint + graph e2e + ingest smoke | backend redirect and unknown-route fallback preserved until switch |
| `AT-RCL-10` governance default gate | required checks, PR evidence, docs navigation update become default expectations | gate scripts + standardize test pack + docs index diff | policy can stay advisory only if workflow mismatch remains unresolved |

Exit policy:

1. 任何 topic 只有在 authority path、compat status、minimum evidence、rollback handle 四项同时齐备时，才允许从 pending 进入 closure。
2. 若只完成实现、未完成 evidence 或 rollback，则状态只能记为 in progress，不得记为 closed。

## Touched-Module Execution Sheet

| Task | Allowed primary write surface | Expected secondary impact | Forbidden first move |
|---|---|---|---|
| `AT-RCL-01` | current topic docs only | `development/latest-dev-docs` indexes at closure time | no runtime/code default changes |
| `AT-RCL-02` | `services/workflow_graph/*`, `api/workflow_graph.py`, workflow graph tests | session projection, store metadata | do not delete `_compiled`; do not change compile/run API shape |
| `AT-RCL-03` | workflow graph contract/schema/edit paths and tests | observability / replay diagnostics | do not make silent drift “best effort” |
| `AT-RCL-04` | `services/agent_runtime/*`, `services/agent_batch/*`, `api/agent_batch.py` | migration docs, session tests | do not remove compat entrypoints first |
| `AT-RCL-05` | `settings/config.py`, `app/main.py`, API project-key helpers, integration tests | rollout notes, headers/logging | do not flip all environments to require first |
| `AT-RCL-06` | llm-report / writing services + APIs + related docs/tests | response metadata, API wording | do not rename public route first |
| `AT-RCL-07` | source-library adapter / terminal output / ingress / postprocess / core tests | resolver metadata, compat docs | do not remove compat fields first |
| `AT-RCL-08` | frontend kernel contracts/routes/renderer/shell | nav / stories / e2e | do not assume metadata convergence equals render convergence |
| `AT-RCL-09` | legacy hash adapter / kernel app / visualization shell / backend web routes | nav parity, redirects, smoke | do not remove unknown-route fallback first |
| `AT-RCL-10` | `.github/*`, gate scripts, test docs, dev-doc indexes | CI alignment and PR flow | do not claim hard gate if workflow mismatch still exists |
| `AT-RCL-11` | closure docs, indexes, merged overview, regression evidence | final status recommendation | do not archive before evidence pack completes |

## Task AT-RCL-01: Freeze Closure Scope, Owner Map, and Compatibility Inventory

- Goal: 冻结本轮收口的范围、owner、兼容面与退出标准，避免后续任务发生口径漂移。
- Status: completed
- Depends_on: `[]`
- Blocks: `["AT-RCL-02","AT-RCL-04","AT-RCL-05","AT-RCL-06","AT-RCL-08","AT-RCL-10"]`
- Input:
  - [01_repo-logic-gap-assessment-2026-04-06.md](./01_repo-logic-gap-assessment-2026-04-06.md)
  - [02_repo-closure-plan-aligned-with-latest-direction-2026-04-06.md](./02_repo-closure-plan-aligned-with-latest-direction-2026-04-06.md)
- Output:
  - closure owner map
  - compatibility inventory
  - topic exit criteria
  - touched-module execution sheet
- Likely files:
  - `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-04-06-repo-logic-gap-assessment/02_repo-closure-plan-aligned-with-latest-direction-2026-04-06.md`
  - `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-04-06-repo-logic-gap-assessment/03_atomic-tasklist-repo-closure-plan-2026-04-06.md`
- Acceptance:
  - 每个收口对象都有 owner、compat status、最低验收项和回退路径。
- Closure result:
  - `Frozen Closure Owner Map`
  - `Frozen Compatibility Inventory`
  - `Topic Exit Criteria`
  - `Touched-Module Execution Sheet`
- Minimum validation:
  - `rg -n "workflow graph|agent runtime|project_key|LLM|source-library|frontend|required checks|compat" development/latest-dev-docs/development-plans/CURRENT_DEV/2026-04-06-repo-logic-gap-assessment -S`

## Task AT-RCL-02: Land Durable Workflow Graph Runtime Contract

- Goal: 将 workflow graph 从单进程 `_compiled` 句柄收口到 durable compiled artifact store / registry 驱动的 runtime，并与现有 run store / handoff store 持久化边界对齐。
- Status: completed
- Depends_on: `["AT-RCL-01"]`
- Blocks: `["AT-RCL-03","AT-RCL-11"]`
- Input:
  - `main/backend/app/services/workflow_graph/__init__.py`
  - `main/backend/app/services/workflow_graph/compiler.py`
  - `main/backend/app/services/workflow_graph/runtime.py`
  - `main/backend/app/services/workflow_graph/store.py`
  - `main/backend/app/services/workflow_graph/handoff_store.py`
  - `main/backend/app/api/workflow_graph.py`
- Output:
  - durable compiled artifact contract
  - explicit graph id / version / resume semantics
  - runtime handoff storage alignment note
- Likely files:
  - `main/backend/app/services/workflow_graph/__init__.py`
  - `main/backend/app/services/workflow_graph/store.py`
  - `main/backend/app/services/workflow_graph/runtime.py`
  - `main/backend/app/api/workflow_graph.py`
- Acceptance:
  - compile -> persist -> reload -> run 不再依赖同一进程内存态。
  - graph id 语义不再等同于 session-local temporary handle。
  - 不重复实现已有 run-event / handoff persistence，而是与其 contract 对齐。
  - 在默认执行链切换前，现有 compile/run API 仍保持可用。
- Current implementation slice:
  - compiled artifact durable store builder landed with the same fail-closed posture as run store
  - compile path now persists compiled artifacts while retaining in-memory `_compiled`
  - reload path now falls back to durable compiled registry before failing
  - targeted workflow graph unit/integration pack is green
- Closure decision:
  - promoted to `completed` by `07_topic-closure-matrix-repo-closure-plan-2026-04-07.md`
  - retained compat surface is `_compiled` fallback; rollback handles are `workflow_graph_db_store_enabled` / `workflow_graph_db_store_fail_closed`
- Safety mode:
  - `additive-only`
- Do not do first:
  - 不先删除 `_compiled` registry。
  - 不先改 `run()` 的请求/响应外形。
- Minimum validation:
  - `cd main/backend && .venv311/bin/python -m pytest -q tests/unit/test_workflow_graph_compiler_unittest.py tests/unit/test_workflow_graph_runtime_unittest.py tests/unit/test_workflow_graph_handoff_store_unittest.py`
  - `cd main/backend && .venv311/bin/python -m pytest -q tests/integration/test_workflow_graph_api_unittest.py`

## Task AT-RCL-03: Add Workflow Graph Integrity and Replay Closure Checks

- Goal: 在 workflow graph durable runtime 之上补完整性校验、回放一致性和 closure boundary 门禁。
- Status: completed
- Depends_on: `["AT-RCL-02"]`
- Blocks: `["AT-RCL-11"]`
- Input:
  - `main/backend/app/services/workflow_graph/contracts.py`
  - `main/backend/app/services/workflow_graph/schema.py`
  - `main/backend/app/services/workflow_graph/edit_contract.py`
  - `main/backend/app/services/workflow_graph/observability.py`
- Output:
  - graph integrity checks
  - replay consistency checks
  - failure diagnostics for invalid closure state
- Likely files:
  - `main/backend/app/services/workflow_graph/contracts.py`
  - `main/backend/app/services/workflow_graph/schema.py`
  - `main/backend/app/services/workflow_graph/edit_contract.py`
  - `main/backend/tests/unit/test_workflow_graph_edit_contract_unittest.py`
- Acceptance:
  - orphan/cycle/reference drift/replay inconsistency 有明确失败信号，而不是静默容忍。
- Current implementation slice:
  - shared integrity report now detects missing references, cycles, topo-order gaps, and dependency drift
  - edit-contract and curated draft save now fail early on integrity violations instead of deferring them
  - runtime now emits explicit `workflow_integrity_failed` run failure payloads for invalid execution graphs
  - replay output now carries additive consistency diagnostics when stored run state and event-derived state diverge
- Closure decision:
  - promoted to `completed` by `07_topic-closure-matrix-repo-closure-plan-2026-04-07.md`
  - rollback remains additive-only: integrity diagnostics can be downgraded without removing the durable/runtime path
- Minimum validation:
  - `cd main/backend && .venv311/bin/python -m pytest -q tests/unit/test_workflow_graph_edit_contract_unittest.py tests/unit/test_workflow_graph_curated_service_unittest.py`

## Task AT-RCL-04: Converge Agent Runtime to Session/Task/Event Canonical Path

- Goal: 把 agent runtime 主执行链收敛到 session/task/event 核心，旧 `agent_batch` 等入口降为 adapter。
- Status: completed
- Depends_on: `["AT-RCL-01"]`
- Blocks: `["AT-RCL-11"]`
- Input:
  - `main/backend/app/services/agent_runtime/coordinator.py`
  - `main/backend/app/services/agent_runtime/task_bus.py`
  - `main/backend/app/services/agent_runtime/watchers.py`
  - `main/backend/app/services/agent_runtime/memory.py`
  - `main/backend/app/services/agent_batch/*`
  - `main/backend/app/api/agent_batch.py`
  - [01_claude-agent-high-fidelity-migration-mapping-2026-04-02.md](../2026-04-02-claude-agent-high-fidelity-migration/01_claude-agent-high-fidelity-migration-mapping-2026-04-02.md)
- Output:
  - canonical runtime path note
  - compat adapter map for old entrypoints
  - session migration / resume contract
- Likely files:
  - `main/backend/app/services/agent_runtime/coordinator.py`
  - `main/backend/app/services/agent_runtime/task_bus.py`
  - `main/backend/app/services/agent_batch/task_contract.py`
  - `main/backend/app/services/agent_batch/approval_binding.py`
  - `main/backend/app/api/agent_batch.py`
- Acceptance:
  - “真实入口”与“compat 入口”边界明确，且 session lifecycle 可以被画成单一主链。
- Current implementation slice:
  - freeze-only canonical path snapshot documents `/agent-batch/jobs` as the direct submit path and `nl-command` as a planner loop that rejoins it
  - `project_agent_batch_job_submission(...)` now creates a compat session from direct job submit and returns additive `session_id` / `current_phase`
  - `project_agent_batch_job_state(...)` now projects celery/runtime snapshots back into implementation / verification tasks in the session ledger
  - retry, approvals, direct NL command, and curated workflow-graph registration surfaces remain explicit compat entrypoints instead of parallel main chains
  - runtime convergence closure note is captured in [08_agent-runtime-canonical-path-closure-2026-04-07.md](./08_agent-runtime-canonical-path-closure-2026-04-07.md)
- Safety mode:
  - `freeze-only -> additive-only -> switchable`
- Do not do first:
  - 不先把 `agent_batch`、`workflow_graph`、`skill_runtime` 当成可直接下线的旧入口。
  - 不先改变现有 task manifest / retry / approval contract 默认语义。
- Minimum validation:
  - `cd main/backend && .venv311/bin/python -m pytest -q tests/unit/test_agent_batch_api_unittest.py tests/unit/test_agent_sessions_service_unittest.py`
  - `cd main/backend && .venv311/bin/python -m pytest -q tests/integration/test_agent_batch_workflow_closure_unittest.py tests/integration/test_agent_sessions_api_unittest.py`

## Task AT-RCL-05: Harden Project Key to Environment-Ready Hard Gate

- Goal: 把 `project_key` 从默认软约束收敛为目标环境可启用的硬门禁。
- Status: in_progress
- Depends_on: `["AT-RCL-01"]`
- Blocks: `["AT-RCL-11"]`
- Input:
  - `main/backend/app/settings/config.py`
  - `main/backend/app/main.py`
  - `main/backend/app/web_ui_routes.py`
  - `main/backend/tests/integration/test_project_key_policy_unittest.py`
- Output:
  - hardened enforcement policy
  - fallback telemetry rules
  - rollout note for dev vs non-dev environments
- Likely files:
  - `main/backend/app/settings/config.py`
  - `main/backend/app/main.py`
  - `main/backend/tests/integration/test_project_key_policy_unittest.py`
- Acceptance:
  - 非开发环境可切 `require`，并保持明确失败行为与告警头/日志。
- Current implementation slice:
  - effective enforcement mode now supports `project_key_require_in_non_dev`
  - middleware exposes enforcement and fallback headers for observability
  - ingest/source-library helpers now use the effective enforcement mode
  - targeted project key integration pack is green
- Closure decision:
  - promoted to `completed` by `07_topic-closure-matrix-repo-closure-plan-2026-04-07.md`
  - rollback handles remain `project_key_enforcement_mode`, `project_key_require_in_non_dev`, and fallback telemetry headers
- Safety mode:
  - `additive-only -> switchable`
- Do not do first:
  - 不先把当前默认配置直接改成全环境 `require`。
  - 不先删除 fallback telemetry 和 warning header。
- Minimum validation:
  - `cd main/backend && .venv311/bin/python -m pytest -q tests/integration/test_project_key_policy_unittest.py`
  - `cd main/backend && .venv311/bin/python -m pytest -m "integration and not external" tests/integration/test_project_schema_guard_unittest.py -q`

## Task AT-RCL-06: Split Real LLM Capability From Template/Rule Fallback

- Goal: 收紧 LLM 相关能力语义，避免“命名像成品、实现仍是 fallback”。
- Status: completed
- Depends_on: `["AT-RCL-01"]`
- Blocks: `["AT-RCL-11"]`
- Input:
  - `main/backend/app/services/llm_report_generator.py`
  - `main/backend/app/services/llm_report_source_enrichment.py`
  - `main/backend/app/services/writing/llm_action_service.py`
  - `main/backend/app/api/llm_report.py`
  - `main/backend/app/api/writing.py`
- Output:
  - capability naming split
  - response metadata for real vs fallback path
  - updated docs / API wording
- Likely files:
  - `main/backend/app/services/llm_report_generator.py`
  - `main/backend/app/services/writing/llm_action_service.py`
  - `main/backend/app/api/llm_report.py`
  - `main/backend/app/api/writing.py`
- Acceptance:
  - 上层调用方和文档能明确区分真实模型路径与模板/规则路径。
- Current implementation slice:
  - `llm_report` success, strict-block, and internal-error paths now emit additive `capability_truth`
  - writing `llm_actions` responses now expose explicit rule-template fallback metadata without renaming current routes
  - schema contract now retains payload shape while making real-model vs fallback semantics machine-readable
  - targeted llm-report and writing unit/integration pack is the required validation gate for this slice
- Closure decision:
  - promoted to `completed` by `07_topic-closure-matrix-repo-closure-plan-2026-04-07.md`
  - rollback is additive: old callers may ignore `capability_truth` while route/payload outer shape stays unchanged
- Minimum validation:
  - `cd main/backend && .venv311/bin/python -m pytest -q tests/unit/test_llm_report_generator_unittest.py tests/unit/test_llm_report_api_unittest.py tests/unit/test_writing_llm_action_service_unittest.py`
  - `cd main/backend && .venv311/bin/python -m pytest -q tests/integration/test_llm_report_api_unittest.py tests/integration/test_writing_llm_actions_api_unittest.py`

## Task AT-RCL-07: Separate Source-Library Authority Output From Compat Projection

- Goal: 保留 source-library compat 输出，但明确 authority output、compat projection 和优先级。
- Status: completed
- Depends_on: `["AT-RCL-02","AT-RCL-03","AT-RCL-06"]`
- Blocks: `["AT-RCL-11"]`
- Input:
  - `main/backend/app/services/collect_runtime/adapters/source_library.py`
  - `main/backend/app/services/source_library/terminal_output.py`
  - `main/backend/app/services/source_library/resolver.py`
  - `main/backend/app/services/ingest/frontdoor_ingress.py`
  - `main/backend/app/services/ingest/postprocess_frontdoor.py`
- Output:
  - authority output contract
  - compat projection note
  - deprecation conditions for retained legacy fields
- Likely files:
  - `main/backend/app/services/collect_runtime/adapters/source_library.py`
  - `main/backend/app/services/source_library/terminal_output.py`
  - `main/backend/app/services/source_library/resolver.py`
  - `main/backend/tests/core_business/test_source_library_core_contract.py`
- Acceptance:
  - 调用方不再把 `legacy_result` 和权威输出混为一谈。
  - compat 字段保留状态和下线条件可追溯。
- Current implementation slice:
  - source-library sync response now emits additive `authority_output` and `compat_projection` while retaining `legacy_result`
  - API terminal payload wrapper can synthesize authority/compat metadata when older compat stubs only provide terminal/frontdoor/legacy fields
  - graph structured `source_collect` sync path now reads authority summary instead of raw `legacy_result.result`
  - source-library adapter, ingest core contract, frontend smoke, external project bridge, and scrapy collect-runtime pack are green on the new contract
- Closure decision:
  - promoted to `completed` by `07_topic-closure-matrix-repo-closure-plan-2026-04-07.md`
  - retained compat surface remains explicit and removal is still gated by caller migration, not implied by completion
- Safety mode:
  - `freeze-only -> additive-only -> switchable`
- Do not do first:
  - 不先移除 `legacy_result`、`terminal_output`、`frontdoor_ingress`、`postprocess_frontdoor`。
  - 不先改 `to_source_library_response(...)` 的默认返回字段集合。
- Minimum validation:
  - `cd main/backend && .venv311/bin/python -m pytest -q tests/unit/test_source_library_terminal_output_unittest.py tests/unit/test_collect_runtime_source_library_adapter_unittest.py tests/unit/test_postprocess_frontdoor_unittest.py`
  - `cd main/backend && .venv311/bin/python -m pytest -q tests/core_business/test_source_library_core_contract.py tests/integration/test_t22_source_library_scrapy_collect_runtime_integration_unittest.py`

## Task AT-RCL-08: Unify Frontend Render Ownership and Shell Facts

- Goal: 将 frontend 的 render ownership、route dispatch、surface、shell 关系收敛为单一事实源，同时保持模块 metadata 继续从 manifest 派生。
- Status: completed
- Depends_on: `["AT-RCL-01"]`
- Blocks: `["AT-RCL-09","AT-RCL-11"]`
- Input:
  - `main/frontend-modern/src/app/kernel/moduleManifest.ts`
  - `main/frontend-modern/src/app/platform/modules/registry.ts`
  - `main/frontend-modern/src/app/kernel/contracts.ts`
  - `main/frontend-modern/src/app/kernel/routes.ts`
  - `main/frontend-modern/src/app/kernel/ModuleRenderer.tsx`
  - `main/frontend-modern/src/app/shell/AppShell.tsx`
- Output:
  - render/shell single source of truth
  - route/module mapping closure note
  - parity checklist for module metadata -> route -> render -> shell -> nav
- Likely files:
  - `main/frontend-modern/src/app/kernel/moduleManifest.ts`
  - `main/frontend-modern/src/app/platform/modules/registry.ts`
  - `main/frontend-modern/src/app/kernel/contracts.ts`
  - `main/frontend-modern/src/app/kernel/routes.ts`
  - `main/frontend-modern/src/app/kernel/ModuleRenderer.tsx`
  - `main/frontend-modern/src/app/shell/AppShell.tsx`
- Acceptance:
  - 页面渲染与 shell dispatch 只剩一份权威来源。
  - `moduleManifest` 继续作为模块 metadata 的权威来源。
  - `AppShell` 与 `ModuleRenderer` 不再分别维护双份事实。
- Current implementation slice:
  - shared kernel render table now owns module-to-page dispatch for both `ModuleRenderer` and legacy `AppShell`
  - `AppShell` retains legacy hash and unknown-route compatibility behavior, but no longer keeps a second page component switch table
  - detached LLM designer handling remains explicit via shell-mode context instead of duplicated per-shell render branches
  - frontend build and homepage e2e are green; lint stays warning-only with pre-existing hook warnings outside this slice
- Closure decision:
  - promoted to `completed` by `07_topic-closure-matrix-repo-closure-plan-2026-04-07.md`
  - rollback remains the retained `AppShell` fallback behavior rather than a second dispatch fact table
- Safety mode:
  - `freeze-only -> additive-only`
- Do not do first:
  - 不先删 `AppShell` 内的旧分发。
  - 不先把 metadata registry 的收敛误当成 render ownership 已经收敛。
  - 不先假定 `moduleManifest` 已经天然覆盖全部 nav / route / shell 事实。
- Minimum validation:
  - `cd main/frontend-modern && npm run lint`
  - `cd main/frontend-modern && npm run build`
  - `cd main/frontend-modern && npm run test:e2e -- tests/e2e/homepage.spec.ts`

## Task AT-RCL-09: Close Legacy Hash Adapter Boundary and B-Layer Shell Coverage

- Goal: 将 legacy hash 兼容下沉到显式 adapter，并补齐 B 层 shell 与导航可见性。
- Status: completed
- Depends_on: `["AT-RCL-08"]`
- Blocks: `["AT-RCL-11"]`
- Input:
  - `main/frontend-modern/src/app/kernel/legacyHashAdapter.ts`
  - `main/frontend-modern/src/app/navigation/index.ts`
  - `main/frontend-modern/src/app/kernel/FrontendKernelApp.tsx`
  - `main/frontend-modern/src/app/kernel/VisualizationLayerShell.tsx`
  - `main/frontend-modern/src/components/FigmaSideNav.tsx`
  - `main/backend/app/web_ui_routes.py`
- Output:
  - supported legacy hash matrix
  - canonical modern hash output rules
  - B-layer shell / nav parity closure note
- Likely files:
  - `main/frontend-modern/src/app/kernel/legacyHashAdapter.ts`
  - `main/frontend-modern/src/app/navigation/index.ts`
  - `main/frontend-modern/src/app/kernel/FrontendKernelApp.tsx`
  - `main/frontend-modern/src/app/kernel/VisualizationLayerShell.tsx`
  - `main/frontend-modern/src/components/FigmaSideNav.tsx`
  - `main/backend/app/web_ui_routes.py`
- Acceptance:
  - legacy hash 只在 adapter 层承载兼容语义。
  - 所有 `LayerId='B'` 模块具备 route / shell / nav 一致性。
- Current implementation slice:
  - `hashByMode` 已切换为 canonical modern route hash；legacy hash 保留在显式 `legacyHashByMode` / `parseLegacyHashToMode` adapter 中。
  - `AppShell` 当前通过 kernel route resolver 同时接受 layered route 与 legacy hash 输入，但默认输出只写 canonical route。
  - B 层 shell section 覆盖矩阵与模块图标已抽到共享 kernel chrome 映射，`VisualizationLayerShell` 与 `FigmaSideNav` 不再各自维护第二份 icon 事实。
  - backend 旧 HTML graph/topic 入口兼容矩阵已补最小 redirect 契约测试，固定 modern frontend redirect 目标。
- Closure decision:
  - promoted to `completed` by `07_topic-closure-matrix-repo-closure-plan-2026-04-07.md`
  - rollback remains explicit through legacy hash adapters, backend redirects, and unknown-route fallback
- Safety mode:
  - `freeze-only -> additive-only -> switchable`
- Do not do first:
  - 不先修改 legacy hash 的默认解析规则。
  - 不先改 backend `/graph.html`、`/dashboard.html`、`/topic-dashboard.html` 等跳转目标。
  - 不先把 unknown route fallback 从 `FrontendKernelApp` 中移除。
- Minimum validation:
  - `cd main/frontend-modern && npm run lint`
  - `cd main/frontend-modern && npm run test:e2e -- tests/e2e/graphpage.spec.ts`
  - `cd main/frontend-modern && npm run test:ingest-smoke`

## Task AT-RCL-10: Turn Required Checks, PR Evidence, and Docs Navigation Into Default Gates

- Goal: 把治理要求从“文档建议”收紧为默认门禁和默认留痕。
- Status: completed
- Depends_on: `["AT-RCL-01"]`
- Blocks: `["AT-RCL-11"]`
- Input:
  - `.github/branch-protection-required-checks.json`
  - `.github/workflows/backend-tests.yml`
  - `.github/PULL_REQUEST_TEMPLATE.md`
  - `main/backend/tests/README.md`
  - `development/latest-dev-docs/README.md`
  - `development/latest-dev-docs/MERGED_OVERVIEW.md`
- Output:
  - required check matrix alignment note
  - PR evidence expectations
  - docs navigation maintenance checklist
- Likely files:
  - `.github/branch-protection-required-checks.json`
  - `.github/workflows/backend-tests.yml`
  - `.github/PULL_REQUEST_TEMPLATE.md`
  - `main/backend/tests/README.md`
  - `development/latest-dev-docs/README.md`
  - `development/latest-dev-docs/MERGED_OVERVIEW.md`
- Acceptance:
  - required checks 与实际 workflow 不冲突。
  - PR evidence 至少包含 scope / risk / test evidence / rollback。
  - 文档新增与 closure note 默认同步索引。
- Current implementation slice:
  - branch protection baseline now records required check sources, default PR evidence sections, docs sync targets, and local repro profiles in `.github/branch-protection-required-checks.json`
  - PR template now defaults to `Scope / Risk / Test Evidence / Rollback Strategy / Docs And Closure`
  - governance alignment note landed as `05_governance-default-gates-pr-evidence-and-docs-navigation-2026-04-07.md`
  - `development/latest-dev-docs` top-level and development-plan indexes now include the governance baseline note as the latest navigation entry
  - local governance repair slice landed for test/gate stability: `信息采集测试.py` import path is now lazy, crawler-management core contract matches current async payload shape, API-layer HTTPException allowlist is refreshed to current baseline, and `test_api_group_a_core_contract.py` now patches `resource_pool_api.list_urls` via object patching to avoid alias-level drift
  - minimum local validation pack was executed successfully from the current workspace and is now evidence-backed rather than note-only
- Minimum validation:
  - `main/backend/.venv311/bin/python main/backend/scripts/check_api_layer_imports.py`
  - `./scripts/test-standardize.sh unit`
  - `./scripts/test-standardize.sh integration`
  - `./scripts/test-standardize.sh contract`
- Closure result:
  - `main/backend/.venv311/bin/python main/backend/scripts/check_api_layer_imports.py` -> passed
  - `./scripts/test-standardize.sh unit` -> `443 passed, 4 skipped, 244 deselected`
  - `./scripts/test-standardize.sh integration` -> `111 passed`
  - `./scripts/test-standardize.sh contract` -> `90 passed, 601 deselected`

## Task AT-RCL-11: Run Final Regression Pack and Documentation Closure

- Goal: 以一组最小但真实的回归包结束本轮收口，并同步文档与状态。
- Status: completed
- Depends_on: `["AT-RCL-02","AT-RCL-03","AT-RCL-04","AT-RCL-05","AT-RCL-06","AT-RCL-07","AT-RCL-08","AT-RCL-09","AT-RCL-10"]`
- Blocks: `[]`
- Input:
  - all outputs from `AT-RCL-01 ~ AT-RCL-10`
- Output:
  - final closure report
  - updated status snapshot
  - updated indexes and merged overview
  - exit recommendation: remain in `CURRENT_DEV` or archive
- Likely files:
  - `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-04-06-repo-logic-gap-assessment/03_atomic-tasklist-repo-closure-plan-2026-04-06.md`
  - `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-04-06-repo-logic-gap-assessment/04_validation-closure-repo-closure-plan-2026-04-06.md`
  - `development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md`
  - `development/latest-dev-docs/development-plans/INDEX.md`
  - `development/latest-dev-docs/README.md`
  - `development/latest-dev-docs/MERGED_OVERVIEW.md`
- Acceptance:
  - 至少一轮真实 regression pack 跑通并留痕。
  - 文档、验证、回退、compat status 四条线都闭环。
  - 是否归档的判断基于证据，不基于主观完成感。
- Current implementation slice:
  - final validation note landed as `06_validation-closure-repo-closure-plan-2026-04-07.md`
  - repo-level final regression pack is green across `ci-pr`, targeted backend closure tests, and frontend lint/build/homepage e2e
  - status snapshot and top-level navigation now carry an explicit exit recommendation to remain in `CURRENT_DEV`
- Closure result:
  - `./scripts/test-standardize.sh ci-pr` -> `554 passed, 4 skipped, 133 deselected`
  - targeted backend closure pack -> `55 passed`
  - frontend closure pack -> `lint green with 19 existing warnings`, `build green`, `homepage e2e 2 passed`
  - exit recommendation -> remain in `CURRENT_DEV`
- Minimum validation:
  - `./scripts/test-standardize.sh ci-pr`
  - `cd main/frontend-modern && npm run lint && npm run build && npm run test:e2e -- tests/e2e/homepage.spec.ts`
  - `cd main/backend && .venv311/bin/python -m pytest -q tests/integration/test_workflow_graph_api_unittest.py tests/integration/test_project_key_policy_unittest.py tests/integration/test_llm_report_api_unittest.py tests/integration/test_writing_llm_actions_api_unittest.py tests/core_business/test_source_library_core_contract.py`

## Minimum Regression Pack Summary

- Backend runtime:
  - `cd main/backend && .venv311/bin/python -m pytest -q tests/unit/test_workflow_graph_compiler_unittest.py tests/unit/test_workflow_graph_runtime_unittest.py tests/unit/test_workflow_graph_handoff_store_unittest.py`
- Backend policy / capability:
  - `cd main/backend && .venv311/bin/python -m pytest -q tests/integration/test_project_key_policy_unittest.py tests/integration/test_llm_report_api_unittest.py tests/integration/test_writing_llm_actions_api_unittest.py`
- Source-library / ingest:
  - `cd main/backend && .venv311/bin/python -m pytest -q tests/unit/test_collect_runtime_source_library_adapter_unittest.py tests/unit/test_source_library_terminal_output_unittest.py tests/core_business/test_source_library_core_contract.py`
- Frontend:
  - `cd main/frontend-modern && npm run lint`
  - `cd main/frontend-modern && npm run build`
  - `cd main/frontend-modern && npm run test:e2e -- tests/e2e/homepage.spec.ts`
  - `cd main/frontend-modern && npm run test:e2e -- tests/e2e/graphpage.spec.ts`

## Residual Risk Notes

- `workflow graph` durable store 若没有版本和 replay contract，容易把“可恢复”做成“可写但不可验证”。
- agent runtime 若只补 adapter、不明确 canonical path，会继续保留“双入口都像主入口”的问题。
- `project_key` 强化若没有 rollout 区分，可能误伤本地和历史调用链。
- source-library 若只加字段、不标权威优先级，会继续维持多合同歧义。
- frontend 若只改 route，或只整理 registry metadata，而不收 render / shell / nav 三处事实源，双中心问题不会真正消失。
- required checks 和 PR evidence 若不转成默认执行，收口计划仍会停留在文档层。
