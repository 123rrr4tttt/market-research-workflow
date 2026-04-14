# Phase 2 开发后 Docker 环境最小验收步骤

> 基于 `RESOURCE_LIBRARY_IMPLEMENTATION_PLAN.md` Phase 2：采集配置（Ingest Config）

## 0. 非交互启动（替代 start-all.sh）

`start-all.sh` 在端口占用时会 `read -p "是否继续？(y/N):"` 交互。验收时使用非交互命令：

```bash
cd /Users/wangyiliang/projects/信息收集工作流/main/ops
docker-compose down 2>/dev/null || true
docker-compose up -d
```

或使用已有测试脚本（同样无交互）：

```bash
cd /Users/wangyiliang/projects/信息收集工作流/main/ops
./test-docker-startup.sh
```

**注意**：若 5432/9200/6379/8000 端口被占用，`docker-compose up -d` 会直接失败并报错，不会阻塞等待输入。

---

## 1. 等待服务就绪

```bash
# 等待 Backend 健康（最多约 60 秒）
for i in $(seq 1 30); do
  curl -s http://localhost:8000/api/v1/health >/dev/null 2>&1 && break
  sleep 2
done
```

---

## 2. 基础健康检查

```bash
curl -s http://localhost:8000/api/v1/health
```

**预期输出**（示例）：

```json
{"status":"ok","provider":"...","env":"..."}
```

或类似包含 `"status":"ok"` 的 JSON。

---

## 3. Ingest Config API 验收（Phase 2 核心）

### 3.1 GET 未存在的配置 → 404

```bash
curl -s -w "\nHTTP_CODE:%{http_code}" \
  "http://localhost:8000/api/v1/ingest/config?project_key=online_lottery&config_key=social_forum"
```

**预期**：

- HTTP 状态码：`404`
- 响应体包含 `"status":"error"` 且 `error.code` 为 `NOT_FOUND`

示例：

```json
{"status":"error","data":null,"error":{"code":"NOT_FOUND","message":"Config not found: social_forum","details":{}},"meta":{}}
```

### 3.2 POST 创建/更新配置

```bash
curl -s -X POST "http://localhost:8000/api/v1/ingest/config" \
  -H "Content-Type: application/json" \
  -d '{
    "project_key": "online_lottery",
    "config_key": "social_forum",
    "config_type": "structure",
    "payload": {
      "platforms": ["reddit"],
      "base_subreddits": ["lottery", "gambling"],
      "enable_subreddit_discovery": true
    }
  }'
```

**预期输出**（示例）：

```json
{
  "status": "ok",
  "data": {
    "project_key": "online_lottery",
    "config_key": "social_forum",
    "config_type": "structure",
    "payload": {
      "platforms": ["reddit"],
      "base_subreddits": ["lottery", "gambling"],
      "enable_subreddit_discovery": true
    },
    "created_at": "2026-02-26T...",
    "updated_at": "2026-02-26T..."
  },
  "error": null,
  "meta": {}
}
```

### 3.3 GET 已存在的配置 → 200

```bash
curl -s "http://localhost:8000/api/v1/ingest/config?project_key=online_lottery&config_key=social_forum"
```

**预期**：

- HTTP 状态码：`200`
- `status` 为 `ok`，`data` 包含刚写入的 `payload`

---

## 4. 一键验收脚本（可选）

```bash
#!/bin/bash
set -e
BASE="http://localhost:8000/api/v1"
PK="online_lottery"
CK="social_forum"

echo "1. Health check..."
curl -sf "$BASE/health" | grep -q '"status":"ok"' || { echo "FAIL: health"; exit 1; }
echo "   OK"

echo "2. GET non-existent config (expect 404)..."
code=$(curl -s -o /tmp/resp.json -w "%{http_code}" "$BASE/ingest/config?project_key=$PK&config_key=$CK")
[ "$code" = "404" ] || { echo "FAIL: expected 404, got $code"; cat /tmp/resp.json; exit 1; }
echo "   OK"

echo "3. POST upsert config..."
curl -sf -X POST "$BASE/ingest/config" \
  -H "Content-Type: application/json" \
  -d "{\"project_key\":\"$PK\",\"config_key\":\"$CK\",\"config_type\":\"structure\",\"payload\":{\"platforms\":[\"reddit\"],\"base_subreddits\":[\"lottery\"]}}" \
  | grep -q '"status":"ok"' || { echo "FAIL: upsert"; exit 1; }
echo "   OK"

echo "4. GET existing config..."
curl -sf "$BASE/ingest/config?project_key=$PK&config_key=$CK" | grep -q '"config_key":"social_forum"' || { echo "FAIL: get"; exit 1; }
echo "   OK"

echo "All Phase 2 checks passed."
```

---

## 5. 项目上下文说明

- 默认项目：`online_lottery`（由 bootstrap 创建，或存在 `business_survey`）
- 若项目不存在，POST/GET 可能因外键或业务逻辑返回 400/404，需先确认 `public.projects` 中有对应 `project_key`

---

## 6. 停止服务

```bash
cd /Users/wangyiliang/projects/信息收集工作流/main/ops
docker-compose down
```
