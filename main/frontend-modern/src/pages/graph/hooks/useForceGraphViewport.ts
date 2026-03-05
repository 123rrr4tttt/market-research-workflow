import { useEffect, useState, type RefObject } from 'react'

export function useForceGraphViewport(
  enabled: boolean,
  containerRef: RefObject<HTMLDivElement | null>,
) {
  const [viewport, setViewport] = useState({ width: 1280, height: 720 })

  useEffect(() => {
    if (!enabled) return
    const el = containerRef.current
    if (!el) return
    const updateViewport = () => {
      const width = Math.round(el.clientWidth || 0)
      const height = Math.round(el.clientHeight || 0)
      if (width <= 0 || height <= 0) return
      setViewport((prev) => (
        prev.width === width && prev.height === height
          ? prev
          : { width, height }
      ))
    }
    updateViewport()
    const observer = new ResizeObserver(updateViewport)
    observer.observe(el)
    window.addEventListener('resize', updateViewport)
    return () => {
      observer.disconnect()
      window.removeEventListener('resize', updateViewport)
    }
  }, [enabled, containerRef])

  return viewport
}
