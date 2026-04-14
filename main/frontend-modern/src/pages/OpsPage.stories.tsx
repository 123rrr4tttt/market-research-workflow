import type { Meta, StoryObj } from '@storybook/react-vite'
import OpsPage from './OpsPage'
import { pageDecorators, pageParameters } from './storybookPageUtils'

const meta = {
  title: 'Pages/OpsPage',
  component: OpsPage,
  parameters: pageParameters,
  decorators: pageDecorators,
} satisfies Meta<typeof OpsPage>

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    projectKey: '',
    variant: 'ops',
  },
}
