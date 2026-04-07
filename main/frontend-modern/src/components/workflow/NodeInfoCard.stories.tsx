import { useState } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import NodeInfoCard from './NodeInfoCard'
import type { NodeSchema } from './nodeSchemaRegistry'
import type { BackendTaskSpec } from './backendTaskCatalog'

const meta = {
  title: 'Workflow/NodeInfoCard',
  component: NodeInfoCard,
  decorators: [
    (Story) => (
      <div style={{ minHeight: 780, position: 'relative' }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof NodeInfoCard>

export default meta

type Story = StoryObj<typeof meta>

const schema: NodeSchema = {
  nodeType: 'llm_call',
  fields: [
    { key: 'provider', label: 'provider', type: 'select', options: ['openai', 'azure'] },
    { key: 'model', label: 'model', type: 'text', placeholder: 'gpt-5.4' },
    { key: 'temperature', label: 'temperature', type: 'number', placeholder: '0.2' },
    { key: 'prompt_template', label: 'prompt_template', type: 'textarea', placeholder: 'Prompt template...' },
  ],
}

const backendTasks: BackendTaskSpec[] = [
  {
    taskKey: 'task_collect_weekly_reports',
    label: 'Collect Weekly Reports',
    moduleGroup: 'report',
    description: 'Generate weekly market reports.',
    suggestedNodeType: 'llm_call',
    inputs: [{ name: 'project_key', valueType: 'string', required: false }],
    outputs: [{ name: 'reports', valueType: 'array', required: false }],
  },
]

const initialDraft = JSON.stringify(
  {
    provider: 'openai',
    model: 'gpt-5.4',
    temperature: 0.2,
    prompt_template: 'Summarize the latest market movements.',
    input_vars: [{ name: 'project_key', value_type: 'string', source: 'input', required: false }],
    output_vars: [{ name: 'reports', value_type: 'array', required: false }],
  },
  null,
  2,
)

export const Open: Story = {
  render: function Render(args) {
    const [draft, setDraft] = useState(args.draft)
    const [rect, setRect] = useState({ x: args.x, y: args.y, width: args.width, height: args.height })

    return (
      <NodeInfoCard
        {...args}
        draft={draft}
        x={rect.x}
        y={rect.y}
        width={rect.width}
        height={rect.height}
        onDraftChange={setDraft}
        onMove={(x, y) => setRect((prev) => ({ ...prev, x, y }))}
        onResize={(payload) => setRect(payload)}
      />
    )
  },
  args: {
    open: true,
    x: 32,
    y: 24,
    width: 620,
    height: 640,
    onMove: () => undefined,
    onResize: () => undefined,
    onClose: () => undefined,
    nodeId: 'node-llm-1',
    nodeType: 'llm_call',
    templates: [
      { key: 'default', label: 'Default Prompt', description: 'Balanced analyst prompt' },
      { key: 'concise', label: 'Concise', description: 'Short synthesis' },
    ],
    draft: initialDraft,
    apply: () => undefined,
    save: () => undefined,
    availableNodeOutputs: [{ nodeId: 'node-source-1', nodeLabel: 'Source', outputKeys: ['items', 'status'] }],
    availableVariables: ['project_key', 'selection_text', 'report_range'],
    schema,
    backendTasks,
  },
}
