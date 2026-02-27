# Codex 工作约定

## 任务执行前检查

在开始执行每个任务前，**简要判断**是否适合调用 multi-agent 技能（`multi-agent-parallel-development`）：

- 若任务涉及 **3 个及以上独立子项**、**多文件/多目录改动** 或 **多维度审查**（安全/质量/bug 等），优先考虑使用 spawn_agent 并行执行；若适用，先说明「本任务适合多 Agent 并行」，再按该技能流程拆解并执行。
- **若仅需单 Agent**：直接自己干活，无需说明「不适合多 Agent」或做任何额外判断，直接按常规流程执行即可。
- 判断应快速完成，不拖慢简单任务。

## 修改前

- 先读相关代码与文档，确认影响范围，避免盲目改动。
- 若项目有 `.cursor/rules` 或 `main/*/docs/`，优先查阅再实现。

## 修改后

- 改动完成后运行项目内测试或 lint（如 `pytest`、`npm run lint`、`./scripts/docker-deploy.sh preflight` 等），确保无回归。
- 若项目默认 Docker 运行，测试优先在 Docker 环境执行。

## 风格与范围

- 代码主体用英文，注释可用中文；以完成目标为重，不过度发散。
- 新增 API 时遵循项目既有 envelope 与分层（如 `status/data/error/meta`、`API -> services -> adapters`）。
