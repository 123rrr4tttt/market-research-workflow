import type { Meta, StoryObj } from '@storybook/react-vite'
import GraphNodeCard from './GraphNodeCard'

const meta = {
  title: 'Graph/GraphNodeCard',
  component: GraphNodeCard,
  decorators: [
    (Story) => (
      <div style={{ maxWidth: 420 }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof GraphNodeCard>

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    title: 'Graph Node',
    subtitle: 'Document',
    children: (
      <div style={{ display: 'grid', gap: 8 }}>
        <span>source: market-report</span>
        <span>status: indexed</span>
      </div>
    ),
  },
}
