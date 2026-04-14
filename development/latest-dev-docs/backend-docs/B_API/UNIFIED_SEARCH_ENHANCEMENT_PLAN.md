# Unified Search 最小增强方案

> 基于 `/api/v1/resource_pool/unified-search` 已实现（rss/sitemap/search_template），提出下一步最小增强集合。

## 1. 建议实现顺序

| 顺序 | 增强项 | 理由 |
|------|--------|------|
| **1** | 候选 URL 过滤（同域、去 tracking、去无关站） | 投入小、收益高；直接提升结果质量，减少噪音；不依赖其他改动 |
| **2** | RSS/Atom 解析更稳健 | 当前 `ET.fromstring` + 简单 XPath 易受 namespace/CDATA 影响；影响面集中在 `_extract_urls_from_rss_xml` |
| **3** | sitemapindex 递归/分页 | 当前把 sitemapindex 的 `<sitemap><loc>` 当普通 URL 入库，导致大量无效候选；需区分 urlset vs sitemapindex 并递归抓取 |
| **4** | 写回 resource_pool_urls 的 source_ref 结构 | 依赖前 3 项稳定产出；增强可追溯性，便于后续去重/召回分析 |

---

## 2. 各增强项说明

### 2.1 候选 URL 过滤（同域、去 tracking、去无关站）

**现状**：`_filter_urls_by_terms` 仅做关键词匹配，无 domain/tracking/无关站过滤。

**改动点**：
- 在 `url_utils.py` 新增 `strip_tracking_params(url)`：移除 `utm_*`、`fbclid`、`gclid`、`ref` 等常见 tracking 参数
- 在 `unified_search.py` 新增 `_filter_candidate_urls(urls, entry_domain, allow_cross_domain)`：
  - 同域优先：`domain_from_url(u) == entry_domain` 或可配置允许跨域
  - 去 tracking：对 URL 做 `strip_tracking_params` 后再 `normalize_url` 去重
  - 去无关站：可选 deny_domains（如 `facebook.com`、`twitter.com`、`google.com`）或通过 ingest_config 配置

**风险**：
- 过度过滤：某些站点的有效链接带 tracking，strip 后可能重复；需在 strip 后做去重
- 同域过严：部分 RSS 聚合多站点，同域过滤会漏掉有效链接；建议默认「同域优先」+ 可配置放宽

**验收指标**：
- [ ] 带 `utm_source=xxx` 的 URL 入库前被 strip 为无 tracking 版本
- [ ] 同域模式下，仅保留与 site_entry 同 domain 的 URL
- [ ] deny_domains 配置生效时，对应 domain 的 URL 被排除

---

### 2.2 RSS/Atom 解析更稳健

**现状**：`_extract_urls_from_rss_xml` 使用 `root.findall(".//item/link")` 和 `.//{*}entry/{*}link`，对 namespace、CDATA、多 link 支持不足。

**改动点**：
- 使用 `defusedxml` 或 `lxml` 替代 `xml.etree`，避免 XXE/实体膨胀（若需安全加固）
- 统一 namespace 处理：`{http://www.w3.org/2005/Atom}` 等
- RSS：`item/link` 支持 text 与 CDATA；`item/guid` 若 `isPermaLink="true"` 可作备选
- Atom：`entry/link[@rel="alternate"]` 或 `@rel` 缺省时取 `@href`；支持 `link` 无 href 时用 `entry/id`（若为 URL）

**风险**：
- 部分 feed 格式非标准，过度兼容可能引入误解析；建议保留 fallback 到当前逻辑
- 大 feed 内存占用；可加 `max_items` 截断

**验收指标**：
- [ ] 含 CDATA 的 `<link><![CDATA[https://...]]></link>` 能正确提取
- [ ] Atom feed 的 `entry/link[@href]` 能正确提取
- [ ] 含 namespace 的 feed（如 `feed` 根元素带 `xmlns`）能解析
- [ ] 解析失败时 fallback 到原逻辑，不直接抛错导致整次搜索失败

---

### 2.3 sitemapindex 递归/分页

**现状**：`_extract_urls_from_sitemap_xml` 对所有 `loc` 一视同仁；sitemapindex 的 `loc` 指向子 sitemap，当前被当作普通 URL 入库。

