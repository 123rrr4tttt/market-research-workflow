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

const WORKBENCH_MODULES: KernelModuleKey[] = [
  'flowWriting',
  'flowAgentChat',
  'flowLlmNodeDesign',
  'flowIngest',
  'flowSpecialized',
  'flowRawData',
]

export default function WorkbenchLayerShell({ activeModule, runtime }: Props) {
  const locale = useAppLocale()
  const isWriting = activeModule === 'flowWriting'

  return (
    <div className={`kernel-workbench kernel-workbench--${activeModule}`}>
      <header className="kernel-workbench__rail">
        <div className="kernel-workbench__rail-bar">
          <div className="kernel-workbench__rail-heading">
            <span>workbench</span>
            <strong>{runtime.projectKey}</strong>
          </div>
          <LayerSwitch activeLayer="A" runtime={runtime} />
          <nav className="kernel-workbench__rail-nav" aria-label="Layer A modules">
            {WORKBENCH_MODULES.map((moduleKey) => {
              const contract = getKernelModuleContract(moduleKey)
              const active = moduleKey === activeModule
              return (
                <button
                  key={moduleKey}
                  type="button"
                  className={`kernel-workbench__rail-nav-item ${active ? 'is-active' : ''}`.trim()}
                  onClick={() => runtime.navigateToModule(moduleKey)}
                >
                  {translate(locale, contract.navLabelKey, moduleKey)}
                </button>
              )
            })}
          </nav>
        </div>

        <div className="kernel-workbench__project-control">
          <label className="kernel-workbench__project-field">
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
      </header>

      <section className={`kernel-workbench__main ${isWriting ? 'is-immersive' : ''}`.trim()}>
        <section className={`kernel-workbench__grid ${isWriting ? 'is-immersive' : 'is-single-pane'}`.trim()}>
          <div className="kernel-workbench__stage-column">
            <section className={`kernel-workbench__stage ${isWriting ? 'is-immersive' : ''}`.trim()}>
              <ModuleRenderer
                moduleKey={activeModule}
                projectKey={runtime.projectKey}
                onProjectChange={runtime.setProjectKey}
                shellMode="workbench"
              />
            </section>
          </div>
        </section>
      </section>
    </div>
  )
}
