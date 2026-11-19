# 可选搜索服务

MRW 默认可以使用现有搜索 API。若需要在本机运行 SearXNG 或 YaCy，这两个可选服务由主 Compose 的 `search-enhancements` profile 提供。

```bash
docker compose -f main/ops/docker-compose.yml --profile search-enhancements up -d searxng yacy
```

| 服务 | 本机地址 | 后端配置 |
| --- | --- | --- |
| SearXNG | <http://127.0.0.1:8088> | `SEARXNG_BASE_URL=http://127.0.0.1:8088` |
| YaCy | <http://127.0.0.1:8090> | `YACY_BASE_URL=http://127.0.0.1:8090`、`YACY_RESOURCE_MODE=local` |

SearXNG 配置位于 `searxng/settings.yml`。YaCy 运行时数据写入 `yacy/DATA/`，该目录不进入 Git。两者只作为显式搜索通道使用，不加入 `provider="auto"`。停止服务：

```bash
docker compose -f main/ops/docker-compose.yml --profile search-enhancements stop searxng yacy
```
