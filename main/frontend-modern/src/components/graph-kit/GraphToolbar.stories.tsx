import type { Meta, StoryObj } from '@storybook/react-vite'
import GraphToolbar from './GraphToolbar'

const meta = {
  title: 'Graph/GraphToolbar',
  component: GraphToolbar,
  args: {
    title: 'Market Graph Controls',
  },
} satisfies Meta<typeof GraphToolbar>

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {}
