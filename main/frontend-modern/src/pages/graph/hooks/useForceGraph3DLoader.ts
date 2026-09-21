import { useCallback, useEffect, useRef, useState, type ComponentType } from 'react'

type ForceGraph3DComponentLike = ComponentType<Record<string, unknown>>

let forceGraph3DPromise: Promise<{ default: ForceGraph3DComponentLike }> | null = null
const MAX_RETRY = 2

export function useForceGraph3DLoader(enabled: boolean) {
  const [component, setComponent] = useState<ForceGraph3DComponentLike | null>(null)
  const [loadFailure, setLoadFailure] = useState<{ attempt: string; message: string } | null>(null)
  const [retryNonce, setRetryNonce] = useState(0)
  const retryCountRef = useRef(0)
  const currentAttempt = `${enabled ? 'enabled' : 'disabled'}:${retryNonce}`
  const error = loadFailure?.attempt === currentAttempt ? loadFailure.message : null

  const retry = useCallback(() => {
    retryCountRef.current = 0
    forceGraph3DPromise = null
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
      forceGraph3DPromise = import('react-force-graph-3d') as Promise<{
        default: ForceGraph3DComponentLike
      }>
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
        forceGraph3DPromise = null
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
