import type { Meta, StoryObj } from '@storybook/react-vite'
import LlmNodeDesigner from './LlmNodeDesigner'

const meta = {
  title: 'Workflow/LlmNodeDesigner',
  component: LlmNodeDesigner,
  parameters: {
    layout: 'fullscreen',
  },
} satisfies Meta<typeof LlmNodeDesigner>

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {}
