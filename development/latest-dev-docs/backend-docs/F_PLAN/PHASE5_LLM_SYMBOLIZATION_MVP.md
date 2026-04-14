# Phase 5：LLM+符号化 最小可行方案设计

> 目标：新增站点入口 → 自动归类 → 推荐 handler/工具 → 生成配置；规则优先，LLM 仅在不规则不确定时调用；LLM 输出必须脚本校验后落地。

---

## 1. 设计原则

| 原则 | 实现 |
|------|------|
| 规则优先 | 先用 entry_type/path/domain 规则推断 channel_key、handler；规则能确定则绝不调 LLM |
| LLM 仅 fallback | 仅在规则无法确定（如未知 URL 模式、search_template 需推断）时调用 |
| 脚本校验落地 | LLM 输出经 validator 校验通过后才写入 DB/config；校验失败则回退到 url_pool 或人工 |
| 无新依赖 | 复用现有 `app/services/llm/`（get_chat_model、config_loader）；若无 key 则仅做骨架、跳过 LLM 分支 |

---

## 2. 规则层（Rule-First）

### 2.1 entry_type → channel_key 映射（确定性）

| entry_type | channel_key | 说明 |
|------------|-------------|------|
| `rss` | `generic_web.rss` | 直接映射 |
| `sitemap` | `generic_web.sitemap` | 直接映射 |
| `domain_root` | `url_pool` | 无检索能力，仅抓取 |
| `search_template` | `generic_web.search_template` | 需 template 字段 |
| `official_api` | `official_access.api` | 占位，后续扩展 |

### 2.2 URL 规则（用于 url_channel_routing 生成）

- `path_suffix` 含 `.xml`、`/feed`、`/rss` → rss
- `path_contains` 含 `sitemap` → sitemap
- `path_contains` 含 `search`、`q=`、`query=` → 可能 search_template（需 LLM 推断 template）
- 其他 → domain_root → url_pool

### 2.3 何时触发 LLM

- **entry_type 不确定**：脚本探测不到 sitemap/rss，URL 形态不匹配已知规则
- **search_template 推断**：需从站点首页/搜索页推断 `{{q}}`/`{{page}}` 模板 URL
- **符号/标签建议**（可选）：为 Item 层符号聚类提供候选 tag（低优先级 MVP）

---

## 3. LLM 输出与校验

### 3.1 LLM 输出结构（JSON）

```json
{
  "entry_type": "search_template",
  "channel_key": "generic_web.search_template",
  "template": "https://example.com/search?q={{q}}&page={{page}}",
  "symbol_suggestion": "example_site"
}
```

### 3.2 校验规则（Validator）

| 字段 | 校验 |
|------|------|
| `entry_type` | 必须在 `rss|sitemap|domain_root|search_template|official_api` 中 |
| `channel_key` | 必须在白名单：`generic_web.rss|sitemap|search_template`、`official_access.api`、`url_pool` |
| `template` | 若 entry_type=search_template：必须含 `{{q}}`；URL 可解析；domain 与 site_url 一致 |
| `symbol_suggestion` | 非空则需为合法标识符（字母数字下划线） |

校验失败 → 不落地，回退 `channel_key=url_pool` 或返回「需人工确认」。

---

## 4. 流程

```
site_entry (site_url, entry_type?, template?)
    → 规则分类：entry_type 已知 → 直接推荐 channel_key
    → 规则不确定：entry_type 未知 或 search_template 缺 template
        → 有 LLM key：调用 LLM，得到 JSON
        → 无 LLM key：回退 url_pool，不落地建议
    → Validator 校验 LLM 输出
    → 通过：写入 site_entry.extra.recommended_channel / 或生成 url_channel_routing 规则
    → 不通过：不写入，返回 fallback
```

---

## 5. 建议落点文件/模块

| 模块 | 路径 | 职责 |
|------|------|------|
| 规则分类 | `main/backend/app/services/resource_pool/auto_classify.py` | `classify_site_entry(site_url, entry_type?, template?) -> Recommendation`；规则优先，不确定时调 LLM |
| 校验器 | `main/backend/app/services/resource_pool/llm_validator.py` | `validate_llm_recommendation(raw: dict, site_url: str) -> ValidatedRecommendation | None` |
| LLM 调用 | 复用 `app/services/llm/provider.py`、`config_loader.py` | 新增 `llm_prompts/default.yaml` 中 `site_entry_classification` 配置（可选） |
| 配置生成 | `main/backend/app/services/ingest_config/service.py` | 已有 `upsert_config`；auto_classify 产出通过校验后，可调用以追加 `url_channel_routing.rules` |
| 发现集成 | `main/backend/app/services/resource_pool/site_entry_discovery.py` | 发现完成后，对 `entry_type=domain_root` 且无 sitemap/rss 的候选，可选调用 `classify_site_entry` 做二次推断 |
| API | `main/backend/app/api/resource_pool.py` | 新增 `POST /site_entries/recommend`：输入 site_url，返回 `{ channel_key, template?, validated }`，供前端「采纳建议」按钮 |

---

## 6. 骨架实现要点

1. **auto_classify.py**  
   - `_rule_classify(site_url, entry_type, template)`：纯规则，返回 `Recommendation | None`  
   - `_llm_classify(site_url, entry_type, template)`：仅在规则返回 None 时调用；无 key 则返回 `None`  
   - `classify_site_entry(...)`：先规则，再 LLM，再 validator

2. **llm_validator.py**  
   - 白名单常量 `ALLOWED_CHANNEL_KEYS`、`ALLOWED_ENTRY_TYPES`  
   - `validate_llm_recommendation(raw, site_url)`：校验并返回规范 dict 或 None

3. **无 LLM 时**  
   - `_llm_classify` 直接返回 `None`，不抛错  
   - `classify_site_entry` 回退 `channel_key=url_pool`，`entry_type=domain_root`

---

## 7. 验收标准（MVP）

- [x] 规则能确定的 site_entry 不调 LLM
- [x] 规则不确定时，有 key 则调 LLM；无 key 则回退 url_pool
- [x] LLM 输出经 validator 校验，不通过则不写入
- [x] 可通过 API 或 discovery 流程获得「推荐 channel_key / template」
- [x] 不引入新依赖

## 8. 实现状态（2026-02）

- `auto_classify.py`: `_llm_classify` 已实现，复用 `get_llm_config("site_entry_classification")`，无配置时用内置 prompt
- `POST /site_entries/recommend`: 支持 `use_llm` 参数
- Discovery: `run_auto_classify` + `use_llm` 可选
- 前端: 采纳建议按钮 + LLM 勾选；探测时可选启用 LLM
- 符号聚类: `GET /source_library/items/by_symbol`，items 按 tag 分组；前端「符号聚类」卡片
- 通道聚类: `GET /source_library/channels/grouped`，channels 按 provider 分组；前端「通道聚类」卡片
