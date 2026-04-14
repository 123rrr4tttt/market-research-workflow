import { useState } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import LlmAssistantPanel from './LlmAssistantPanel'
import type { WritingLlmActionHistoryItem } from '../../lib/api'

const meta = {
  title: 'Writing/LlmAssistantPanel',
  component: LlmAssistantPanel,
  decorators: [
    (Story) => (
      <div style={{ maxWidth: 420 }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof LlmAssistantPanel>

export default meta

type Story = StoryObj<typeof meta>

const history: WritingLlmActionHistoryItem[] = [
  {
    job_id: 101,
    job_type: 'llm_action',
    status: 'completed',
    action_id: 'outline_generate',
    template_key: 'weekly-report',
    request_meta: {},
    result_summary: {},
    created_at: '2026-04-02 18:10',
    duration_ms: 890,
    trace_id: 'trace-101',
  },
  {
    job_id: 102,
    job_type: 'llm_action',
    status: 'running',
    action_id: 'selection_rewrite',
    template_key: 'rewrite-short',
    request_meta: {},
    result_summary: {},
    created_at: '2026-04-02 18:12',
    duration_ms: null,
  },
]

export const Interactive: Story = {
  render: function Render(args) {
    const [selectedJobId, setSelectedJobId] = useState<number | null>(args.selectedJobId ?? history[0].job_id)
    const detail = history.find((item) => item.job_id === selectedJobId) || null

    return (
      <LlmAssistantPanel
        {...args}
        selectedJobId={selectedJobId}
        detail={detail}
        onSelectHistory={setSelectedJobId}
      />
    )
  },
  args: {
    history,
    generatedContent: '1. 跟踪锂盐价格\n2. 跟踪储能招标\n3. 汇总政策变化',
  },
}

export const Busy: Story = {
  args: {
    history,
    busy: true,
  },
}
