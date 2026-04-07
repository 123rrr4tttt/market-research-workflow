import { useState } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import WritingInsightCard from './WritingInsightCard'

const meta = {
  title: 'Writing/WritingInsightCard',
  component: WritingInsightCard,
  decorators: [
    (Story) => (
      <div style={{ maxWidth: 560 }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof WritingInsightCard>

export default meta

type Story = StoryObj<typeof meta>

const preview = {
  card_id: 'card-a',
  title: '锂盐价格快照',
  url: 'https://example.com/lithium',
  publisher: '内部研报',
  snippet: '碳酸锂价格较上周回落 2.1%。',
  score: 0.93,
  source_type: 'document' as const,
  quick_actions: ['补查供给端', '加入摘要'],
}

const detail = {
  card_id: 'card-a',
  title: '锂盐价格快照',
  url: 'https://example.com/lithium',
  score: 0.93,
  evidence: '库存压力缓解，但上游供给释放预期仍压制价格弹性。',
  publisher: '内部研报',
  published_at: '2026-03-31',
  retrieved_at: '2026-04-02',
  normalized_query: 'lithium carbonate spot price',
  dedupe_trace: [],
  provenance: {
    source: 'internal',
    region: 'CN',
  },
  selection_matches: {
    keyword: '储能电芯出口',
    overlap: 0.71,
  },
  source_type: 'document' as const,
}

export const Interactive: Story = {
  render: function Render(args) {
    const [pinned, setPinned] = useState(false)

    return (
      <WritingInsightCard
        {...args}
        pinned={pinned}
        onTogglePin={() => setPinned((prev) => !prev)}
      />
    )
  },
  args: {
    preview,
    detail,
    onAddCitation: () => undefined,
  },
}
