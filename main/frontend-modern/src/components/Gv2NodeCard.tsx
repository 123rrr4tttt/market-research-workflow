import type { CSSProperties, DragEventHandler, MouseEventHandler, ReactNode } from 'react'

type Gv2NodeCardProps = {
  title: string
  subtitle?: string
  onClose?: () => void
  actions?: ReactNode
  style?: CSSProperties
  draggable?: boolean
  onDragStart?: DragEventHandler<HTMLElement>
  onDragEnd?: DragEventHandler<HTMLElement>
  onHeadMouseDown?: MouseEventHandler<HTMLDivElement>
  children?: ReactNode
}

export default function Gv2NodeCard({
  title,
  subtitle,
  onClose,
  actions,
  style,
  draggable = false,
  onDragStart,
  onDragEnd,
  onHeadMouseDown,
  children,
}: Gv2NodeCardProps) {
  return (
    <article className="gv2-node-card" style={style} draggable={draggable} onDragStart={onDragStart} onDragEnd={onDragEnd}>
      <div className="gv2-node-card-head" onMouseDown={onHeadMouseDown} style={onHeadMouseDown ? { cursor: 'move' } : undefined}>
        <div>
          <strong>{title}</strong>
          <small>{subtitle || '-'}</small>
        </div>
        {actions}
        {onClose ? (
          <button type="button" onClick={onClose} aria-label="关闭">
            ×
          </button>
        ) : null}
      </div>
      <div className="gv2-node-card-body">{children}</div>
    </article>
  )
}
