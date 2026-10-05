import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { PanelLeftClose, PanelLeftOpen } from 'lucide-react'
import { translate, useAppLocale } from '../platform/i18n'
import { getGraphConfig } from '../../lib/api'
import { queryKeys } from '../../lib/queryKeys'
import {
  applyWorkspaceTabBindings,
  buildGraphTemplateRoute,
  coerceGraphProjectionBindings,
  getGraphTemplateKeyFromHash,
  GRAPH_WORKSPACE_TABS,
} from '../../pages/graph/realizer/workspaceNavigation'
import { useProjectGraphTemplates } from '../../pages/graph/hooks/useProjectGraphTemplates'
import LayerSwitch from './LayerSwitch'
import { getVisualizationShellCoverage, getVisualizationShellSections, MODULE_ICON_BY_KEY } from './moduleChrome'
import ModuleRenderer from './ModuleRenderer'
import './visualization-shell.css'
import type { KernelModuleKey } from './types'
import type { useKernelRuntime } from './useKernelRuntime'

type Runtime = ReturnType<typeof useKernelRuntime>

type Props = {
  activeModule: KernelModuleKey
  runtime: Runtime
}

const PROJECT_NAVIGATION_STORAGE_KEY = 'visualization-shell:project-navigation-expanded'

function readProjectNavigationPreference() {
  if (typeof window === 'undefined') return true
  try {
    return window.localStorage.getItem(PROJECT_NAVIGATION_STORAGE_KEY) !== 'false'
  } catch {
    return true
  }
}

function persistProjectNavigationPreference(expanded: boolean) {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(PROJECT_NAVIGATION_STORAGE_KEY, String(expanded))
  } catch {
    return
  }
}

function statusChipClass(value: string | boolean) {
  if (typeof value === 'boolean') return value ? 'chip chip-ok' : 'chip chip-warn'
  const normalized = String(value || '').toLowerCase()
  if (!normalized) return 'chip chip-warn'
  if (normalized.includes('ok')) return 'chip chip-ok'
  if (normalized.includes('degraded') || normalized.includes('loading')) return 'chip chip-warn'
  return 'chip chip-danger'
}

