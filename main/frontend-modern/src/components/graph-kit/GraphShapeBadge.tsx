import type { GraphShape } from '../../lib/graph-kit'

type Props = {
  shape: GraphShape
}

export default function GraphShapeBadge({ shape }: Props) {
  return <span className={`gk-shape gk-shape--${shape}`} aria-label={shape} />
}
