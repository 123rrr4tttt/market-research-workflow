import {
  Activity,
  Bot,
  Boxes,
  DatabaseZap,
  FolderKanban,
  Radar,
  Settings2,
  ShieldCheck,
  Workflow,
  type LucideIcon,
} from 'lucide-react'
import { translate, useAppLocale } from '../platform/i18n'
import { getKernelModuleContract } from './contracts'
import LayerSwitch from './LayerSwitch'
import ModuleRenderer from './ModuleRenderer'
import type { KernelModuleKey } from './types'
import type { useKernelRuntime } from './useKernelRuntime'

type Runtime = ReturnType<typeof useKernelRuntime>

type Props = {
  activeModule: KernelModuleKey
  runtime: Runtime
}

const ADMIN_GROUPS: Array<{ label: string; items: KernelModuleKey[] }> = [
  { label: 'Operations', items: ['overviewTasks', 'flowProcessing', 'overviewData', 'sysBackend'] },
  { label: 'Governance', items: ['sysProjects', 'sysCrawler', 'sysResource', 'flowExtract'] },
  { label: 'System', items: ['sysSettings', 'sysLlm'] },
]

const ICON_BY_MODULE: Record<KernelModuleKey, LucideIcon> = {
  overviewTasks: Activity,
  overviewData: ShieldCheck,
  dataDashboard: Activity,
  dataMarket: Activity,
  dataSocial: Activity,
  dataPolicy: Activity,
  dataCatalog: Activity,
  graphMarket: Activity,
  graphPolicy: Activity,
  graphSocial: Activity,
  graphCompany: Activity,
  graphProduct: Activity,
  graphOperation: Activity,
  graphDeep: Activity,
  graphBuilder: Activity,
  flowIngest: Workflow,
  flowSpecialized: Workflow,
  flowProcessing: Workflow,
  flowRawData: Workflow,
  flowExtract: Boxes,
  flowAnalysis: Activity,
  flowBoard: Activity,
  flowWriting: Activity,
  flowAgentChat: Bot,
  flowLlmNodeDesign: Activity,
  sysProjects: FolderKanban,
  sysCrawler: Radar,
  sysResource: DatabaseZap,
  sysBackend: ShieldCheck,
  sysSettings: Settings2,
  sysLlm: Bot,
}

function statusChipClass(value: string | boolean) {
  if (typeof value === 'boolean') return value ? 'chip chip-ok' : 'chip chip-warn'
  const normalized = String(value || '').toLowerCase()
  if (!normalized) return 'chip chip-warn'
  if (normalized.includes('ok')) return 'chip chip-ok'
  if (normalized.includes('degraded') || normalized.includes('loading')) return 'chip chip-warn'
  return 'chip chip-danger'
}

export default function AdminLayerShell({ activeModule, runtime }: Props) {
  const locale = useAppLocale()
  const activeContract = getKernelModuleContract(activeModule)
  const activeLabel = translate(locale, activeContract.navLabelKey, activeModule)
  const loadedProjects = runtime.projects.data?.length || 0

  return (
    <div className="kernel-admin">
      <header className="kernel-admin__rail">
        <div className="kernel-admin__rail-control">
          <div className="kernel-admin__rail-heading">
            <span>project control</span>
            <strong>{loadedProjects} projects loaded</strong>
          </div>
          <LayerSwitch activeLayer="C" runtime={runtime} />
          <div className="kernel-admin__rail-actions">
            <label className="kernel-admin__control-field">
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
              onClick={() => runtime.activateMutation.mutate(runtime.pendingProjectKey)}
              disabled={runtime.activateMutation.isPending || !runtime.pendingProjectKey || runtime.pendingProjectKey === runtime.projectKey}
            >
              {runtime.activateMutation.isPending ? 'switching' : 'activate project'}
            </button>
            <button
              onClick={() => {
                const target = String(runtime.pendingProjectKey || '').trim()
                if (!target) return
                const ok = window.confirm(`将从 demo_proj 注入初始化到项目 ${target}（覆盖模式）并激活，是否继续？`)
                if (!ok) return
                runtime.injectInitialMutation.mutate(target)
              }}
              disabled={runtime.injectInitialMutation.isPending || !runtime.pendingProjectKey}
            >
              {runtime.injectInitialMutation.isPending ? 'injecting' : 'inject template'}
            </button>
            <button type="button" onClick={() => runtime.navigateToModule('overviewTasks')}>
              process home
            </button>
          </div>
          {runtime.message ? <p className="kernel-admin__message">{runtime.message}</p> : null}
        </div>
      </header>

      <section className="kernel-admin__shell">
        <aside className="kernel-admin__sidebar">
          <div className="kernel-admin__brand">
            <span>Layer C</span>
            <strong>MRW</strong>
          </div>
          <div className="kernel-admin__nav">
            {ADMIN_GROUPS.map((group) => (
              <section key={group.label} className="kernel-admin__section">
                <p className="kernel-admin__section-title">{group.label}</p>
                {group.items.map((moduleKey) => {
                  const Icon = ICON_BY_MODULE[moduleKey]
                  const contract = getKernelModuleContract(moduleKey)
                  const active = moduleKey === activeModule
                  return (
                    <button
                      key={moduleKey}
                      type="button"
                      className={`kernel-admin__nav-item ${active ? 'is-active' : ''}`.trim()}
                      onClick={() => runtime.navigateToModule(moduleKey)}
                    >
                      <Icon size={15} />
                      <span>{translate(locale, contract.navLabelKey, moduleKey)}</span>
                    </button>
                  )
                })}
              </section>
            ))}
          </div>
        </aside>

        <section className="kernel-admin__main">
          <header className="kernel-admin__hero">
            <p>{runtime.projectKey} / management surface / {activeContract.entryRoute}</p>
            <h1>{activeLabel}</h1>
          </header>

          <section className="kernel-admin__status-strip">
            <span className="kernel-admin__status-strip-label">status matrix</span>
            <div className="kernel-admin__status-strip-chips">
              <button className={statusChipClass(runtime.status.api)} onClick={() => runtime.navigateToModule('sysBackend')}>
                API {runtime.status.api}
              </button>
              <button className={statusChipClass(runtime.status.llmReady)} onClick={() => runtime.navigateToModule('sysLlm')}>
                LLM {runtime.status.llmReady ? 'ready' : 'missing'}
              </button>
              <button className={statusChipClass(runtime.status.searchReady)} onClick={() => runtime.navigateToModule('sysSettings')}>
                SEARCH {runtime.status.searchReady ? 'ready' : 'missing'}
              </button>
              <button className={statusChipClass(runtime.status.newsReady)} onClick={() => runtime.navigateToModule('sysSettings')}>
                NEWS {runtime.status.newsReady ? 'ready' : 'missing'}
              </button>
              <button className={statusChipClass(runtime.status.dbReady)} onClick={() => runtime.navigateToModule('sysBackend')}>
                DB {runtime.status.dbReady ? 'ready' : 'missing'}
              </button>
            </div>
          </section>

          <section className="kernel-admin__panels">
            <section className="kernel-admin__stage">
              <ModuleRenderer moduleKey={activeModule} projectKey={runtime.projectKey} onProjectChange={runtime.setProjectKey} />
            </section>
          </section>
        </section>
      </section>
    </div>
  )
}
