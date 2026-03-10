export type WorkflowNodeType = 'vector_search' | 'llm_call' | 'join' | 'filter'

export type WorkflowModuleType =
  | 'ingest'
  | 'vector'
  | 'llm'
  | 'filter'
  | 'join'
  | 'output'
  | 'report'

export type WorkflowModuleTemplateKey =
  | 'ingest-query'
  | 'ingest-market-news'
  | 'ingest-social-posts'
  | 'ingest-policy-docs'
  | 'ingest-ecom-signals'
  | 'vector-retrieve-fast'
  | 'vector-retrieve-deep'
  | 'llm-analyze'
  | 'llm-extract'
  | 'llm-summarize'
  | 'llm-risk-score'
  | 'filter-predicate'
  | 'filter-topk'
  | 'join-concat'
  | 'join-json'
  | 'report-weekly'
  | 'output-final'

export type WorkflowModuleTemplate = {
  key: WorkflowModuleTemplateKey
  label: string
  moduleType: WorkflowModuleType
  nodeType: WorkflowNodeType
  description: string
  data: Record<string, unknown>
}

export type WorkflowPresetNode = {
  id: string
  templateKey: WorkflowModuleTemplateKey
  position: { x: number; y: number }
  overrides?: Record<string, unknown>
}

export type WorkflowPresetEdge = {
  id: string
  source: string
  target: string
  label?: string
}

export type WorkflowLinkPresetKey =
  | 'collect-market-news-basic'
  | 'collect-policy-basic'
  | 'collect-social-basic'
  | 'collect-ecom-basic'
  | 'collect-multi-source-fusion'
  | 'biz-market-rag'
  | 'biz-social-sentiment'
  | 'biz-policy-watch'
  | 'biz-ecom-price-signal'
  | 'biz-competitor-intel'
  | 'biz-weekly-report'
  | 'biz-risk-alert'
  | 'biz-full-funnel'

export type WorkflowLinkPreset = {
  key: WorkflowLinkPresetKey
  label: string
  description: string
  nodes: WorkflowPresetNode[]
  edges: WorkflowPresetEdge[]
}