**改动点**：
- 区分根元素：`{*}sitemapindex` vs `{*}urlset`
- 若为 sitemapindex：遍历 `sitemap/loc`，对每个 URL 递归 fetch + 解析，深度限制（如 `max_depth=2`）
- 若为 urlset：保持现有逻辑
- 分页：sitemapindex 可能很大，可加 `max_sitemaps` 限制单次递归抓取的 sitemap 数量

**风险**：
- 递归过深或 sitemap 过多导致超时/请求过多；必须设 `max_depth`、`max_sitemaps`
- 循环引用：A→B→A；需 `seen_urls` 防重
- 与 `max_candidates` 的配合：递归可能产出大量 URL，需在合并时遵守 `max_candidates` 截断

**验收指标**：
- [ ] 对 `sitemap_index.xml` 类 URL，能递归解析子 sitemap 并提取真实页面 URL
- [ ] 递归深度超过 `max_depth` 时停止
- [ ] 已访问的 sitemap URL 不重复 fetch
- [ ] 单次 unified_search 总耗时在 `probe_timeout * (1 + N)` 量级内可接受（N 为 sitemap 数量）

---

### 2.4 写回 resource_pool_urls 的 source_ref 结构

**现状**：`append_url` 时 `source_ref={"item_key": ..., "query_terms": [...]}`，缺少来源粒度信息。

**目标结构**（建议）：
```json
{
  "item_key": "xxx",
  "query_terms": ["a", "b"],
  "site_entry_url": "https://example.com/sitemap.xml",
  "entry_type": "sitemap",
  "domain": "example.com"
}
```

**改动点**：
- `unified_search_by_item` 在调用 `append_url` 时，传入扩展的 `source_ref`，包含 `site_entry_url`、`entry_type`、`domain`
- 若单 URL 来自多个 site_entry（去重后），可保留「首次命中」的 site_entry 信息，或合并为 `site_entries: [...]`

**风险**：
- `source` 字段长度 32，`source_ref` 为 JSONB 无长度限制；注意 `site_entry_url` 过长时不影响
- 历史数据无新字段，查询时需兼容空值

**验收指标**：
- [ ] `write_to_pool=true` 时，新写入的 `resource_pool_urls` 行其 `source_ref` 包含 `site_entry_url`、`entry_type`、`domain`
- [ ] 可通过 `source_ref->>'entry_type'` 等查询统计各来源贡献

---

## 3. 风险汇总

| 风险 | 缓解措施 |
|------|----------|
| 过滤过严导致漏召回 | 同域/deny 可配置，默认保守；提供 `allow_cross_domain` 开关 |
| RSS 解析兼容性 | 保留 fallback，解析失败不阻塞整次搜索 |
| sitemap 递归爆炸 | `max_depth=2`、`max_sitemaps=50`、`seen_urls` 防重 |
| 超时 | 每个 site_entry 独立 try/except，单点失败不影响其他；总耗时可加 `max_total_time` 软限制 |
| source_ref 结构变更 | 仅新增字段，不删旧字段；下游查询做空值兼容 |

---

## 4. 可验收指标（汇总）

1. **URL 过滤**：strip tracking、同域过滤、deny_domains 生效
2. **RSS/Atom**：CDATA、namespace、Atom link 正确解析；失败有 fallback
3. **sitemapindex**：递归解析子 sitemap，深度与数量受控，无重复 fetch
4. **source_ref**：写入包含 `site_entry_url`、`entry_type`、`domain` 的可追溯结构

---

## 5. 实现依赖关系

```
[URL 过滤] ─────────────────────────────────────────┐
     │                                               │
[RSS/Atom 解析] ────────────────────────────────────┼──► [unified_search 主流程]
     │                                               │
[sitemapindex 递归] ─────────────────────────────────┤
     │                                               │
     └──────────────────────────────────────────────┴──► [source_ref 写回]
```

- 1、2、3 可并行开发，均修改 `unified_search.py` 及 `url_utils.py`
- 4 依赖 1～3 稳定后，在 `append_url` 调用处扩展 `source_ref` 即可
