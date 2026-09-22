import { useState } from 'react'
import {
  Activity,
  Bot,
  Boxes,
  DatabaseZap,
  FolderKanban,
  Gauge,
  Radar,
  Settings2,
  ShieldCheck,
  Workflow,
  type LucideIcon,
} from 'lucide-react'
import { bootstrapCodexCliLogin } from '../../lib/api'
import { translate, useAppLocale, type MessageKey } from '../platform/i18n'
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

const ADMIN_GROUPS: Array<{ labelKey: MessageKey; items: KernelModuleKey[] }> = [
  { labelKey: 'shell.admin.group.operations', items: ['overviewTasks', 'flowProcessing', 'overviewData', 'sysBackend'] },
  { labelKey: 'shell.admin.group.governance', items: ['sysProjects', 'sysCrawler', 'sysResource', 'flowExtract'] },
  { labelKey: 'shell.admin.group.system', items: ['sysSettings', 'sysLlm', 'sysSuccessorRuntime'] },
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
  sysSuccessorRuntime: Gauge,
}

function statusChipClass(value: string | boolean) {
  if (typeof value === 'boolean') return value ? 'chip chip-ok' : 'chip chip-warn'
  const normalized = String(value || '').toLowerCase()
  if (!normalized) return 'chip chip-warn'
  if (normalized.includes('ok')) return 'chip chip-ok'
  if (normalized.includes('degraded') || normalized.includes('loading')) return 'chip chip-warn'
  return 'chip chip-danger'
}

function formatCatalogTemplate(template: string, values: Record<string, string | number>) {
  return template.replace(/\{([A-Za-z0-9_]+)\}/g, (_, key: string) => String(values[key] ?? ''))
}

