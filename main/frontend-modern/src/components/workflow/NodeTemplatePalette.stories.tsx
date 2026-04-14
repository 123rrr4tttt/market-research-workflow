import { useState } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import NodeTemplatePalette from './NodeTemplatePalette'

const meta = {
  title: 'Workflow/NodeTemplatePalette',
  component: NodeTemplatePalette,
} satisfies Meta<typeof NodeTemplatePalette>

export default meta

type Story = StoryObj<typeof meta>

const templates = [
  { key: 'market-ingest', label: 'Market Ingest', description: 'Collect market items', data: { kind: 'ingest' } },
  { key: 'policy-extract', label: 'Policy Extract', description: 'Extract policy entities', data: { kind: 'extract' } },
  { key: 'weekly-report', label: 'Weekly Report', description: 'Generate weekly summary', data: { kind: 'report' } },
]

export const Interactive: Story = {
  render: function Render(args) {
    const [selectedKey, setSelectedKey] = useState('market-ingest')

    return (
      <NodeTemplatePalette
        {...args}
        selectedTemplateKey={selectedKey}
        onSelectTemplate={(item) => setSelectedKey(item.key)}
      />
    )
  },
  args: {
    templates,
    selectedNodeCount: 2,
    onAddTemplate: () => undefined,
    onApplyTemplateToSelected: () => undefined,
  },
}

export const Empty: Story = {
  args: {
    templates: [],
    selectedNodeCount: 0,
  },
}
