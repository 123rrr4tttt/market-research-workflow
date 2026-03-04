# LLM Embedded Snapshots

更新时间：2026-03-04（US/Pacific）

本目录是链路8（内嵌 LLM 平台化）的“爬库快照池”。

## 文件说明

- `all_urls.txt`：从链路文档与 A-F 子域快照中抽取的全部链接。
- `github_repos.txt`：去重后的 GitHub 仓库列表（owner/repo）。
- `github_repo_catalog.csv`：仓库元数据目录（GitHub API 抓取；受频率限制时可能为 NA）。
- `github_repo_catalog_basic.csv`：基础目录（repo/url/title/snapshot_status）。
- `readmes/`：仓库 README 镜像快照（最佳努力抓取）。

## 子域快照来源

- `../llm_embedded_repos_A.txt` 推理服务层
- `../llm_embedded_repos_B.txt` 网关与路由层
- `../llm_embedded_repos_C.txt` 提示词与评测治理层
- `../llm_embedded_repos_D.txt` Agent编排层
- `../llm_embedded_repos_E.txt` RAG与向量层
- `../llm_embedded_repos_F.txt` 本地与边缘运行层

## 备注

- GitHub 接口存在频率限制，`github_repo_catalog.csv` 可能出现 `NA`。
- 目录可直接用于后续“唯一方案收敛”和 PoC 任务拆分。
