import { useState } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import WritingShell from './WritingShell'
import MarkdownEditor from './MarkdownEditor'
import MarkdownPreview from './MarkdownPreview'

const meta = {
  title: 'Writing/WritingShell',
  component: WritingShell,
  parameters: {
    layout: 'fullscreen',
  },
} satisfies Meta<typeof WritingShell>

export default meta

type Story = StoryObj<typeof meta>

export const Interactive: Story = {
  render: function Render(args) {
    const [viewMode, setViewMode] = useState(args.viewMode)
    const [body, setBody] = useState('# 市场周报\n\n- 储能\n- 电池\n- 原材料')

    return (
      <WritingShell
        {...args}
        viewMode={viewMode}
        onViewModeChange={setViewMode}
        editorSlot={<MarkdownEditor value={body} onChange={setBody} autosaveLabel="Autosave enabled" />}
        previewSlot={<MarkdownPreview markdown={body} />}
      />
    )
  },
  args: {
    projectKey: 'demo-proj',
    title: 'Writing Workbench',
    subtitle: 'Structured drafting surface for research output.',
    viewMode: 'split',
    onViewModeChange: () => undefined,
    documents: [
      { id: 'doc-1', title: '本周周报', status: 'draft', updatedAt: '2026-04-02 18:00', active: true },
      { id: 'doc-2', title: '政策简报', status: 'published', updatedAt: '2026-04-01 09:30' },
    ],
    templates: [
      { id: 'tpl-1', label: 'Weekly Report', description: '市场周报模板' },
      { id: 'tpl-2', label: 'Policy Brief', description: '政策简报模板' },
    ],
    insights: [
      { id: 'insight-1', title: '锂盐价格', subtitle: '价格下行 2.1%', tag: 'market' },
      { id: 'insight-2', title: '并网政策', subtitle: '审批节奏加快', tag: 'policy' },
    ],
    activity: [
      { id: 'act-1', label: '生成提纲', meta: '2 min ago' },
      { id: 'act-2', label: '加入引用', meta: '5 min ago' },
    ],
    editorSlot: <div />,
    previewSlot: <div />,
  },
}
