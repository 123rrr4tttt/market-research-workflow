# 市场研究工作流

面向研究与信息处理的通用平台，提供项目管理、来源采集、文档导入、检索、信息图谱、写作和任务运维。Agent 执行使用 Codex Core，交互使用 Codex WebUI。

## 开始使用

本机入口：业务界面 <http://127.0.0.1:5173>，Codex WebUI <http://127.0.0.1:8172>，API <http://127.0.0.1:8000/docs>。

```bash
./scripts/local-deploy.sh status
./scripts/local-deploy.sh health
```

启停、宿主 OAuth、容器模式和故障定位统一见[使用说明](docs/usage.md)。当前机器的全链路验证记录来自 2026-10-04；具体能力和运行边界见该说明。

## 文档

从[文档导航](docs/README.md)进入：

| 要做的事 | 阅读入口 |
| --- | --- |
| 运行与使用 | [使用说明](docs/usage.md) |
| 理解模块和数据归属 | [架构说明](docs/architecture/README.md) |
| 修改代码与验证 | [开发指南](docs/development/README.md) |
| 查找已完成方案和旧证据 | [历史资料](docs/history/README.md) |

## 源码

| 路径 | 责任 |
| --- | --- |
| [main/backend](main/backend) | API、领域服务、后台任务、迁移和后端测试 |
| [main/frontend-modern](main/frontend-modern) | 业务界面 |
| [main/ops](main/ops) | 运行配置、运维及 Codex WebUI |
| [contributions](contributions) | 原生能力声明与公共装配接入 |
| [scripts](scripts) | 启停、开发检查、测试和维护入口 |

协作规则见 [AGENTS.md](AGENTS.md)，提交约定见 [GIT_WORKFLOW.md](GIT_WORKFLOW.md)。
