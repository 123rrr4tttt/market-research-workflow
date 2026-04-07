import { useState } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import KeywordInsightSidebar from './KeywordInsightSidebar'
import type { WritingKeywordCard, WritingSuggestItem } from '../../lib/api'

const meta = {
  title: 'Writing/KeywordInsightSidebar',
  component: KeywordInsightSidebar,
  decorators: [
    (Story) => (
      <div style={{ maxWidth: 420 }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof KeywordInsightSidebar>

export default meta

type Story = StoryObj<typeof meta>

const cards: WritingKeywordCard[] = [
  {
    card_id: 'card-a',
    source_type: 'document',
    title: '锂盐价格快照',
    snippet: '碳酸锂价格较上周回落 2.1%。',
    score: 0.93,
    publisher: '内部研报',
    relevance_tags: ['锂盐', '价格'],
    quick_actions: ['补查供给端', '加入摘要'],
    extra: {},
  },
  {
    card_id: 'card-b',
    source_type: 'graph',
    title: '储能需求节点',
    snippet: '储能装机计划与电池出口趋势存在共振。',
    score: 0.84,
    publisher: 'Graph Index',
    relevance_tags: ['储能', '出口'],
    quick_actions: ['展开图谱', '添加引用'],
    extra: {},
  },
]

const suggestItems: WritingSuggestItem[] = [
  { kind: 'keyword', id: 's1', label: '储能并网政策', extra: {} },
  { kind: 'material', id: 's2', label: '碳酸锂现货价格', extra: {} },
]

export const Interactive: Story = {
  render: function Render(args) {
    const [selectedCardId, setSelectedCardId] = useState<string | null>(args.selectedCardId ?? null)

    return (
      <KeywordInsightSidebar
        {...args}
        selectedCardId={selectedCardId}
        onSelectCard={setSelectedCardId}
      />
    )
  },
  args: {
    cards,
    suggestItems,
    selectionText: '储能电芯出口',
  },
}

export const Empty: Story = {
  args: {
    cards: [],
    loading: false,
    error: null,
  },
}
