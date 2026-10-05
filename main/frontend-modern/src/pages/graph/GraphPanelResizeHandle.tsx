import {
  useEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
  type RefObject,
} from 'react'
import { Grip } from 'lucide-react'

const MIN_PANEL_WIDTH = 180
const MIN_PANEL_HEIGHT = 100
const KEYBOARD_RESIZE_STEP = 16

type Props = {
  panelRef: RefObject<HTMLElement | null>
  onResize: (width: number, height: number) => void
  anchor?: 'left' | 'right'
  label: string
  testId?: string
}

type DragState = {
  pointerId: number
  startClientX: number
  startClientY: number
  startWidth: number
  startHeight: number
}

type PanelGeometry = {
  width: number
  height: number
  maxWidth: number
  maxHeight: number
}

const SCENE_BOUNDARY = 4

function availableSize(value: number) {
  return Math.max(0, value)
}

function clampPanelSize(value: number, minimum: number, maximum: number) {
  if (maximum < minimum) return Math.round(maximum)
  return Math.round(Math.min(Math.max(value, minimum), maximum))
}

function readPanelGeometry(panel: HTMLElement, anchor: 'left' | 'right'): PanelGeometry {
  const panelRect = panel.getBoundingClientRect()
  const sceneRect = panel.closest('#graph-projection-panel')?.getBoundingClientRect()
  const panelStyle = window.getComputedStyle(panel)
  const isBottomAnchored = panelStyle.top === 'auto' && panelStyle.bottom !== 'auto'

  return {
    width: panelRect.width,
    height: panelRect.height,
    maxWidth: availableSize(sceneRect
      ? anchor === 'right'
        ? panelRect.right - sceneRect.left - SCENE_BOUNDARY
        : sceneRect.right - panelRect.left - SCENE_BOUNDARY
      : panelRect.width),
    maxHeight: availableSize(sceneRect
      ? isBottomAnchored
        ? panelRect.bottom - sceneRect.top - SCENE_BOUNDARY
        : sceneRect.bottom - panelRect.top - SCENE_BOUNDARY
      : panelRect.height),
  }
}

export function GraphPanelResizeHandle({
  panelRef,
  onResize,
  anchor = 'left',
  label,
  testId,
}: Props) {
  const handleRef = useRef<HTMLButtonElement | null>(null)
  const dragRef = useRef<DragState | null>(null)
  const onResizeRef = useRef(onResize)
  const [activePointerId, setActivePointerId] = useState<number | null>(null)

  useEffect(() => {
    onResizeRef.current = onResize
  }, [onResize])

  useEffect(() => {
    if (activePointerId === null) return

    const handle = handleRef.current
    const previousCursor = document.body.style.cursor
    const previousUserSelect = document.body.style.userSelect
    document.body.style.cursor = 'nwse-resize'
    document.body.style.userSelect = 'none'

    const emitSize = (nextWidth: number, nextHeight: number) => {
      const panel = panelRef.current
      if (!panel) return
      const geometry = readPanelGeometry(panel, anchor)

      onResizeRef.current(
        clampPanelSize(nextWidth, MIN_PANEL_WIDTH, geometry.maxWidth),
        clampPanelSize(nextHeight, MIN_PANEL_HEIGHT, geometry.maxHeight),
      )
    }

    const handleMove = (event: PointerEvent) => {
      const drag = dragRef.current
      if (!drag || event.pointerId !== activePointerId) return

      const horizontalDelta = event.clientX - drag.startClientX
      const widthDelta = anchor === 'right' ? -horizontalDelta : horizontalDelta
      emitSize(
        drag.startWidth + widthDelta,
        drag.startHeight + event.clientY - drag.startClientY,
      )
    }

    const finishDrag = (event?: PointerEvent) => {
      if (event && event.pointerId !== activePointerId) return
      setActivePointerId(null)
    }

    window.addEventListener('pointermove', handleMove)
    window.addEventListener('pointerup', finishDrag)
    window.addEventListener('pointercancel', finishDrag)

    return () => {
      window.removeEventListener('pointermove', handleMove)
      window.removeEventListener('pointerup', finishDrag)
      window.removeEventListener('pointercancel', finishDrag)

      if (handle?.hasPointerCapture(activePointerId)) {
        handle.releasePointerCapture(activePointerId)
      }

      document.body.style.cursor = previousCursor
      document.body.style.userSelect = previousUserSelect
      if (dragRef.current?.pointerId === activePointerId) dragRef.current = null
    }
  }, [activePointerId, anchor, panelRef])

  const startPointerResize = (event: ReactPointerEvent<HTMLButtonElement>) => {
    const panel = panelRef.current
    if (!panel || event.button !== 0 || !event.isPrimary) return

    event.preventDefault()
    event.stopPropagation()
    const geometry = readPanelGeometry(panel, anchor)
    dragRef.current = {
      pointerId: event.pointerId,
      startClientX: event.clientX,
      startClientY: event.clientY,
      startWidth: geometry.width,
      startHeight: geometry.height,
    }
    event.currentTarget.setPointerCapture(event.pointerId)
    setActivePointerId(event.pointerId)
  }

  const handleKeyDown = (event: ReactKeyboardEvent<HTMLButtonElement>) => {
    const horizontalStep = event.key === 'ArrowRight'
      ? KEYBOARD_RESIZE_STEP
      : event.key === 'ArrowLeft'
        ? -KEYBOARD_RESIZE_STEP
        : 0
    const verticalStep = event.key === 'ArrowDown'
      ? KEYBOARD_RESIZE_STEP
      : event.key === 'ArrowUp'
        ? -KEYBOARD_RESIZE_STEP
        : 0
    if (!horizontalStep && !verticalStep) return

    event.preventDefault()
    event.stopPropagation()
    const panel = panelRef.current
    if (!panel) return

    const geometry = readPanelGeometry(panel, anchor)
    const widthStep = anchor === 'right' ? -horizontalStep : horizontalStep
    const width = clampPanelSize(
      geometry.width + widthStep,
      MIN_PANEL_WIDTH,
      geometry.maxWidth,
    )
    const height = clampPanelSize(
      geometry.height + verticalStep,
      MIN_PANEL_HEIGHT,
      geometry.maxHeight,
    )
    onResizeRef.current(width, height)
  }

  return (
    <button
      ref={handleRef}
      type="button"
      className={`graph-panel-resize-handle graph-panel-resize-handle--${anchor}`}
      data-testid={testId}
      aria-label={label}
      title={label}
      onPointerDown={startPointerResize}
      onLostPointerCapture={() => setActivePointerId(null)}
      onKeyDown={handleKeyDown}
    >
      <Grip aria-hidden="true" size={13} />
    </button>
  )
}
