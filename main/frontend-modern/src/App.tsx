import { Suspense, lazy, useEffect, useState } from 'react'
import FrontendKernelApp from './app/kernel/FrontendKernelApp'

const ConceptLabIndexPage = lazy(() => import('./pages/ConceptLabIndexPage'))
const ConceptQuietPage = lazy(() => import('./pages/ConceptQuietPage'))
const ConceptMonolithPage = lazy(() => import('./pages/ConceptMonolithPage'))
const ConceptOrbitalPage = lazy(() => import('./pages/ConceptOrbitalPage'))

export default function App() {
  const [hash, setHash] = useState(() => window.location.hash)

  useEffect(() => {
    const onHashChange = () => setHash(window.location.hash)
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  const decodedHash = decodeURIComponent((hash || '').replace(/^#/, '')).trim().toLowerCase()

  if (decodedHash.includes('design-concepts.html') || decodedHash.includes('concept-lab')) {
    return (
      <Suspense fallback={null}>
        <ConceptLabIndexPage />
      </Suspense>
    )
  }

  if (decodedHash.includes('concept-quiet.html')) {
    return (
      <Suspense fallback={null}>
        <ConceptQuietPage />
      </Suspense>
    )
  }

  if (decodedHash.includes('concept-monolith.html')) {
    return (
      <Suspense fallback={null}>
        <ConceptMonolithPage />
      </Suspense>
    )
  }

  if (decodedHash.includes('concept-orbital.html')) {
    return (
      <Suspense fallback={null}>
        <ConceptOrbitalPage />
      </Suspense>
    )
  }

  return <FrontendKernelApp />
}
