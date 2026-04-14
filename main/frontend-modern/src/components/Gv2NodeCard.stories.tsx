import type { Meta, StoryObj } from '@storybook/react-vite'
import Gv2NodeCard from './Gv2NodeCard'

const meta = {
  title: 'Graph/Gv2NodeCard',
  component: Gv2NodeCard,
  args: {
    title: '市场图谱节点',
    subtitle: 'Company',
  },
  decorators: [
    (Story) => (
      <div style={{ maxWidth: 420 }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof Gv2NodeCard>

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    children: (
      <div style={{ display: 'grid', gap: 8 }}>
        <span>行业: 新能源</span>
        <span>热度: High</span>
        <span>更新时间: 2026-04-02</span>
      </div>
    ),
  },
}

export const WithActions: Story = {
  args: {
    actions: (
      <button type="button" className="gv2-node-toggle">
        查看详情
      </button>
    ),
    children: (
      <div style={{ display: 'grid', gap: 8 }}>
        <span>上游供应商: 12</span>
        <span>关联政策: 7</span>
      </div>
    ),
  },
}

export const Closable: Story = {
  args: {
    onClose: () => undefined,
    children: <span>用于 MCP 和人工共同查看卡片头部结构与关闭态。</span>,
  },
}
