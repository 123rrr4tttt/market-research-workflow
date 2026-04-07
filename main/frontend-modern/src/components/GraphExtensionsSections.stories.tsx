import type { Meta, StoryObj } from '@storybook/react-vite'
import GraphExtensionsSections from './GraphExtensionsSections'
import type { GraphElementGroup, GraphInfoSections, GraphRelationGroup } from './GraphExtensionsSections'

const meta = {
  title: 'Graph/GraphExtensionsSections',
  component: GraphExtensionsSections,
  decorators: [
    (Story) => (
      <div style={{ maxWidth: 520 }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof GraphExtensionsSections>

export default meta

type Story = StoryObj<typeof meta>

const graphInfo: GraphInfoSections = {
  degree: 18,
  neighborTypeCount: 4,
  marketDocCount: 11,
  neighborTypeItems: [
    { type: 'Company', count: 6 },
    { type: 'Policy', count: 4 },
    { type: 'Product', count: 5 },
  ],
  predicateItems: [
    { predicate: 'SUPPLIES', count: 4 },
    { predicate: 'MENTIONED_IN', count: 3 },
  ],
  neighborNodesByType: {
    Company: [
      { id: 'company-1', name: '宁德时代', type: 'Company' },
      { id: 'company-2', name: '比亚迪', type: 'Company' },
    ],
    Policy: [{ id: 'policy-1', name: '制造业升级指引', type: 'Policy' }],
    Product: [{ id: 'product-1', name: '储能电芯', type: 'Product' }],
  },
  relationsByPredicate: {
    SUPPLIES: [
      { id: 'supplies-1', direction: 'OUT', targetName: '储能电芯', targetType: 'Product' },
      { id: 'supplies-2', direction: 'OUT', targetName: '动力电池', targetType: 'Product' },
    ],
    MENTIONED_IN: [{ id: 'doc-1', direction: 'IN', targetName: '新能源周报', targetType: 'Document' }],
  },
}

const nodeElementGroups: GraphElementGroup[] = [
  {
    label: '产能',
    items: [
      { id: 'capacity-1', value: '120 GWh', label: '产能' },
      { id: 'capacity-2', value: '海外工厂 3 座', label: '产能' },
    ],
  },
  {
    label: '财务',
    items: [
      { id: 'finance-1', value: '营收同比 +18%', label: '财务' },
      { id: 'finance-2', value: '毛利率 22.4%', label: '财务' },
    ],
  },
]

const relationGroups: GraphRelationGroup[] = [
  {
    relation: '供应链关系',
    items: [
      { id: 'rel-1', direction: 'OUT', relation: '供应', targetName: '车企客户', targetType: 'Company' },
      { id: 'rel-2', direction: 'IN', relation: '采购', targetName: '锂盐厂商', targetType: 'Company' },
    ],
  },
  {
    relation: '政策关系',
    items: [{ id: 'rel-3', direction: 'IN', relation: '被提及', targetName: '产业政策', targetType: 'Policy' }],
  },
]

export const FullData: Story = {
  args: {
    graphInfo,
    nodeElementGroups,
    relationGroups,
    nodeTypeColor: {
      Company: '#7dd3fc',
      Product: '#c084fc',
      Policy: '#f59e0b',
      Document: '#34d399',
    },
    elementColorForLabel: (label: string) => (label === '财务' ? '#f59e0b' : '#7dd3fc'),
  },
}

export const ElementsOnly: Story = {
  args: {
    nodeElementGroups,
    elementColorForLabel: (label: string) => (label === '财务' ? '#f59e0b' : '#7dd3fc'),
  },
}
