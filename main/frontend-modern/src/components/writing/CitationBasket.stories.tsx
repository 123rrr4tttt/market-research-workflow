import { useState } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import CitationBasket from './CitationBasket'
import type { WritingCitation } from '../../lib/api'

const meta = {
  title: 'Writing/CitationBasket',
  component: CitationBasket,
  decorators: [
    (Story) => (
      <div style={{ maxWidth: 920 }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof CitationBasket>

export default meta

type Story = StoryObj<typeof meta>

const citations: WritingCitation[] = [
  {
    id: 1,
    source_title: '新能源周报',
    source_uri: 'https://example.com/report-1',
    quote_text: '储能电芯出口在一季度延续高增长。',
    card_id: 'card-1',
  },
  {
    id: 2,
    source_title: '政策摘要',
    source_uri: 'https://example.com/policy-2',
    quote_text: '政策对并网和回收环节提出了更高要求。',
    card_id: 'card-2',
  },
]

export const Interactive: Story = {
  render: function Render(args) {
    const [collapsed, setCollapsed] = useState(false)
    const [items, setItems] = useState(args.citations)

    return (
      <CitationBasket
        {...args}
        citations={items}
        collapsed={collapsed}
        onToggleCollapsed={() => setCollapsed((prev) => !prev)}
        onRemoveCitation={(id) => setItems((prev) => prev.filter((item) => item.id !== id))}
      />
    )
  },
  args: {
    citations,
    dockEdge: 'bottom',
  },
}

export const DragActive: Story = {
  args: {
    citations,
    dragActive: true,
  },
}
