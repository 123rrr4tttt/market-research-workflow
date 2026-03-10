import { DEFAULT_APP_LOCALE, type AppLocale } from './types'

export const MESSAGE_KEY_SHAPE = {
  shell: {
    'title.overviewTasks': '',
    'title.overviewData': '',
    'title.dataDashboard': '',
    'title.dataMarket': '',
    'title.dataSocial': '',
    'title.dataPolicy': '',
    'title.dataCatalog': '',
    'title.graphMarket': '',
    'title.graphPolicy': '',
    'title.graphSocial': '',
    'title.graphCompany': '',
    'title.graphProduct': '',
    'title.graphOperation': '',
    'title.graphDeep': '',
    'title.graphBuilder': '',
    'title.flowIngest': '',
    'title.flowSpecialized': '',
    'title.flowProcessing': '',
    'title.flowRawData': '',
    'title.flowExtract': '',
    'title.flowAnalysis': '',
    'title.flowBoard': '',
    'title.flowWriting': '',
    'title.flowLlmNodeDesign': '',
    'title.sysProjects': '',
    'title.sysCrawler': '',
    'title.sysResource': '',
    'title.sysBackend': '',
    'title.sysSettings': '',
    'title.sysLlm': '',
  },
  navigation: {
    'group.overview': '',
    'group.dataFacets': '',
    'group.graph': '',
    'group.flow': '',
    'group.system': '',
    'item.overviewTasks': '',
    'item.overviewData': '',
    'item.dataDashboard': '',
    'item.dataMarket': '',
    'item.dataSocial': '',
    'item.dataPolicy': '',
    'item.dataCatalog': '',
    'item.graphMarket': '',
    'item.graphPolicy': '',
    'item.graphSocial': '',
    'item.graphCompany': '',
    'item.graphProduct': '',
    'item.graphOperation': '',
    'item.graphDeep': '',
    'item.graphBuilder': '',
    'item.flowIngest': '',
    'item.flowSpecialized': '',
    'item.flowProcessing': '',
    'item.flowRawData': '',
    'item.flowExtract': '',
    'item.flowAnalysis': '',
    'item.flowBoard': '',
    'item.flowWriting': '',
    'item.flowLlmNodeDesign': '',
    'item.sysProjects': '',
    'item.sysCrawler': '',
    'item.sysResource': '',
    'item.sysBackend': '',
    'item.sysSettings': '',
    'item.sysLlm': '',
    'action.createGraph': '',
  },
  settings: {
    'locale.label': '',
    'locale.zh-CN': '',
    'locale.en-US': '',
    'theme.label': '',
    'theme.light': '',
    'theme.dark': '',
    'theme.brand': '',
  },
  shared: {
    loading: '',
    error: '',
    empty: '',
    'action.save': '',
    'action.cancel': '',
    'action.confirm': '',
  },
} as const

type CatalogShape = {
  [N in keyof typeof MESSAGE_KEY_SHAPE]: {
    [K in keyof (typeof MESSAGE_KEY_SHAPE)[N]]: string
  }
}

