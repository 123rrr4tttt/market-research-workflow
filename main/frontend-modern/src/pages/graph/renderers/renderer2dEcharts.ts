import type { RenderApplyResult, RenderNode } from './types'

export function applyRenderer2D(nodes: RenderNode[]): RenderApplyResult {
  return {
    nodes,
    series: {
      layout: 'force',
      animation: false,
      animationDurationUpdate: 0,
      animationEasingUpdate: 'linear',
    },
    cacheNodePositions: true,
  }
}
