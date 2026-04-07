import { Activity, BarChart3, Compass, Network, Sparkles, type LucideIcon } from 'lucide-react'
import { translate, useAppLocale } from '../platform/i18n'
import { getKernelModuleContract } from './contracts'
import ModuleRenderer from './ModuleRenderer'
import type { KernelModuleKey } from './types'
import type { useKernelRuntime } from './useKernelRuntime'

type Runtime = ReturnType<typeof useKernelRuntime>

type Props = {
  activeModule: KernelModuleKey
  runtime: Runtime
}

const VISUAL_GROUPS: Array<{ label: string; items: KernelModuleKey[] }> = [
  { label: 'Signals', items: ['dataDashboard', 'dataMarket', 'dataSocial', 'dataPolicy', 'dataCatalog'] },
  { label: 'Graphs', items: ['graphMarket', 'graphPolicy', 'graphSocial', 'graphCompany', 'graphProduct', 'graphOperation', 'graphDeep', 'graphBuilder'] },
  { label: 'Review', items: ['flowAnalysis', 'flowBoard'] },
]

const ICON_BY_MODULE: Record<KernelModuleKey, LucideIcon> = {
  overviewTasks: Activity,
  overviewData: Activity,
  dataDashboard: BarChart3,
  dataMarket: Compass,
  dataSocial: Compass,
  dataPolicy: Compass,
  dataCatalog: Compass,
  graphMarket: Network,
  graphPolicy: Network,
  graphSocial: Network,
  graphCompany: Network,
  graphProduct: Network,
  graphOperation: Network,
  graphDeep: Network,
  graphBuilder: Sparkles,
  flowIngest: Activity,
  flowSpecialized: Activity,
  flowProcessing: Activity,
  flowRawData: Activity,
  flowExtract: Activity,
  flowAnalysis: BarChart3,
  flowBoard: BarChart3,
  flowWriting: Activity,
  flowAgentChat: Activity,
  flowLlmNodeDesign: Activity,
  sysProjects: Activity,
  sysCrawler: Activity,
  sysResource: Activity,
  sysBackend: Activity,
  sysSettings: Activity,
  sysLlm: Activity,
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

  return (
    <div className={`kernel-visual kernel-visual--${activeModule}`}>
      <header className="kernel-visual__masthead">
        <div className="kernel-visual__eyebrow">Layer B / Visualization</div>
        <div className="kernel-visual__heading">
          <div>
            <p>{runtime.projectKey} / observation surface / {activeContract.entryRoute}</p>
            <h1>{translate(locale, activeContract.navLabelKey, activeModule)}</h1>
          </div>
          <div className="kernel-visual__project-switch">
            <label className="kernel-visual__project-field">
              <span>target project</span>
              <select
                value={runtime.pendingProjectKey}
                onChange={(event) => {
                  runtime.setPendingProjectKey(event.target.value)
                  runtime.setMessage('')
                }}
                disabled={runtime.activateMutation.isPending}
              >
                {!runtime.projects.data?.find((item) => item.project_key === runtime.projectKey) ? (
                  <option value={runtime.projectKey}>{runtime.projectKey}</option>
                ) : null}
                {(runtime.projects.data || []).map((item) => (
                  <option key={item.project_key} value={item.project_key}>{item.project_key}</option>
                ))}
              </select>
            </label>
            <button
              type="button"
              onClick={() => runtime.activateMutation.mutate(runtime.pendingProjectKey)}
              disabled={runtime.activateMutation.isPending || !runtime.pendingProjectKey || runtime.pendingProjectKey === runtime.projectKey}
            >
              {runtime.activateMutation.isPending ? 'switching' : 'activate'}
            </button>
          </div>
        </div>
        <div className="kernel-visual__status-strip">
          <button className={statusChipClass(runtime.status.api)} onClick={() => runtime.navigateToModule('overviewData')}>
            API {runtime.status.api}
          </button>
          <button className={statusChipClass(runtime.status.llmReady)} onClick={() => runtime.navigateToModule('flowAnalysis')}>
            LLM {runtime.status.llmReady ? 'ready' : 'missing'}
          </button>
          <button className={statusChipClass(runtime.status.searchReady)} onClick={() => runtime.navigateToModule('dataCatalog')}>
            SEARCH {runtime.status.searchReady ? 'ready' : 'missing'}
          </button>
          <button className={statusChipClass(runtime.status.newsReady)} onClick={() => runtime.navigateToModule('dataSocial')}>
            NEWS {runtime.status.newsReady ? 'ready' : 'missing'}
          </button>
          <button className={statusChipClass(runtime.status.dbReady)} onClick={() => runtime.navigateToModule('graphMarket')}>
            DB {runtime.status.dbReady ? 'ready' : 'missing'}
          </button>
        </div>
      </header>

      <section className="kernel-visual__shell">
        <aside className="kernel-visual__sidebar">
          {VISUAL_GROUPS.map((group) => (
            <section key={group.label} className="kernel-visual__section">
              <p className="kernel-visual__section-title">{group.label}</p>
              {group.items.map((moduleKey) => {
                const Icon = ICON_BY_MODULE[moduleKey]
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
