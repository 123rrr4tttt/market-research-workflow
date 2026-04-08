# 内置写作工作台设计方案（Markdown / 预览 / 资料卡 / 模板 / LLM）

> 日期：2026-03-07
> 范围：`main/frontend-modern`、`main/backend/app/api/*`
> 状态：设计方案，默认不直接改业务代码

## 1. 目标

为现有平台增加一个内置写作工作台，核心能力只做五件事：

1. 支持 Markdown 文档编辑。
2. 支持 Markdown 实时预览。
3. 在编辑区划词或选中关键词后，侧边栏自动调出相关资料文档卡片。
4. 支持多种报告模板快速起稿。
5. 支持 LLM 对话、改写、续写、摘要、引用整理等写作辅助。

这个能力应当是现有资源库、文档库、LLM 配置、图模板体系之上的增量工作台，而不是另起一套孤立系统。

## 2. 当前基线

仓库里已经有可复用基础：

- 前端壳层与导航：`main/frontend-modern/src/app/shell/AppShell.tsx`
- 侧边导航与 hash 路由：`main/frontend-modern/src/components/FigmaSideNav.tsx`、`main/frontend-modern/src/app/navigation/index.ts`
- 文档管理与搜索：`main/frontend-modern/src/pages/OpsPage.tsx`、`main/frontend-modern/src/lib/api/domains/project-admin.ts`
- 资源库与资料池：`main/frontend-modern/src/pages/ResourcePage.tsx`
- LLM 配置：`main/frontend-modern/src/pages/SettingsPage.tsx`
- 报告生成与质量门禁：`main/backend/app/api/llm_report.py`、`main/backend/app/services/llm_report_generator.py`
- 自动补来源：`main/backend/app/services/llm_report_source_enrichment.py`

当前缺口也很明确：

- 没有 Markdown 编辑器。
- 没有 Markdown 预览渲染链。
- 没有“划词 -> 资料卡检索”联动事件链。
- 没有面向写作场景的模板实体。
- 现有 `llm-report` 更像生成器接口，不是完整写作工作台。
- 仓库当前没有 `main/backend/app/api/writing.py`，也没有 `main/backend/app/services/writing/` 领域服务目录。
- 现有 `admin` 路由更偏读取/管理与 `extracted_data` 修改，不足以承接写作页的草稿、版本、引用、审计和交互型检索。

## 3. 推荐产品形态

建议新增一个一级页面：`写作工作台`。

页面采用三栏布局：

- 左栏：文档与模板区
  - 文档树
  - 最近打开
  - 模板库
  - 文档元数据（项目、标签、状态、更新时间）
- 中栏：编辑 / 预览双栏主工作区
  - `Write`：Markdown 编辑
  - `Preview`：渲染预览
  - `Split`：左右分栏
- 右栏：智能侧边栏
  - 划词资料卡
  - 引用素材篮
  - LLM 助手
  - 模板变量面板

主交互流：

1. 用户选择模板或空白文档。
2. 在中栏写 Markdown。
3. 划词或选中一段文本。
4. 右栏自动请求相关资料卡。
5. 用户将资料卡插入为引用、摘要、脚注或待办素材。
6. 用户触发 LLM 操作，按模板或选区生成内容。
7. 最终导出 Markdown 或保存在平台内。

### 3.1 UI 优化与复用原则

这一条是强约束，不是建议：

- UI 优化必须优先参考现有成熟实现，不允许从空白状态手搓整套核心交互。
- 可以自定义视觉风格，但交互骨架、面板组织、hover/preview、模板选择、右侧 AI 助手等能力应先从本地 OSS 参考池借鉴。
- 简洁、便利、低学习成本是第一优先级，高于“做一个看起来更新奇”的界面。

MVP 的 UI 复用优先级：

1. `reference-pool/oss/outline`
   - 参考知识库壳层、左侧栏、hover preview、模板入口。
2. `reference-pool/oss/silverbullet`
   - 参考 Markdown live preview、编辑与预览的衔接方式。
3. `reference-pool/oss/silverbullet-ai`
   - 参考右侧 AI 面板、prompt 动作、聊天面板结构。
4. `reference-pool/oss/logseq`
   - 参考搜索入口、关联资料组织、模板搜索与插入交互。
5. `reference-pool/oss/codemirror-view`
   - 参考 tooltip、panel、selection 状态与编辑器内部交互。

对应的本地优先复用入口：

- 左栏文档/模板壳层：
  - `reference-pool/oss/outline/app/components/Sidebar`
  - `reference-pool/oss/outline/app/components/Template`
  - `reference-pool/oss/outline/app/components/TemplatizeDialog`
- Hover 与资料卡预览：
  - `reference-pool/oss/outline/app/components/HoverPreview`
  - `reference-pool/oss/codemirror-view/src/tooltip.ts`
  - `reference-pool/oss/codemirror-view/src/panel.ts`
- 中栏编辑/预览体验：
  - `reference-pool/oss/silverbullet/client/codemirror`
  - `reference-pool/oss/silverbullet/client/markdown_renderer`
  - `reference-pool/oss/silverbullet/client/markdown_parser`
- 右栏 AI 助手：
  - `reference-pool/oss/silverbullet-ai/src/chat-panel.ts`
  - `reference-pool/oss/silverbullet-ai/assets/chat-panel.html`
  - `reference-pool/oss/silverbullet-ai/src/prompts.ts`
- 搜索 / 关联资料：
  - `reference-pool/oss/logseq/src/main/frontend/search`
  - `reference-pool/oss/logseq/src/main/frontend/commands.cljs`
  - `reference-pool/oss/logseq/src/main/frontend/handler/route.cljs`

MVP 要强制满足的 UI 目标：

- 新用户 30 秒内能看懂三栏分工。
- 不需要二级弹窗就能完成“选词 -> 看资料 -> 插引用 -> 继续写”。
- 键盘优先，鼠标补充，不做必须依赖 hover 才看得到的主流程。
- 侧边栏、预览、AI 面板都要支持空状态、加载态、失败态，且反馈明确。
- 模板切换、引用插入、LLM 动作都必须是可撤销的。
- 右栏卡片信息密度高，但操作按钮少而明确，避免一张卡片塞过多功能。

