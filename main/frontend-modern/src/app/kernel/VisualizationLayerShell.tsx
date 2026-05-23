import { useEffect } from 'react'
import { translate, useAppLocale } from '../platform/i18n'
import { getKernelModuleContract } from './contracts'
import LayerSwitch from './LayerSwitch'
import { getVisualizationShellCoverage, MODULE_ICON_BY_KEY, VISUALIZATION_SHELL_SECTIONS } from './moduleChrome'
import ModuleRenderer from './ModuleRenderer'
import type { KernelModuleKey } from './types'
import type { useKernelRuntime } from './useKernelRuntime'

type Runtime = ReturnType<typeof useKernelRuntime>

type Props = {
  activeModule: KernelModuleKey
  runtime: Runtime
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
  const activeContract = getKernelModuleContract(activeModule)

  useEffect(() => {
    const coverage = getVisualizationShellCoverage()
    if (!coverage.isComplete) {
      console.warn(translate(locale, 'shell.visualization.coverageMismatch'), coverage)
    }
  }, [locale])

  return (
    <div className={`kernel-visual kernel-visual--${activeModule}`}>
      <header className="kernel-visual__masthead">
        <div className="kernel-visual__eyebrow">{translate(locale, 'shell.visualization.eyebrow')}</div>
        <LayerSwitch activeLayer="B" runtime={runtime} />
        <div className="kernel-visual__heading">
          <div>
            <p>{runtime.projectKey} / observation surface / {activeContract.entryRoute}</p>
            <h1>{translate(locale, activeContract.navLabelKey, activeModule)}</h1>
          </div>
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
          <button className={statusChipClass(runtime.status.api)} onClick={() => runtime.navigateToModule('overviewData')}>
            API {runtime.status.api}
          </button>
          <button className={statusChipClass(runtime.status.llmReady)} onClick={() => runtime.navigateToModule('flowAnalysis')}>
            LLM {translate(locale, runtime.status.llmReady ? 'shell.status.ready' : 'shell.status.missing')}
          </button>
          <button className={statusChipClass(runtime.status.searchReady)} onClick={() => runtime.navigateToModule('dataCatalog')}>
            SEARCH {translate(locale, runtime.status.searchReady ? 'shell.status.ready' : 'shell.status.missing')}
          </button>
          <button className={statusChipClass(runtime.status.newsReady)} onClick={() => runtime.navigateToModule('dataSocial')}>
            NEWS {translate(locale, runtime.status.newsReady ? 'shell.status.ready' : 'shell.status.missing')}
          </button>
          <button className={statusChipClass(runtime.status.dbReady)} onClick={() => runtime.navigateToModule('graphMarket')}>
            DB {translate(locale, runtime.status.dbReady ? 'shell.status.ready' : 'shell.status.missing')}
          </button>
        </div>
      </header>

      <section className="kernel-visual__shell">
        <aside className="kernel-visual__sidebar">
          {VISUALIZATION_SHELL_SECTIONS.map((group) => (
            <section key={group.labelKey} className="kernel-visual__section">
              <p className="kernel-visual__section-title">{translate(locale, group.labelKey)}</p>
              {group.moduleKeys.map((moduleKey) => {
                const Icon = MODULE_ICON_BY_KEY[moduleKey]
                const contract = getKernelModuleContract(moduleKey)
                const active = moduleKey === activeModule
                return (
                  <button
                    key={moduleKey}
                    type="button"
                    className={`kernel-visual__nav-item ${active ? 'is-active' : ''}`.trim()}
                    onClick={() => runtime.navigateToModule(moduleKey)}
                  >
                    <Icon size={15} />
                    <span>{translate(locale, contract.navLabelKey, moduleKey)}</span>
                  </button>
                )
              })}
            </section>
          ))}
        </aside>

        <main className="kernel-visual__main">
          <section className="kernel-visual__stage">
            <ModuleRenderer
              moduleKey={activeModule}
              projectKey={runtime.projectKey}
              onProjectChange={runtime.setProjectKey}
              shellMode="visualization"
            />
          </section>
        </main>
      </section>
    </div>
  )
}
