import type { Meta, StoryObj } from '@storybook/react-vite'
import PolicyPage from './PolicyPage'
import { pageDecorators, pageParameters } from './storybookPageUtils'

const meta = {
  title: 'Pages/PolicyPage',
  component: PolicyPage,
  parameters: pageParameters,
  decorators: pageDecorators,
} satisfies Meta<typeof PolicyPage>

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    projectKey: '',
    variant: 'policy',
  },
}
