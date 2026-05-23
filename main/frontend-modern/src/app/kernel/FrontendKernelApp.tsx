import { useEffect, useMemo, useState } from 'react'
import AppShell from '../shell/AppShell'
import { translate, useAppLocale } from '../platform/i18n'
import { applyThemeTokens, useAppTheme } from '../platform/theme'
import AdminLayerShell from './AdminLayerShell'
import { getKernelModuleContract } from './contracts'
import ModuleRenderer from './ModuleRenderer'
import { resolveKernelRoute } from './routes'
import { useKernelRuntime } from './useKernelRuntime'
import VisualizationLayerShell from './VisualizationLayerShell'
import WorkbenchLayerShell from './WorkbenchLayerShell'
import type { KernelModuleKey } from './types'

function readHash() {
  return window.location.hash
}

function LayerBridge({
  moduleKey,
  projectKey,
  onProjectChange,
}: {
  moduleKey: KernelModuleKey
  projectKey: string
  onProjectChange: (next: string) => void
}) {
  const locale = useAppLocale()
  const appTheme = useAppTheme()
  const contract = getKernelModuleContract(moduleKey)
  const layerLabelKey = contract.layerId === 'A' ? 'shell.layer.workbench' : 'shell.layer.visualization'

  return (
    <div className={`kernel-bridge kernel-bridge--${contract.surfaceKind}`}>
      <header className={`kernel-bridge__header app-global-status is-${appTheme}`}>
        <div>
          <span className="kernel-bridge__eyebrow">Kernel Bridge / Layer {contract.layerId}</span>
          <h1>{translate(locale, contract.titleKey, moduleKey)}</h1>
        </div>
        <div className="kernel-bridge__meta">
          <span>{translate(locale, layerLabelKey)}</span>
          <span>{contract.entryRoute}</span>
          <span>{contract.keepLoops.join(' / ')}</span>
        </div>
      </header>
      <section className="kernel-bridge__content">
        <ModuleRenderer moduleKey={moduleKey} projectKey={projectKey} onProjectChange={onProjectChange} />
      </section>
    </div>
  )
}

export default function FrontendKernelApp() {
  const [hash, setHash] = useState(readHash)
  const runtime = useKernelRuntime()
  const route = useMemo(() => resolveKernelRoute(hash), [hash])
  const appTheme = useAppTheme()

  useEffect(() => {
    const onHashChange = () => setHash(readHash())
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  useEffect(() => {
    applyThemeTokens(appTheme)
  }, [appTheme])

  if (route.source === 'unknown') {
    return <AppShell />
  }

  if (route.layerId === 'C') {
    return <AdminLayerShell activeModule={route.moduleKey} runtime={runtime} />
  }

  if (route.layerId === 'A') {
    return <WorkbenchLayerShell activeModule={route.moduleKey} runtime={runtime} />
  }

  if (route.layerId === 'B') {
    return <VisualizationLayerShell activeModule={route.moduleKey} runtime={runtime} />
  }

  return <LayerBridge moduleKey={route.moduleKey} projectKey={runtime.projectKey} onProjectChange={runtime.setProjectKey} />
}
