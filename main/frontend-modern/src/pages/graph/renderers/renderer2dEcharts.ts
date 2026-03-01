import type { RenderApplyResult, RenderNode } from './types'

export const RENDERER_2D_CAPABILITIES = {
  supportsForceControl: true,
  supportsProjectionControls: false,
} as const

export function applyRenderer2D(nodes: RenderNode[]): RenderApplyResult {
  return {
    nodes,
    series: {
      layout: 'force',
      animation: true,
      animationDurationUpdate: 90,
      animationEasingUpdate: 'linear',
    },
    cacheNodePositions: true,
    capabilities: RENDERER_2D_CAPABILITIES,
  }
}
