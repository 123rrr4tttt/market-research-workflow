import type { Meta, StoryObj } from '@storybook/react-vite'
import GraphLegend from './GraphLegend'

const meta = {
  title: 'Graph/GraphLegend',
  component: GraphLegend,
  decorators: [
    (Story) => (
      <div style={{ maxWidth: 560 }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof GraphLegend>

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {}
