import { DEFAULT_KERNEL_MODULE, moduleManifest } from './moduleManifest'
import type { KernelModuleKey } from './types'

export const defaultNavMode: KernelModuleKey = DEFAULT_KERNEL_MODULE

export const hashByMode = Object.fromEntries(
  moduleManifest.map((entry) => [entry.moduleKey, entry.legacyHashes[0] || `#${entry.entryRoute}`]),
) as Record<KernelModuleKey, string>

const navModes = new Set<KernelModuleKey>(moduleManifest.map((entry) => entry.moduleKey))

export function parseLegacyHashToMode(rawHash: string): KernelModuleKey | null {
  const decoded = decodeURIComponent((rawHash || '').replace(/^#/, '')).trim().toLowerCase()
  if (!decoded) return null
  if (navModes.has(decoded as KernelModuleKey)) return decoded as KernelModuleKey

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

  if (path.includes('graph-template-new.html') || path.includes('graph-builder.html')) return 'graphBuilder'

  if (path.includes('market-data-visualization.html')) return 'dataMarket'
  if (path.includes('social-media-visualization.html')) return 'dataSocial'
  if (path.includes('policy-visualization.html')) return 'dataPolicy'
  if (path.includes('writing-workbench.html') || path.includes('writing.html')) return 'flowWriting'
  if (path.includes('agent-chat.html') || path.includes('agent.html')) return 'flowAgentChat'
  if (path.includes('workflow-designer.html')) {
    const mode = (query.get('mode') || '').toLowerCase()
    if (mode === 'llm-node-design' || mode === 'llm-node' || mode === 'llm') return 'flowLlmNodeDesign'
    return null
  }
  if (path.includes('llm-designer.html')) return 'flowLlmNodeDesign'
  if (path.includes('project-management.html')) return 'sysProjects'
  if (path.includes('crawler-management.html')) return 'sysCrawler'
  if (path.includes('resource-pool-management.html')) return 'sysResource'
  if (path.includes('backend-dashboard.html')) return 'sysBackend'
  if (path.includes('ingest.html')) {
    if ((query.get('mode') || '').toLowerCase() === 'specialized') return 'flowSpecialized'
    return 'flowIngest'
  }

  return null
}