export const WORKFLOW_MODULE_TEMPLATES: WorkflowModuleTemplate[] = [
  {
    key: 'ingest-query',
    label: 'Ingest Query',
    moduleType: 'ingest',
    nodeType: 'vector_search',
    description: 'Manual input entry for ad-hoc analysis.',
    data: {
      label: 'Input Query',
      node_type: 'vector_search',
      role: 'input',
      query_key: 'query',
      module_domain: 'generic',
    },
  },
  {
    key: 'ingest-market-news',
    label: 'Ingest Market News',
    moduleType: 'ingest',
    nodeType: 'vector_search',
    description: 'Market/news ingestion entry.',
    data: {
      label: 'Market News Ingest',
      node_type: 'vector_search',
      role: 'ingest',
      source: 'market_news',
      query_key: 'topic',
      module_domain: 'market',
    },
  },
  {
    key: 'ingest-social-posts',
    label: 'Ingest Data API',
    moduleType: 'ingest',
    nodeType: 'vector_search',
    description: 'Data-API ingestion entry.',
    data: {
      label: 'Data API Ingest',
      node_type: 'vector_search',
      role: 'ingest',
      source: 'social_posts',
      query_key: 'topic',
      module_domain: 'social',
    },
  },
  {
    key: 'ingest-policy-docs',
    label: 'Ingest Policy Docs',
    moduleType: 'ingest',
    nodeType: 'vector_search',
    description: 'Policy/regulation ingestion entry.',
    data: {
      label: 'Policy Ingest',
      node_type: 'vector_search',
      role: 'ingest',
      source: 'policy_docs',
      query_key: 'region',
      module_domain: 'policy',
    },
  },
  {
    key: 'ingest-ecom-signals',
    label: 'Ingest Ecom Signals',
    moduleType: 'ingest',
    nodeType: 'vector_search',
    description: 'E-commerce/product signals ingestion entry.',
    data: {
      label: 'Ecom Signals Ingest',
      node_type: 'vector_search',
      role: 'ingest',
      source: 'ecom_signals',
      query_key: 'product_keyword',
      module_domain: 'ecom',
    },
  },
  {
    key: 'vector-retrieve-fast',
    label: 'Vector Fast Retrieve',
    moduleType: 'vector',
    nodeType: 'vector_search',
    description: 'Fast recall for lightweight retrieval.',
    data: {
      label: 'Vector Fast',
      node_type: 'vector_search',
      top_k: 5,
      source: 'default_corpus',
      rerank: false,
    },
  },
  {
    key: 'vector-retrieve-deep',
    label: 'Vector Deep Retrieve',
    moduleType: 'vector',
    nodeType: 'vector_search',
    description: 'Deep retrieval with higher recall.',
    data: {
      label: 'Vector Deep',
      node_type: 'vector_search',
      top_k: 20,
      source: 'default_corpus',
      rerank: true,
    },
  },
  {
    key: 'llm-analyze',
    label: 'LLM Analyze',
    moduleType: 'llm',
    nodeType: 'llm_call',
    description: 'Main analytical generation node.',
    data: {
      label: 'LLM Analyze',
      node_type: 'llm_call',
      provider: 'openai',
      model: 'gpt-4.1',
      temperature: 0.2,
      top_p: 1,
      max_tokens: 1200,
      prompt_class: 'analyst',
      prompt_template: 'Analyze the input and provide evidence-based findings.',
    },
  },
  {
    key: 'llm-extract',
    label: 'LLM Extract',
    moduleType: 'llm',
    nodeType: 'llm_call',
    description: 'Structured extraction node.',
    data: {
      label: 'LLM Extract',
      node_type: 'llm_call',
      provider: 'openai',
      model: 'gpt-4.1-mini',
      temperature: 0,
      top_p: 1,
      max_tokens: 900,
      prompt_class: 'extractor',
      prompt_template: 'Extract key entities, metrics, and risks in JSON.',
    },
  },
  {
    key: 'llm-summarize',
    label: 'LLM Summarize',
    moduleType: 'llm',
    nodeType: 'llm_call',
    description: 'Summary node for concise output.',
    data: {
      label: 'LLM Summarize',
      node_type: 'llm_call',
      provider: 'openai',
      model: 'gpt-4.1-mini',
      temperature: 0.2,
      top_p: 1,
      max_tokens: 700,
      prompt_class: 'summarizer',
      prompt_template: 'Summarize in concise bullets with action items.',
    },
  },
  {
    key: 'llm-risk-score',
    label: 'LLM Risk Score',
    moduleType: 'llm',
    nodeType: 'llm_call',
    description: 'Risk scoring/classification node.',
    data: {
      label: 'LLM Risk Score',
      node_type: 'llm_call',
      provider: 'openai',
      model: 'gpt-4.1-mini',
      temperature: 0,
      top_p: 1,
      max_tokens: 600,
      prompt_class: 'extractor',
      prompt_template: 'Classify risk level and output risk_score, reason, mitigation in JSON.',
    },
  },
  {
    key: 'filter-predicate',
    label: 'Filter Predicate',
    moduleType: 'filter',
    nodeType: 'filter',
    description: 'Filter records by predicate expression.',
    data: {
      label: 'Filter Predicate',
      node_type: 'filter',
      strategy: 'predicate',
      predicate_expr: '={{$node.vector.output}}',
      predicate_mode: 'keep',
      input_vars: [{ name: 'items', value_type: 'array', source: 'node_output', required: true }],
      output_vars: [{ name: 'filtered_items', value_type: 'array', required: true }],
    },
  },
  {
    key: 'filter-topk',
    label: 'Filter TopK',
    moduleType: 'filter',
    nodeType: 'filter',
    description: 'Filter records by score and keep top-k.',
    data: {
      label: 'Filter TopK',
      node_type: 'filter',
      strategy: 'topk',
      topk_k: 20,
      topk_score_field: 'score',
      topk_desc: true,
      input_vars: [{ name: 'items', value_type: 'array', source: 'node_output', required: true }],
      output_vars: [{ name: 'filtered_items', value_type: 'array', required: true }],
    },
  },
  {
    key: 'join-concat',
    label: 'Join Concat',
    moduleType: 'join',
    nodeType: 'join',
    description: 'Merge branches with text concatenation.',
    data: {
      label: 'Join Concat',
      node_type: 'join',
      strategy: 'concat',
      delimiter: '\\n\\n',
    },
  },
  {
    key: 'join-json',
    label: 'Join JSON',
    moduleType: 'join',
    nodeType: 'join',
    description: 'Merge branches in JSON style.',
    data: {
      label: 'Join JSON',
      node_type: 'join',
      strategy: 'json_merge',
    },
  },
  {
    key: 'report-weekly',
    label: 'Weekly Report Builder',
    moduleType: 'report',
    nodeType: 'llm_call',
    description: 'Render weekly report content.',
    data: {
      label: 'Weekly Report',
      node_type: 'llm_call',
      provider: 'openai',
      model: 'gpt-4.1',
      temperature: 0.2,
      top_p: 1,
      max_tokens: 1800,
      prompt_class: 'summarizer',
      prompt_template: 'Generate a weekly report with sections: highlights, risks, recommendations.',
    },
  },
  {
    key: 'output-final',
    label: 'Final Output',
    moduleType: 'output',
    nodeType: 'join',
    description: 'Terminal output node.',
    data: {
      label: 'Final Output',
      node_type: 'join',
      role: 'output',
      strategy: 'concat',
    },
  },
]

