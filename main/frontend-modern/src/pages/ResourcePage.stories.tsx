import type { Meta, StoryObj } from '@storybook/react-vite'
import ResourcePage from './ResourcePage'
import { pageDecorators, pageParameters } from './storybookPageUtils'

const meta = {
  title: 'Pages/ResourcePage',
  component: ResourcePage,
  parameters: pageParameters,
  decorators: pageDecorators,
} satisfies Meta<typeof ResourcePage>

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    projectKey: '',
    variant: 'resource',
  },
}
