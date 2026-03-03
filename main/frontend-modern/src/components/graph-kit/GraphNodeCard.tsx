import type { CSSProperties, MouseEventHandler, ReactNode } from 'react'
import Gv2NodeCard from '../Gv2NodeCard'

type GraphNodeCardProps = {
  title: string
  subtitle?: string
  onClose?: () => void
  actions?: ReactNode
  style?: CSSProperties
  onHeadMouseDown?: MouseEventHandler<HTMLDivElement>
  children?: ReactNode
}

export default function GraphNodeCard(props: GraphNodeCardProps) {
  return <Gv2NodeCard {...props} />
}
