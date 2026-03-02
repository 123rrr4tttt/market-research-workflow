import type { CSSProperties, MouseEventHandler, ReactNode } from 'react'

type Gv2NodeCardProps = {
  title: string
  subtitle?: string
  onClose?: () => void
  actions?: ReactNode
  style?: CSSProperties
  onHeadMouseDown?: MouseEventHandler<HTMLDivElement>
  children?: ReactNode
}

export default function Gv2NodeCard({ title, subtitle, onClose, actions, style, onHeadMouseDown, children }: Gv2NodeCardProps) {
  return (
    <article className="gv2-node-card" style={style}>
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
