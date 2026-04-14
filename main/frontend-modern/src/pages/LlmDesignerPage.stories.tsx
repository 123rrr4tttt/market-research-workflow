import type { Meta, StoryObj } from '@storybook/react-vite'
import { expect } from 'storybook/test'
import LlmDesignerPage from './LlmDesignerPage'
import { pageParameters } from './storybookPageUtils'

const meta = {
  title: 'Pages/Workbench/LlmDesignerPage',
  component: LlmDesignerPage,
  parameters: {
    ...pageParameters,
    docs: {
      description: {
        component: 'Storybook defaults to a lite contract view for MCP consumption. The full ReactFlow runtime stays in the application path.',
      },
    },
  },
  argTypes: {
    presentationMode: {
      control: 'radio',
      options: ['storybook-lite', 'runtime'],
    },
  },
} satisfies Meta<typeof LlmDesignerPage>

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    projectKey: 'demo-proj',
    presentationMode: 'storybook-lite',
  },
  play: async ({ canvas }) => {
    await expect(canvas.getByText('Storybook Contract Surface')).toBeInTheDocument()
    await expect(canvas.getByText('Default Workflow Preview')).toBeInTheDocument()
  },
}
