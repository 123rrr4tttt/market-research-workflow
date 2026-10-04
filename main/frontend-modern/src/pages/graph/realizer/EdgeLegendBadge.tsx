import type { EdgeSymbolName, GraphEdgeVisualProfile } from './edgeStyleLibrary'

type Props = {
  profile: GraphEdgeVisualProfile
  color: string
  scale?: number
}

function Marker({ symbol, color, x }: { symbol: EdgeSymbolName; color: string; x: number }) {
  if (symbol === 'none') return null
  if (symbol === 'circle') return <circle cx={x} cy={10} r={3.1} fill="none" stroke={color} strokeWidth={1.5} />
  if (symbol === 'diamond') return <polygon points={`${x},3.5 ${x + 5.5},10 ${x},16.5 ${x - 5.5},10`} fill={color} />
  if (symbol === 'triangle') return <polygon points={`${x - 4},13.5 ${x + 5},10 ${x - 4},6.5`} fill={color} />
  return <polygon points={`${x - 5},4.5 ${x + 4},10 ${x - 5},15.5`} fill={color} />
}

export function EdgeLegendBadge({ profile, color, scale = 1 }: Props) {
  const stroke = {
    stroke: color,
    strokeWidth: Math.max(1.2, profile.width * scale),
    fill: 'none',
    strokeLinecap: 'round' as const,
  }
  const dash = profile.lineType === 'dotted' ? '1.5 4'
    : profile.lineType === 'dashed' ? '6 4'
    : profile.lineType === 'longDash' ? '12 5'
    : profile.lineType === 'dashDot' ? '8 3 2 3'
    : undefined
  return (
    <svg
      className="gv2-edge-svg-badge"
      viewBox="0 0 44 20"
      aria-hidden="true"
      style={{ width: `${44 * Math.max(0.65, Math.min(1.8, scale))}px` }}
    >
      {profile.strokeKind === 'wavy' ? (
        <path d="M6 10 q4 -7 8 0 t8 0 t8 0 t8 0" {...stroke} strokeDasharray={dash} />
      ) : profile.strokeKind === 'double' ? (
        <>
          {profile.curveness === 0 ? (
            <>
              <path d="M6 7 H38" {...stroke} strokeDasharray={dash} />
              <path d="M6 13 H38" {...stroke} strokeDasharray={dash} />
            </>
          ) : (
            <>
              <path d="M6 7 Q22 2 38 7" {...stroke} strokeDasharray={dash} />
              <path d="M6 13 Q22 18 38 13" {...stroke} strokeDasharray={dash} />
            </>
          )}
        </>
      ) : profile.strokeKind === 'curved' ? (
        <path d={profile.curveness < 0 ? 'M6 14 Q22 2 38 14' : 'M6 6 Q22 18 38 6'} {...stroke} strokeDasharray={dash} />
      ) : (
        <path d="M6 10 H38" {...stroke} strokeDasharray={dash} />
      )}
      <Marker symbol={profile.symbol[0]} color={color} x={5} />
      <Marker symbol={profile.symbol[1]} color={color} x={39} />
    </svg>
  )
}