export const WORKFLOW_MODULE_TEMPLATE_BY_KEY: Record<WorkflowModuleTemplateKey, WorkflowModuleTemplate> =
  Object.fromEntries(WORKFLOW_MODULE_TEMPLATES.map((item) => [item.key, item])) as Record<WorkflowModuleTemplateKey, WorkflowModuleTemplate>

export const WORKFLOW_LINK_PRESETS: WorkflowLinkPreset[] = [
  {
    key: 'collect-market-news-basic',
    label: '采集链: 市场新闻基础采集',
    description: '市场采集 -> 快检索 -> 结构抽取 -> 输出',
    nodes: [
      { id: 'c-market-ingest', templateKey: 'ingest-market-news', position: { x: 80, y: 120 } },
      { id: 'c-market-vector', templateKey: 'vector-retrieve-fast', position: { x: 320, y: 120 } },
      { id: 'c-market-extract', templateKey: 'llm-extract', position: { x: 560, y: 120 } },
      { id: 'c-market-output', templateKey: 'output-final', position: { x: 800, y: 120 } },
    ],
    edges: [
      { id: 'e-c-market-1', source: 'c-market-ingest', target: 'c-market-vector' },
      { id: 'e-c-market-2', source: 'c-market-vector', target: 'c-market-extract' },
      { id: 'e-c-market-3', source: 'c-market-extract', target: 'c-market-output' },
    ],
  },
  {
    key: 'collect-policy-basic',
    label: '采集链: 法规来源入库',
    description: '法规来源 -> 深检索 -> 结构抽取 -> JSON 聚合 -> 输出',
    nodes: [
      { id: 'c-policy-ingest', templateKey: 'ingest-policy-docs', position: { x: 80, y: 220 } },
      { id: 'c-policy-vector', templateKey: 'vector-retrieve-deep', position: { x: 320, y: 220 } },
      { id: 'c-policy-extract', templateKey: 'llm-extract', position: { x: 560, y: 220 } },
      { id: 'c-policy-join', templateKey: 'join-json', position: { x: 800, y: 220 } },
      { id: 'c-policy-output', templateKey: 'output-final', position: { x: 1040, y: 220 } },
    ],
    edges: [
      { id: 'e-c-policy-1', source: 'c-policy-ingest', target: 'c-policy-vector' },
      { id: 'e-c-policy-2', source: 'c-policy-vector', target: 'c-policy-extract' },
      { id: 'e-c-policy-3', source: 'c-policy-extract', target: 'c-policy-join' },
      { id: 'e-c-policy-4', source: 'c-policy-join', target: 'c-policy-output' },
    ],
  },
  {
    key: 'collect-social-basic',
    label: '采集链: 数据 API 采集',
    description: '数据 API 采集 -> 快检索 -> 风险评分 -> 输出',
    nodes: [
      { id: 'c-social-ingest', templateKey: 'ingest-social-posts', position: { x: 80, y: 320 } },
      { id: 'c-social-vector', templateKey: 'vector-retrieve-fast', position: { x: 320, y: 320 } },
      { id: 'c-social-risk', templateKey: 'llm-risk-score', position: { x: 560, y: 320 } },
      { id: 'c-social-output', templateKey: 'output-final', position: { x: 800, y: 320 } },
    ],
    edges: [
      { id: 'e-c-social-1', source: 'c-social-ingest', target: 'c-social-vector' },
      { id: 'e-c-social-2', source: 'c-social-vector', target: 'c-social-risk' },
      { id: 'e-c-social-3', source: 'c-social-risk', target: 'c-social-output' },
    ],
  },
  {
    key: 'collect-ecom-basic',
    label: '采集链: 电商价格采集',
    description: '电商采集 -> 快检索 -> 抽取 -> 输出',
    nodes: [
      { id: 'c-ecom-ingest', templateKey: 'ingest-ecom-signals', position: { x: 80, y: 420 } },
      { id: 'c-ecom-vector', templateKey: 'vector-retrieve-fast', position: { x: 320, y: 420 } },
      { id: 'c-ecom-extract', templateKey: 'llm-extract', position: { x: 560, y: 420 } },
      { id: 'c-ecom-output', templateKey: 'output-final', position: { x: 800, y: 420 } },
    ],
    edges: [
      { id: 'e-c-ecom-1', source: 'c-ecom-ingest', target: 'c-ecom-vector' },
      { id: 'e-c-ecom-2', source: 'c-ecom-vector', target: 'c-ecom-extract' },
      { id: 'e-c-ecom-3', source: 'c-ecom-extract', target: 'c-ecom-output' },
    ],
  },
  {
    key: 'collect-multi-source-fusion',
    label: '采集链: 多源信息汇聚',
    description: '市场 + 法规来源 + 数据 API 入库 -> 聚合 -> 输出',
    nodes: [
      { id: 'c-ms-market', templateKey: 'ingest-market-news', position: { x: 80, y: 560 } },
      { id: 'c-ms-policy', templateKey: 'ingest-policy-docs', position: { x: 80, y: 700 } },
      { id: 'c-ms-social', templateKey: 'ingest-social-posts', position: { x: 80, y: 840 } },
      { id: 'c-ms-join', templateKey: 'join-concat', position: { x: 360, y: 700 } },
      { id: 'c-ms-output', templateKey: 'output-final', position: { x: 640, y: 700 } },
    ],
    edges: [
      { id: 'e-c-ms-1', source: 'c-ms-market', target: 'c-ms-join' },
      { id: 'e-c-ms-2', source: 'c-ms-policy', target: 'c-ms-join' },
      { id: 'e-c-ms-3', source: 'c-ms-social', target: 'c-ms-join' },
      { id: 'e-c-ms-4', source: 'c-ms-join', target: 'c-ms-output' },
    ],
  },
  {
    key: 'biz-market-rag',
    label: '业务链: 市场情报 RAG',
    description: '市场采集 -> 深检索 -> 分析 -> 摘要 -> 输出',
    nodes: [
      { id: 'market-ingest', templateKey: 'ingest-market-news', position: { x: 80, y: 140 } },
      { id: 'market-vector', templateKey: 'vector-retrieve-deep', position: { x: 320, y: 140 } },
      { id: 'market-analyze', templateKey: 'llm-analyze', position: { x: 560, y: 140 } },
      { id: 'market-summary', templateKey: 'llm-summarize', position: { x: 800, y: 140 } },
      { id: 'market-output', templateKey: 'output-final', position: { x: 1040, y: 140 } },
    ],
    edges: [
      { id: 'e-market-1', source: 'market-ingest', target: 'market-vector' },
      { id: 'e-market-2', source: 'market-vector', target: 'market-analyze' },
      { id: 'e-market-3', source: 'market-analyze', target: 'market-summary' },
      { id: 'e-market-4', source: 'market-summary', target: 'market-output' },
    ],
  },
  {
    key: 'biz-social-sentiment',
    label: '业务链: 数据 API 监测',
    description: '数据 API 采集 -> 快检索 -> 风险评分 -> 摘要 -> 输出',
    nodes: [
      { id: 'social-ingest', templateKey: 'ingest-social-posts', position: { x: 80, y: 220 } },
      { id: 'social-vector', templateKey: 'vector-retrieve-fast', position: { x: 320, y: 220 } },
      { id: 'social-risk', templateKey: 'llm-risk-score', position: { x: 560, y: 220 } },
      { id: 'social-summary', templateKey: 'llm-summarize', position: { x: 800, y: 220 } },
      { id: 'social-output', templateKey: 'output-final', position: { x: 1040, y: 220 } },
    ],
    edges: [
      { id: 'e-social-1', source: 'social-ingest', target: 'social-vector' },
      { id: 'e-social-2', source: 'social-vector', target: 'social-risk' },
      { id: 'e-social-3', source: 'social-risk', target: 'social-summary' },
      { id: 'e-social-4', source: 'social-summary', target: 'social-output' },
    ],
  },
  {
    key: 'biz-policy-watch',
    label: '业务链: 法规可视化',
    description: '法规来源 -> 深检索 -> 结构抽取 -> JSON 聚合 -> 输出',
    nodes: [
      { id: 'policy-ingest', templateKey: 'ingest-policy-docs', position: { x: 80, y: 300 } },
      { id: 'policy-vector', templateKey: 'vector-retrieve-deep', position: { x: 320, y: 300 } },
      { id: 'policy-extract', templateKey: 'llm-extract', position: { x: 560, y: 300 } },
      { id: 'policy-join', templateKey: 'join-json', position: { x: 800, y: 300 } },
      { id: 'policy-output', templateKey: 'output-final', position: { x: 1040, y: 300 } },
    ],
    edges: [
      { id: 'e-policy-1', source: 'policy-ingest', target: 'policy-vector' },
      { id: 'e-policy-2', source: 'policy-vector', target: 'policy-extract' },
      { id: 'e-policy-3', source: 'policy-extract', target: 'policy-join' },
      { id: 'e-policy-4', source: 'policy-join', target: 'policy-output' },
    ],
  },
  {
    key: 'biz-ecom-price-signal',
    label: '业务链: 电商价格信号',
    description: '电商采集 -> 快检索 -> 结构抽取 -> 输出',
    nodes: [
      { id: 'ecom-ingest', templateKey: 'ingest-ecom-signals', position: { x: 80, y: 380 } },
      { id: 'ecom-vector', templateKey: 'vector-retrieve-fast', position: { x: 320, y: 380 } },
      { id: 'ecom-extract', templateKey: 'llm-extract', position: { x: 560, y: 380 } },
      { id: 'ecom-output', templateKey: 'output-final', position: { x: 800, y: 380 } },
    ],
    edges: [
      { id: 'e-ecom-1', source: 'ecom-ingest', target: 'ecom-vector' },
      { id: 'e-ecom-2', source: 'ecom-vector', target: 'ecom-extract' },
      { id: 'e-ecom-3', source: 'ecom-extract', target: 'ecom-output' },
    ],
  },
  {
    key: 'biz-competitor-intel',
    label: '业务链: 竞品情报',
    description: '市场采集 + 数据 API 采集 -> 合并 -> 分析 -> 输出',
    nodes: [
      { id: 'comp-market-ingest', templateKey: 'ingest-market-news', position: { x: 80, y: 480 } },
      { id: 'comp-social-ingest', templateKey: 'ingest-social-posts', position: { x: 80, y: 620 } },
      { id: 'comp-join', templateKey: 'join-concat', position: { x: 340, y: 550 } },
      { id: 'comp-analyze', templateKey: 'llm-analyze', position: { x: 600, y: 550 } },
      { id: 'comp-output', templateKey: 'output-final', position: { x: 860, y: 550 } },
    ],
    edges: [
      { id: 'e-comp-1', source: 'comp-market-ingest', target: 'comp-join' },
      { id: 'e-comp-2', source: 'comp-social-ingest', target: 'comp-join' },
      { id: 'e-comp-3', source: 'comp-join', target: 'comp-analyze' },
      { id: 'e-comp-4', source: 'comp-analyze', target: 'comp-output' },
    ],
  },
  {
    key: 'biz-weekly-report',
    label: '业务链: 周报自动生成',
    description: '市场/数据 API/法规来源 -> 聚合 -> 周报生成 -> 输出',
    nodes: [
      { id: 'wk-market', templateKey: 'ingest-market-news', position: { x: 80, y: 760 } },
      { id: 'wk-social', templateKey: 'ingest-social-posts', position: { x: 80, y: 900 } },
      { id: 'wk-policy', templateKey: 'ingest-policy-docs', position: { x: 80, y: 1040 } },
      { id: 'wk-join', templateKey: 'join-concat', position: { x: 360, y: 900 } },
      { id: 'wk-report', templateKey: 'report-weekly', position: { x: 640, y: 900 } },
      { id: 'wk-output', templateKey: 'output-final', position: { x: 920, y: 900 } },
    ],
    edges: [
      { id: 'e-wk-1', source: 'wk-market', target: 'wk-join' },
      { id: 'e-wk-2', source: 'wk-social', target: 'wk-join' },
      { id: 'e-wk-3', source: 'wk-policy', target: 'wk-join' },
      { id: 'e-wk-4', source: 'wk-join', target: 'wk-report' },
      { id: 'e-wk-5', source: 'wk-report', target: 'wk-output' },
    ],
  },
  {
    key: 'biz-risk-alert',
    label: '业务链: 风险告警',
    description: '法规来源 + 数据 API -> 风险评分 -> 输出',
    nodes: [
      { id: 'risk-policy', templateKey: 'ingest-policy-docs', position: { x: 80, y: 1160 } },
      { id: 'risk-social', templateKey: 'ingest-social-posts', position: { x: 80, y: 1300 } },
      { id: 'risk-join', templateKey: 'join-json', position: { x: 340, y: 1230 } },
      { id: 'risk-score', templateKey: 'llm-risk-score', position: { x: 600, y: 1230 } },
      { id: 'risk-output', templateKey: 'output-final', position: { x: 860, y: 1230 } },
    ],
    edges: [
      { id: 'e-risk-1', source: 'risk-policy', target: 'risk-join' },
      { id: 'e-risk-2', source: 'risk-social', target: 'risk-join' },
      { id: 'e-risk-3', source: 'risk-join', target: 'risk-score' },
      { id: 'e-risk-4', source: 'risk-score', target: 'risk-output' },
    ],
  },
  {
    key: 'biz-full-funnel',
    label: '业务链: 全链路总览',
    description: '采集 -> 检索 -> 抽取 -> 聚合 -> 分析 -> 摘要 -> 输出',
    nodes: [
      { id: 'full-ingest', templateKey: 'ingest-market-news', position: { x: 80, y: 1440 } },
      { id: 'full-vector', templateKey: 'vector-retrieve-deep', position: { x: 300, y: 1440 } },
      { id: 'full-extract', templateKey: 'llm-extract', position: { x: 520, y: 1440 } },
      { id: 'full-join', templateKey: 'join-json', position: { x: 740, y: 1440 } },
      { id: 'full-analyze', templateKey: 'llm-analyze', position: { x: 960, y: 1440 } },
      { id: 'full-summary', templateKey: 'llm-summarize', position: { x: 1180, y: 1440 } },
      { id: 'full-output', templateKey: 'output-final', position: { x: 1400, y: 1440 } },
    ],
    edges: [
      { id: 'e-full-1', source: 'full-ingest', target: 'full-vector' },
      { id: 'e-full-2', source: 'full-vector', target: 'full-extract' },
      { id: 'e-full-3', source: 'full-extract', target: 'full-join' },
      { id: 'e-full-4', source: 'full-join', target: 'full-analyze' },
      { id: 'e-full-5', source: 'full-analyze', target: 'full-summary' },
      { id: 'e-full-6', source: 'full-summary', target: 'full-output' },
    ],
  },
]

export const DEFAULT_WORKFLOW_LINK_PRESET_KEY: WorkflowLinkPresetKey = 'collect-market-news-basic'

export const WORKFLOW_LINK_PRESET_BY_KEY: Record<WorkflowLinkPresetKey, WorkflowLinkPreset> =
  Object.fromEntries(WORKFLOW_LINK_PRESETS.map((item) => [item.key, item])) as Record<WorkflowLinkPresetKey, WorkflowLinkPreset>
