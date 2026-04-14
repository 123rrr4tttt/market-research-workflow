import { useCallback, useEffect, useRef, useState } from 'react'

export type GraphVisualState = {
  repulsion: number
  gravityPercent: number
  nodeScale: number
  nodeContrastCentral: number
  nodeContrastNeighbor: number
  nodeAlpha: number
  edgeWidth: number
  edgeAlpha: number
  showLabel: boolean
}

const INITIAL_GRAPH_VISUAL_STATE: GraphVisualState = {
  repulsion: 180,
  gravityPercent: 100,
  nodeScale: 100,
  nodeContrastCentral: 0,
  nodeContrastNeighbor: 0,
  nodeAlpha: 72,
  edgeWidth: 100,
  edgeAlpha: 100,
  showLabel: true,
}

const DEFAULT_APPLY_DELAY_MS = 120

type UpdateVisualOptions = {
  immediate?: boolean
  delayMs?: number
  mode?: 'debounce' | 'raf' | 'throttle'
}

export function useGraphVisualState() {
  const [visualDraft, setVisualDraft] = useState<GraphVisualState>(INITIAL_GRAPH_VISUAL_STATE)
  const [visualApplied, setVisualApplied] = useState<GraphVisualState>(INITIAL_GRAPH_VISUAL_STATE)
  const applyTimerRef = useRef<number | null>(null)
  const applyRafRef = useRef<number | null>(null)
  const pendingPatchRef = useRef<Partial<GraphVisualState>>({})
  const visualInteractionActiveRef = useRef(false)
  const lastApplyAtRef = useRef(0)

  const flushPendingPatch = useCallback(() => {
    const patch = pendingPatchRef.current
    pendingPatchRef.current = {}
    if (!Object.keys(patch).length) return
    lastApplyAtRef.current = Date.now()
    setVisualApplied((prev) => ({ ...prev, ...patch }))
  }, [])

  useEffect(() => {
    return () => {
      if (applyTimerRef.current !== null) {
        window.clearTimeout(applyTimerRef.current)
      }
      if (applyRafRef.current !== null) {
        window.cancelAnimationFrame(applyRafRef.current)
      }
    }
  }, [])

  const scheduleRafApply = useCallback(() => {
    if (applyRafRef.current !== null) return
    applyRafRef.current = window.requestAnimationFrame(() => {
      applyRafRef.current = null
      flushPendingPatch()
    })
  }, [flushPendingPatch])

  const updateVisual = useCallback(
    <K extends keyof GraphVisualState>(key: K, value: GraphVisualState[K], options?: UpdateVisualOptions) => {
      const immediate = options?.immediate ?? false
      const delayMs = options?.delayMs ?? DEFAULT_APPLY_DELAY_MS
      const mode = options?.mode || (visualInteractionActiveRef.current ? 'raf' : 'debounce')
      setVisualDraft((prev) => ({ ...prev, [key]: value }))

      if (immediate) {
        if (applyTimerRef.current !== null) {
          window.clearTimeout(applyTimerRef.current)
          applyTimerRef.current = null
        }
        if (applyRafRef.current !== null) {
          window.cancelAnimationFrame(applyRafRef.current)
          applyRafRef.current = null
        }
        pendingPatchRef.current[key] = value
        flushPendingPatch()
        return
      }

      pendingPatchRef.current[key] = value
      if (mode === 'raf') {
        if (applyTimerRef.current !== null) {
          window.clearTimeout(applyTimerRef.current)
          applyTimerRef.current = null
        }
        scheduleRafApply()
        return
      }
      if (mode === 'throttle') {
        const now = Date.now()
        const waitMs = Math.max(0, delayMs)
        const elapsed = now - lastApplyAtRef.current
        if (applyTimerRef.current !== null) {
          window.clearTimeout(applyTimerRef.current)
          applyTimerRef.current = null
        }
        if (elapsed >= waitMs) {
          flushPendingPatch()
          return
        }
        applyTimerRef.current = window.setTimeout(() => {
          applyTimerRef.current = null
          flushPendingPatch()
        }, waitMs - elapsed)
        return
      }
      if (applyTimerRef.current !== null) {
        window.clearTimeout(applyTimerRef.current)
      }
      applyTimerRef.current = window.setTimeout(() => {
        applyTimerRef.current = null
        flushPendingPatch()
      }, delayMs)
    },
    [flushPendingPatch, scheduleRafApply],
  )

  const startVisualInteraction = useCallback(() => {
    visualInteractionActiveRef.current = true
  }, [])

  const endVisualInteraction = useCallback(() => {
    visualInteractionActiveRef.current = false
    if (applyTimerRef.current !== null) {
      window.clearTimeout(applyTimerRef.current)
      applyTimerRef.current = null
    }
    if (applyRafRef.current !== null) {
      window.cancelAnimationFrame(applyRafRef.current)
      applyRafRef.current = null
    }
    flushPendingPatch()
  }, [flushPendingPatch])

  return {
    visualDraft,
    visualApplied,
    setVisualDraft,
    setVisualApplied,
    updateVisual,
    startVisualInteraction,
    endVisualInteraction,
  }
}