const zhCNMessages: CatalogShape = {
  shell: {
    'title.overviewTasks': '任务',
    'title.overviewData': '数据',
    'title.dataDashboard': '数据仪表盘',
    'title.dataMarket': '市场',
    'title.dataSocial': '舆情',
    'title.dataPolicy': '政策',
    'title.dataCatalog': '行业公司/商品/经营',
    'title.graphMarket': '市场图谱',
    'title.graphPolicy': '政策图谱',
    'title.graphSocial': '社媒图谱',
    'title.graphCompany': '公司图谱',
    'title.graphProduct': '商品图谱',
    'title.graphOperation': '电商/经营图谱',
    'title.graphDeep': '市场实体加细图',
    'title.graphBuilder': '新建图谱',
    'title.flowIngest': '采集',
    'title.flowSpecialized': '特化采集',
    'title.flowProcessing': '数据处理',
    'title.flowRawData': '原始数据处理',
    'title.flowExtract': '提取',
    'title.flowAnalysis': '分析',
    'title.flowBoard': '看板',
    'title.flowWriting': '写作工作台',
    'title.flowLlmNodeDesign': 'LLM 节点设计',
    'title.sysProjects': '项目管理',
    'title.sysCrawler': '爬虫管理',
    'title.sysResource': '信息资源库管理',
    'title.sysBackend': '后端监控',
    'title.sysSettings': '系统设置',
    'title.sysLlm': 'LLM 配置',
  },
  navigation: {
    'group.overview': '总览',
    'group.dataFacets': '数据侧面',
    'group.graph': '图谱',
    'group.flow': '流程视角',
    'group.system': '系统管理',
    'item.overviewTasks': '任务',
    'item.overviewData': '数据',
    'item.dataDashboard': '数据仪表盘',
    'item.dataMarket': '市场',
    'item.dataSocial': '舆情',
    'item.dataPolicy': '政策',
    'item.dataCatalog': '行业公司/商品/经营',
    'item.graphMarket': '市场图谱',
    'item.graphPolicy': '政策图谱',
    'item.graphSocial': '社媒图谱',
    'item.graphCompany': '公司图谱',
    'item.graphProduct': '商品图谱',
    'item.graphOperation': '电商/经营图谱',
    'item.graphDeep': '市场实体加细图',
    'item.graphBuilder': '新建图谱',
    'item.flowIngest': '采集',
    'item.flowSpecialized': '特化采集',
    'item.flowProcessing': '数据处理',
    'item.flowRawData': '原始数据处理',
    'item.flowExtract': '提取',
    'item.flowAnalysis': '分析',
    'item.flowBoard': '看板',
    'item.flowWriting': '写作工作台',
    'item.flowLlmNodeDesign': 'LLM 节点设计',
    'item.sysProjects': '项目管理',
    'item.sysCrawler': '爬虫管理',
    'item.sysResource': '信息资源库管理',
    'item.sysBackend': '后端监控',
    'item.sysSettings': '系统设置',
    'item.sysLlm': 'LLM 配置',
    'action.createGraph': '新建图谱',
  },
  settings: {
    'locale.label': '界面语言',
    'locale.zh-CN': '简体中文',
    'locale.en-US': 'English',
    'theme.label': '界面主题',
    'theme.light': '浅色',
    'theme.dark': '深色',
    'theme.brand': '品牌',
  },
  shared: {
    loading: '加载中...',
    error: '出错了',
    empty: '暂无数据',
    'action.save': '保存',
    'action.cancel': '取消',
    'action.confirm': '确认',
  },
}

