import { useState } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import MarkdownEditor from './MarkdownEditor'

const meta = {
  title: 'Writing/MarkdownEditor',
  component: MarkdownEditor,
  decorators: [
    (Story) => (
      <div style={{ maxWidth: 720 }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof MarkdownEditor>

export default meta

type Story = StoryObj<typeof meta>

export const Interactive: Story = {
  render: function Render(args) {
    const [value, setValue] = useState(args.value)
    const [selectionText, setSelectionText] = useState('')

    return (
      <div style={{ display: 'grid', gap: 12 }}>
        <MarkdownEditor
          {...args}
          value={value}
          onChange={setValue}
          onSelectionChange={setSelectionText}
        />
        <div className="gv2-node-context">
          <strong>Selection</strong>
          <div className="gv2-node-block">
            <pre className="gv2-node-content-pre">{selectionText || '(none)'}</pre>
          </div>
        </div>
      </div>
    )
  },
  args: {
    value: '# 周报标题\n\n- 电池\n- 储能\n- 原材料',
    autosaveLabel: 'Autosave enabled',
    onChange: () => undefined,
  },
}

export const EmptyDraft: Story = {
  args: {
    value: '',
    placeholder: '输入 Markdown 草稿...',
    onChange: () => undefined,
  },
}
