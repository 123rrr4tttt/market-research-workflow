export type GraphShape =
  | 'circle'
  | 'emptyCircle'
  | 'roundRect'
  | 'emptyRoundRect'
  | 'rect'
  | 'emptyRect'
  | 'diamond'
  | 'emptyDiamond'
  | 'triangle'
  | 'emptyTriangle'
  | 'pin'
  | 'emptyPin'
  | 'arrow'
  | 'emptyArrow'

export type GraphShapeConfig = {
  key: GraphShape
  label: string
  group: 'core' | 'semantic' | 'flow'
}

export const GRAPH_SHAPES: GraphShapeConfig[] = [
  { key: 'circle', label: 'Circle', group: 'core' },
  { key: 'emptyCircle', label: 'Empty Circle', group: 'core' },
  { key: 'roundRect', label: 'Round Rect', group: 'core' },
  { key: 'emptyRoundRect', label: 'Empty Round Rect', group: 'core' },
  { key: 'rect', label: 'Rect', group: 'core' },
  { key: 'emptyRect', label: 'Empty Rect', group: 'core' },
  { key: 'diamond', label: 'Diamond', group: 'semantic' },
  { key: 'emptyDiamond', label: 'Empty Diamond', group: 'semantic' },
  { key: 'triangle', label: 'Triangle', group: 'semantic' },
  { key: 'emptyTriangle', label: 'Empty Triangle', group: 'semantic' },
  { key: 'pin', label: 'Pin', group: 'semantic' },
  { key: 'emptyPin', label: 'Empty Pin', group: 'semantic' },
  { key: 'arrow', label: 'Arrow', group: 'flow' },
  { key: 'emptyArrow', label: 'Empty Arrow', group: 'flow' },
]

export const GRAPH_TONE = {
  bg: '#06080d',
  surface: '#0d1118',
  line: '#2a3446',
  text: '#d6dfef',
  textMuted: '#8793aa',
  accent: '#b4c2dc',
}

export function graphVariantTitle(variant: string) {
  const titleMap: Record<string, string> = {
    graphMarket: '市场图谱',
    graphPolicy: '政策图谱',
    graphSocial: '社媒图谱',
    graphCompany: '公司图谱',
    graphProduct: '商品图谱',
    graphOperation: '经营图谱',
    graphDeep: '市场实体加细图',
  }
  return titleMap[variant] || '图谱视图'
}
