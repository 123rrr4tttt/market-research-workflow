import type { Meta, StoryObj } from '@storybook/react-vite'
import AgentChatPage from './AgentChatPage'
import { pageDecorators, pageParameters } from './storybookPageUtils'

const meta = {
  title: 'Pages/AgentChatPage',
  component: AgentChatPage,
  parameters: pageParameters,
  decorators: pageDecorators,
} satisfies Meta<typeof AgentChatPage>

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    projectKey: 'demo-proj',
  },
}
