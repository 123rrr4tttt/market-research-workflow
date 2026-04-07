import type { KernelModuleKey, ModuleManifestEntry } from './types'

const WRITING_LOOPS = ['edit', 'preview', 'template', 'llm-assist', 'citation-basket', 'info-card'] as const
const WORKFLOW_LOOPS = ['node-template', 'edge-link', 'run-params', 'result-review', 'import-export'] as const
const INGEST_LOOPS = ['input-config', 'execute', 'status-feedback', 'result-review'] as const
const RAW_DATA_LOOPS = ['data-input', 'process-chain', 'result-review', 'continue-operation'] as const
const AGENT_CHAT_LOOPS = ['session-context', 'nl-command', 'stage-observe', 'report-review'] as const
const VISUAL_LOOPS = ['view-switch', 'filter', 'object-selection', 'detail-inspect'] as const
const RESOURCE_LOOPS = ['search', 'filter', 'recommendation', 'site-entry-maintenance', 'batch-actions'] as const
const PROCESS_LOOPS = ['task-list', 'detail', 'auto-refresh', 'cancel', 'history'] as const
const GOVERNANCE_LOOPS = ['project-switch', 'crawler-import', 'crawler-deploy', 'crawler-rollback', 'settings-edit'] as const

const DESIGN_SOURCES = {
  figma: 'development/latest-dev-docs/ops-frontend/F_PLAN/frontend-modern-figma-sync-PULL_STATUS_2026-02-27.md',
  quiet: 'main/frontend-modern/src/pages/ConceptQuietPage.tsx',
  orbital: 'main/frontend-modern/src/pages/ConceptOrbitalPage.tsx',
  monolith: 'main/frontend-modern/src/pages/ConceptMonolithPage.tsx',
  outlineSidebar: 'reference-pool/oss/outline/app/components/Sidebar',
  silverbulletChat: 'reference-pool/oss/silverbullet-ai/src/chat-panel.ts',
  codemirrorTooltip: 'reference-pool/oss/codemirror-view/src/tooltip.ts',
} as const

function buildDesignSources(layerId: ModuleManifestEntry['layerId'], moduleKey: KernelModuleKey): readonly string[] {
  const shared = [DESIGN_SOURCES.figma]
  if (layerId === 'A') {
    const sources: string[] = [DESIGN_SOURCES.quiet, DESIGN_SOURCES.outlineSidebar]
    if (moduleKey === 'flowWriting' || moduleKey === 'flowAgentChat') sources.push(DESIGN_SOURCES.silverbulletChat)
    if (moduleKey === 'flowWriting' || moduleKey === 'flowLlmNodeDesign' || moduleKey === 'flowRawData') {
      sources.push(DESIGN_SOURCES.codemirrorTooltip)
    }
    return [...shared, ...sources]
  }
  if (layerId === 'B') {
    return [...shared, DESIGN_SOURCES.orbital, DESIGN_SOURCES.codemirrorTooltip]
  }
  return [...shared, DESIGN_SOURCES.monolith, DESIGN_SOURCES.outlineSidebar]
}

function defineModule(
  moduleKey: KernelModuleKey,
  layerId: ModuleManifestEntry['layerId'],
  surfaceKind: ModuleManifestEntry['surfaceKind'],
  entryRoute: ModuleManifestEntry['entryRoute'],
  legacyHash: string,
  navGroupKey: ModuleManifestEntry['navGroupKey'],
  keepLoops: readonly string[],
  supportsInfoCard: boolean,
): ModuleManifestEntry {
  return {
    moduleKey,
    layerId,
    surfaceKind,
    entryRoute,
    legacyHashes: [legacyHash],
    titleKey: `shell.title.${moduleKey}`,
    navLabelKey: `navigation.item.${moduleKey}`,
    navGroupKey,
    storybookGroup: layerId === 'A' ? 'Workbench' : layerId === 'B' ? 'Visualization' : 'Management',
    requiredContext: ['project_key'],
    keepLoops,
    supportsInfoCard,
    visibleInNav: true,
    enabled: true,
    designSourceRefs: buildDesignSources(layerId, moduleKey),
  }
}

export const DEFAULT_KERNEL_MODULE: KernelModuleKey = 'overviewTasks'

