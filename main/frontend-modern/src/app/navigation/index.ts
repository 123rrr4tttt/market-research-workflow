import type { NavMode } from '../../components/FigmaSideNav'

export const defaultNavMode: NavMode = 'overviewTasks'

export const hashByMode: Record<NavMode, string> = {
  overviewTasks: '#process-management.html',
  overviewData: '#admin.html',
  dataDashboard: '#dashboard.html',
  dataMarket: '#market-data-visualization.html',
  dataSocial: '#social-media-visualization.html',
  dataPolicy: '#policy-visualization.html',
  dataCatalog: '#topic-dashboard.html?topic=company',
  graphMarket: '#graph.html?type=market',
  graphPolicy: '#graph.html?type=policy',
  graphSocial: '#graph.html?type=social',
  graphCompany: '#graph.html?type=company',
  graphProduct: '#graph.html?type=product',
  graphOperation: '#graph.html?type=operation',
  graphDeep: '#graph.html?type=market_deep_entities',
  flowIngest: '#ingest.html',
  flowSpecialized: '#ingest.html?mode=specialized',
  flowProcessing: '#process-management.html?view=processing',
  flowRawData: '#raw-data-processing.html',
  flowExtract: '#admin.html#extracted',
  flowAnalysis: '#dashboard.html#analysis',
  flowBoard: '#dashboard.html#board',
  flowWorkflow: '#workflow-designer.html',
  sysProjects: '#project-management.html',
  sysResource: '#resource-pool-management.html',
  sysBackend: '#backend-dashboard.html',
  sysSettings: '#settings.html',
  sysLlm: '#settings.html#llm-config',
}

const navModes = new Set<NavMode>(Object.keys(hashByMode) as NavMode[])

export function parseLegacyHashToMode(rawHash: string): NavMode | null {
  const decoded = decodeURIComponent((rawHash || '').replace(/^#/, '')).trim().toLowerCase()
  if (!decoded) return null
  if (navModes.has(decoded as NavMode)) return decoded as NavMode

  if (decoded.includes('raw-data-processing.html') || decoded === 'raw-data' || decoded.includes('/raw-data')) {
    return 'flowRawData'
  }

  const [pathQuery, hashFragment = ''] = decoded.split('#')
  const [path, rawQuery = ''] = pathQuery.split('?')
  const query = new URLSearchParams(rawQuery)
  const fragment = hashFragment.trim()

  if (path.includes('settings.html')) {
    if (fragment.includes('llm-config')) return 'sysLlm'
    return 'sysSettings'
  }

  if (path.includes('admin.html')) {
    if (fragment.includes('extracted') || fragment.includes('extract')) return 'flowExtract'
    return 'overviewData'
  }

  if (path.includes('process-management.html')) {
    if (query.get('view') === 'processing' || fragment.includes('processing')) return 'flowProcessing'
    return 'overviewTasks'
  }

  if (path.includes('dashboard.html')) {
    if (fragment.includes('analysis')) return 'flowAnalysis'
    if (fragment.includes('board')) return 'flowBoard'
    if (fragment.includes('market')) return 'dataMarket'
    if (fragment.includes('social')) return 'dataSocial'
    return 'dataDashboard'
  }

  if (path.includes('topic-dashboard.html')) {
    const topic = (query.get('topic') || '').toLowerCase()
    if (topic === 'company') return 'graphCompany'
    if (topic === 'product' || topic === 'commodity') return 'graphProduct'
    if (topic === 'operation' || topic === 'ecom') return 'graphOperation'
    if (topic === 'policy') return 'dataPolicy'
    if (topic === 'social' || topic === 'public-opinion') return 'dataSocial'
    if (topic === 'market') return 'dataMarket'
    return 'dataCatalog'
  }

  if (path.includes('graph.html')) {
    const graphType = (query.get('type') || '').toLowerCase()
    if (graphType === 'policy') return 'graphPolicy'
    if (graphType === 'social') return 'graphSocial'
    if (graphType === 'company') return 'graphCompany'
    if (graphType === 'product' || graphType === 'commodity') return 'graphProduct'
    if (graphType === 'operation' || graphType === 'ecom') return 'graphOperation'
    if (graphType === 'deep' || graphType === 'market_deep_entities') return 'graphDeep'
    return 'graphMarket'
  }

  if (path.includes('market-data-visualization.html')) return 'dataMarket'
  if (path.includes('social-media-visualization.html')) return 'dataSocial'
  if (path.includes('policy-visualization.html')) return 'dataPolicy'
  if (path.includes('raw-data-processing.html') || path.includes('raw-data.html')) return 'flowRawData'
  if (path.includes('workflow-designer.html')) return 'flowWorkflow'
  if (path.includes('project-management.html')) return 'sysProjects'
  if (path.includes('resource-pool-management.html')) return 'sysResource'
  if (path.includes('backend-dashboard.html')) return 'sysBackend'
  if (path.includes('ingest.html')) {
    if ((query.get('mode') || '').toLowerCase() === 'specialized') return 'flowSpecialized'
    return 'flowIngest'
  }

  return null
}