## 4. 技术选型建议

### 4.1 编辑器

推荐主方案：`CodeMirror 6`。

原因：

- 需求是 Markdown-first，不是富文本-first。
- 现阶段只要求 md 编辑与预览，CodeMirror 的复杂度和接入成本低于富文本编辑器。
- 选词、hover、tooltip、panel 等扩展能力成熟，适合做“关键词资料卡”。
- 现有前端未引入编辑器框架，先上轻量文本编辑器更稳。

不推荐当前阶段直接选 `Tiptap Markdown` 作为主编辑器，原因是其官方 Markdown 扩展当前仍标注为 early release / beta，适合后续需要富文本块能力时再评估。

### 4.2 预览渲染

推荐：

- `react-markdown`
- `remark-gfm`
- `rehype-sanitize`

策略：

- 默认不启用原始 HTML 渲染。
- 如果后续确实要支持模板内嵌 HTML，再走 `rehype-sanitize` 白名单。

### 4.3 模板

模板实体采用两层结构：

- `template_manifest.json`
  - 模板元信息、变量定义、适用报告类型、默认 LLM preset
- `template.md`
  - Markdown 主体，支持占位变量

变量风格建议：

```md
---
template_key: market-weekly
title: 市场周报
variables:
  subject: text
  date_range: text
  audience: dropdown(exec, analyst, public)
---

# {{subject}} 周报

## 执行摘要

## 关键变化

## 风险

## 建议
```

### 4.4 LLM 交互

LLM 不应直接接管整页写作，而是做四类动作：

- `outline_generate`：基于模板生成提纲
- `section_expand`：扩写当前章节
- `selection_rewrite`：改写选区
- `evidence_summary`：把资料卡压缩为可引用摘要

所有 LLM 操作都必须显式返回：

- `content`
- `sources`
- `mode`
- `warnings`
- `trace_id`

### 4.5 本地 OSS 参考池

为避免重复造轮子，已经把可直接复用的开源仓库拉到本地：

- 编辑器与 Markdown：
  - `reference-pool/oss/tiptap`
  - `reference-pool/oss/codemirror-view`
  - `reference-pool/oss/codemirror-lang-markdown`
- 知识库 / 侧边栏 / 卡片：
  - `reference-pool/oss/outline`
  - `reference-pool/oss/logseq`
  - `reference-pool/oss/silverbullet`
- AI 侧栏 / Prompt / Embeddings：
  - `reference-pool/oss/silverbullet-ai`
  - `reference-pool/oss/dify`
  - `reference-pool/oss/langflow`

索引总入口：

- `reference-pool/oss/INDEX.md`

建议按“代码块级复用”而不是“整仓迁移”来使用这些仓库，避免引入不一致的技术栈和过重依赖。

### 4.6 本地参考实现调查结论

下面是已经确认过的本地代码位置，以及它们对应的可复用思路：

- `reference-pool/oss/outline/app/components/Sidebar/Sidebar.tsx`
  - 已确认这里实现了可折叠、可 resize、带 hover 行为的知识库侧栏壳层。
  - 可直接借鉴到写作工作台左栏，不必自己从零做文档树外壳和宽度拖拽。
- `reference-pool/oss/outline/app/components/Sidebar/components/DocumentLink.tsx`
  - 可借鉴文档入口行、激活态、层级行项目组织。
- `reference-pool/oss/outline/app/components/Sidebar/components/CollectionLink.tsx`
  - 可借鉴模板分组或文档分组的导航方式。
- `reference-pool/oss/outline/app/components/HoverPreview/HoverPreview.tsx`
  - 已确认这里实现了 hover 延迟关闭、portal 渲染、点击外部关闭、Escape 关闭、滚动关闭。
  - 这正是“选词后资料卡预览”最值得直接抄的骨架。
- `reference-pool/oss/silverbullet/client/markdown_parser/parser.ts`
  - 可借鉴 Markdown 解析入口和结构化节点生成方式。
- `reference-pool/oss/silverbullet/client/markdown_renderer/markdown_render.ts`
  - 可借鉴 live preview 的 Markdown 渲染主路径。
- `reference-pool/oss/silverbullet/client/markdown_renderer/html_render.ts`
  - 可借鉴 HTML 渲染边界和最终输出层。
- `reference-pool/oss/silverbullet/client/codemirror/editor_state.ts`
  - 可借鉴编辑器状态组织方式。
- `reference-pool/oss/silverbullet/client/codemirror/top_bottom_panels.ts`
  - 可借鉴编辑器上下 panel 布局方式，适合映射状态条、插入提示、检索反馈。
- `reference-pool/oss/silverbullet/client/codemirror/wiki_link.ts`
  - 可借鉴文内引用、内部链接、引用跳转行为。
- `reference-pool/oss/silverbullet-ai/src/chat-panel.ts`
  - 已确认这里直接调用 `editor.showPanel(\"rhs\", ...)` 打开右侧 AI 助手面板，并管理面板状态与聊天上下文。
  - 这比自己手搓右侧 AI 助手容器更稳。
- `reference-pool/oss/silverbullet-ai/assets/chat-panel.html`
  - 可借鉴右侧 AI 面板的结构骨架。
- `reference-pool/oss/silverbullet-ai/src/prompts.ts`
  - 可借鉴 prompt template 的注册、发现和执行方式。
- `reference-pool/oss/silverbullet-ai/src/embeddings.ts`
  - 已确认这里有 query cache、embedding search、chat 搜索上下文拼接逻辑。
  - 可借鉴到“关键词 -> 相关资料”的结果缓存和摘要补全。
- `reference-pool/oss/logseq/src/main/frontend/search/browser.cljs`
  - 可借鉴搜索结果页与搜索结果组织。
- `reference-pool/oss/logseq/src/main/frontend/search/protocol.cljs`
  - 可借鉴搜索模块接口边界。
- `reference-pool/oss/logseq/src/main/frontend/commands.cljs`
  - 已确认这里包含 `search-page`、`search-block`、`search-template` 等命令入口。
  - 可借鉴模板搜索、资料插入、命令面板的统一触发方式。
