# 链路6：Observability & Ops Platform 平台化替代参考

## 1) 现状（metrics + deep health + scripts）

基于现有实现（`main/backend/app/main.py`、`main/backend/app/models/base.py`、`main/ops/*.sh`、`scripts/docker-deploy.sh`），当前链路现状如下：

- 指标（Metrics）
  - 已内置 Prometheus 指标暴露：`GET /metrics`。
  - 已记录基础 HTTP 指标：
    - `market_api_requests_total{method,endpoint,status}`（计数器）
    - `market_api_request_latency_seconds{endpoint}`（直方图）
  - 指标采集在 FastAPI middleware 中完成，且请求日志已包含 `request_id/project_key/error_code`。

- 健康检查（Health / Deep Health）
  - 轻量健康：`GET /api/v1/health` 返回 `status/provider/env`。
  - 深度健康：`GET /api/v1/health/deep` 已覆盖：
    - PostgreSQL 连通性与延迟（`database_latency_ms`）
    - SQLAlchemy 连接池状态（`size/checkedout/overflow/status`）
    - 连接池耗尽门控（`deep_health_pool_gate_enabled` + ratio 阈值）
    - Elasticsearch `ping` 与延迟（`elasticsearch_latency_ms`）
  - 状态输出为 `ok/degraded`，已具备平台接入前的基础可观测数据面。

- 运维脚本（Ops / 发布回滚）
  - 统一入口：`scripts/docker-deploy.sh`（`start/stop/restart/status/logs/health/preflight/checkpoint/rollback`）。
  - 环境预检：`preflight` 覆盖命令依赖、compose 配置、端口占用、env 文件。
  - 回滚机制：`main/ops/rollback.sh` 支持 `snapshot/list/rollback`，可回滚 `docker-compose.yml`、`backend/.env`，并记录 `git head`。
  - 启停脚本：`main/ops/start-all.sh`、`stop-all.sh`、`restart.sh`。
  - 自检脚本：`main/ops/test-docker-startup.sh` 已串联 preflight + 启动 + health/deep health + 服务日志。

结论：当前已经有“可运行”的可观测与回滚基础，但仍偏“脚本驱动 + 单服务内埋点”，缺少统一平台控制面（采集治理、告警策略治理、灰度发布控制面、多环境一致性）。

---

## 2) 开源替代（3-5个）

以下方案可进入参考池（按“优先组合”排序）：

### 方案A（优先）：OpenTelemetry + Prometheus/Grafana + Loki/Tempo + Argo Rollouts

- 组件
  - OpenTelemetry SDK + OTel Collector（统一 logs/metrics/traces 管道）
  - Prometheus + Alertmanager + Grafana（指标与告警）
  - Loki + Tempo（日志与追踪，Grafana 统一查询）
  - Argo Rollouts（金丝雀/蓝绿发布与自动回滚）
- 适配理由
  - 与现有 `/metrics` 可直接衔接（Prometheus scrape）。
  - 可逐步把应用日志改为 OTel log/export 或 promtail 采集。
  - Rollout 策略可绑定 Prometheus 指标做自动分析回滚。
- 参考链接
  - OpenTelemetry: https://opentelemetry.io/
  - OTel Collector: https://opentelemetry.io/docs/collector/
  - Prometheus: https://prometheus.io/
  - Grafana: https://grafana.com/oss/grafana/
  - Loki: https://grafana.com/oss/loki/
  - Tempo: https://grafana.com/oss/tempo/
  - Argo Rollouts: https://argo-rollouts.readthedocs.io/

### 方案B：OpenTelemetry + Prometheus/Grafana + Jaeger + Flagger

- 组件
  - OTel Collector（OTLP 汇聚）
  - Prometheus/Grafana（SLI/SLO）
  - Jaeger（Trace 后端）
  - Flagger（渐进发布控制器）
- 适配理由
  - Jaeger 对 tracing 落地简单，Flagger 对网格/Ingress 金丝雀支持成熟。
- 参考链接
  - Jaeger: https://www.jaegertracing.io/
  - Flagger: https://flagger.app/

### 方案C：Prometheus Operator（kube-prometheus-stack）+ Grafana + Loki + Tempo

- 组件
  - kube-prometheus-stack（Prometheus Operator + Alertmanager + Grafana）
  - Loki/Tempo 以 Helm 方式统一运维
- 适配理由
  - 若未来迁移 K8s，可将当前脚本式监控迁移到 CRD/Helm 的声明式治理。
- 参考链接
  - kube-prometheus-stack: https://github.com/prometheus-community/helm-charts/tree/main/charts/kube-prometheus-stack
  - Grafana Helm: https://grafana.com/docs/grafana/latest/setup-grafana/installation/helm/

### 方案D：VictoriaMetrics + Grafana + Loki + Argo Rollouts

- 组件
  - VictoriaMetrics（高性价比 metrics 存储）
  - Grafana（可视化）
  - Loki（日志）
  - Argo Rollouts（发布策略）
- 适配理由
  - 指标存储成本优化场景可选。
- 参考链接
  - VictoriaMetrics: https://victoriametrics.com/

---

