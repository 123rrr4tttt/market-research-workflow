export type GuideLocale = 'zh-CN' | 'en-US'

export type BusinessChainStage = {
  id: string
  label: Record<GuideLocale, string>
  detail: Record<GuideLocale, string>
  kind: 'input' | 'transform' | 'effect' | 'evidence' | 'projection'
}

export type BusinessChain = {
  id: string
  label: Record<GuideLocale, string>
  summary: Record<GuideLocale, string>
  route: string
  authority: Record<GuideLocale, string>
  operator: Record<GuideLocale, string>
  artifact: Record<GuideLocale, string>
  uiRoute: Record<GuideLocale, string>
  stageDetails: Record<string, { label: Record<GuideLocale, string>; detail: Record<GuideLocale, string> }>
  stages: readonly string[]
}

export type BusinessChainGraphNode = {
  id: string
  label: string
  detail: string
  kind: BusinessChainStage['kind'] | 'root' | 'chain'
  x: number
  y: number
}

export type BusinessChainGraphEdge = {
  id: string
  source: string
  target: string
  chainId?: string
}

export const BUSINESS_CHAIN_GUIDE = {
  version: 'mrw.business-chain-guide.v1',
  title: {
    'zh-CN': 'MRW 业务链条说明',
    'en-US': 'MRW business-chain guide',
  },
  subtitle: {
    'zh-CN': '把同一条业务运动投影为入口、变换、效果、证据与观察结果。',
    'en-US': 'One business movement projected as entry, transformation, effect, evidence, and observation.',
  },
  stages: [
    {
      id: 'input',
      label: { 'zh-CN': '入口', 'en-US': 'Entry' },
      detail: { 'zh-CN': 'HTTP、页面操作或已登记的任务请求', 'en-US': 'HTTP, page action, or a registered task request' },
      kind: 'input',
    },
    {
      id: 'normalize',
      label: { 'zh-CN': '规范化', 'en-US': 'Normalize' },
      detail: { 'zh-CN': '把请求变成带 project scope 的领域对象', 'en-US': 'Turn the request into a domain object with project scope' },
      kind: 'transform',
    },
    {
      id: 'plan',
      label: { 'zh-CN': '计划与解释', 'en-US': 'Plan and interpret' },
      detail: { 'zh-CN': '选择能力、操作、失败族与执行顺序', 'en-US': 'Select capability, operation, failure family, and order' },
      kind: 'transform',
    },
    {
      id: 'execute',
      label: { 'zh-CN': '执行效果', 'en-US': 'Execute effect' },
      detail: { 'zh-CN': '由现有 worker、provider 或数据库端口解释程序', 'en-US': 'Interpret the program through existing workers, providers, or database ports' },
      kind: 'effect',
    },
    {
      id: 'persist',
      label: { 'zh-CN': '持久化证据', 'en-US': 'Persist evidence' },
      detail: { 'zh-CN': '写入 canonical state、任务结果与可读回记录', 'en-US': 'Write canonical state, task result, and readback records' },
      kind: 'evidence',
    },
    {
      id: 'project',
      label: { 'zh-CN': '投影', 'en-US': 'Project' },
      detail: { 'zh-CN': '把权威结果投影到搜索、图谱、看板或 DTO', 'en-US': 'Project authority into search, graph, dashboard, or DTO views' },
      kind: 'projection',
    },
    {
      id: 'observe',
      label: { 'zh-CN': '观察与读回', 'en-US': 'Observe and read back' },
      detail: { 'zh-CN': '前端只读观察状态、失败与下一步', 'en-US': 'The frontend observes status, failure, and next action read-only' },
      kind: 'projection',
    },
  ] satisfies readonly BusinessChainStage[],
  chains: [
    {
      id: 'ingest',
      label: { 'zh-CN': '采集与原始入库', 'en-US': 'Ingest and raw import' },
      summary: { 'zh-CN': '从 URL、文本或采集任务进入，形成文档和 ingest evidence。', 'en-US': 'URL, text, or collection task becomes a document and ingest evidence.' },
      route: '/api/v1/admin/documents/raw-import',
      authority: { 'zh-CN': 'Document / Process owner', 'en-US': 'Document / Process owner' },
      operator: { 'zh-CN': 'API → task_raw_import_documents → Celery worker', 'en-US': 'API → task_raw_import_documents → Celery worker' },
      artifact: { 'zh-CN': 'Document、Process、ingest evidence、任务读回', 'en-US': 'Document, Process, ingest evidence, task readback' },
      uiRoute: { 'zh-CN': '#/workbench/raw-data → #/admin/process', 'en-US': '#/workbench/raw-data → #/admin/process' },
      stageDetails: {
        input: { label: { 'zh-CN': 'POST raw-import', 'en-US': 'POST raw-import' }, detail: { 'zh-CN': 'URL / 文本 / 文件 + project_key', 'en-US': 'URL / text / file + project_key' } },
        normalize: { label: { 'zh-CN': 'DocumentInput', 'en-US': 'DocumentInput' }, detail: { 'zh-CN': '解析来源、项目和幂等键', 'en-US': 'Resolve source, project, and idempotency key' } },
        plan: { label: { 'zh-CN': '采集任务计划', 'en-US': 'Ingest task plan' }, detail: { 'zh-CN': '绑定 task_raw_import_documents', 'en-US': 'Bind task_raw_import_documents' } },
        execute: { label: { 'zh-CN': 'Celery worker', 'en-US': 'Celery worker' }, detail: { 'zh-CN': '下载、解析、提取正文', 'en-US': 'Fetch, parse, and extract content' } },
        persist: { label: { 'zh-CN': 'Document + Process', 'en-US': 'Document + Process' }, detail: { 'zh-CN': '写入 PostgreSQL 与任务结果', 'en-US': 'Write PostgreSQL and task result' } },
        project: { label: { 'zh-CN': '原始资料投影', 'en-US': 'Raw material projection' }, detail: { 'zh-CN': '文档、来源和状态可检索', 'en-US': 'Document, source, and status become searchable' } },
        observe: { label: { 'zh-CN': '任务/原始数据页', 'en-US': 'Process / raw-data UI' }, detail: { 'zh-CN': '查看状态、结果和失败原因', 'en-US': 'Inspect status, result, and failure reason' } },
      },
      stages: ['input', 'normalize', 'plan', 'execute', 'persist', 'project', 'observe'],
    },
    {
      id: 'search',
      label: { 'zh-CN': '搜索、发现与索引', 'en-US': 'Search, discovery, and indexing' },
      summary: { 'zh-CN': '把已持久化资料转成搜索索引和检索结果。', 'en-US': 'Persisted material becomes search indexes and retrieval results.' },
      route: '/api/v1/search',
      authority: { 'zh-CN': 'Search index projection', 'en-US': 'Search index projection' },
      operator: { 'zh-CN': 'search_endpoint → Elasticsearch / PostgreSQL', 'en-US': 'search_endpoint → Elasticsearch / PostgreSQL' },
      artifact: { 'zh-CN': '检索结果、retrieval run、命中资料 ID', 'en-US': 'Search results, retrieval run, matched material IDs' },
      uiRoute: { 'zh-CN': '#/visual/catalog → #/visual/dashboard', 'en-US': '#/visual/catalog → #/visual/dashboard' },
      stageDetails: {
        input: { label: { 'zh-CN': 'GET /search', 'en-US': 'GET /search' }, detail: { 'zh-CN': 'q、filters、project_key', 'en-US': 'q, filters, project_key' } },
        normalize: { label: { 'zh-CN': 'SearchQuery', 'en-US': 'SearchQuery' }, detail: { 'zh-CN': '规范关键词、分页和范围', 'en-US': 'Normalize terms, paging, and scope' } },
        plan: { label: { 'zh-CN': '检索策略', 'en-US': 'Retrieval plan' }, detail: { 'zh-CN': '索引、过滤器和失败族', 'en-US': 'Index, filters, and failure family' } },
        execute: { label: { 'zh-CN': 'ES / DB 查询', 'en-US': 'ES / DB query' }, detail: { 'zh-CN': '执行索引检索与回读', 'en-US': 'Run index search and readback' } },
        persist: { label: { 'zh-CN': 'Retrieval run', 'en-US': 'Retrieval run' }, detail: { 'zh-CN': '保留查询和命中证据', 'en-US': 'Retain query and hit evidence' } },
        project: { label: { 'zh-CN': '结果列表/索引视图', 'en-US': 'Result / index view' }, detail: { 'zh-CN': '返回材料 ID、摘要和来源', 'en-US': 'Return material IDs, snippets, and sources' } },
        observe: { label: { 'zh-CN': '目录/检索页面', 'en-US': 'Catalog / search UI' }, detail: { 'zh-CN': '筛选、打开和继续处理', 'en-US': 'Filter, open, and continue processing' } },
      },
      stages: ['input', 'normalize', 'plan', 'execute', 'persist', 'project', 'observe'],
    },
    {
      id: 'dashboard',
      label: { 'zh-CN': '仪表盘与治理', 'en-US': 'Dashboard and governance' },
      summary: { 'zh-CN': '从统计、任务和质量记录生成管理观察面。', 'en-US': 'Statistics, tasks, and quality records form the management view.' },
      route: '/api/v1/dashboard/stats',
      authority: { 'zh-CN': 'Dashboard read model', 'en-US': 'Dashboard read model' },
      operator: { 'zh-CN': 'dashboard/stats 查询服务', 'en-US': 'dashboard/stats query service' },
      artifact: { 'zh-CN': '任务计数、资料计数、质量与运行指标', 'en-US': 'Task counts, material counts, quality, and runtime metrics' },
      uiRoute: { 'zh-CN': '#/visual/dashboard', 'en-US': '#/visual/dashboard' },
      stageDetails: {
        input: { label: { 'zh-CN': 'GET dashboard/stats', 'en-US': 'GET dashboard/stats' }, detail: { 'zh-CN': 'project_key + 时间/过滤范围', 'en-US': 'project_key + time/filter scope' } },
        normalize: { label: { 'zh-CN': 'DashboardQuery', 'en-US': 'DashboardQuery' }, detail: { 'zh-CN': '固定统计口径和项目范围', 'en-US': 'Fix metric definitions and project scope' } },
        plan: { label: { 'zh-CN': '统计查询计划', 'en-US': 'Metric query plan' }, detail: { 'zh-CN': '任务、资料、质量、运行四组指标', 'en-US': 'Tasks, materials, quality, and runtime metrics' } },
        execute: { label: { 'zh-CN': 'SQL / runtime readback', 'en-US': 'SQL / runtime readback' }, detail: { 'zh-CN': '只读聚合，不写 canonical state', 'en-US': 'Read-only aggregation; no canonical write' } },
        persist: { label: { 'zh-CN': '既有事实记录', 'en-US': 'Existing fact records' }, detail: { 'zh-CN': '读取任务、文档和健康记录', 'en-US': 'Read task, document, and health records' } },
        project: { label: { 'zh-CN': 'Dashboard DTO', 'en-US': 'Dashboard DTO' }, detail: { 'zh-CN': '聚合为前端统计卡片', 'en-US': 'Aggregate into frontend metric cards' } },
        observe: { label: { 'zh-CN': '可视化仪表盘', 'en-US': 'Visualization dashboard' }, detail: { 'zh-CN': '趋势、计数、异常和下一步', 'en-US': 'Trends, counts, anomalies, and next steps' } },
      },
      stages: ['input', 'normalize', 'plan', 'execute', 'persist', 'project', 'observe'],
    },
    {
      id: 'projects',
      label: { 'zh-CN': '项目、配置与工作流', 'en-US': 'Projects, configuration, and workflow' },
      summary: { 'zh-CN': '项目 scope、配置和任务编排保持同一身份边界。', 'en-US': 'Project scope, configuration, and task orchestration keep one identity boundary.' },
      route: '/api/v1/projects',
      authority: { 'zh-CN': 'Project scope registry', 'en-US': 'Project scope registry' },
      operator: { 'zh-CN': 'projects API → PostgreSQL project registry', 'en-US': 'projects API → PostgreSQL project registry' },
      artifact: { 'zh-CN': 'project_key、项目状态、激活关系', 'en-US': 'project_key, project status, and activation relation' },
      uiRoute: { 'zh-CN': '#/admin/projects → 顶部项目选择器', 'en-US': '#/admin/projects → project selector' },
      stageDetails: {
        input: { label: { 'zh-CN': 'GET/POST projects', 'en-US': 'GET/POST projects' }, detail: { 'zh-CN': '创建、切换、归档项目', 'en-US': 'Create, switch, or archive project' } },
        normalize: { label: { 'zh-CN': 'ProjectKey', 'en-US': 'ProjectKey' }, detail: { 'zh-CN': '校验 project scope 与保留名', 'en-US': 'Validate project scope and reserved names' } },
        plan: { label: { 'zh-CN': '项目操作计划', 'en-US': 'Project operation plan' }, detail: { 'zh-CN': 'activate / inject / archive', 'en-US': 'activate / inject / archive' } },
        execute: { label: { 'zh-CN': '项目服务', 'en-US': 'Project service' }, detail: { 'zh-CN': '执行权限和状态转换', 'en-US': 'Apply authority and state transitions' } },
        persist: { label: { 'zh-CN': 'Project registry', 'en-US': 'Project registry' }, detail: { 'zh-CN': '写入项目身份和生命周期', 'en-US': 'Write project identity and lifecycle' } },
        project: { label: { 'zh-CN': '项目选项 DTO', 'en-US': 'Project options DTO' }, detail: { 'zh-CN': '供页面和请求携带 project_key', 'en-US': 'Feed page and request project_key' } },
        observe: { label: { 'zh-CN': '项目管理/顶部栏', 'en-US': 'Project admin / top bar' }, detail: { 'zh-CN': '当前项目决定业务读写范围', 'en-US': 'Active project defines business scope' } },
      },
      stages: ['input', 'normalize', 'plan', 'execute', 'persist', 'project', 'observe'],
    },
    {
      id: 'writing',
      label: { 'zh-CN': '写作、知识图谱与 Agent', 'en-US': 'Writing, knowledge graph, and agent' },
      summary: { 'zh-CN': '证据、图谱和 Agent 操作通过既有能力端口组合。', 'en-US': 'Evidence, graph, and agent operations compose through existing capability ports.' },
      route: '/api/v1/admin/market-graph',
      authority: { 'zh-CN': 'Evidence and graph owner', 'en-US': 'Evidence and graph owner' },
      operator: { 'zh-CN': 'market-graph API → graph/agent capability ports', 'en-US': 'market-graph API → graph/agent capability ports' },
      artifact: { 'zh-CN': '线索、证据边、图谱节点、写作卡片', 'en-US': 'Clues, evidence edges, graph nodes, and writing cards' },
      uiRoute: { 'zh-CN': '#/visual/graph/* → #/workbench/writing', 'en-US': '#/visual/graph/* → #/workbench/writing' },
      stageDetails: {
        input: { label: { 'zh-CN': 'POST market-graph', 'en-US': 'POST market-graph' }, detail: { 'zh-CN': '材料、线索、关系和项目范围', 'en-US': 'Material, clues, relations, and project scope' } },
        normalize: { label: { 'zh-CN': 'GraphCommand', 'en-US': 'GraphCommand' }, detail: { 'zh-CN': '校验节点、边和证据身份', 'en-US': 'Validate nodes, edges, and evidence identity' } },
        plan: { label: { 'zh-CN': '图谱/Agent 程序', 'en-US': 'Graph / Agent program' }, detail: { 'zh-CN': '选择图谱、写作或 Agent 能力', 'en-US': 'Select graph, writing, or Agent capability' } },
        execute: { label: { 'zh-CN': 'worker / provider port', 'en-US': 'worker / provider port' }, detail: { 'zh-CN': '提取关系、生成观察或调用模型', 'en-US': 'Extract relations, produce observation, or call model' } },
        persist: { label: { 'zh-CN': 'Evidence + graph store', 'en-US': 'Evidence + graph store' }, detail: { 'zh-CN': '保留来源、证据和变更记录', 'en-US': 'Retain source, evidence, and change record' } },
        project: { label: { 'zh-CN': 'Graph / writing DTO', 'en-US': 'Graph / writing DTO' }, detail: { 'zh-CN': '投影为节点、边、卡片和报告片段', 'en-US': 'Project to nodes, edges, cards, and report fragments' } },
        observe: { label: { 'zh-CN': '图谱/写作/Agent 页面', 'en-US': 'Graph / writing / Agent UI' }, detail: { 'zh-CN': '查看关系、证据和待审结果', 'en-US': 'Review relations, evidence, and pending results' } },
      },
      stages: ['input', 'normalize', 'plan', 'execute', 'persist', 'project', 'observe'],
    },
    {
      id: 'resource',
      label: { 'zh-CN': '资源与来源库', 'en-US': 'Resource and source library' },
      summary: { 'zh-CN': '来源、站点和能力配置形成可审计的资源投影。', 'en-US': 'Sources, sites, and capabilities form an auditable resource projection.' },
      route: '/api/v1/resource_pool/site_entries/grouped',
      authority: { 'zh-CN': 'Resource pool owner', 'en-US': 'Resource pool owner' },
      operator: { 'zh-CN': 'resource pool API → source registry / provider ports', 'en-US': 'resource pool API → source registry / provider ports' },
      artifact: { 'zh-CN': '站点条目、来源能力、分组结果、绑定状态', 'en-US': 'Site entries, source capabilities, grouped results, and bindings' },
      uiRoute: { 'zh-CN': '#/admin/resources → #/admin/resources/extract', 'en-US': '#/admin/resources → #/admin/resources/extract' },
      stageDetails: {
        input: { label: { 'zh-CN': 'GET site_entries/grouped', 'en-US': 'GET site_entries/grouped' }, detail: { 'zh-CN': '搜索词、分组和 provider 过滤', 'en-US': 'Terms, groups, and provider filters' } },
        normalize: { label: { 'zh-CN': 'ResourceQuery', 'en-US': 'ResourceQuery' }, detail: { 'zh-CN': '统一 site/source/provider 身份', 'en-US': 'Unify site/source/provider identity' } },
        plan: { label: { 'zh-CN': '来源能力计划', 'en-US': 'Source capability plan' }, detail: { 'zh-CN': '决定可用入口和执行约束', 'en-US': 'Determine available entry and execution constraints' } },
        execute: { label: { 'zh-CN': 'registry / provider', 'en-US': 'registry / provider' }, detail: { 'zh-CN': '发现、绑定或维护来源条目', 'en-US': 'Discover, bind, or maintain source entries' } },
        persist: { label: { 'zh-CN': 'Resource pool', 'en-US': 'Resource pool' }, detail: { 'zh-CN': '保存来源、站点和绑定状态', 'en-US': 'Save source, site, and binding state' } },
        project: { label: { 'zh-CN': 'Grouped resource DTO', 'en-US': 'Grouped resource DTO' }, detail: { 'zh-CN': '按项目和能力分组返回', 'en-US': 'Return grouped by project and capability' } },
        observe: { label: { 'zh-CN': '资源库管理页', 'en-US': 'Resource management UI' }, detail: { 'zh-CN': '筛选、维护、提取和批量操作', 'en-US': 'Filter, maintain, extract, and batch operate' } },
      },
      stages: ['input', 'normalize', 'plan', 'execute', 'persist', 'project', 'observe'],
    },
    {
      id: 'runtime',
      label: { 'zh-CN': '运行态与 Successor', 'en-US': 'Runtime and Successor' },
      summary: { 'zh-CN': '程序、worker、持久化运行记录和只读观察保持分层。', 'en-US': 'Programs, workers, durable runs, and read-only observation stay layered.' },
      route: '/api/v1/health/deep',
      authority: { 'zh-CN': 'Runtime authority and readback', 'en-US': 'Runtime authority and readback' },
      operator: { 'zh-CN': 'health/deep → DB、连接池、Elasticsearch probes', 'en-US': 'health/deep → DB, pool, and Elasticsearch probes' },
      artifact: { 'zh-CN': '健康 DTO、延迟、连接池和依赖状态', 'en-US': 'Health DTO, latency, pool, and dependency status' },
      uiRoute: { 'zh-CN': '#/admin/backend → #/admin/successor-runtime', 'en-US': '#/admin/backend → #/admin/successor-runtime' },
      stageDetails: {
        input: { label: { 'zh-CN': 'GET health/deep', 'en-US': 'GET health/deep' }, detail: { 'zh-CN': '当前项目的运行态查询', 'en-US': 'Runtime query for the active project' } },
        normalize: { label: { 'zh-CN': 'RuntimeProbe', 'en-US': 'RuntimeProbe' }, detail: { 'zh-CN': '固定依赖检查和超时边界', 'en-US': 'Fix dependency probes and timeout boundary' } },
        plan: { label: { 'zh-CN': '健康检查计划', 'en-US': 'Health-check plan' }, detail: { 'zh-CN': 'DB、pool、ES、provider 分层检查', 'en-US': 'Layered DB, pool, ES, and provider checks' } },
        execute: { label: { 'zh-CN': '依赖探针', 'en-US': 'Dependency probes' }, detail: { 'zh-CN': '读取连接和依赖可用性', 'en-US': 'Read connection and dependency availability' } },
        persist: { label: { 'zh-CN': 'Runtime receipt', 'en-US': 'Runtime receipt' }, detail: { 'zh-CN': '保留观测结果，不冒充业务完成', 'en-US': 'Retain observation; no business-completion claim' } },
        project: { label: { 'zh-CN': 'Health DTO', 'en-US': 'Health DTO' }, detail: { 'zh-CN': 'status、latency、failure identity', 'en-US': 'status, latency, and failure identity' } },
        observe: { label: { 'zh-CN': '后端/Successor 观察页', 'en-US': 'Backend / Successor UI' }, detail: { 'zh-CN': '定位依赖故障和下一步动作', 'en-US': 'Locate dependency failures and next action' } },
      },
      stages: ['input', 'normalize', 'plan', 'execute', 'persist', 'project', 'observe'],
    },
  ] satisfies readonly BusinessChain[],
} as const