- `reference-pool/oss/logseq/src/main/frontend/handler/route.cljs`
  - 可借鉴从路由切换到搜索态的组织方式。
- `reference-pool/oss/logseq/src/resources/templates/contents.md`
  - 可借鉴模板内容文件的组织约定。
- `reference-pool/oss/codemirror-view/src/tooltip.ts`
  - 已确认这里包含 tooltip manager、measure、定位和容器管理。
  - 可直接借鉴“选词后就地提示层”的基础逻辑。
- `reference-pool/oss/codemirror-view/src/panel.ts`
  - 可借鉴编辑器内 panel 机制。
- `reference-pool/oss/codemirror-lang-markdown/src/markdown.ts`
  - 可借鉴 Markdown 语言扩展本身。
- `reference-pool/oss/codemirror-lang-markdown/src/commands.ts`
  - 可借鉴标题/列表/块命令的现成实现。

对应的直接落地建议：

- 左栏交互先看 `outline`，不要自己设计文档树壳层。
- 中栏编辑/预览先看 `silverbullet + codemirror`，不要自己重造编辑器-预览联动。
- 右栏 AI 与资料交互先看 `silverbullet-ai + outline hover preview`，不要从空白弹层开始拼。
- 搜索与模板命令先看 `logseq commands/search`，不要自己额外发明命令体系。

## 5. 关键词资料卡设计

### 5.1 触发方式

优先级如下：

1. 选中文本后停顿 250ms 自动触发。
2. 右键菜单触发“查资料”。
3. 快捷键触发，比如 `Cmd/Ctrl + Shift + K`。

### 5.2 查询策略

后端先做轻量 query rewrite，再并发查三类来源：

- 平台文档库：`admin documents`
- 资源池 / 资料池：`resource_pool`
- 已有图谱或抽取摘要：`graph node / extracted_data`

返回统一卡片结构：

```json
{
  "id": "doc-1288",
  "title": "California Sales Report",
  "source_type": "document",
  "snippet": "Revenue grew 8.2% in Q4...",
  "uri": "https://...",
  "score": 0.84,
  "tags": ["market", "report"],
  "published_at": "2026-02-18T00:00:00Z",
  "actions": ["insert_quote", "insert_summary", "pin", "open_detail"]
}
```

### 5.3 侧边栏分区

- `相关资料`
- `已加入引用`
- `同义词/扩展词`
- `LLM 建议问题`

### 5.4 交互规则

- 选区长度 `< 2` 字符时不触发。
- 连续相同选词 10 秒内不重复请求。
- 右栏请求必须取消过期请求，避免卡片闪烁。
- 卡片插入文档时必须保留来源链接。

## 6. 页面与模块拆分

建议新增模块：

- `src/pages/WritingWorkbenchPage.tsx`
- `src/components/writing/WritingShell.tsx`
- `src/components/writing/MarkdownEditor.tsx`
- `src/components/writing/MarkdownPreview.tsx`
- `src/components/writing/KeywordInsightSidebar.tsx`
- `src/components/writing/TemplateLibraryPanel.tsx`
- `src/components/writing/LlmAssistantPanel.tsx`
- `src/components/writing/CitationBasket.tsx`
- `src/lib/api/domains/writing.ts`
- `src/lib/writing/*`

现有改动点：

- `src/components/FigmaSideNav.tsx`：新增“写作工作台”入口
- `src/app/navigation/index.ts`：新增 `NavMode`
- `src/app/shell/AppShell.tsx`：挂载新页面
- `src/lib/queryKeys.ts`：新增 writing query keys
- `src/lib/api/endpoints.ts`：新增 writing endpoints

## 7. 后端接口建议

推荐新增 `api/v1/writing/*`，不要把写作页面直接耦合到 `admin` 或 `llm-report` 原始接口。

最小接口集合：

- `GET /api/v1/writing/documents`
- `POST /api/v1/writing/documents`
- `GET /api/v1/writing/documents/{doc_id}`
- `PATCH /api/v1/writing/documents/{doc_id}`
- `POST /api/v1/writing/documents/{doc_id}/draft`
- `POST /api/v1/writing/documents/{doc_id}/citations`
- `GET /api/v1/writing/documents/{doc_id}/citations`
- `GET /api/v1/writing/templates`
- `POST /api/v1/writing/templates/validate`
- `POST /api/v1/writing/keyword-cards`
- `POST /api/v1/writing/keyword-cards/preview`
- `GET /api/v1/writing/cards/{card_id}`
- `GET /api/v1/writing/suggest`
- `POST /api/v1/writing/llm-actions`
- `GET /api/v1/writing/llm-actions/history`
- `POST /api/v1/writing/export/markdown`

其中：

- `keyword-cards` 是一个面向前端右栏的聚合接口，后端统一调文档库、资源池、图谱，不把三套查询逻辑暴露给前端。
- `keyword-cards/preview` 用于 hover 场景下的轻量预取，避免每次悬停都拉完整卡片。
- `cards/{card_id}` 用于右栏资料卡详情、来源可信度、去重快照与溯源信息展示。
- `suggest` 用于命令面板、模板搜索、关键词联想和 related-material typeahead。
- `templates/validate` 负责服务端变量解析、默认值回填、类型/必填检查，不把模板校验仅留在前端。
- `documents/{doc_id}/draft` 用于自动保存草稿、增量保存和版本冲突检测。
- `documents/{doc_id}/citations` 用于引用实体持久化、恢复和导出前重建。
- `llm-actions` 是对现有 `llm-report` 和后续 prompt chain 的包装层，负责模式分发、审计和引用回填。
- `llm-actions/history` 用于审计读取、trace 回放、来源版本查看和失败原因展示。

仍然复用现有能力：

- `llm_report_source_enrichment`
- `llm_report_generator`
- `admin document list/detail`
- `resource_pool` 与 `source_library`

### 7.1 按交互反推的后端缺失

根据当前交互设计，下面这些后端能力不能缺，否则前端会被迫手工兜底：

- Hover Preview 预取与详情接口
  - 否则“选词后快速预览”只能靠一次性拉完整卡片，交互会抖且浪费请求。
- 资料卡来源可信度与去重快照
  - 否则用户无法判断两张相似卡片是否来自同一来源链，也不利于调试召回质量。
