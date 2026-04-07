import type { Meta, StoryObj } from '@storybook/react-vite'
import RawDataPage from './RawDataPage'
import { pageDecorators, pageParameters } from './storybookPageUtils'

const meta = {
  title: 'Pages/RawDataPage',
  component: RawDataPage,
  parameters: pageParameters,
  decorators: pageDecorators,
} satisfies Meta<typeof RawDataPage>

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    projectKey: 'demo-proj',
    variant: 'rawData',
  },
}
