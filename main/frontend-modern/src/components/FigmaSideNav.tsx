import { useState, type ComponentType } from 'react'
import {
  AreaChart,
  Brain,
  Building2,
  ChevronDown,
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
  Plus,
  Puzzle,
  Radar,
  Settings2,
  ShoppingBag,
  ShoppingCart,
  Sparkles,
  TrendingUp,
  Wrench,
  Zap,
} from 'lucide-react'
import { translate, useAppLocale } from '../app/platform/i18n'
import { getModulesByGroup, MODULE_NAV_GROUP_KEYS } from '../app/platform/modules'
import type { ModuleDescriptor, ModuleNavGroupKey } from '../app/platform/modules'
import { resolveInteractionSurface } from '../app/topology/contracts'
import type { InteractionSurface } from '../app/topology/surfaces'

export type NavMode =
  | 'overviewTasks'
  | 'overviewData'
  | 'dataDashboard'
  | 'dataMarket'
  | 'dataSocial'
  | 'dataPolicy'
  | 'dataCatalog'
  | 'graphMarket'
  | 'graphPolicy'
  | 'graphSocial'
  | 'graphCompany'
  | 'graphProduct'
  | 'graphOperation'
  | 'graphDeep'
  | 'graphBuilder'
  | 'flowIngest'
  | 'flowSpecialized'
  | 'flowProcessing'
  | 'flowRawData'
  | 'flowExtract'
  | 'flowAnalysis'
  | 'flowBoard'
  | 'flowWriting'
  | 'flowAgentChat'
  | 'flowLlmNodeDesign'
  | 'sysProjects'
  | 'sysCrawler'
  | 'sysResource'
  | 'sysBackend'
  | 'sysSettings'
  | 'sysLlm'

type Props = {
  mode: NavMode
  onModeChange: (mode: NavMode) => void
  surface: InteractionSurface
  onSurfaceChange: (surface: InteractionSurface) => void
  theme?: 'light' | 'dark' | 'brand'
}

const iconByMode: Record<NavMode, ComponentType<{ size?: number; className?: string }>> = {
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
  graphBuilder: Network,
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

export default function FigmaSideNav({ mode, onModeChange, surface, onSurfaceChange, theme = 'dark' }: Props) {
  const locale = useAppLocale()
  const [expandedByGroup, setExpandedByGroup] = useState<Record<ModuleNavGroupKey, boolean>>(() =>
    Object.fromEntries(MODULE_NAV_GROUP_KEYS.map((groupKey) => [groupKey, true])) as Record<ModuleNavGroupKey, boolean>,
  )
  const visibleGroups: Array<{ groupKey: ModuleNavGroupKey; items: ModuleDescriptor[] }> = MODULE_NAV_GROUP_KEYS
    .map((group) => ({
      groupKey: group,
      items: getModulesByGroup(group).filter((item) => resolveInteractionSurface(item.mode) === surface),
    }))
    .filter((group) => group.items.length > 0)

  return (
    <aside className={`figma-side-nav is-${theme}`} data-node-id="1186:27288" data-surface={surface}>
      <div className="figma-side-nav__surface-switch" role="tablist" aria-label="interaction surface switch">
        <button
          type="button"
          role="tab"
          aria-selected={surface === 'management'}
          className={`figma-side-nav__surface-btn ${surface === 'management' ? 'is-active' : ''}`.trim()}
          onClick={() => onSurfaceChange('management')}
        >
          Management
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={surface === 'workbench'}
          className={`figma-side-nav__surface-btn ${surface === 'workbench' ? 'is-active' : ''}`.trim()}
          onClick={() => onSurfaceChange('workbench')}
        >
          Workbench
        </button>
      </div>
      <div className="figma-side-nav__group">
        {visibleGroups.map((group) => {
          const expanded = expandedByGroup[group.groupKey] || group.items.some((item) => item.mode === mode)
          return (
            <section key={group.groupKey} className="figma-side-nav__section">
              <div className="figma-side-nav__title-row">
                <button
                  type="button"
                  className="figma-side-nav__title"
                  onClick={() => {
                    setExpandedByGroup((prev) => {
                      const currentlyExpanded = prev[group.groupKey] || group.items.some((item) => item.mode === mode)
                      return { ...prev, [group.groupKey]: !currentlyExpanded }
                    })
                  }}
                >
                  <span>{translate(locale, group.groupKey, group.groupKey)}</span>
                  <ChevronDown
                    size={14}
                    className={`figma-side-nav__title-chevron ${expanded ? 'is-open' : ''}`}
                  />
                </button>
                {group.groupKey === 'navigation.group.graph' && group.items.some((item) => item.mode === 'graphBuilder') ? (
                  <button
                    type="button"
                    className={`figma-side-nav__title-plus ${mode === 'graphBuilder' ? 'is-active' : ''}`.trim()}
                    onClick={() => onModeChange('graphBuilder')}
                    title={translate(locale, 'navigation.action.createGraph', 'Create Graph')}
                    aria-label={translate(locale, 'navigation.action.createGraph', 'Create Graph')}
                  >
                    <Plus size={14} />
                  </button>
                ) : null}
              </div>
              {expanded ? group.items.map((item) => {
                const Icon = iconByMode[item.mode] || ShoppingCart
                const active = mode === item.mode
                return (
                  <button
                    type="button"
                    key={item.mode}
                    className={`figma-side-nav__item ${active ? 'is-active' : ''}`}
                    onClick={() => onModeChange(item.mode)}
                  >
                    <Icon size={15} className="figma-side-nav__icon" />
                    <span className="figma-side-nav__label">
                      {translate(locale, item.navLabelKey, item.mode)}
                    </span>
                  </button>
                )
              }) : null}
            </section>
          )
        })}
      </div>
      <button type="button" className="figma-side-nav__fold" aria-label="sidebar hint">
        <Wrench size={14} />
      </button>
    </aside>
  )
}