- 引用实体持久化与恢复
  - 否则引用仅停留在前端状态，刷新、导出、回放和审计都会失真。
- 模板变量服务端校验
  - 否则模板切换和 LLM 动作只靠前端校验，容易出现“本地通过、服务端执行失败”。
- 草稿自动保存与版本冲突协议
  - 至少需要 `version/etag/if-match/conflict_code` 这一组语义。
- LLM 动作审计读接口
  - 不仅要写 trace，还要能回查 action history、来源版本、失败原因。
- suggest / typeahead 接口
  - 否则模板搜索、关键词联想、命令面板、相关资料发现都只能退化成一次性搜索。

建议的后端落点：

- `main/backend/app/api/writing.py`
- `main/backend/app/services/writing/document_service.py`
- `main/backend/app/services/writing/keyword_card_service.py`
- `main/backend/app/services/writing/llm_action_service.py`
- `main/backend/app/services/writing/template_service.py`
- `main/backend/app/services/writing/citation_service.py`
- 如需版本快照与引用持久化：`main/backend/app/models/entities.py` + 对应 migration

### 7.2 按交互拆分的后端职责矩阵

不要只按“接口名”拆后端，更要按前端交互链路拆职责：

- 文档打开 / 新建 / 保存 / 自动保存
  - 主落点：`main/backend/app/services/writing/document_service.py`
  - 关键职责：文档头信息、正文 Markdown、草稿 checkpoint、`version/etag/if-match`、冲突回包。
  - 备注：不要直接复用 ingestion 语义下的 `documents` 作为用户写作文档唯一模型，避免“资料源文档”和“用户产出文档”混语义。
- 选词后相关资料聚合
  - 主落点：`main/backend/app/services/writing/keyword_card_service.py`
  - 关键职责：query rewrite、三路召回、统一卡片映射、来源打分、去重快照、轻量预取。
  - 优先复用：
    - `main/backend/app/services/search/hybrid.py`
    - `main/backend/app/services/resource_pool/unified_search.py`
    - `main/backend/app/services/llm_report_source_enrichment.py`
- Hover Preview / 卡片详情 / 来源溯源
  - 主落点：`main/backend/app/services/writing/keyword_card_service.py`
  - 关键职责：`preview` 返回轻载荷，`detail` 返回完整来源、可信度、去重链、命中原因、关联引用状态。
  - 协议要求：同一 `card_id` 必须能稳定回放，不允许 hover 一次一个结构。
- suggest / typeahead / 模板搜索 / 命令面板补全
  - 主落点：`main/backend/app/services/writing/search_suggest_service.py`
  - 关键职责：关键词联想、模板关键字补全、资料搜索补全、命令面板统一候选。
  - 优先复用：
    - `main/backend/app/api/search.py`
    - `main/backend/app/services/search/hybrid.py`
    - `main/backend/app/services/source_library/resolver.py`
- 模板加载 / 变量回填 / 服务端校验
  - 主落点：`main/backend/app/services/writing/template_service.py`
  - 关键职责：模板元数据、变量 schema、默认值、类型校验、缺失变量提示、模板快照版本。
  - 备注：模板不是单纯 Markdown 文件，服务端要能感知变量语义和模板版本。
- LLM 动作网关
  - 主落点：`main/backend/app/services/writing/llm_action_service.py`
  - 关键职责：动作分发、前置校验、来源注入、失败不覆盖原文、同步/异步模式、trace/audit。
  - 优先复用：
    - `main/backend/app/api/llm_report.py`
    - `main/backend/app/services/llm_report_generator.py`
    - `main/backend/app/services/job_logger.py`
- 引用持久化 / 导出重建
  - 主落点：`main/backend/app/services/writing/citation_service.py`
  - 关键职责：引用实体存储、正文锚点映射、引用恢复、导出前引用重组、失效来源标记。

### 7.3 需要补齐的数据对象与状态字段

若按当前交互做成可恢复、可审计、可导出，至少要补齐下面这些对象或等价存储：

- `writing_documents`
  - 字段建议：`id`, `project_key`, `title`, `body_md`, `status`, `head_version`, `etag`, `created_by`, `updated_by`, `updated_at`
  - 用途：用户写作产物主表，不要和采集/入库文档混在一张语义表里。
- `writing_document_drafts`
  - 字段建议：`doc_id`, `draft_body_md`, `selection_snapshot`, `autosave_token`, `base_version`, `saved_at`
  - 用途：自动保存与正式保存解耦，支撑“脏态恢复”和“版本冲突提示”。
- `writing_citations`
  - 字段建议：`id`, `doc_id`, `card_id`, `source_uri`, `source_title`, `snippet`, `anchor_text`, `insert_range`, `source_snapshot_json`
  - 用途：右栏引用篮、正文引用块、导出链路共享一份标准化引用实体。
- `writing_template_snapshots`
  - 字段建议：`template_key`, `template_version`, `manifest_json`, `body_md`, `project_key`
  - 用途：模板切换、模板变量校验、历史回放时保持版本稳定。
- `writing_llm_action_logs`
  - 字段建议：`trace_id`, `doc_id`, `project_key`, `action_type`, `selection_text`, `input_snapshot_json`, `output_snapshot_json`, `status`, `error_code`, `created_at`
  - 用途：动作历史、失败定位、来源回放。
  - MVP 也可以优先复用 `main/backend/app/services/job_logger.py` 对应的 `EtlJobRun`，但对外仍要包装成写作域读模型。
- `writing_keyword_cache`
  - 字段建议：`project_key`, `selection_hash`, `normalized_query`, `preview_payload_json`, `detail_payload_json`, `ttl_expires_at`
  - 用途：10 秒去重窗口、hover 预取、右栏详情复用。
  - 备注：这张表可以先用 Redis 或内存缓存替代，不要求一开始就落库。

### 7.4 交互敏感能力的协议细节

为了让前端交互真正稳定，后端还要明确下面这些协议语义：

- 自动保存幂等性
  - `draft` 写接口应接受 `autosave_token` 或 `idempotency_key`，避免网络抖动导致重复写。
