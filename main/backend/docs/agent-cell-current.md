# Agent 与 Cell：现行接线入口

设计原文见[Agent 宏观架构](../../../docs/architecture/agent/cell.md)。这里仅定位当前代码接口，不另立一套设计。

| 要查什么 | 代码入口 |
| --- | --- |
| WebUI 的配置与启动 | [Codex WebUI](../../ops/codex-webui/README.md) |
| 查看项目下已激活的 Cell 环境、工具与摘要；不启动 Core 或执行工具 | [`GET /api/v1/agent-cell`](../app/api/agent_cell.py) |
| 宿主准备环境、绑定线程、记录输入、准备回合、批准、派发与结束回合 | [`/api/v1/agent-macro-host`](../app/api/agent_macro_host.py) |
| 解析已激活注册包并装配工具 | [环境解析](../app/services/agent_core/macro_environment.py)、[项目工具注册](../app/services/agent_core/project_tools.py) |
| 审查会话消息、任务和产物的实际读回 | [会话服务](../app/services/agent_sessions/service.py) |
| 查系统对象与工具目录 | [系统投影](../app/services/agent_runtime/system_projection.py) |

看到环境、注册包或工具目录，不代表已经请求、批准或执行操作。核验端到端效果时，从实际宿主调用追到原执行者和领域读回，不能用上述只读入口代替。
