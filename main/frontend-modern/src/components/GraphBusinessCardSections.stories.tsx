import type { Meta, StoryObj } from '@storybook/react-vite'
import GraphBusinessCardSections from './GraphBusinessCardSections'

const meta = {
  title: 'Graph/GraphBusinessCardSections',
  component: GraphBusinessCardSections,
  decorators: [
    (Story) => (
      <div style={{ maxWidth: 720 }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof GraphBusinessCardSections>

export default meta

type Story = StoryObj<typeof meta>

export const CompanyProfile: Story = {
  args: {
    node: {
      id: 'company-001',
      type: 'Company',
      name: '宁德时代',
      canonical_name: 'Contemporary Amperex Technology Co., Limited',
      status: 'active',
      state: 'Fujian',
      topics: ['储能', '动力电池'],
      keywords: ['锂电', '新能源', '出海'],
      summary: '全球动力电池龙头，近期持续扩展储能与海外产线。',
      content: '企业重点关注动力电池、储能电池和全球供应链布局。',
      employee_count: 116000,
      extracted_data: {
        market_cap: '780B CNY',
        production_sites: 13,
      },
    },
  },
}

export const PolicyDocument: Story = {
  args: {
    node: {
      id: 'policy-017',
      type: 'Policy',
      title: '新能源产业升级行动方案',
      policy_type: '指导意见',
      publish_date: '2026-03-28',
      states: ['全国'],
      key_points: ['储能并网', '电池回收', '供应链韧性'],
      text: '政策提出对储能并网、关键材料回收和供应链稳定进行专项支持。',
      extracted_data: {
        agencies: ['国家能源局', '工信部'],
        phase: 'draft',
      },
    },
  },
}
