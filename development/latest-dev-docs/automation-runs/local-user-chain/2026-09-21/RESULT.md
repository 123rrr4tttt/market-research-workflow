# 本地测试数据注入与用户链路结果

日期：2026-09-21  
范围：当前工作树源码覆盖到保留镜像上的本机 Compose 环境；不是冻结候选回放或生产部署。

## 注入数据与结果

- 种子文件：`main/backend/seed_data/project_demo_proj_v0.9-rc2.0.sql`。
- 通过产品接口创建项目 `local_demo_20260921`，复制 75 篇文档和 6 个来源；没有复制种子中的历史 ETL 任务。完整回执见 [`seed-injection.json`](seed-injection.json)。
- 从资源页提交真实 Celery URL 提取任务，扫描 75 篇文档并新增 267 条项目级 URL。再次执行扫描出相同 267 条，新增 0、重复 267，验证去重。任务状态和结果见 [`url-extraction-task.json`](url-extraction-task.json)、[`url-extraction-dedup-task.json`](url-extraction-dedup-task.json)；资源池读回见 [`url-pool-readback.json`](url-pool-readback.json)。
- 原始数据页 README 摘录导入成功：插入 1 条、错误 0。修复前的一次失败尝试仍保留在任务历史中；前后读回见 [`raw-import-before-fix.json`](raw-import-before-fix.json)、[`raw-import-after-fix.json`](raw-import-after-fix.json)。
- 修复后端新文档分支空 `doc` 访问，并调整前端任务摘要，使其展示 `urls_extracted`，且把“已提交”与最终完成状态区分开。
- 修复异步原始导入没有注册为 Celery task 的缺口：`task_raw_import_documents` 原来是普通函数，但 API 调用它的 `.delay()`。按同文件既有 `@celery_app.task` 方式注册后，重启 backend/worker 并从 worker registry 读到 `app.services.tasks.task_raw_import_documents`。
- 通过真实 API 提交一条关闭 URL 推断、URL 抓取及结构化提取的异步 smoke import。Celery task `afea152f-2d9e-4397-b348-5416d8dfe5c8` 返回 `SUCCESS`，插入 1 条、错误 0；worker 日志确认 task received/succeeded，Process API 读回状态及结果，文档列表 API 读回 `doc_id=148`。提交、worker 日志、任务和文档读回分别见 [`async-raw-import-submit.json`](async-raw-import-submit.json)、[`async-raw-import-worker.log`](async-raw-import-worker.log)、[`async-raw-import-task-readback.json`](async-raw-import-task-readback.json)、[`async-raw-import-document-readback.json`](async-raw-import-document-readback.json)。

## 验证与限制

- 前端 `npm run build`、相关 ESLint、Resource/Process 文案检查通过；原始导入和 task runtime focused tests 共 11 项通过（2 条既有 Pydantic deprecation warnings）。`git diff --check` 与本地 Compose 配置校验通过。
- UI 与 API 文档返回 HTTP 200。最近核对时六个 Compose 服务仍在运行，后端及数据库、Redis、Elasticsearch、Celery worker 容器报告健康。项目 `main/backend/.env` 中 `OPENAI_API_KEY` 有非空配置；本地用户 Compose overlay 有意清空 `env_file` 并向服务传空值，因此容器环境仍报告 key 缺失。仅检查了配置是否非空，未显示或验证 key，也未调用模型。Codex Auth 未认证，见 [`auth-status.json`](auth-status.json)。
- 本次 URL 提取只从已入库文本中解析 URL；异步 smoke raw import 也未请求 URL 目标。两条链路均没有调用 LLM、外部搜索或新闻服务。
- 当时宿主磁盘可用约 34 GiB；Docker 报告镜像 18.8 GB、卷 1.123 GB、构建缓存 10.39 GB。没有清理或 prune。
- 运行输入与代码摘要见 [`runtime-inputs.json`](runtime-inputs.json)。本地数据库保存在 `mrw-local-user` 独立命名卷中。

## 本机访问与服务控制

- UI：<http://127.0.0.1:15132/>
- API：<http://127.0.0.1:18132/docs>
- 启动/恢复：在仓库根目录按 [`main/ops/README.md`](../../../../../main/ops/README.md) 中“当前工作树的本地用户环境”执行 Compose `up` 命令。
- 如修改 Celery task 定义/注册，backend 与 worker 都需加载当前源码；执行同一 Compose 命令的 `restart backend celery-worker`，并检查 worker registered 清单后再提交异步请求。
- 停止并保留数据：执行同一说明中的 Compose `stop` 命令。不要使用 `down -v` 或全局 prune。

此环境和本次结果仅用于本地用户链路验证，不启动 Stage 7–9，不授予发布权限，也不代表生产资格。