export function projectBusinessChainGraph(locale: GuideLocale) {
  const nodes: BusinessChainGraphNode[] = [
    { id: 'root', label: BUSINESS_CHAIN_GUIDE.title[locale], detail: BUSINESS_CHAIN_GUIDE.subtitle[locale], kind: 'root', x: 32, y: 245 },
  ]
  const edges: BusinessChainGraphEdge[] = []
  const stageById = new Map(BUSINESS_CHAIN_GUIDE.stages.map((stage) => [stage.id, stage]))

  BUSINESS_CHAIN_GUIDE.chains.forEach((chain, chainIndex) => {
    const chainId = `chain:${chain.id}`
    const y = 54 + chainIndex * 72
    nodes.push({ id: chainId, label: chain.label[locale], detail: chain.summary[locale], kind: 'chain', x: 232, y })
    edges.push({ id: `root:${chain.id}`, source: 'root', target: chainId, chainId: chain.id })
    chain.stages.forEach((stageId, stageIndex) => {
      const stage = stageById.get(stageId)
      if (!stage) return
      const stageInfo = (chain.stageDetails as Record<string, { label: Record<GuideLocale, string>; detail: Record<GuideLocale, string> }>)[stageId] ?? { label: stage.label, detail: stage.detail }
      const nodeId = `${chain.id}:${stageId}`
      nodes.push({
        id: nodeId,
        label: stageInfo.label[locale],
        detail: stageInfo.detail[locale],
        kind: stage.kind,
        x: 438 + stageIndex * 172,
        y: y + 18,
      })
      edges.push({ id: `${chain.id}:${stageId}`, source: stageIndex === 0 ? chainId : `${chain.id}:${chain.stages[stageIndex - 1]}`, target: nodeId, chainId: chain.id })
    })
  })

  return { nodes, edges, width: 438 + BUSINESS_CHAIN_GUIDE.stages.length * 172, height: 54 + BUSINESS_CHAIN_GUIDE.chains.length * 72 }
}