- 版本冲突语义
  - `PATCH /documents/{doc_id}` 与 `POST /documents/{doc_id}/draft` 都应支持 `version` 或 `If-Match`。
  - 冲突时返回当前 head 版本、最近保存人、最近保存时间、可选 diff 摘要。
- 选词请求去重
  - 后端应接受 `selection_hash` / `request_id`，便于前后端共同识别重复请求和过期请求。
- Preview / Detail 分层
  - `preview` 只返回标题、snippet、score、轻量来源标识。
  - `detail` 再返回 full snippet、provenance、dedupe trace、可信度解释、相关引用状态。
- LLM 动作执行模式
  - 短动作如 `selection_rewrite` 可同步返回。
  - 长动作如 `outline_generate`、大段 `section_expand` 应预留异步模式，至少返回 `job_id/trace_id/status`。
- 审计与可观测性
  - 所有写作域接口都应把 `trace_id/project_key` 放进 `meta`。
  - 关键词召回还应回传 `search_backends_used/source_count/dedupe_count` 之类的调试字段。

### 7.5 优先复用的现有后端实现

后端也不要手搓一套新基建，优先借现有仓库里的这些入口：

- API envelope 与 `meta`
  - `main/backend/app/contracts/responses.py`
  - `main/backend/app/contracts/api.py`
- 路由注册方式
  - `main/backend/app/api/__init__.py`
- 搜索统一入口与 fallback 约定
  - `main/backend/app/api/search.py`
  - `main/backend/app/services/search/hybrid.py`
- 来源补强与标准化 source payload
  - `main/backend/app/services/llm_report_source_enrichment.py`
- 资源池统一搜索与 URL 归一化
  - `main/backend/app/services/resource_pool/unified_search.py`
- 项目级 source library 执行入口
  - `main/backend/app/services/source_library/resolver.py`
- LLM 动作 job 记录与 trace 复用
  - `main/backend/app/services/job_logger.py`
- 现有 LLM 报告接口骨架
  - `main/backend/app/api/llm_report.py`
  - `main/backend/app/services/llm_report_generator.py`

建议做法不是“重写这些模块”，而是新建 `writing` 域服务时把它们包成更适合交互页的 façade。

### 7.6 实现前后端清单（可直接分派给子 Agent）

下面这组清单不是泛化建议，而是已经按当前仓库结构收紧过的一版“实现前输入”。

但它只能作为入口，不能替代子 Agent 自己爬库：

- 子 Agent 不能只根据本节直接开写代码。
- 每个后端子 Agent 在开始实现前，仍然必须自己：
  - 打开本节映射到的 repo 文件逐个阅读；
  - 用 `rg` 再检索一次相关关键词、错误码、版本语义、project 绑定语义；
  - 确认主文档中的建议没有和仓库现状漂移。
- 如果子 Agent 实际读到的仓库实现与本节不一致，应以仓库现状为准，并把偏差回写到任务 notes 或实施记录里，而不是硬套这里的清单。

#### 7.6.1 A12：Contract / Route Group 清单

统一约定：

- 路由前缀继续使用本方案既定的 `api/v1/writing/*`，不要另外再起一套 `writing-workbench/*` 命名。
- 所有响应统一走 `main/backend/app/contracts/responses.py` 的 `ok/fail` envelope。
- 所有 `meta` 至少带：
  - `trace_id`
  - `project_key`
  - `request_id`
  - `deprecated` 可选

建议首批 request / response schema：

- `KeywordCardRequest`
  - `project_key: str`
  - `query: str`
  - `selection_hash: str | None`
  - `request_id: str | None`
  - `limit: int = 10`
  - `sources: list[str] | None`
  - `timeout_ms: int | None`
- `KeywordCardItem`
  - `card_id: str`
  - `source_type: "document" | "resource" | "graph"`
  - `title: str`
  - `snippet: str`
  - `url: str | None`
  - `score: float`
  - `publisher: str | None`
  - `published_at: str | None`
  - `evidence: str | None`
  - `relevance_tags: list[str]`
  - `credibility: float | None`
- `KeywordCardListResponse`
  - `cards: list[KeywordCardItem]`
  - `selection_hash: str`
  - `suggested_queries: list[str]`
  - `search_backends_used: list[str]`
  - `source_count: dict[str, int]`
  - `dedupe_count: int`
  - `score_snapshot: dict`
  - `cache_hit: bool`
  - `cache_ttl_ms: int | None`
- `KeywordCardPreviewRequest`
  - `project_key: str`
  - `card_id: str`
  - `query: str | None`
  - `trace_id: str | None`
- `KeywordCardPreviewResponse`
  - `card_id`
  - `title`
  - `url`
  - `publisher`
  - `snippet`
  - `score`
  - `source_type`
  - `quick_actions: list[str]`
- `KeywordCardDetailResponse`
  - `card_id`
  - `title`
  - `url`
  - `score`
  - `evidence`
  - `publisher`
  - `published_at`
  - `retrieved_at`
  - `normalized_query`
  - `dedupe_trace: list[dict]`
  - `provenance: dict`
  - `selection_matches: dict`
- `SuggestRequest`
  - `project_key: str`
  - `query: str`
  - `mode: "keyword" | "template" | "material" | "command"`
  - `limit: int = 20`
  - `request_id: str | None`
- `SuggestItem`
  - `kind: "template" | "keyword" | "material" | "command"`
  - `id: str`
  - `label: str`
  - `snippet: str | None`
  - `score: float | None`
  - `extra: dict`

建议保留的错误码与细分 `details`：

- 主错误码继续复用：
  - `INVALID_INPUT`
  - `PROJECT_KEY_REQUIRED`
  - `NOT_FOUND`
  - `CONFIG_ERROR`
  - `UPSTREAM_ERROR`
  - `INTERNAL_ERROR`
- 写作域细分错误放到 `details`：
  - `conflict_code`
  - `selection_hash_invalid`
  - `request_timeout`
  - `template_variable_missing`
  - `cross_project_denied`

建议文件落点：

- `main/backend/app/api/writing.py`
- `main/backend/app/contracts/schemas/writing.py` 或同级等价 schema 文件
- `main/backend/app/api/__init__.py`

#### 7.6.2 A13：Keyword Aggregation / Preview / Suggest 清单

