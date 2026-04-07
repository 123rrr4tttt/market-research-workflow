import type { Meta, StoryObj } from '@storybook/react-vite'
import DashboardPage from './DashboardPage'
import { pageDecorators, pageParameters } from './storybookPageUtils'

const meta = {
  title: 'Pages/DashboardPage',
  component: DashboardPage,
  parameters: pageParameters,
  decorators: pageDecorators,
} satisfies Meta<typeof DashboardPage>

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    projectKey: '',
    variant: 'dashboard',
  },
}
