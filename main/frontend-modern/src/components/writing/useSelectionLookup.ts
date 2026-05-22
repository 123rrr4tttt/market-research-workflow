import { useEffect, useEffectEvent, useRef, useState } from 'react'

export type SelectionLookupStatus = 'idle' | 'loading' | 'success' | 'error'

export type UseSelectionLookupOptions<T> = {
  selectionText: string
  enabled?: boolean
  lookupScopeKey?: string
  debounceMs?: number
  dedupeWindowMs?: number
  minLength?: number
  lookup: (selectionText: string, selectionHash: string) => Promise<T>
}

export type UseSelectionLookupResult<T> = {
  data: T | null
  error: string | null
  status: SelectionLookupStatus
  selectionHash: string
}

function normalizeSelection(value: string) {
  return String(value || '').replace(/\s+/g, ' ').trim()
}

function hashSelection(value: string) {
  let hash = 0
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash * 31 + value.charCodeAt(index)) >>> 0
  }
  return `sel_${hash.toString(16).padStart(8, '0')}`
}

export function useSelectionLookup<T>({
  selectionText,
  enabled = true,
  lookupScopeKey = '',
  debounceMs = 250,
  dedupeWindowMs = 10_000,
  minLength = 2,
  lookup,
}: UseSelectionLookupOptions<T>): UseSelectionLookupResult<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [status, setStatus] = useState<SelectionLookupStatus>('idle')
  const seenLookupRef = useRef<Map<string, number>>(new Map())
  const runLookup = useEffectEvent(lookup)

  const normalizedSelection = normalizeSelection(selectionText)
  const selectionHash = normalizedSelection ? hashSelection(normalizedSelection) : ''
  const scopedLookupKey = lookupScopeKey ? `${selectionHash}:${lookupScopeKey}` : selectionHash
  const shouldLookup = enabled && normalizedSelection.length >= minLength && Boolean(selectionHash)

  useEffect(() => {
    if (!shouldLookup) return

    const lastLookupAt = seenLookupRef.current.get(scopedLookupKey)
    if (lastLookupAt && Date.now() - lastLookupAt < dedupeWindowMs) {
      return
    }

    let active = true
    const timer = window.setTimeout(async () => {
      setStatus('loading')
      setError(null)
      try {
        const nextData = await runLookup(normalizedSelection, selectionHash)
        if (!active) return
        seenLookupRef.current.set(scopedLookupKey, Date.now())
        setData(nextData)
        setStatus('success')
      } catch (cause) {
        if (!active) return
        setStatus('error')
        setError(cause instanceof Error ? cause.message : 'selection_lookup_failed')
      }
    }, debounceMs)

    return () => {
      active = false
      window.clearTimeout(timer)
    }
  }, [debounceMs, dedupeWindowMs, normalizedSelection, scopedLookupKey, selectionHash, shouldLookup])

  return {
    data: shouldLookup ? data : null,
    error: shouldLookup ? error : null,
    status: shouldLookup ? status : 'idle',
    selectionHash,
  }
}

export function getCurrentTextSelection() {
  return normalizeSelection(window.getSelection?.()?.toString() || '')
}