建议的 service façade：

- `aggregate_cards(payload)`
- `get_card_preview(payload)`
- `get_card_detail(payload)`
- `suggest(payload)`
- `normalize_and_rewrite_query(text)`
- `dedupe_and_score(cards, query, project_key)`

建议的内部调用顺序：

1. 规范化 `query`，生成 `selection_hash`。
2. 先查短期缓存：
   - key 建议：`project_key + selection_hash + mode`
3. 并行召回三类来源：
   - 文档检索：`main/backend/app/services/search/hybrid.py`
   - 资源池与候选 URL：`main/backend/app/services/resource_pool/unified_search.py`
   - 来源补强 / RAG / graph 兜底：`main/backend/app/services/llm_report_source_enrichment.py`
4. 使用统一映射器转换成 `KeywordCardItem`。
5. 按 `url + title + normalized_query` 去重。
6. 生成：
   - `preview payload`
   - `detail payload`
   - `score_snapshot`
   - `source_count`
   - `search_backends_used`

关键协议要求：

- `preview` 只返回轻载荷，不返回完整 provenance。
- `detail` 再返回：
  - `dedupe_trace`
  - `provenance`
  - `selection_matches`
  - `credibility`
- `selection_hash` 的 canonicalization 必须与前端一致，否则 10 秒去重无效。
- 长尾来源查询必须有超时、降级与 `cache_hit/cache_ttl_ms` 标记。

建议文件落点：

- `main/backend/app/services/writing/keyword_card_service.py`
- `main/backend/app/services/writing/search_suggest_service.py`
- `main/backend/app/services/writing/keyword_cache.py` 或等价缓存层

#### 7.6.3 A14：Draft / Citation / Conflict 清单

结论先写明：

- 不要直接复用 `main/backend/app/models/entities.py` 里的 `Document` 作为用户写作文档主表。
- `Document` 更偏采集与来源文档语义，缺少写作域所需的版本、autosave、citation 锚点与恢复结构。

建议新增或等价存储的表：

- `writing_documents`
  - `id`
  - `project_key`
  - `title`
  - `body_md`
  - `status`
  - `head_version`
  - `etag`
  - `updated_by_user_id`
  - `updated_at`
  - `created_at`
  - `deleted_at`
  - `metadata_json`
- `writing_document_drafts`
  - `id`
  - `doc_id`
  - `project_key`
  - `draft_body_md`
  - `selection_snapshot`
  - `base_version`
  - `autosave_token`
  - `request_id`
  - `created_at`
  - `updated_at`
- `writing_document_citations`
  - `id`
  - `doc_id`
  - `project_key`
  - `source_doc_id`
  - `source_uri`
  - `source_title`
  - `quote_text`
  - `position_anchor`
  - `card_id`
  - `metadata_json`
  - `created_at`
  - `updated_at`
- `writing_document_events` 可选
  - `id`
  - `doc_id`
  - `project_key`
  - `event_type`
  - `payload_json`
  - `actor_user_id`
  - `created_at`

建议 service 方法：

- `create_document`
- `get_document`
- `save_document_with_conflict`
- `save_draft_autosave`
- `publish_document`
- `resolve_conflict_payload`
- `upsert_citations`
- `list_citations`
- `rebuild_markdown_with_citations`

建议冲突协议：

- 读接口返回：
  - `version`
  - `etag`
- 写接口接受：
  - `If-Match`
  - 或 `base_version`
- 冲突时返回 `409`，并在 `details` 里带：
  - `conflict_code: "VERSION_CONFLICT"`
  - `expected_version`
  - `current_version`
  - `server_snapshot`
  - `updated_by_user_id`
  - `updated_at`
- `draft` 自动保存还应接受：
  - `autosave_token`
  - `request_id`

建议文件落点：

- `main/backend/app/services/writing/document_service.py`
- `main/backend/app/services/writing/citation_service.py`
- `main/backend/app/models/entities.py` 或独立 `writing_entities.py`
- 对应 migration

#### 7.6.4 A15：Template Validate / LLM Gateway / Audit 清单

统一原则：

- 优先复用 `main/backend/app/api/llm_report.py` 和 `main/backend/app/services/job_logger.py` 的同步执行 + job 记录语义。
- 当前阶段不要声称“真异步执行”；如果 `async=true`，也只是先把响应协议预留成 `job_id + trace_id + status`。

建议首批 route：

- `POST /api/v1/writing/templates/validate`
- `POST /api/v1/writing/llm-actions`
- `GET /api/v1/writing/llm-actions/history`
- `GET /api/v1/writing/llm-actions/{job_id}`

建议 request / response 结构：

- `TemplateValidateRequest`
  - `project_key`
  - `template_key`
  - `template_content | template_id`
  - `sample_payload`
  - `strict`
- `TemplateValidateResponse`
  - `valid`
  - `errors`
  - `warnings`
  - `normalized_template`
  - `rules`
  - `observability`
- `LlmActionRequest`
  - `project_key`
  - `action_id`
  - `template_key`
  - `template_version`
  - `document_id | doc_id`
  - `input_markdown`
  - `selection_text`
  - `trace_id`
  - `async`
  - `gate_mode`
- `LlmActionResponse`
  - 同步模式：
    - `content`
    - `sources`
    - `mode`
    - `warnings`
    - `trace_id`
    - `observability`
  - 预留异步模式：
    - `job_id`
    - `trace_id`
    - `status`
    - `observability`
- `LlmActionHistoryItem`
  - `job_id`
  - `job_type`
  - `status`
  - `project_key`
  - `action_id`
  - `template_key`
  - `template_version`
  - `request_meta`
  - `actor_id`
  - `trace_id`
  - `created_at`
  - `duration_ms`
  - `result_summary`

建议 service 方法：

- `validate_template_payload`
- `dispatch_action`
- `map_to_history`
- `get_action_history`
- `get_action_detail`
- `authz_gate`

建议 authz 检查顺序：

1. 规范化 `project_key`
2. 校验 project 是否存在
3. 校验模板 / 文档是否属于同一 `project_key`
4. 再执行 llm action
5. history/detail 查询必须显式受 `project_key` 过滤

注意事项：

