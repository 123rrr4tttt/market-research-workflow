import type { Meta, StoryObj } from '@storybook/react-vite'
import GraphShapeBadge from './GraphShapeBadge'

const meta = {
  title: 'Graph/GraphShapeBadge',
  component: GraphShapeBadge,
  args: {
    shape: 'circle',
  },
  decorators: [
    (Story) => (
      <div style={{ padding: 24 }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof GraphShapeBadge>

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {}

export const Diamond: Story = {
  args: {
    shape: 'diamond',
  },
}

export const FlowArrow: Story = {
  args: {
    shape: 'arrow',
  },
}