const enUSMessages: CatalogShape = {
  shell: {
    'title.overviewTasks': 'Tasks',
    'title.overviewData': 'Data',
    'title.dataDashboard': 'Data Dashboard',
    'title.dataMarket': 'Market',
    'title.dataSocial': 'Public Opinion',
    'title.dataPolicy': 'Policy',
    'title.dataCatalog': 'Industry/Company/Product/Operation',
    'title.graphMarket': 'Market Graph',
    'title.graphPolicy': 'Policy Graph',
    'title.graphSocial': 'Social Graph',
    'title.graphCompany': 'Company Graph',
    'title.graphProduct': 'Product Graph',
    'title.graphOperation': 'E-commerce/Operation Graph',
    'title.graphDeep': 'Deep Market Entities',
    'title.graphBuilder': 'New Graph',
    'title.flowIngest': 'Ingest',
    'title.flowSpecialized': 'Specialized Ingest',
    'title.flowProcessing': 'Processing',
    'title.flowRawData': 'Raw Data Processing',
    'title.flowExtract': 'Extraction',
    'title.flowAnalysis': 'Analysis',
    'title.flowBoard': 'Board',
    'title.flowWriting': 'Writing Workbench',
    'title.flowLlmNodeDesign': 'LLM Node Design',
    'title.sysProjects': 'Project Management',
    'title.sysCrawler': 'Crawler Management',
    'title.sysResource': 'Resource Library Management',
    'title.sysBackend': 'Backend Monitor',
    'title.sysSettings': 'System Settings',
    'title.sysLlm': 'LLM Config',
  },
  navigation: {
    'group.overview': 'Overview',
    'group.dataFacets': 'Data Facets',
    'group.graph': 'Graph',
    'group.flow': 'Workflow',
    'group.system': 'System',
    'item.overviewTasks': 'Tasks',
    'item.overviewData': 'Data',
    'item.dataDashboard': 'Data Dashboard',
    'item.dataMarket': 'Market',
    'item.dataSocial': 'Public Opinion',
    'item.dataPolicy': 'Policy',
    'item.dataCatalog': 'Industry/Company/Product/Operation',
    'item.graphMarket': 'Market Graph',
    'item.graphPolicy': 'Policy Graph',
    'item.graphSocial': 'Social Graph',
    'item.graphCompany': 'Company Graph',
    'item.graphProduct': 'Product Graph',
    'item.graphOperation': 'E-commerce/Operation Graph',
    'item.graphDeep': 'Deep Market Entities',
    'item.graphBuilder': 'New Graph',
    'item.flowIngest': 'Ingest',
    'item.flowSpecialized': 'Specialized Ingest',
    'item.flowProcessing': 'Processing',
    'item.flowRawData': 'Raw Data Processing',
    'item.flowExtract': 'Extraction',
    'item.flowAnalysis': 'Analysis',
    'item.flowBoard': 'Board',
    'item.flowWriting': 'Writing Workbench',
    'item.flowLlmNodeDesign': 'LLM Node Design',
    'item.sysProjects': 'Project Management',
    'item.sysCrawler': 'Crawler Management',
    'item.sysResource': 'Resource Library Management',
    'item.sysBackend': 'Backend Monitor',
    'item.sysSettings': 'System Settings',
    'item.sysLlm': 'LLM Config',
    'action.createGraph': 'Create Graph',
  },
  settings: {
    'locale.label': 'UI Language',
    'locale.zh-CN': 'Simplified Chinese',
    'locale.en-US': 'English',
    'theme.label': 'Theme',
    'theme.light': 'Light',
    'theme.dark': 'Dark',
    'theme.brand': 'Brand',
  },
  shared: {
    loading: 'Loading...',
    error: 'Something went wrong',
    empty: 'No data',
    'action.save': 'Save',
    'action.cancel': 'Cancel',
    'action.confirm': 'Confirm',
  },
}

export const MESSAGE_CATALOGS: Record<AppLocale, CatalogShape> = {
  'zh-CN': zhCNMessages,
  'en-US': enUSMessages,
}

type NamespaceKey = keyof CatalogShape
type MessageKeysOf<N extends NamespaceKey> = Extract<keyof CatalogShape[N], string>

export type MessageKey = {
  [N in NamespaceKey]: `${N}.${MessageKeysOf<N>}`
}[NamespaceKey]

export function translate(locale: AppLocale, key: MessageKey, fallback?: string): string {
  const [namespace, ...parts] = key.split('.')
  if (!namespace || parts.length === 0) return fallback || key

  const messageKey = parts.join('.')
  const catalog = MESSAGE_CATALOGS[locale]
  const defaultCatalog = MESSAGE_CATALOGS[DEFAULT_APP_LOCALE]

  const value = readCatalogValue(catalog, namespace, messageKey)
  if (value) return value

  const defaultValue = readCatalogValue(defaultCatalog, namespace, messageKey)
  if (defaultValue) return defaultValue

  return fallback || key
}

function readCatalogValue(catalog: CatalogShape, namespace: string, messageKey: string): string {
  if (namespace === 'shell') return catalog.shell[messageKey as keyof CatalogShape['shell']] || ''
  if (namespace === 'navigation') return catalog.navigation[messageKey as keyof CatalogShape['navigation']] || ''
  if (namespace === 'settings') return catalog.settings[messageKey as keyof CatalogShape['settings']] || ''
  if (namespace === 'shared') return catalog.shared[messageKey as keyof CatalogShape['shared']] || ''
  return ''
}