- `job_logger` 的 `job_type` 最长 16 字符，写作域动作命名必须提前约束，例如不要直接把完整 action name 塞进去。
- 模板校验不能只做结构校验，还要把变量缺失、类型不符、模板版本缺失一并前置。

建议文件落点：

- `main/backend/app/services/writing/template_service.py`
- `main/backend/app/services/writing/llm_action_service.py`
- `main/backend/app/services/job_logger.py` 仅在需要补 meta 标准化时修改

### 7.7 最小测试骨架（实现前就该预留）

建议后端测试最小集：

- `main/backend/tests/core_business/test_writing_api_contract.py`
  - 校验 `status/data/error/meta`
  - 校验 `trace_id/project_key/request_id` 是否稳定回传
- `main/backend/tests/integration/test_writing_keyword_cards_api.py`
  - 三路聚合
  - preview/detail 分层
  - `selection_hash` 去重
  - `suggest` 模式切换
- `main/backend/tests/core_business/test_writing_document_service.py`
  - 保存成功
  - 版本冲突
  - autosave 幂等
  - citation 回放
- `main/backend/tests/integration/test_writing_documents_api.py`
  - create / open / patch / draft / citations
  - export 时重建 citation
- `main/backend/tests/integration/test_writing_llm_actions_api.py`
  - template validate
  - sync llm action
  - pseudo-async envelope
  - history/detail read
- `main/backend/tests/security/test_writing_authz.py`
  - 缺失 `project_key`
  - 跨项目 doc/template/action 拒绝
  - history 越权读取拒绝

如果后续拆子 Agent，A12-A15 应直接以“接口 schema + service skeleton + tests skeleton”作为第一轮交付，而不是先写页面再补后端。

## 8. 模板体系建议

模板不要只存静态 Markdown，建议加入执行语义：

- `template_key`
- `template_type`
- `audience`
- `section_order`
- `default_prompt_class`
- `citation_mode`
- `required_variables`
- `suggested_queries`

模板分类建议首批只做三类：

1. `market_weekly`
2. `policy_brief`
3. `company_deep_dive`

避免一开始上太多模板，先把“模板变量 + 资料卡 + LLM 动作”闭环跑通。

## 9. 安全与质量要求

### 9.1 Markdown 安全

- 预览链必须默认安全。
- 不允许未消毒 HTML 直接落到预览区。
- 引用外部内容时要做 URL 白名单和文本截断。

### 9.2 项目隔离

- 所有写作查询都必须透传 `project_key`。
- 模板、文档、引用篮都要绑定项目上下文。

### 9.3 生成可追溯

- 所有 AI 生成内容要记录 `trace_id`
- 记录触发动作、使用模型、引用来源、时间戳
- 支持“查看本段来源”

## 10. 分阶段实施

### Phase 1：MVP

- 新增写作页面入口
- CodeMirror Markdown 编辑
- React Markdown 预览
- 文档保存/打开
- 草稿自动保存与版本冲突提示
- 选词触发资料卡
- 资料卡 hover preview / detail
- suggest / typeahead
- 引用持久化与恢复
- 3 个模板
- 模板变量服务端校验
- 4 个 LLM 动作
- LLM 动作审计历史读取

### Phase 2：增强

- 资料卡拖拽插入
- 引用脚注自动编号
- 模板变量向导
- 多文档大纲管理
- 最近检索缓存

### Phase 3：高级

- 文档版本 diff
- 协作评论
- 模板市场
- 图谱节点反向引用
- 一键从资源池生成初稿

## 11. 最小回归验证

1. 导航可进入 `写作工作台`，刷新后 hash 路由仍有效。
2. 新建 Markdown 文档后可保存、再次打开、内容一致。
3. `Write / Preview / Split` 三种模式切换正常。
4. 选中关键词后右栏 500ms 内出现资料卡。
5. 点击资料卡“插入引用”后，文档内出现带链接的引用块。
6. 模板切换不会污染已有文档正文。
7. LLM 改写失败时不覆盖原文，且错误可见。
8. Markdown 预览区对脚本、事件属性、危险链接不执行。

## 12. 推荐实现决策

如果现在开始做，我建议按下面的决策落地：

- 编辑器：`CodeMirror 6`
- 预览：`react-markdown + remark-gfm + rehype-sanitize`
- 页面形态：三栏工作台
- 检索：后端聚合 `keyword-cards`
- 模板：`manifest + markdown body`
- LLM：把现有 `llm-report` 下沉为动作引擎，不直接当页面

这是当前仓库里最小改动、最容易复用现有能力、也最不容易把编辑器复杂度做炸的一条路径。

## 13. 本地代码复用地图

下面这些本地仓库已经足够支撑第一版实现，建议按优先级复用：

### 13.1 编辑器主链

- `reference-pool/oss/codemirror-view/src/tooltip.ts`
  - 直接参考 hover / tooltip 机制，做划词后的就地提示层。
- `reference-pool/oss/codemirror-view/src/panel.ts`
  - 参考 editor panel 机制，做编辑器内部提示或底部状态条。
- `reference-pool/oss/codemirror-view/src/draw-selection.ts`
  - 参考选区绘制与 selection state。
- `reference-pool/oss/codemirror-lang-markdown/src/markdown.ts`
  - 直接参考 Markdown 语言扩展与语法支持。
- `reference-pool/oss/codemirror-lang-markdown/src/commands.ts`
  - 直接参考标题、列表、块级命令处理。

### 13.2 Markdown / 预览 / 模板

- `reference-pool/oss/silverbullet/client/markdown_parser`
  - 参考 Markdown 解析管线。
- `reference-pool/oss/silverbullet/client/markdown_renderer`
  - 参考 live preview 渲染分层。
- `reference-pool/oss/silverbullet/client/codemirror`
  - 参考编辑器与 Markdown 渲染衔接方式。
- `reference-pool/oss/silverbullet/client/space_lua`
  - 参考模板、命令、可编程内容块的扩展思路。
- `reference-pool/oss/logseq/src/resources/templates`
  - 参考模板组织方式。

### 13.3 侧边栏 / 文档壳层 / Hover 卡片

- `reference-pool/oss/outline/app/components/Sidebar`
  - 直接参考知识库左侧导航和文档壳层组织。