export default function VisualizationLayerShell({ activeModule, runtime }: Props) {
  const locale = useAppLocale()
  const projectKey = runtime.projectKey
  const activeIsGraphModule = activeModule.startsWith('graph')
  const [routeHash, setRouteHash] = useState(() => (typeof window === 'undefined' ? '' : window.location.hash))
  const [projectNavigationExpanded, setProjectNavigationExpanded] = useState(readProjectNavigationPreference)
  // A project may bind the graph entry points; the masthead follows the same
  // declaration as the projection tabs instead of the shared module label.
  const graphConfig = useQuery({
    queryKey: queryKeys.graph.config(projectKey),
    queryFn: getGraphConfig,
    enabled: Boolean(projectKey),
  })
  const declaredProjections = useMemo(
    () => coerceGraphProjectionBindings(graphConfig.data?.graph_projections),
    [graphConfig.data?.graph_projections],
  )
  const workspaceTabs = useMemo(
    () => applyWorkspaceTabBindings(GRAPH_WORKSPACE_TABS, declaredProjections),
    [declaredProjections],
  )
  const graphTemplates = useProjectGraphTemplates(projectKey, Boolean(projectKey))
  const templatesPending = Boolean(projectKey) && graphTemplates.isPending
  const templatesFailed = Boolean(projectKey) && graphTemplates.isError
  const templateItems = useMemo(
    () => (graphTemplates.isSuccess ? graphTemplates.data || [] : []),
    [graphTemplates.data, graphTemplates.isSuccess],
  )
  const navSections = useMemo(
    () => {
      const sections = getVisualizationShellSections(workspaceTabs, templateItems)
      if (!templatesPending && !templatesFailed && templateItems.length === 0) {
        return sections.filter((section) => section.labelKey !== 'shell.visualizationSection.graphTemplates')
      }
      return sections
    },
    [templateItems, templatesFailed, templatesPending, workspaceTabs],
  )
  const activeTemplateKey = useMemo(
    () => getGraphTemplateKeyFromHash(routeHash),
    [routeHash],
  )
  const activeTitle = useMemo(() => {
    if (!activeIsGraphModule) return translate(locale, 'shell.visualization.statsTitle')
    if (activeModule === 'graphBuilder' && activeTemplateKey) {
      const activeTemplate = templateItems.find((item) => item.key === activeTemplateKey)
      return activeTemplate?.name || translate(locale, 'shell.visualizationSection.projectGraph')
    }
    const activeTab = workspaceTabs.find((tab) => tab.moduleKey === activeModule)
    return activeTab?.label || translate(locale, activeTab?.labelKey || 'shell.visualizationSection.projectGraph')
  }, [activeIsGraphModule, activeModule, activeTemplateKey, locale, templateItems, workspaceTabs])

  useEffect(() => {
    if (typeof window === 'undefined') return
    const syncRouteHash = () => setRouteHash(window.location.hash)
    window.addEventListener('hashchange', syncRouteHash)
    syncRouteHash()
    return () => window.removeEventListener('hashchange', syncRouteHash)
  }, [])

  useEffect(() => {
    persistProjectNavigationPreference(projectNavigationExpanded)
  }, [projectNavigationExpanded])

  useEffect(() => {
    const coverage = getVisualizationShellCoverage(workspaceTabs, templateItems)
    if (!coverage.isComplete) {
      console.warn(translate(locale, 'shell.visualization.coverageMismatch'), coverage)
    }
  }, [locale, templateItems, workspaceTabs])

  return (
    <div className={`kernel-visual kernel-visual--${activeModule}`}>
      <header className="kernel-visual__masthead kernel-visual__topbar">
        <div className="kernel-visual__topbar-navigation">
          <LayerSwitch activeLayer="B" runtime={runtime} />
          <button
            type="button"
            className="kernel-visual__nav-toggle"
            data-testid="visual-sidebar-toggle"
            title={translate(locale, projectNavigationExpanded ? 'graphPage.action.collapse' : 'graphPage.action.expand')}
            aria-label={translate(locale, projectNavigationExpanded ? 'graphPage.action.collapse' : 'graphPage.action.expand')}
            aria-expanded={projectNavigationExpanded}
            aria-controls="visual-project-navigation"
            onClick={() => setProjectNavigationExpanded((expanded) => !expanded)}
          >
            {projectNavigationExpanded
              ? <PanelLeftClose size={16} aria-hidden="true" />
              : <PanelLeftOpen size={16} aria-hidden="true" />}
          </button>
        </div>
        <div className="kernel-visual__heading">
          <h1>{activeTitle}</h1>
          <div className="kernel-visual__project-switch">
            <label className="kernel-visual__project-field">
              <span>{translate(locale, 'shell.field.targetProject')}</span>
              <select
                value={runtime.pendingProjectKey}
                onChange={(event) => {
                  runtime.setPendingProjectKey(event.target.value)
                  runtime.setMessage('')
                }}
                disabled={runtime.activateMutation.isPending}
              >
                {runtime.projectOptions.map((item) => (
                  <option key={item.project_key} value={item.project_key}>{item.project_key}</option>
                ))}
              </select>
            </label>
            <button
              type="button"
              onClick={() => runtime.activateMutation.mutate(runtime.pendingProjectKey)}
              disabled={runtime.activateMutation.isPending || !runtime.canActivatePendingProject || runtime.pendingProjectKey === runtime.projectKey}
            >
              {translate(locale, runtime.activateMutation.isPending ? 'shell.status.switching' : 'shell.action.activate')}
            </button>
          </div>
        </div>
        <div className="kernel-visual__status-strip">
          <span className={statusChipClass(runtime.status.api)}>
            API {runtime.status.api}
          </span>
          <span className={statusChipClass(runtime.status.llmReady)}>
            LLM {translate(locale, runtime.status.llmReady ? 'shell.status.ready' : 'shell.status.missing')}
          </span>
          <span className={statusChipClass(runtime.status.searchReady)}>
            SEARCH {translate(locale, runtime.status.searchReady ? 'shell.status.ready' : 'shell.status.missing')}
          </span>
          <span className={statusChipClass(runtime.status.newsReady)}>
            NEWS {translate(locale, runtime.status.newsReady ? 'shell.status.ready' : 'shell.status.missing')}
          </span>
          <span className={statusChipClass(runtime.status.dbReady)}>
            DB {translate(locale, runtime.status.dbReady ? 'shell.status.ready' : 'shell.status.missing')}
          </span>
        </div>
      </header>

      <section className={`kernel-visual__shell ${projectNavigationExpanded ? '' : 'kernel-visual__shell--nav-collapsed'}`.trim()}>
        <aside id="visual-project-navigation" className="kernel-visual__sidebar">
          {navSections.map((group) => (
            <section
              key={group.labelKey}
              className={`kernel-visual__section ${group.labelKey === 'shell.visualizationSection.graphTemplates' ? 'kernel-visual__section--graph-templates' : ''}`.trim()}
            >
              <p className="kernel-visual__section-title">{translate(locale, group.labelKey)}</p>
              {group.labelKey === 'shell.visualizationSection.graphTemplates' && templatesPending ? (
                <p className="kernel-visual__template-status">{translate(locale, 'shared.loading')}</p>
              ) : group.labelKey === 'shell.visualizationSection.graphTemplates' && templatesFailed ? (
                <p
                  className="kernel-visual__template-status"
                  role="status"
                  aria-live="polite"
                >
                  {translate(locale, 'graphPage.error.templateListLoadFailed')}
                </p>
              ) : null}
              {group.items.map((item) => {
                const Icon = MODULE_ICON_BY_KEY[item.moduleKey]
                const active = item.templateKey
                  ? activeModule === 'graphBuilder' && item.templateKey === activeTemplateKey
                  : activeIsGraphModule
                    ? item.moduleKey === activeModule && !(activeModule === 'graphBuilder' && activeTemplateKey)
                    : item.moduleKey === 'dataDashboard'
                return (
                  <button
                    key={item.templateKey || item.moduleKey}
                    type="button"
                    className={`kernel-visual__nav-item ${item.templateKey ? 'kernel-visual__nav-item--template' : ''} ${active ? 'is-active' : ''}`.trim()}
                    onClick={() => {
                      if (item.templateKey) {
                        window.location.assign(`#${buildGraphTemplateRoute(item.templateKey)}`)
                        return
                      }
                      runtime.navigateToModule(item.moduleKey)
                    }}
                  >
                    <Icon size={15} />
                    <span>{item.label || translate(locale, item.labelKey)}</span>
                  </button>
                )
              })}
            </section>
          ))}
        </aside>

        <main className="kernel-visual__main kernel-visual__stage">
          {activeIsGraphModule ? (
            <ModuleRenderer
              moduleKey={activeModule}
              projectKey={runtime.projectKey}
              onProjectChange={runtime.setProjectKey}
              shellMode="visualization"
            />
          ) : (
            <div className="kernel-visual__stats-empty">
              <h2>{translate(locale, 'shell.visualization.statsTitle')}</h2>
              <p>{translate(locale, 'shell.visualization.statsEmpty')}</p>
            </div>
          )}
        </main>
      </section>
    </div>
  )
}
