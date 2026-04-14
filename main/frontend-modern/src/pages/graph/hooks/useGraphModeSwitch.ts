import { useCallback, useEffect, useRef, useState } from 'react'
import type { RenderMode } from '../renderers/types'

export type ProjectionEngine = 'legacy' | 'force3d'

const DEFAULT_ENGINE_SWITCH_GUARD_MS = 140

type UseGraphModeSwitchOptions = {
  initialRenderMode?: RenderMode
  initialProjectionEngine?: ProjectionEngine
  guardMs?: number
}

export function useGraphModeSwitch(options: UseGraphModeSwitchOptions = {}) {
  const {
    initialRenderMode = '2d',
    initialProjectionEngine = 'force3d',
    guardMs = DEFAULT_ENGINE_SWITCH_GUARD_MS,
  } = options

  const [renderMode, setRenderMode] = useState<RenderMode>(initialRenderMode)
  const [projectionEngine, setProjectionEngine] = useState<ProjectionEngine>(initialProjectionEngine)

  const renderModeRef = useRef<RenderMode>(initialRenderMode)
  const projectionEngineRef = useRef<ProjectionEngine>(initialProjectionEngine)
  const renderModeSwitchTimerRef = useRef<number | null>(null)
  const projectionEngineSwitchTimerRef = useRef<number | null>(null)
  const lastRenderModeSwitchAtRef = useRef(0)
  const lastProjectionEngineSwitchAtRef = useRef(0)

  useEffect(() => {
    renderModeRef.current = renderMode
  }, [renderMode])

  useEffect(() => {
    projectionEngineRef.current = projectionEngine
  }, [projectionEngine])

  const requestRenderModeChange = useCallback((next: RenderMode) => {
    if (next === renderModeRef.current) return
    const now = Date.now()
    const elapsed = now - lastRenderModeSwitchAtRef.current
    if (elapsed >= guardMs) {
      lastRenderModeSwitchAtRef.current = now
      setRenderMode(next)
      return
    }
    if (renderModeSwitchTimerRef.current != null) {
      window.clearTimeout(renderModeSwitchTimerRef.current)
      renderModeSwitchTimerRef.current = null
    }
    renderModeSwitchTimerRef.current = window.setTimeout(() => {
      renderModeSwitchTimerRef.current = null
      if (renderModeRef.current === next) return
      lastRenderModeSwitchAtRef.current = Date.now()
      setRenderMode(next)
    }, guardMs - elapsed)
  }, [guardMs])

  const requestProjectionEngineChange = useCallback((next: ProjectionEngine) => {
    if (next === projectionEngineRef.current) return
    const now = Date.now()
    const elapsed = now - lastProjectionEngineSwitchAtRef.current
    if (elapsed >= guardMs) {
      lastProjectionEngineSwitchAtRef.current = now
      setProjectionEngine(next)
      return
    }
    if (projectionEngineSwitchTimerRef.current != null) {
      window.clearTimeout(projectionEngineSwitchTimerRef.current)
      projectionEngineSwitchTimerRef.current = null
    }
    projectionEngineSwitchTimerRef.current = window.setTimeout(() => {
      projectionEngineSwitchTimerRef.current = null
      if (projectionEngineRef.current === next) return
      lastProjectionEngineSwitchAtRef.current = Date.now()
      setProjectionEngine(next)
    }, guardMs - elapsed)
  }, [guardMs])

  useEffect(() => {
    return () => {
      if (renderModeSwitchTimerRef.current != null) window.clearTimeout(renderModeSwitchTimerRef.current)
      if (projectionEngineSwitchTimerRef.current != null) window.clearTimeout(projectionEngineSwitchTimerRef.current)
    }
  }, [])

  return {
    renderMode,
    projectionEngine,
    renderModeRef,
    requestRenderModeChange,
    requestProjectionEngineChange,
  }
}
