import {
  AreaChart,
  Brain,
  Building2,
  Database,
  DatabaseZap,
  Download,
  Factory,
  FileInput,
  Folders,
  Landmark,
  Layers,
  LineChart,
  MessageCircleMore,
  MessageSquare,
  Network,
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
import { moduleManifest } from './moduleManifest'
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
  flowLlmNodeDesign: Brain,
  sysProjects: Folders,
  sysCrawler: Radar,
  sysResource: DatabaseZap,
  sysBackend: Layers,
  sysSettings: Settings2,
  sysLlm: Wrench,
}

export type VisualizationShellSection = {
  labelKey: MessageKey
  moduleKeys: readonly KernelModuleKey[]
}

export const VISUALIZATION_SHELL_SECTIONS: readonly VisualizationShellSection[] = [
  { labelKey: 'shell.visualizationSection.signals', moduleKeys: ['dataDashboard', 'dataMarket', 'dataSocial', 'dataPolicy', 'dataCatalog'] },
  { labelKey: 'shell.visualizationSection.graphs', moduleKeys: ['graphMarket', 'graphPolicy', 'graphSocial', 'graphCompany', 'graphProduct', 'graphOperation', 'graphDeep', 'graphBuilder'] },
  { labelKey: 'shell.visualizationSection.review', moduleKeys: ['flowAnalysis', 'flowBoard'] },
] as const

export type VisualizationShellCoverage = {
  expected: readonly KernelModuleKey[]
  covered: readonly KernelModuleKey[]
  missing: readonly KernelModuleKey[]
  extra: readonly KernelModuleKey[]
  duplicated: readonly KernelModuleKey[]
  isComplete: boolean
}

export function getVisualizationShellCoverage(): VisualizationShellCoverage {
  const expected = moduleManifest
    .filter((entry) => entry.layerId === 'B' && entry.visibleInNav && entry.enabled)
    .map((entry) => entry.moduleKey)
  const covered = VISUALIZATION_SHELL_SECTIONS.flatMap((section) => section.moduleKeys)
  const expectedSet = new Set(expected)
  const coveredSet = new Set(covered)
  const missing = expected.filter((moduleKey) => !coveredSet.has(moduleKey))
  const extra = covered.filter((moduleKey) => !expectedSet.has(moduleKey))
  const counts = covered.reduce<Record<KernelModuleKey, number>>(
    (acc, moduleKey) => ({ ...acc, [moduleKey]: (acc[moduleKey] || 0) + 1 }),
    {} as Record<KernelModuleKey, number>,
  )
  const duplicated = Object.keys(counts).filter((moduleKey) => counts[moduleKey as KernelModuleKey] > 1) as KernelModuleKey[]

  return {
    expected,
    covered,
    missing,
    extra,
    duplicated,
    isComplete: missing.length === 0 && extra.length === 0 && duplicated.length === 0,
  }
}