- `reference-pool/oss/outline/app/components/HoverPreview`
  - 直接参考 hover 卡片预览。
- `reference-pool/oss/outline/app/components/Template`
  - 参考模板卡片展示。
- `reference-pool/oss/outline/app/components/TemplatizeDialog`
  - 参考把现有内容转成模板的交互。
- `reference-pool/oss/logseq/src/main/frontend/search`
  - 参考搜索入口和关联资料召回。
- `reference-pool/oss/logseq/src/main/frontend/components`
  - 参考文档页 / 侧边栏 / 卡片的整体组织方式。
- `reference-pool/oss/logseq/src/main/frontend/extensions`
  - 参考双链、扩展点和编辑期增强。

### 13.3.1 UI 交互不要手搓的重点

以下交互优先按现有实现“借骨架、换皮肤”，不要从零设计：

- 左栏文档树与模板切换：
  - 先参考 `outline` 的 sidebar / template 组织。
- 选词后就地预览与右栏联动：
  - 先参考 `codemirror-view` 的 tooltip/panel，再参考 `outline` 的 hover preview。
- 编辑区与预览区联动：
  - 先参考 `silverbullet` 的 markdown renderer 与 editor integration。
- 右栏 AI 助手：
  - 先参考 `silverbullet-ai` 的 chat panel 与 prompt action。
- 搜索与关联资料：
  - 先参考 `logseq` 的 search / command / route 体系。

只有在本地参考池里找不到足够接近的交互骨架时，才允许补自定义实现；并且需要在开发记录里注明“为什么不能复用现有实现”。

### 13.3.2 调查后的优先阅读顺序

真正开始实现前，建议按下面顺序先读代码：

1. `reference-pool/oss/outline/app/components/HoverPreview/HoverPreview.tsx`
2. `reference-pool/oss/outline/app/components/Sidebar/Sidebar.tsx`
3. `reference-pool/oss/silverbullet-ai/src/chat-panel.ts`
4. `reference-pool/oss/codemirror-view/src/tooltip.ts`
5. `reference-pool/oss/silverbullet/client/markdown_renderer/markdown_render.ts`
6. `reference-pool/oss/silverbullet/client/codemirror/editor_state.ts`
7. `reference-pool/oss/logseq/src/main/frontend/commands.cljs`
8. `reference-pool/oss/logseq/src/main/frontend/search/browser.cljs`

这 8 个文件基本覆盖了本次 MVP 的核心交互骨架。

### 13.4 AI 右栏 / Prompt / Embeddings

- `reference-pool/oss/silverbullet-ai/src/chat-panel.ts`
  - 直接参考右侧 AI 面板形态。
- `reference-pool/oss/silverbullet-ai/assets/chat-panel.html`
  - 直接参考聊天面板结构。
- `reference-pool/oss/silverbullet-ai/src/prompts.ts`
  - 参考模板化 prompt 注册方式。
- `reference-pool/oss/silverbullet-ai/src/editorUtils.ts`
  - 参考“对当前选区 / 当前页面”做 AI 操作的封装。
- `reference-pool/oss/silverbullet-ai/src/embeddings.ts`
  - 参考本地向量检索和上下文补全路径。
- `reference-pool/oss/dify`
  - 参考模板 DSL、知识检索返回结构、Prompt IDE。
- `reference-pool/oss/langflow`
  - 参考 Prompt Template 组件与模板元数据治理。

### 13.5 富文本升级备用

- `reference-pool/oss/tiptap/packages/markdown`
  - 后续需要富文本块编辑时再启用。
- `reference-pool/oss/tiptap/packages/react`
  - 参考 React 封装方式。
- `reference-pool/oss/tiptap/demos/src`
  - 参考 demo 级交互和扩展接法。

当前结论：

- MVP 直接抄 `CodeMirror + SilverBullet + Outline + SilverBullet AI` 这一组最划算。
- `Logseq` 主要补“关联文档 / 双链 / 搜索侧栏”的设计与数据组织。
- `Tiptap` 先作为 Phase 2/3 升级储备，不进 MVP 主链。

## 14. 外部最佳实践参考

以下参考都来自成熟开源项目或其官方文档：

- Tiptap Markdown 文档说明了 Markdown 解析/序列化与自定义 tokenizer 的能力，但官方当前仍标注为 early release / beta，因此更适合作为后续富文本升级方向，而不是本次 MVP 主方案。  
  https://tiptap.dev/docs/editor/markdown
- CodeMirror 6 官方提供 `hoverTooltip`、tooltip/panel 扩展，适合实现“选词后就近展示知识提示，再同步右栏卡片”的交互。  
  https://codemirror.net/docs/ref/  
  https://codemirror.net/examples/tooltip/
- Dify 的 Knowledge Retrieval 节点强调“检索结果返回 chunk + metadata + title”，这很适合作为资料卡后端返回结构参考。  
  https://docs.dify.ai/en/use-dify/nodes/knowledge-retrieval
- Dify 的 `Go to Anything` 说明全局检索入口应支持快捷键、分组结果和范围限定，可用于后续补充文档/模板快速切换。  
  https://docs.dify.ai/en/use-dify/build/goto-anything
- Langflow 的 Prompt Template 说明模板变量应该显式声明、动态注入，而不是把 prompt 写死在代码里。  
  https://docs.langflow.org/components-prompts
- Langflow 的模板贡献规范强调模板需要有名称、描述、分类、README/Quickstart，这适合直接套到本项目报告模板治理。  
  https://docs.langflow.org/contributing-templates
- Joplin Templates 插件证明“Markdown 模板 + 变量 + 默认模板”是成熟且低学习成本的路径。  
  https://joplinapp.org/plugins/plugin/joplin.plugin.templates/
- Obsidian Web Clipper 的高亮与模板机制说明“用户已有 selection 时优先使用 selection”是很自然的写作辅助交互。  
  https://help.obsidian.md/web-clipper  
  https://help.obsidian.md/web-clipper/capture
- `rehype-sanitize` 官方文档明确建议在不完全信任作者输入时做 HTML 安全清洗，适合本项目 Markdown 预览。  
  https://github.com/rehypejs/rehype-sanitize
