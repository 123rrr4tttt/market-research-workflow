import { useEffect, useLayoutEffect, useRef, useState, type RefObject } from 'react'

type PausableGraphEngine = {
  pauseAnimation?: () => void
}

type ResourceLease = {
  key: string
  epoch: number
  width: number
  height: number
}

/**
 * Owns only the display-resource lease (DOM size, canvas generation and mount
 * timing). It deliberately does not own render mode, force parameters, or graph
 * projection state; those remain independently controlled by their owners.
 */
export function useGraphDisplayResourceScheduler(
  resourceKey: string,
  enabled: boolean,
  hostRef: RefObject<HTMLDivElement | null>,
  engineRef: RefObject<PausableGraphEngine | null>,
) {
  const [lease, setLease] = useState<ResourceLease | null>(null)
  const epochRef = useRef(0)
  const ready = enabled && lease?.key === resourceKey

  useLayoutEffect(() => {
    if (!enabled || lease?.key !== resourceKey) {
      engineRef.current?.pauseAnimation?.()
    }
  }, [enabled, engineRef, lease?.key, resourceKey])

  useEffect(() => {
    if (!enabled) return
    if (lease?.key === resourceKey) return

    engineRef.current?.pauseAnimation?.()
    const scheduledEngine = engineRef.current
    let frame = 0
    let attempts = 0
    let canceled = false
    const acquire = () => {
      if (canceled) return
      attempts += 1
      const host = hostRef.current
      const rect = host?.getBoundingClientRect()
      const width = Math.round(rect?.width || 0)
      const height = Math.round(rect?.height || 0)
      if ((width > 0 && height > 0) || attempts >= 8) {
        epochRef.current += 1
        setLease({
          key: resourceKey,
          epoch: epochRef.current,
          width: Math.max(1, width),
          height: Math.max(1, height),
        })
        return
      }
      frame = window.requestAnimationFrame(acquire)
    }
    frame = window.requestAnimationFrame(() => {
      frame = window.requestAnimationFrame(acquire)
    })

    return () => {
      canceled = true
      if (frame) window.cancelAnimationFrame(frame)
      scheduledEngine?.pauseAnimation?.()
    }
  }, [enabled, engineRef, hostRef, lease?.key, resourceKey])

  return {
    ready,
    epoch: ready ? lease?.epoch || 0 : 0,
    width: ready ? lease?.width || 0 : 0,
    height: ready ? lease?.height || 0 : 0,
  }
}
