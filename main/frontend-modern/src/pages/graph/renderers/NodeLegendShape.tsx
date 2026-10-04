import { resolveNodeSymbol } from '../realizer/nodeStyleLibrary'

export function NodeLegendShape({ nodeType, color }: { nodeType: string; color: string }) {
  const rawSymbol = resolveNodeSymbol(nodeType)
  const stroke = color
  const fill = rawSymbol.startsWith('empty') ? '#ffffff' : color
  const common = { strokeWidth: 1.5, strokeLinejoin: 'round' as const }
  const icon = (() => {
    if (rawSymbol === 'rect' || rawSymbol === 'emptyRect') {
      return <rect x="4.6" y="4.6" width="10.8" height="10.8" fill={fill} stroke={stroke} {...common} />
    }
    if (rawSymbol === 'roundRect' || rawSymbol === 'emptyRoundRect') {
      return <rect x="4.2" y="5" width="11.6" height="10" rx="2.4" fill={fill} stroke={stroke} {...common} />
    }
    if (rawSymbol === 'diamond' || rawSymbol === 'emptyDiamond') {
      return <polygon points="10,3.8 16.2,10 10,16.2 3.8,10" fill={fill} stroke={stroke} {...common} />
    }
    if (rawSymbol === 'triangle' || rawSymbol === 'emptyTriangle') {
      return <polygon points="10,3.8 16.2,15.8 3.8,15.8" fill={fill} stroke={stroke} {...common} />
    }
    if (rawSymbol === 'pin' || rawSymbol === 'emptyPin') {
      return (
        <>
          <circle cx="10" cy="8.1" r="3.4" fill={fill} stroke={stroke} {...common} />
          <polygon points="10,17 6.8,11.6 13.2,11.6" fill={fill} stroke={stroke} {...common} />
        </>
      )
    }
    if (rawSymbol === 'arrow') {
      return <polygon points="4,6 15.6,10 4,14.2 7.3,10" fill={color} stroke={stroke} {...common} />
    }
    if (rawSymbol === 'convexStar') {
      return <polygon points="10,3 12.8,7.1 17.3,8.2 14.4,11.7 15.1,16.3 10,14.3 4.9,16.3 5.6,11.7 2.7,8.2 7.2,7.1" fill={color} stroke={stroke} {...common} />
    }
    return <circle cx="10" cy="10" r="5.2" fill={fill} stroke={stroke} {...common} />
  })()
  return (
    <span className="gv2-node-shape-badge" data-symbol={rawSymbol}>
      <svg viewBox="0 0 20 20" aria-hidden="true">{icon}</svg>
    </span>
  )
}
