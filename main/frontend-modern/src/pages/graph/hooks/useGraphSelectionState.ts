import { useEffect, useMemo, useRef, useState } from 'react'
import { collectFocusNodeKeys } from '../domain/topology'

export function useGraphSelectionState(adjacencyConnectedMap: Map<string, Set<string>>) {
  const [selectionEnabled, setSelectionEnabled] = useState(false)
  const [manualSelectedNodeKeys, setManualSelectedNodeKeys] = useState<Set<string>>(new Set())
  const [manualDeselectedNodeKeys, setManualDeselectedNodeKeys] = useState<Set<string>>(new Set())
  const [radiationSelectionByCenter, setRadiationSelectionByCenter] = useState<Record<string, boolean>>({})
  const [selectionPinned, setSelectionPinned] = useState(false)
  const [autoFocusEnabled, setAutoFocusEnabled] = useState(false)
  const [hoverNodeKey, setHoverNodeKey] = useState<string | null>(null)

  const selectionEnabledRef = useRef(false)
  const autoFocusEnabledRef = useRef(false)
  const selectedNodeKeysRef = useRef<Set<string>>(new Set())
  const hoverNodeKeyRef = useRef<string | null>(null)

  const selectedNodeKeys = useMemo(() => {
    const merged = new Set(manualSelectedNodeKeys)
    Object.entries(radiationSelectionByCenter).forEach(([centerKey, enabled]) => {
      if (!enabled) return
      collectFocusNodeKeys(centerKey, adjacencyConnectedMap).forEach((item) => merged.add(item))
    })
    manualDeselectedNodeKeys.forEach((key) => merged.delete(key))
    return merged
  }, [manualSelectedNodeKeys, manualDeselectedNodeKeys, radiationSelectionByCenter, adjacencyConnectedMap])

  useEffect(() => {
    selectionEnabledRef.current = selectionEnabled
  }, [selectionEnabled])

  useEffect(() => {
    autoFocusEnabledRef.current = autoFocusEnabled
  }, [autoFocusEnabled])

  useEffect(() => {
    selectedNodeKeysRef.current = selectedNodeKeys
  }, [selectedNodeKeys])

  useEffect(() => {
    hoverNodeKeyRef.current = hoverNodeKey
  }, [hoverNodeKey])

  useEffect(() => {
    if (selectionPinned && !selectedNodeKeys.size) setSelectionPinned(false)
  }, [selectionPinned, selectedNodeKeys])

  return {
    selectionEnabled,
    setSelectionEnabled,
    manualSelectedNodeKeys,
    setManualSelectedNodeKeys,
    manualDeselectedNodeKeys,
    setManualDeselectedNodeKeys,
    radiationSelectionByCenter,
    setRadiationSelectionByCenter,
    selectionPinned,
    setSelectionPinned,
    autoFocusEnabled,
    setAutoFocusEnabled,
    hoverNodeKey,
    setHoverNodeKey,
    selectedNodeKeys,
    selectionEnabledRef,
    autoFocusEnabledRef,
    selectedNodeKeysRef,
    hoverNodeKeyRef,
  }
}
