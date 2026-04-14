export type RenderMode = '2d' | 'projection3d'

export type RendererCapabilities = {
  supportsForceControl: boolean
  supportsProjectionControls: boolean
}

export type RenderNode = {
  id: string
  x?: number
  y?: number
  symbolSize: number
  [key: string]: unknown
}

export type RenderSeriesConfig = {
  layout: 'force' | 'none'
  animation: boolean
  animationDurationUpdate: number
  animationEasingUpdate: 'linear'
}

export type RenderApplyResult = {
  nodes: RenderNode[]
  series: RenderSeriesConfig
  cacheNodePositions: boolean
  capabilities: RendererCapabilities
}
