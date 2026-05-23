# 来源库实测验证：write-through 与结构化链路并存现状（2026-03-14）

## 1. 目的

记录一轮基于真实来源项的运行验证，回答两个问题：

1. 当前来源库执行后，是否会发生真实入库
2. 这一轮真实入库的数据，是否已经经过统一结构化服务

本记录用于澄清当前过渡期状态，避免误判为：

1. `source_library` 已完全变成纯 fetch-only 边界
2. 或者相反，误判为来源库仍然完全主导写库与结构化

## 2. 验证方式

使用同步后端运行入口：

- `app.services.collect_runtime.run_source_library_item_compat(...)`

项目：

- `demo_proj`

验证来源项：

1. `news.general.regulation`
2. `market.general.baseline`

关键词与限制：

1. `news.general.regulation`
   - `keywords=["lottery regulation california"]`
   - `limit=10`
   - `max_items=10`
   - `max_candidates=10`
2. `market.general.baseline`
   - `keywords=["lottery market california"]`
   - `limit=10`
   - `max_items=10`
   - `max_candidates=10`

## 3. 实测结果

### 3.1 `news.general.regulation`

返回结果显示：

1. `result.inserted = 4`
2. `result.skipped = 6`
3. `result.single_write_workflow = "single_url"`

同时可在 `demo_proj.documents` 中观察到新增记录，示例：

1. `id=757` `https://people.com/`
2. `id=758` `https://www.nbclosangeles.com/`
3. `id=759` `https://nypost.com/ca/`
4. `id=760` `https://calmatters.org/`

### 3.2 `market.general.baseline`

返回结果显示：

1. `result.inserted = 0`
2. `result.skipped = 0`

本次未形成新写入。

### 3.3 外部依赖现象

运行期间观测到：

- `search_sources: ddg rate limited in site fallback, skipping`

说明本轮结果会受上游搜索源限流影响，不代表所有来源项稳定可复现。

## 4. 结构化状态核验

对本轮新增文档 `id=757..760` 检查 `Document.extracted_data`，观察到：

1. `schema_version = "terminal.ingest.v1.1"`
2. `structured_extraction_status = "ok"`
3. 存在 `extraction`
4. 存在 `domains`
5. 存在 `source_ref`
6. 存在 `source_mode`
7. 存在 `ingestion_entrypoint`
8. 存在 `policy`
9. 存在 `market`
10. 存在 `sentiment`
11. 存在 `entities_relations`
12. 存在 `company_structured / product_structured / operation_structured`

这说明：

1. 本轮真实写入的记录已经过统一结构化服务
2. 实际写入形态已是 `terminal.ingest.v1.1`
3. 不是旧式裸 `Document(...) + 零散 extracted_data` 形态

## 5. 当前架构现状判断

### 5.1 来源库对外主语义仍偏 clean terminal boundary

当前 `source_library` 适配层仍会输出：

1. `terminal_output`
2. `frontdoor_ingress`
3. `postprocess_frontdoor`
4. `legacy_result`

且该层的 `postprocess_frontdoor` 当前仍使用：

- `run_writer=False`

这意味着来源库对外边界设计上仍偏向：

1. clean terminal output
2. candidate/fetch result boundary

而不是把来源库重新定义为正式写库宿主。

### 5.2 但兼容写入链仍然可能真实下沉到 `single_url`

本轮 `news.general.regulation` 的返回结果同时显示：

- `single_write_workflow = "single_url"`

这说明当前仍存在一条兼容 write-through 路径：

`source_library item -> routed execution -> single_url write path`

因此，来源库在“对外边界语义”上已经 clean，但在“兼容运行现实”上，仍可能触发真实入库。

### 5.3 本轮真实入库的数据已经过统一结构化主干

由于本轮新增文档都带有：

1. `terminal.ingest.v1.1`
2. `structured_extraction_status = ok`
3. 完整 `policy/market/sentiment/entities_relations/...`

可以确认：

当前兼容写入链并不是绕开结构化服务裸写，而是已经下沉到：

`single_url ingress -> postprocess_frontdoor -> unified structured extraction -> normalizer -> compat -> writer`

## 6. 当前最关键的过渡期现象

本次验证最关键的事实是：

来源库 `terminal_output` 口径与 legacy 写入计数口径仍然并存。

具体表现为：

1. `terminal_output.results.stats` 可能仍为零值口径
2. 但 `legacy result.inserted/skipped` 已体现真实写入结果
3. 同时数据库里确实能看到新增 `Document`

这说明当前系统处于“边界已 clean、运行现实仍兼容 write-through”的过渡态，而不是单一模式。

## 7. 结论

一句话结论：

当前来源库表面上已按 clean terminal boundary 输出，但兼容运行链仍可能继续写入；而这条真实写入链已经接入统一结构化服务。

更精确地说：

1. `source_library` 本层并未重新成为 writer 宿主
2. 但某些来源项仍会下沉到 `single_url` 写入链
3. 这条写入链当前已产出 `terminal.ingest.v1.1` 结构化结果
4. 因此“来源库 clean boundary”与“兼容 write-through 仍存在”两件事同时成立

## 8. 后续建议

基于本轮验证，建议后续继续明确两件事：

1. 是否要保留这条兼容 write-through 路径
   - 若保留，应显式文档化，不再让它停留在“隐式兼容行为”
2. 如何统一 `terminal_output stats` 与真实写入计数
   - 至少要避免对外出现“terminal output 看起来没写入，但数据库实际新增了文档”的认知错位

## 9. 架构修正意见（2026-03-14）

基于本轮验证，后续统一标准化不建议再以 `single_url` 为标准宿主。

更合理的方向是：

1. 把 `single_url` 明确定义为历史遗留实现
2. 把历史中的质检逻辑抽象成“前门统一质检-清洗/发回/清理层”
3. 先在 `source_library terminal output` 后落地该层
4. 等来源库链跑通后，再决定如何回收 `single_url` 遗留逻辑

也就是说：

1. 本次实测证明 `single_url` 当前仍承载了一部分真实质检与写入能力
2. 但这不应继续成为目标架构
3. 目标架构应是“来源库先统一质检，再向后分发”，而不是“继续借道 single_url 完成质检”
