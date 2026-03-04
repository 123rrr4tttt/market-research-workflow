# R8.1-C 可验收最小交付（Observability & Reliability）

## 范围
对应 reference pack 的 C 切片 Must 项，提供可审计基线清单。

## Must 基线

### 1) 三层指标体系：业务 SLI + RED + USE
- 业务 SLI：
  - `search_request_success_rate`
  - `search_p95_latency_ms`
- RED：
  - `http_requests_total`
  - `http_request_duration_seconds`
  - `http_5xx_total`
- USE：
  - `process_cpu_seconds_total`
  - `process_resident_memory_bytes`
  - `worker_queue_utilization`

### 2) Burn-rate 告警策略（快烧/慢烧）
- 快烧窗口：5m/1h，阈值 `burn_rate > 14`
- 慢烧窗口：30m/6h，阈值 `burn_rate > 6`
- 值班手册绑定：`main/backend/docs/implementation/R8_1_C_ACCEPTANCE.md`（本文件）

### 3) OTel 语义约定
- trace/span 字段使用 OpenTelemetry semantic conventions：
  - `http.method`
  - `http.route`
  - `http.status_code`
  - `net.peer.name`
  - `service.name`

## 验收命令
```bash
python3 scripts/verify_r8_1_c.py
```

预期：输出 `R8.1-C verification passed` 且退出码 0。