export const moduleManifest: readonly ModuleManifestEntry[] = [
  defineModule('overviewTasks', 'C', 'management', '/admin/process', '#process-management.html', 'navigation.group.overview', PROCESS_LOOPS, false),
  defineModule('overviewData', 'C', 'management', '/admin/ops', '#admin.html', 'navigation.group.overview', ['status-review', 'control-entry'], false),
  defineModule('dataDashboard', 'B', 'visualization', '/visual/dashboard', '#dashboard.html', 'navigation.group.dataFacets', VISUAL_LOOPS, true),
  defineModule('dataMarket', 'B', 'visualization', '/visual/dashboard/market', '#market-data-visualization.html', 'navigation.group.dataFacets', VISUAL_LOOPS, true),
  defineModule('dataSocial', 'B', 'visualization', '/visual/dashboard/social', '#social-media-visualization.html', 'navigation.group.dataFacets', VISUAL_LOOPS, true),
  defineModule('dataPolicy', 'B', 'visualization', '/visual/policy', '#policy-visualization.html', 'navigation.group.dataFacets', VISUAL_LOOPS, true),
  defineModule('dataCatalog', 'B', 'visualization', '/visual/catalog', '#topic-dashboard.html?topic=company', 'navigation.group.dataFacets', VISUAL_LOOPS, true),
  defineModule('graphMarket', 'B', 'visualization', '/visual/graph/market', '#graph.html?type=market', 'navigation.group.graph', VISUAL_LOOPS, true),
  defineModule('graphPolicy', 'B', 'visualization', '/visual/graph/policy', '#graph.html?type=policy', 'navigation.group.graph', VISUAL_LOOPS, true),
  defineModule('graphSocial', 'B', 'visualization', '/visual/graph/social', '#graph.html?type=social', 'navigation.group.graph', VISUAL_LOOPS, true),
  defineModule('graphCompany', 'B', 'visualization', '/visual/graph/company', '#graph.html?type=company', 'navigation.group.graph', VISUAL_LOOPS, true),
  defineModule('graphProduct', 'B', 'visualization', '/visual/graph/product', '#graph.html?type=product', 'navigation.group.graph', VISUAL_LOOPS, true),
  defineModule('graphOperation', 'B', 'visualization', '/visual/graph/operation', '#graph.html?type=operation', 'navigation.group.graph', VISUAL_LOOPS, true),
  defineModule('graphDeep', 'B', 'visualization', '/visual/graph/deep', '#graph.html?type=market_deep_entities', 'navigation.group.graph', VISUAL_LOOPS, true),
  defineModule('graphBuilder', 'B', 'visualization', '/visual/graph/builder', '#graph-template-new.html', 'navigation.group.graph', ['template-builder', 'object-selection', 'detail-inspect'], true),
  defineModule('flowIngest', 'A', 'workbench', '/workbench/ingest', '#ingest.html', 'navigation.group.flow', INGEST_LOOPS, true),
  defineModule('flowSpecialized', 'A', 'workbench', '/workbench/ingest/specialized', '#ingest.html?mode=specialized', 'navigation.group.flow', INGEST_LOOPS, true),
  defineModule('flowProcessing', 'C', 'management', '/admin/process/processing', '#process-management.html?view=processing', 'navigation.group.flow', PROCESS_LOOPS, false),
  defineModule('flowRawData', 'A', 'workbench', '/workbench/raw-data', '#raw-data-processing.html', 'navigation.group.flow', RAW_DATA_LOOPS, true),
  defineModule('flowExtract', 'C', 'management', '/admin/resources/extract', '#admin.html#extracted', 'navigation.group.flow', RESOURCE_LOOPS, false),
  defineModule('flowAnalysis', 'B', 'visualization', '/visual/analysis', '#dashboard.html#analysis', 'navigation.group.flow', VISUAL_LOOPS, true),
  defineModule('flowBoard', 'B', 'visualization', '/visual/board', '#dashboard.html#board', 'navigation.group.flow', VISUAL_LOOPS, true),
  defineModule('flowWriting', 'A', 'workbench', '/workbench/writing', '#writing-workbench.html', 'navigation.group.flow', WRITING_LOOPS, true),
  defineModule('flowAgentChat', 'A', 'workbench', '/workbench/agent', '#agent-chat.html', 'navigation.group.flow', AGENT_CHAT_LOOPS, false),
  defineModule('flowLlmNodeDesign', 'A', 'workbench', '/workbench/designer/llm', '#llm-designer.html', 'navigation.group.flow', WORKFLOW_LOOPS, true),
  defineModule('sysProjects', 'C', 'management', '/admin/projects', '#project-management.html', 'navigation.group.system', GOVERNANCE_LOOPS, false),
  defineModule('sysCrawler', 'C', 'management', '/admin/crawlers', '#crawler-management.html', 'navigation.group.system', GOVERNANCE_LOOPS, false),
  defineModule('sysResource', 'C', 'management', '/admin/resources', '#resource-pool-management.html', 'navigation.group.system', RESOURCE_LOOPS, false),
  defineModule('sysBackend', 'C', 'management', '/admin/backend', '#backend-dashboard.html', 'navigation.group.system', ['status-review', 'ops-control'], false),
  defineModule('sysSettings', 'C', 'management', '/admin/settings', '#settings.html', 'navigation.group.system', ['settings-edit', 'template-config'], false),
  defineModule('sysLlm', 'C', 'management', '/admin/settings/llm', '#settings.html#llm-config', 'navigation.group.system', ['llm-template-edit', 'settings-edit'], false),
] as const

export const moduleManifestByKey = Object.fromEntries(
  moduleManifest.map((entry) => [entry.moduleKey, entry]),
) as Record<KernelModuleKey, ModuleManifestEntry>
