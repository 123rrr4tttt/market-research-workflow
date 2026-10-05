import { useCallback, useRef, useState } from 'react'
import type { RenderMode } from '../renderers/types'

// Projection routes share the user's display intent across component mounts.
let graphWorkspaceRenderMode: RenderMode = '2d'

type UseGraphModeSwitchOptions = {
  initialRenderMode?: RenderMode
}

export function useGraphModeSwitch(options: UseGraphModeSwitchOptions = {}) {
  const [renderMode, setRenderMode] = useState<RenderMode>(() => options.initialRenderMode ?? graphWorkspaceRenderMode)
  const renderModeRef = useRef<RenderMode>(renderMode)

  const requestRenderModeChange = useCallback((next: RenderMode) => {
    if (next === renderModeRef.current) return
    renderModeRef.current = next
    graphWorkspaceRenderMode = next
    setRenderMode(next)
  }, [])

  return { renderMode, renderModeRef, requestRenderModeChange }
}