export default function AdminLayerShell({ activeModule, runtime }: Props) {
  const locale = useAppLocale()
  const t = (key: MessageKey) => translate(locale, key)
  const activeContract = getKernelModuleContract(activeModule)
  const activeLabel = translate(locale, activeContract.navLabelKey, activeModule)
  const loadedProjects = runtime.projects.data?.length || 0
  const [codexActionPending, setCodexActionPending] = useState(false)
  const codexLabel = t(runtime.status.codexReady ? 'shell.admin.status.ready' : codexActionPending ? 'shell.admin.status.starting' : 'shell.admin.status.login')
  const availabilityLabel = (ready: boolean) => t(ready ? 'shell.admin.status.ready' : 'shell.admin.status.missing')

  const handleCodexAuthClick = async () => {
    if (codexActionPending) return

    if (runtime.status.codexReady) {
      await runtime.codexAuth.refetch()
      runtime.setMessage(t('shell.admin.message.codexRefreshed'))
      return
    }

    let deviceTab: Window | null = null
    try {
      setCodexActionPending(true)
      runtime.setMessage(t('shell.admin.message.codexStarting'))
      deviceTab = window.open('about:blank', '_blank')
      const result = await bootstrapCodexCliLogin()
      await runtime.codexAuth.refetch()

      if (result.authenticated) {
        deviceTab?.close()
        runtime.setMessage(t('shell.admin.message.codexAuthenticated'))
        return
      }

      if (result.device_url) {
        if (deviceTab) {
          deviceTab.location.assign(result.device_url)
        } else {
          window.location.assign(result.device_url)
        }
        const code = result.device_code
          ? formatCatalogTemplate(t('shell.admin.message.codexDeviceCodeSuffix'), { deviceCode: result.device_code })
          : ''
        const hint = result.hint
          ? formatCatalogTemplate(t('shell.admin.message.codexDeviceHintSuffix'), { hint: result.hint })
          : ''
        runtime.setMessage(formatCatalogTemplate(t('shell.admin.message.codexDevicePrompt'), { code, hint }))
        return
      }

      deviceTab?.close()
      const deviceUrlMissing = t('shell.admin.message.codexDeviceUrlMissing')
      if (runtime.status.codexOauthEnabled) {
        runtime.setMessage(formatCatalogTemplate(t('shell.admin.message.codexDeviceUnavailable'), { hint: result.hint || deviceUrlMissing }))
        return
      }
      runtime.setMessage(formatCatalogTemplate(t('shell.admin.message.codexNotStarted'), { hint: result.hint || deviceUrlMissing }))
    } catch (error) {
      deviceTab?.close()
      runtime.setMessage(formatCatalogTemplate(t('shell.admin.message.codexStartFailed'), {
        error: error instanceof Error ? error.message : t('shell.admin.message.unknownError'),
      }))
    } finally {
      setCodexActionPending(false)
    }
  }

  return (
    <div className="kernel-admin">
      <header className="kernel-admin__topbar">
        <div className="kernel-admin__topbar-heading">
          <p>
            {formatCatalogTemplate(t('shell.admin.header.surface'), {
              entryRoute: activeContract.entryRoute,
              projectKey: runtime.projectKey,
            })}
          </p>
          <div className="kernel-admin__title-row">
            <h1>{activeLabel}</h1>
            <span>{formatCatalogTemplate(t('shell.admin.header.projectsLoaded'), { count: loadedProjects })}</span>
          </div>
        </div>

        <div className="kernel-admin__topbar-diagnostics">
          <LayerSwitch activeLayer="C" runtime={runtime} />
          <section className="kernel-admin__status-strip" aria-label={t('shell.admin.aria.statusMatrix')}>
            <span className="kernel-admin__status-strip-label">{t('shell.admin.label.statusMatrix')}</span>
            <div className="kernel-admin__status-strip-chips">
              <button className={statusChipClass(runtime.status.api)} onClick={() => runtime.navigateToModule('sysBackend')}>
                API {runtime.status.api}
              </button>
              <button className={statusChipClass(runtime.status.llmReady)} onClick={() => runtime.navigateToModule('sysLlm')}>
                LLM {availabilityLabel(runtime.status.llmReady)}
              </button>
              <button className={statusChipClass(runtime.status.searchReady)} onClick={() => runtime.navigateToModule('sysSettings')}>
                SEARCH {availabilityLabel(runtime.status.searchReady)}
              </button>
              <button className={statusChipClass(runtime.status.newsReady)} onClick={() => runtime.navigateToModule('sysSettings')}>
                NEWS {availabilityLabel(runtime.status.newsReady)}
              </button>
              <button className={statusChipClass(runtime.status.dbReady)} onClick={() => runtime.navigateToModule('sysBackend')}>
                DB {availabilityLabel(runtime.status.dbReady)}
              </button>
              <button
                className={statusChipClass(runtime.status.codexReady)}
                onClick={() => {
                  void handleCodexAuthClick()
                }}
                disabled={codexActionPending}
                title={t(runtime.status.codexOauthEnabled ? 'shell.admin.title.codexOauth' : 'shell.admin.title.codexDeviceAuth')}
              >
                CODEX {codexLabel}
              </button>
            </div>
          </section>
        </div>

        <div className="kernel-admin__project-bar">
          <label className="kernel-admin__control-field">
            <span>{t('shell.admin.label.targetProject')}</span>
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
            onClick={() => runtime.activateMutation.mutate(runtime.pendingProjectKey)}
            disabled={runtime.activateMutation.isPending || !runtime.canActivatePendingProject || runtime.pendingProjectKey === runtime.projectKey}
          >
            {t(runtime.activateMutation.isPending ? 'shell.admin.action.switching' : 'shell.admin.action.activateProject')}
          </button>
          <button
            onClick={() => {
              const target = String(runtime.pendingProjectKey || '').trim()
              if (!target) return
              const ok = window.confirm(formatCatalogTemplate(t('shell.admin.confirm.injectTemplate'), { target }))
              if (!ok) return
              runtime.injectInitialMutation.mutate(target)
            }}
            disabled={runtime.injectInitialMutation.isPending || !runtime.pendingProjectKey}
          >
            {t(runtime.injectInitialMutation.isPending ? 'shell.admin.action.injecting' : 'shell.admin.action.injectTemplate')}
          </button>
          <button type="button" onClick={() => runtime.navigateToModule('overviewTasks')}>
            {t('shell.admin.action.processHome')}
          </button>
          {runtime.message ? <p className="kernel-admin__message">{runtime.message}</p> : null}
        </div>
      </header>

      <section className="kernel-admin__shell">
        <aside className="kernel-admin__sidebar">
          <div className="kernel-admin__brand">
            <span>{t('shell.admin.brand.layerC')}</span>
            <strong>MRW</strong>
          </div>
          <div className="kernel-admin__nav">
            {ADMIN_GROUPS.map((group) => (
              <section key={group.labelKey} className="kernel-admin__section">
                <p className="kernel-admin__section-title">{t(group.labelKey)}</p>
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
          <section className="kernel-admin__panels">
            <section className="kernel-admin__stage">
              <ModuleRenderer
                moduleKey={activeModule}
                projectKey={runtime.projectKey}
                onProjectChange={runtime.setProjectKey}
                shellMode="admin"
              />
            </section>
          </section>
        </section>
      </section>
    </div>
  )
}
