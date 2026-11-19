# 市场研究工作流（MRW）

MRW 是本机单用户研究工作台：按项目整理来源和资料，开展搜索与专题调查，再将可回溯的证据用于分析、写作和报告。业务界面嵌入 Codex WebUI；Agent 通过 Cell 调用获准的领域操作，材料、文档与任务结果仍由对应服务写入。

## 开始使用

从干净的 checkout 开始，按[本机使用说明](docs/usage.md#首次运行)准备依赖、初始化数据库、构建界面并启动服务。默认业务入口是 <http://127.0.0.1:5173>。启动后先创建或选择项目，导入一份材料，在任务页查看处理结果，再搜索并打开原文核对。

## 文档

| 要做的事 | 阅读入口 |
| --- | --- |
| 安装、启动与日常使用 | [使用说明](docs/usage.md) |
| 理解对象、职责与设计取舍 | [总体设计](docs/architecture/README.md) |
| 修改代码与验证 | [开发指南](docs/development/README.md) |
| 定位接口与各领域专题 | [后端接口与专题](main/backend/docs/README.md) |

## 源码

| 路径 | 责任 |
| --- | --- |
| [main/backend](main/backend) | API、领域服务、后台任务、迁移和后端测试 |
| [main/frontend-modern](main/frontend-modern) | 业务界面 |
| [main/ops](main/ops) | 运行配置、运维及 Codex WebUI |
| [contributions](contributions) | 原生能力声明与公共装配接入 |
| [scripts](scripts) | 启停、开发检查、测试和维护入口 |

协作规则见 [AGENTS.md](AGENTS.md)，提交约定见 [GIT_WORKFLOW.md](GIT_WORKFLOW.md)。
