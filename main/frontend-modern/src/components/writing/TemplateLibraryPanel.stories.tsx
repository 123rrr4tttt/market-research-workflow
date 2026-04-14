import { useState } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import TemplateLibraryPanel from './TemplateLibraryPanel'
import type { WritingTemplate } from '../../lib/api'

const meta = {
  title: 'Writing/TemplateLibraryPanel',
  component: TemplateLibraryPanel,
  decorators: [
    (Story) => (
      <div style={{ maxWidth: 420 }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof TemplateLibraryPanel>

export default meta

type Story = StoryObj<typeof meta>

const templates: WritingTemplate[] = [
  {
    template_key: 'weekly-report',
    label: 'Weekly Report',
    description: 'Weekly market summary template',
    template_content: '# Weekly Report',
  },
  {
    template_key: 'policy-brief',
    label: 'Policy Brief',
    description: 'Policy-focused briefing format',
    template_content: '# Policy Brief',
  },
]

export const Interactive: Story = {
  render: function Render(args) {
    const [activeTemplateKey, setActiveTemplateKey] = useState<string | null>(args.activeTemplateKey ?? null)

    return (
      <TemplateLibraryPanel
        {...args}
        activeTemplateKey={activeTemplateKey}
        onApplyTemplate={setActiveTemplateKey}
        onValidateTemplate={setActiveTemplateKey}
      />
    )
  },
  args: {
    templates,
    validation: {
      valid: true,
      errors: [],
      warnings: ['Section "Risks" is optional'],
      normalized_template: {},
      rules: {},
      observability: {},
    },
  },
}
