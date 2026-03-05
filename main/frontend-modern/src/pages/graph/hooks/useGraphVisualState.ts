import { useCallback, useState } from 'react'

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

export function useGraphVisualState() {
  const [visualDraft, setVisualDraft] = useState<GraphVisualState>(INITIAL_GRAPH_VISUAL_STATE)
  const [visualApplied, setVisualApplied] = useState<GraphVisualState>(INITIAL_GRAPH_VISUAL_STATE)

  const updateVisual = useCallback(
    <K extends keyof GraphVisualState>(key: K, value: GraphVisualState[K]) => {
      setVisualDraft((prev) => ({ ...prev, [key]: value }))
      setVisualApplied((prev) => ({ ...prev, [key]: value }))
    },
    [],
  )

  return {
    visualDraft,
    visualApplied,
    setVisualDraft,
    setVisualApplied,
    updateVisual,
  }
}