## 3) SLI/SLO 建议与报警规则模板

## 3.1 建议 SLI（首批）

- 可用性 SLI
  - `HTTP 5xx rate`（排除 4xx）
- 延迟 SLI
  - `p95 latency`（按 endpoint 或服务整体）
- 依赖健康 SLI
  - `deep health degraded ratio`（`/api/v1/health/deep`）
  - DB 连接池耗尽事件率（基于 deep health 细节或新增 gauge）
- 采集链路 SLI
  - Metrics scrape 成功率
  - OTel Collector 导出失败率

## 3.2 建议 SLO（示例）

- API 可用性：30 天 `>= 99.9%`
- API 延迟：30 天 `p95 < 800ms`
- 深度健康：30 天 `degraded 比例 < 0.5%`
- 发布质量：滚动发布期间 `5xx` 不高于基线 `+1%`，否则自动回滚

## 3.3 Prometheus 报警规则模板（可直接改名落地）

```yaml
groups:
- name: market-intel-api
  rules:
  - alert: ApiHigh5xxRate
    expr: |
      sum(rate(market_api_requests_total{status=~"5.."}[5m]))
      /
      sum(rate(market_api_requests_total[5m])) > 0.02
    for: 10m
    labels:
      severity: critical
    annotations:
      summary: "API 5xx 比例过高"
      description: "5xx 比例连续 10 分钟超过 2%"

  - alert: ApiHighLatencyP95
    expr: |
      histogram_quantile(
        0.95,
        sum by (le) (rate(market_api_request_latency_seconds_bucket[5m]))
      ) > 1.2
    for: 10m
    labels:
      severity: warning
    annotations:
      summary: "API p95 延迟过高"
      description: "p95 延迟连续 10 分钟 > 1.2s"

  - alert: ApiLowTrafficOrDown
    expr: up{job="market-api"} == 0
    for: 2m
    labels:
      severity: critical
    annotations:
      summary: "API 实例不可达"
      description: "Prometheus 无法抓取 market-api 指标"
```

注：当前代码已有 `_count` 与 `_latency_seconds`，若要使用 `histogram_quantile`，需确认 bucket 指标被正确导出（Prometheus Python Histogram 默认会导出）。

---

## 4) 发布回滚平台化策略

目标是把“脚本回滚”升级为“策略驱动自动回滚”：

- 阶段1（保持现状兼容）
  - 保留 `scripts/docker-deploy.sh` 与 `main/ops/rollback.sh` 作为兜底。
  - 补齐统一发布元数据：版本号、镜像 digest、git sha、变更窗口。

- 阶段2（引入控制面）
  - 在 K8s 引入 Argo Rollouts 或 Flagger。
  - 将当前健康信号接入 Prometheus（`/metrics` + 探针指标）。
  - 配置 Analysis 模板：以 `5xx`、`p95`、deep health 成功率作为发布门禁。

- 阶段3（自动化回滚）
  - Canary/BG 分批放量（如 5% -> 25% -> 50% -> 100%）。
  - 任一窗口触发告警阈值即自动回滚。
  - 同步回写事件到告警/值班渠道（Alertmanager -> PagerDuty/Slack/飞书）。

- 阶段4（治理与审计）
  - 发布与回滚全部声明式（GitOps），保留审批与审计轨迹。
  - 以错误预算（error budget）约束发布频率：预算不足时只允许修复型发布。

---

## 5) 最小 PoC 命令

以下命令用于最小验证“指标可抓取 + 健康可探测 + 回滚可执行”：

```bash
# 1) 启动前检查
./scripts/docker-deploy.sh preflight

# 2) 启动服务
./scripts/docker-deploy.sh start --non-interactive

# 3) 验证健康与深度健康
curl -fsS http://localhost:8000/api/v1/health | jq .
curl -fsS http://localhost:8000/api/v1/health/deep | jq .

# 4) 验证 Prometheus 指标端点
curl -fsS http://localhost:8000/metrics | head -n 30

# 5) 生成回滚快照
./scripts/docker-deploy.sh checkpoint
./scripts/docker-deploy.sh rollback-list

# 6) 执行一次回滚演练（默认回滚到最新快照）
./scripts/docker-deploy.sh rollback --no-restart

# 7) 停止服务
./scripts/docker-deploy.sh stop
```

如需进入平台化 PoC（K8s 方向），建议最小追加：

```bash
# 示例：安装 Argo Rollouts（集群内）
kubectl create namespace argo-rollouts
kubectl apply -n argo-rollouts -f https://github.com/argoproj/argo-rollouts/releases/latest/download/install.yaml
```

---

## 参考链接汇总

- OpenTelemetry: https://opentelemetry.io/
- Prometheus: https://prometheus.io/
- Alertmanager: https://prometheus.io/docs/alerting/latest/alertmanager/
- Grafana: https://grafana.com/oss/grafana/
- Loki: https://grafana.com/oss/loki/
- Tempo: https://grafana.com/oss/tempo/
- Jaeger: https://www.jaegertracing.io/
- Argo Rollouts: https://argo-rollouts.readthedocs.io/
- Flagger: https://flagger.app/
- Kubernetes Probes: https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/
