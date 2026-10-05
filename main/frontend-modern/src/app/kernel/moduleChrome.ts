import {
  AreaChart,
  Brain,
  BookOpen,
  Building2,
  Database,
  DatabaseZap,
  Download,
  Factory,
  FileInput,
  Folders,
  Gauge,
  Landmark,
  Layers,
  LineChart,
  MessageCircleMore,
  MessageSquare,
  Network,
  Orbit,
  Package,
  Puzzle,
  Radar,
  Settings2,
  ShoppingBag,
  Sparkles,
  TrendingUp,
  Wrench,
  Zap,
  type LucideIcon,
} from 'lucide-react'
import type { MessageKey } from '../platform/i18n'
import { moduleManifest, moduleManifestByKey } from './moduleManifest'
import type { KernelModuleKey } from './types'

export const MODULE_ICON_BY_KEY: Record<KernelModuleKey, LucideIcon> = {
  overviewTasks: Zap,
  overviewData: Database,
  dataDashboard: AreaChart,
  dataMarket: LineChart,
  dataSocial: MessageSquare,
  dataPolicy: Landmark,
  dataCatalog: Factory,
  graphMarket: Network,
  graphPolicy: Network,
  graphSocial: Network,
  graphCompany: Building2,
  graphProduct: Package,
  graphOperation: ShoppingBag,
  graphDeep: TrendingUp,
  graphBuilder: Sparkles,
  flowIngest: Download,
  flowSpecialized: Sparkles,
  flowProcessing: FileInput,
  flowRawData: Database,
  flowExtract: Puzzle,
  flowAnalysis: Brain,
  flowBoard: TrendingUp,
  flowWriting: FileInput,
  flowAgentChat: MessageCircleMore,
  flowCell: Orbit,
  flowLlmNodeDesign: Brain,
  sysProjects: Folders,
  sysCrawler: Radar,
  sysResource: DatabaseZap,
  sysBackend: Layers,
  sysSettings: Settings2,
  sysLlm: Wrench,
  sysSuccessorRuntime: Gauge,
  sysBusinessGuide: BookOpen,
}

export type VisualizationShellSection = {
  labelKey: MessageKey
  items: readonly VisualizationShellNavItem[]
}

export type VisualizationShellNavItem = {
  moduleKey: KernelModuleKey
  labelKey: MessageKey
  /** Project-authored label for a graph entry point. */
  label?: string
  /** Identity of a project graph template rendered by the builder entry point. */
  templateKey?: string
}

export const VISUALIZATION_SHELL_SECTIONS: readonly VisualizationShellSection[] = [
  {
    labelKey: 'shell.visualizationSection.stats',
    items: [{ moduleKey: 'dataDashboard', labelKey: 'shell.visualization.statsTitle' }],
  },
  {
    labelKey: 'shell.visualizationSection.projectGraph',
    items: moduleManifest
      .filter((entry) => entry.navGroupKey === 'navigation.group.graph')
      .map((entry) => ({ moduleKey: entry.moduleKey, labelKey: entry.navLabelKey })),
  },
] as const

export type VisualizationShellCoverage = {
  /** Every Layer B module remains routable even when it is not visible in this shell. */
  routableCatalog: readonly KernelModuleKey[]
  visibleNav: readonly KernelModuleKey[]
  invalidVisibleNav: readonly KernelModuleKey[]
  templateKeys: readonly string[]
  invalidTemplateKeys: readonly string[]
  duplicatedTemplateKeys: readonly string[]
  duplicated: readonly KernelModuleKey[]
  isComplete: boolean
}

type GraphNavItemSource = {
  moduleKey: KernelModuleKey
  labelKey: MessageKey
  label?: string
}

type GraphTemplateItemSource = {
  key: string
  name: string
}

export function getVisualizationShellSections(
  graphItems: readonly GraphNavItemSource[],
  templateItems: readonly GraphTemplateItemSource[] = [],
): readonly VisualizationShellSection[] {
  return [
    VISUALIZATION_SHELL_SECTIONS[0],
    {
      labelKey: 'shell.visualizationSection.projectGraph',
      items: graphItems.map((item) => ({
        moduleKey: item.moduleKey,
        labelKey: item.labelKey,
        label: item.label,
      })),
    },
    {
      labelKey: 'shell.visualizationSection.graphTemplates',
      items: templateItems.map((item) => ({
        moduleKey: 'graphBuilder',
        labelKey: moduleManifestByKey.graphBuilder.navLabelKey,
        label: item.name,
        templateKey: item.key,
      })),
    },
  ]
}

export function getVisualizationShellCoverage(
  graphItems: readonly GraphNavItemSource[],
  templateItems: readonly GraphTemplateItemSource[] = [],
): VisualizationShellCoverage {
  const routableCatalog = moduleManifest
    .filter((entry) => entry.layerId === 'B')
    .map((entry) => entry.moduleKey)
  const sections = getVisualizationShellSections(graphItems, [])
  const visibleNav = sections.flatMap((section) => section.items.map((item) => item.moduleKey))
  const routableSet = new Set(routableCatalog)
  const invalidVisibleNav = visibleNav.filter((moduleKey) => !routableSet.has(moduleKey))
  const counts = visibleNav.reduce<Record<KernelModuleKey, number>>(
    (acc, moduleKey) => ({ ...acc, [moduleKey]: (acc[moduleKey] || 0) + 1 }),
    {} as Record<KernelModuleKey, number>,
  )
  const duplicated = Object.keys(counts).filter((moduleKey) => counts[moduleKey as KernelModuleKey] > 1) as KernelModuleKey[]
  const statsEntryCount = visibleNav.filter((moduleKey) => moduleKey === 'dataDashboard').length
  const templateKeys = templateItems.map((item) => item.key)
  const templateKeySet = new Set(templateKeys)
  const invalidTemplateKeys = templateKeys.filter((key) => !key)
  const duplicatedTemplateKeys = templateKeys.filter((key, index) => templateKeys.indexOf(key) !== index)

  return {
    routableCatalog,
    visibleNav,
    invalidVisibleNav,
    templateKeys: Array.from(templateKeySet),
    invalidTemplateKeys,
    duplicatedTemplateKeys,
    duplicated,
    isComplete: invalidVisibleNav.length === 0
      && duplicated.length === 0
      && statsEntryCount === 1
      && invalidTemplateKeys.length === 0
      && duplicatedTemplateKeys.length === 0,
  }
}
