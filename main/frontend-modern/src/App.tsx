import { Suspense, lazy, useEffect, useState } from 'react'
import AppShell from './app/shell/AppShell'
import { getProjectKey } from './lib/api'

const LlmDesignerPage = lazy(() => import('./pages/LlmDesignerPage'))
const LazyWritingWorkbenchPage = lazy(() => import('./pages/WritingWorkbenchPage'))

function isStandaloneLlmDesigner(hash: string): boolean {
  const decoded = decodeURIComponent((hash || '').replace(/^#/, '')).trim().toLowerCase()
  if (!decoded) return false
  const [pathQuery] = decoded.split('#')
  const [path, rawQuery = ''] = pathQuery.split('?')
  if (path.includes('llm-designer.html')) return true
  if (!path.includes('workflow-designer.html')) return false
  const query = new URLSearchParams(rawQuery)
  const mode = (query.get('mode') || '').toLowerCase()
  return mode === 'llm-node-design' || mode === 'llm-node' || mode === 'llm'
}

function isStandaloneWritingWorkbench(hash: string): boolean {
  const decoded = decodeURIComponent((hash || '').replace(/^#/, '')).trim().toLowerCase()
  if (!decoded) return false
  const [pathQuery] = decoded.split('#')
  const [path] = pathQuery.split('?')
  return path.includes('writing-workbench.html') || path.includes('writing.html')
}

export default function App() {
  const [hash, setHash] = useState(() => window.location.hash)

  useEffect(() => {
    const onHashChange = () => setHash(window.location.hash)
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  if (isStandaloneLlmDesigner(hash)) {
    return (
      <div className="llm-standalone-root">
        <Suspense fallback={null}>
          <LlmDesignerPage projectKey={getProjectKey()} />
        </Suspense>
      </div>
    )
  }

  if (isStandaloneWritingWorkbench(hash)) {
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
