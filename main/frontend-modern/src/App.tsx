import { Suspense, lazy, useEffect, useState } from 'react'
import AppShell from './app/shell/AppShell'
import { resolveStandaloneView } from './app/topology/hash'
import { getProjectKey } from './lib/api'

const LlmDesignerPage = lazy(() => import('./pages/LlmDesignerPage'))
const LazyWritingWorkbenchPage = lazy(() => import('./pages/WritingWorkbenchPage'))

export default function App() {
  const [hash, setHash] = useState(() => window.location.hash)

  useEffect(() => {
    const onHashChange = () => setHash(window.location.hash)
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  const standaloneView = resolveStandaloneView(hash)

  if (standaloneView === 'llm-designer') {
    return (
      <div className="llm-standalone-root">
        <Suspense fallback={null}>
          <LlmDesignerPage projectKey={getProjectKey()} />
        </Suspense>
      </div>
    )
  }

  if (standaloneView === 'writing-workbench') {
    return (
      <div className="writing-standalone-root">
        <Suspense fallback={null}>
          <LazyWritingWorkbenchPage projectKey={getProjectKey()} standalone />
        </Suspense>
      </div>
    )
  }

  return <AppShell />
}
