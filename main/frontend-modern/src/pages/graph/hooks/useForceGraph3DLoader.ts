import { useCallback, useEffect, useMemo, useRef, useState, type ComponentType, type RefAttributes } from 'react'
import type { ForceGraphMethods, ForceGraphProps } from 'react-force-graph-3d'

type ForceGraph3DComponentLike = ComponentType<ForceGraphProps & RefAttributes<ForceGraphMethods>>
type LoadAttempt = { enabled: boolean; retryNonce: number }

let forceGraph3DPromise: Promise<{ default: ForceGraph3DComponentLike }> | null = null
const MAX_RETRY = 2

export function useForceGraph3DLoader(enabled: boolean) {
  const [component, setComponent] = useState<ForceGraph3DComponentLike | null>(null)
  const [loadFailure, setLoadFailure] = useState<{ attempt: LoadAttempt; message: string } | null>(null)
  const [retryNonce, setRetryNonce] = useState(0)
  const retryCountRef = useRef(0)
  const currentAttempt = useMemo(() => ({ enabled, retryNonce }), [enabled, retryNonce])
  const error = loadFailure?.attempt === currentAttempt ? loadFailure.message : null

  const retry = useCallback(() => {
    retryCountRef.current = 0
    setRetryNonce((value) => value + 1)
  }, [])

  useEffect(() => {
    if (!enabled) {
      retryCountRef.current = 0
      return
    }
    if (component) return

    let canceled = false
    let timer: ReturnType<typeof setTimeout> | null = null

    if (!forceGraph3DPromise) {
      const pending = (import('react-force-graph-3d') as Promise<{
        default: ForceGraph3DComponentLike
      }>).catch((error: unknown) => {
        // Invalidate failed imports even when every subscriber has unmounted.
        if (forceGraph3DPromise === pending) forceGraph3DPromise = null
        throw error
      })
      forceGraph3DPromise = pending
    }

    void forceGraph3DPromise
      .then((mod) => {
        if (canceled) return
        retryCountRef.current = 0
        setComponent(() => mod.default)
        setLoadFailure(null)
      })
      .catch((err: unknown) => {
        if (canceled) return
        const message = err instanceof Error ? err.message : '加载失败'
        setLoadFailure({ attempt: currentAttempt, message })
        if (retryCountRef.current >= MAX_RETRY) return
        const backoffMs = 300 * 2 ** retryCountRef.current
        retryCountRef.current += 1
        timer = setTimeout(() => {
          if (canceled) return
          setRetryNonce((value) => value + 1)
        }, backoffMs)
      })

    return () => {
      canceled = true
      if (timer) clearTimeout(timer)
    }
  }, [component, currentAttempt, enabled])

  return { component, error, retry }
}
